"""Protocol loop, deadline guard and action assembly. OWNER: integrator.

Run: python3 -u bot/main.py   (from the repo root; the Dockerfile does this)

Design:
- A reader thread pushes raw stdin lines into a queue; the main thread drains it and keeps only the newest obs.
- The policy (Pilot.decide) runs in ONE worker thread. The main thread waits for it up to HARD_CUTOFF_S after
  reading the obs; if the worker is late (or still busy with an older obs) the main thread replies with a safe
  fallback built from the previous action. A reply is therefore always sent in time, whatever the policy does.
- Every module call inside decide() is wrapped: an exception or a blown soft budget falls back to that
  module's previous output.
- stdout carries protocol lines only. Logs go to stderr.
"""
from __future__ import annotations

import gc
import json
import math
import os
import queue
import random
import sys
import threading
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from pilot import state as st  # noqa: E402

BOT_NAME = "AEGIS v10"
HARD_CUTOFF_S = float(os.environ.get("MECH_HARD_CUTOFF_MS", "26")) / 1000.0   # reply no later than this
SOFT_BUDGET_S = float(os.environ.get("MECH_SOFT_BUDGET_MS", "18")) / 1000.0   # skip optional modules after this
CONTINUOUS = ("move", "boost", "aim")
STATS_PATH = os.environ.get("MECH_STATS")  # optional: write timing/decision stats JSON here at exit (eval)

_OUT = sys.stdout
_err_count = 0


def log(*a) -> None:
    try:
        print(*a, file=sys.stderr, flush=True)
    except Exception:
        pass


def send(msg) -> None:
    _OUT.write(json.dumps(msg, separators=(",", ":"), allow_nan=False) + "\n")
    _OUT.flush()


def _finite(v, lo=-1e6, hi=1e6, default=0.0) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(f):
        return default
    return min(hi, max(lo, f))


def sanitize(action: dict, tick: int) -> dict:
    """Make the action schema-valid and JSON-finite no matter what the modules produced."""
    out = {"tick": tick}
    mv = action.get("move")
    if mv is not None:
        try:
            mx, my = _finite(mv[0], -1, 1), _finite(mv[1], -1, 1)
            n = math.hypot(mx, my)
            if n > 1:
                mx, my = mx / n, my / n
            out["move"] = [round(mx, 4), round(my, 4)]
        except Exception:
            pass
    aim = action.get("aim")
    if aim is not None:
        try:
            out["aim"] = [round(_finite(aim[0], -10, 10), 4), round(_finite(aim[1], -1.6, 1.6), 4)]
        except Exception:
            pass
    for k in ("boost", "jump", "reload"):
        if k in action:
            out[k] = bool(action[k])
    f = action.get("fire")
    if f is not None:
        try:
            out["fire"] = [bool(f[0]), bool(f[1])]
        except Exception:
            pass
    for k in ("pick", "take", "drop"):
        v = action.get(k)
        if v is not None and isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
            out[k] = int(v)
    d = action.get("debug")
    if isinstance(d, dict) and len(json.dumps(d)) < 4000:
        out["debug"] = d
    return out


def fallback(prev: dict, tick: int) -> dict:
    """Safe reply when the policy is late or broken: keep the continuous controls, drop one-shots."""
    return sanitize({k: prev[k] for k in CONTINUOUS if k in prev}, tick)


# ------------------------------------------------------------------------------------------- the pilot
class Pilot:
    """Owns the world state and calls the modules in a fixed order. One instance per match."""

    def __init__(self, hello: dict):
        self.t0 = time.perf_counter()
        random.seed(hello.get("seed", 0))
        arena = None
        try:
            from pilot.arena import Arena
            map_dir = (hello.get("map") or {}).get("dir") or "/arena"
            arena = Arena.load(map_dir)
        except Exception:
            log("arena load failed:\n" + traceback.format_exc())
        self.state = st.WorldState(hello, arena)
        self.mods = {}
        for name in ("brain", "threats", "navigate", "combat"):
            try:
                self.mods[name] = __import__(f"pilot.{name}", fromlist=[name])
            except Exception:
                log(f"import pilot.{name} failed:\n" + traceback.format_exc())
                self.mods[name] = None
        try:   # A/B: brain profile `nav3` selects the frozen good-3 navigation module
            b = self.mods.get("brain")
            if b is not None and b.P.get("nav3"):
                self.mods["navigate"] = __import__("pilot.navigate3", fromlist=["navigate3"])
        except Exception:
            log("nav3 import failed:\n" + traceback.format_exc())
        self.prev = {"threats": st.Threats(), "intent": st.Intent(), "nav": st.NavOut(),
                     "combat": st.CombatOut(), "inv": st.InvOut()}
        self.errors = {}
        self.overruns = {}
        self.mod_time = {}
        brain = self.mods.get("brain")
        if brain is not None and hasattr(brain, "init"):
            self._call("brain_init", brain.init, None, self.state)
        self.init_s = time.perf_counter() - self.t0

    def _call(self, key, fn, default, *args):
        t = time.perf_counter()
        try:
            r = fn(*args)
        except Exception:
            n = self.errors.get(key, 0) + 1
            self.errors[key] = n
            if n <= 3 or n % 200 == 0:
                log(f"[{key}] error #{n} at tick {self.state.tick}:\n{traceback.format_exc()}")
            r = default
        dt = time.perf_counter() - t
        self.mod_time.setdefault(key, []).append(dt)
        return r

    def decide(self, obs: dict, started: float) -> dict:
        s = self.state
        try:
            s.update(obs)
        except Exception:
            log("state.update failed:\n" + traceback.format_exc())
        P = self.prev
        brain, threats, nav, combat = (self.mods.get(k) for k in ("brain", "threats", "navigate", "combat"))

        def over():
            return time.perf_counter() - started > SOFT_BUDGET_S

        th = self._call("threats", threats.assess, P["threats"], s) if threats else P["threats"]
        P["threats"] = th
        intent = self._call("intent", brain.choose_intent, P["intent"], s, th) if brain and not over() else P["intent"]
        P["intent"] = intent
        s.prev_intent = intent
        nv = self._call("navigate", nav.step, P["nav"], s, intent, th) if nav and not over() else None
        if nv is None:
            self.overruns["navigate"] = self.overruns.get("navigate", 0) + 1
            nv = st.NavOut(move=P["nav"].move, boost=P["nav"].boost)
        P["nav"] = nv
        cb = self._call("combat", combat.step, P["combat"], s, intent, th) if combat and not over() else None
        if cb is None:
            self.overruns["combat"] = self.overruns.get("combat", 0) + 1
            cb = st.CombatOut(aim=P["combat"].aim)
        P["combat"] = cb
        inv = self._call("inventory", brain.inventory, st.InvOut(), s, intent) if brain and not over() else st.InvOut()
        P["inv"] = inv

        action = {"tick": s.tick, "move": list(nv.move), "boost": bool(nv.boost), "jump": bool(nv.jump),
                  "fire": [bool(cb.fire[0]), bool(cb.fire[1])], "reload": bool(cb.reload)}
        if cb.aim is not None:
            action["aim"] = list(cb.aim)
        elif "aim" in s.prev_action:
            action["aim"] = s.prev_action["aim"]
        if inv.pick is not None:
            action["pick"] = inv.pick
        if inv.take is not None:
            action["take"] = inv.take
        if inv.drop is not None:
            action["drop"] = inv.drop
        if brain is not None and hasattr(brain, "debug") and os.environ.get("MECH_DEBUG"):
            d = self._call("debug", brain.debug, None, s, intent, th, nv, cb)
            if d:
                action["debug"] = d
        action = sanitize(action, s.tick)
        s.prev_action = action
        return action


# ------------------------------------------------------------------------------------------- worker
class Worker:
    def __init__(self):
        self.cv = threading.Condition()
        self.job = None          # (pilot, obs, started)
        self.result = None       # (tick, action)
        self.busy = False
        th = threading.Thread(target=self._run, daemon=True)
        th.start()

    def submit(self, pilot, obs, started) -> bool:
        with self.cv:
            if self.busy:
                return False
            self.busy = True
            self.result = None
            self.job = (pilot, obs, started)
            self.cv.notify_all()
            return True

    def wait(self, tick, deadline):
        with self.cv:
            while True:
                if self.result is not None and self.result[0] == tick:
                    return self.result[1]
                rem = deadline - time.perf_counter()
                if rem <= 0:
                    return None
                self.cv.wait(rem)

    def _run(self):
        while True:
            with self.cv:
                while self.job is None:
                    self.cv.wait()
                pilot, obs, started = self.job
                self.job = None
            try:
                act = pilot.decide(obs, started)
            except Exception:
                log("decide crashed:\n" + traceback.format_exc())
                act = None
            with self.cv:
                self.result = (obs.get("tick"), act)
                self.busy = False
                self.cv.notify_all()


def _reader(q: "queue.Queue") -> None:
    try:
        for line in sys.stdin.buffer:
            if line.strip():
                q.put(line)
    except Exception:
        pass
    q.put(None)


def main_thread() -> None:
    """Fallback guard: policy in a worker thread (used only if fork is unavailable)."""
    sys.setswitchinterval(0.001)
    q: "queue.Queue" = queue.Queue()
    threading.Thread(target=_reader, args=(q,), daemon=True).start()
    worker = Worker()
    pilot = None
    prev_action: dict = {}
    lat = []           # reply latency from reading the obs (s)
    fallbacks = 0
    skipped = 0
    place = None
    while True:
        batch = [q.get()]
        started = time.perf_counter()
        while True:
            try:
                batch.append(q.get_nowait())
            except queue.Empty:
                break
        # Lines written together can arrive split (docker's stdin proxy): give a queued newer obs 1 ms to show up.
        try:
            batch.append(q.get(timeout=0.001))
            while True:
                batch.append(q.get_nowait())
        except queue.Empty:
            pass
        latest = None
        done = False
        for raw in batch:
            if raw is None:
                done = True
                break
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(msg, dict):
                continue
            kind = msg.get("type")
            if kind == "hello":
                try:
                    pilot = Pilot(msg)
                    log(f"init {pilot.init_s * 1000:.0f} ms, arena={'yes' if pilot.state.arena is not None else 'NO'}")
                except Exception:
                    log("pilot init failed:\n" + traceback.format_exc())
                    pilot = None
                gc.collect()
                gc.freeze()
                send({"type": "ready", "name": BOT_NAME})
            elif kind == "obs":
                if latest is not None:
                    skipped += 1
                latest = msg
            elif kind == "end":
                place = msg.get("place")
                done = True
                break
        if latest is not None and not done:
            tick = latest.get("tick", 0)
            act = None
            if pilot is not None and worker.submit(pilot, latest, started):
                act = worker.wait(tick, started + HARD_CUTOFF_S)
            if act is None:
                fallbacks += 1
                act = fallback(prev_action, tick)
            try:
                send(act)
            except (TypeError, ValueError):
                send({"tick": tick})
            prev_action = act
            lat.append(time.perf_counter() - started)
        if done:
            break
    _report(pilot, lat, fallbacks, skipped, place)


# ------------------------------------------------------------------------------------------- process guard
# The policy runs in a forked child process. The parent only does I/O: it never shares a GIL with numpy-heavy
# policy code, so its reply deadline holds even when a module call blocks for 100 ms inside C code.

def _set_pipe_size(fd: int, size: int = 1 << 20) -> None:
    try:
        import fcntl
        fcntl.fcntl(fd, 1031, size)  # F_SETPIPE_SZ
    except Exception:
        pass


def _child(hello_raw: bytes, rfd: int, wfd: int) -> None:
    """Child: build the Pilot, then answer the newest obs line from rfd with an action line on wfd."""
    try:
        os.dup2(2, 1)  # nothing the child prints may reach the protocol stdout
    except OSError:
        pass
    global _OUT
    _OUT = sys.stderr
    try:
        os.nice(8)  # the I/O parent must always win the CPU when an observation arrives
    except OSError:
        pass
    hello = json.loads(hello_raw)
    pilot = None
    try:
        pilot = Pilot(hello)
        log(f"init {pilot.init_s * 1000:.0f} ms, arena={'yes' if pilot.state.arena is not None else 'NO'}")
    except Exception:
        log("pilot init failed:\n" + traceback.format_exc())
    gc.collect()
    gc.freeze()
    os.write(wfd, b"R\n")
    buf = b""
    lat = []
    skipped = 0
    place = None
    while True:
        try:
            chunk = os.read(rfd, 1 << 20)
        except InterruptedError:
            continue
        except OSError:
            chunk = b""
        if not chunk:
            break
        buf += chunk
        # drain whatever else is already queued so we only answer the newest observation
        while True:
            import select as _sel
            r, _, _ = _sel.select([rfd], [], [], 0)
            if not r:
                break
            more = os.read(rfd, 1 << 20)
            if not more:
                break
            buf += more
        if b"\n" not in buf:
            continue
        *lines, buf = buf.split(b"\n")
        latest, end = None, False
        for raw in lines:
            if not raw.strip():
                continue
            if raw.startswith(b"E"):
                end = True
                try:
                    place = json.loads(raw[1:]).get("place")
                except ValueError:
                    pass
                continue
            if latest is not None:
                skipped += 1
            latest = raw
        if latest is not None and not end:
            started = time.perf_counter()
            try:
                obs = json.loads(latest)
                act = pilot.decide(obs, started) if pilot is not None else {"tick": obs.get("tick", 0)}
                out = (json.dumps(act, separators=(",", ":"), allow_nan=False) + "\n").encode()
                _write_all(wfd, out)
            except Exception:
                log("decide crashed:\n" + traceback.format_exc())
            lat.append(time.perf_counter() - started)
        if end:
            break
    info = _stats(pilot, lat, 0, skipped, place)
    try:
        _write_all(wfd, b"S" + json.dumps(info).encode() + b"\n")
    except Exception:
        pass


def _write_all(fd: int, data: bytes) -> None:
    while data:
        n = os.write(fd, data)
        data = data[n:]


def main_process() -> None:
    import select
    import signal
    fd_in = 0
    os.set_blocking(fd_in, True)
    buf = b""
    child = None          # (pid, to_child_fd, from_child_fd)
    cbuf = b""
    pending = b""         # bytes not yet written to the child
    prev_action: dict = {}
    lat = []
    fallbacks = 0
    skipped = 0
    place = None
    child_stats = None
    eof = False
    hello_keep = None     # raw hello, to re-fork the policy if it ever dies mid-match
    restarts = 0
    dead = []             # pids of exited children (reaped lazily)

    def child_gone():
        nonlocal child
        if child is not None:
            dead.append(child[0])
            for fd in child[1:]:
                try:
                    os.close(fd)
                except OSError:
                    pass
        child = None

    def read_stdin(timeout):
        nonlocal buf, eof
        r, _, _ = select.select([fd_in], [], [], timeout)
        if not r:
            return False
        chunk = os.read(fd_in, 1 << 20)
        if not chunk:
            eof = True
            return False
        buf += chunk
        return True

    def flush_child():
        nonlocal pending, child
        if child is None or not pending:
            return
        try:
            n = os.write(child[1], pending)
            pending = pending[n:]
        except BlockingIOError:
            pass
        except OSError:
            pending = b""
            child_gone()

    def child_lines(deadline, want_tick):
        """Read child output until a reply for want_tick (or the deadline). Returns the action dict or None."""
        nonlocal cbuf, child, child_stats
        while child is not None:
            flush_child()
            rem = deadline - time.perf_counter()
            if b"\n" not in cbuf:
                if rem <= 0:
                    return None
                wl = [child[1]] if pending else []
                r, _, _ = select.select([child[2]], wl, [], rem)
                if not r:
                    continue
                try:
                    chunk = os.read(child[2], 1 << 20)
                except OSError:
                    chunk = b""
                if not chunk:
                    log("policy process exited")
                    child_gone()
                    return None
                cbuf += chunk
                continue
            line, cbuf = cbuf.split(b"\n", 1)
            if line.startswith(b"S"):
                try:
                    child_stats = json.loads(line[1:])
                except ValueError:
                    pass
                continue
            if line == b"R":
                if want_tick == "R":
                    return {}
                continue
            try:
                act = json.loads(line)
            except ValueError:
                continue
            if want_tick is not None and isinstance(act, dict) and act.get("tick") == want_tick:
                return act
        return None

    def start_child(hello_raw):
        nonlocal child
        try:
            a_r, a_w = os.pipe()   # parent -> child
            b_r, b_w = os.pipe()   # child -> parent
            _set_pipe_size(a_w)
            _set_pipe_size(b_w)
            pid = os.fork()
        except OSError:
            log("fork failed:\n" + traceback.format_exc())
            return False
        if pid == 0:
            try:
                os.close(a_w)
                os.close(b_r)
                _child(hello_raw, a_r, b_w)
            except BaseException:
                try:
                    log("child failed:\n" + traceback.format_exc())
                except Exception:
                    pass
            os._exit(0)
        os.close(a_r)
        os.close(b_w)
        os.set_blocking(a_w, False)
        child = (pid, a_w, b_r)
        return True

    while not eof:
        if b"\n" not in buf:
            read_stdin(None)
            continue
        started = time.perf_counter()
        # drain everything already queued, plus a 1 ms grace for a split write
        while read_stdin(0):
            pass
        if not eof:
            read_stdin(0.001)
            while read_stdin(0):
                pass
        *lines, buf = buf.split(b"\n")
        latest_raw, latest, done = None, None, False
        for raw in lines:
            if not raw.strip():
                continue
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(msg, dict):
                continue
            kind = msg.get("type")
            if kind == "hello":
                hello_keep = raw
                if start_child(raw):
                    got = child_lines(time.perf_counter() + 15.0, "R")
                    if got is None:
                        log("policy process not ready in 15 s; replying with fallbacks")
                send({"type": "ready", "name": BOT_NAME})
            elif kind == "obs":
                if latest is not None:
                    skipped += 1
                latest, latest_raw = msg, raw
            elif kind == "end":
                place = msg.get("place")
                done = True
        if latest is not None and not done:
            tick = latest.get("tick", 0)
            act = None
            if child is None and hello_keep is not None and restarts < 3 and not eof:
                # the policy died mid-match: re-fork it (it rebuilds its state; fallbacks until it answers)
                restarts += 1
                for pid in dead:
                    try:
                        os.waitpid(pid, os.WNOHANG)
                    except OSError:
                        pass
                cbuf, pending = b"", b""
                log(f"restarting policy process (#{restarts})")
                start_child(hello_keep)
            if child is not None:
                pending += latest_raw + b"\n"
                act = child_lines(started + HARD_CUTOFF_S, tick)
            if act is None:
                fallbacks += 1
                act = fallback(prev_action, tick)
            send(act)
            prev_action = act
            lat.append(time.perf_counter() - started)
        if done:
            break
    # end: let the child report, then stop it
    if child is not None:
        pending += b"E" + json.dumps({"place": place}).encode() + b"\n"
        child_lines(time.perf_counter() + 0.5, None)
        try:
            os.kill(child[0], signal.SIGKILL)
            os.waitpid(child[0], 0)
        except Exception:
            pass
    info = _stats(None, lat, fallbacks, skipped, place)
    info["policy_restarts"] = restarts
    if child_stats:
        info["policy"] = {k: v for k, v in child_stats.items() if k not in ("replies", "fallbacks", "place")}
        for k in ("brain", "errors", "overruns", "mod_p99_ms", "mod_max_ms", "init_ms"):
            if k in child_stats:
                info[k] = child_stats[k]
    _emit(info)


def main() -> None:
    if os.environ.get("MECH_GUARD", "process") == "thread" or not hasattr(os, "fork"):
        main_thread()
    else:
        main_process()


def _report(pilot, lat, fallbacks, skipped, place) -> None:
    _emit(_stats(pilot, lat, fallbacks, skipped, place))


def _emit(info) -> None:
    try:
        log("stats " + json.dumps(info))
        if STATS_PATH:
            with open(STATS_PATH, "w") as f:
                json.dump(info, f)
    except Exception:
        pass


def _stats(pilot, lat, fallbacks, skipped, place) -> dict:
    try:
        lat.sort()
        pct = lambda p: lat[min(len(lat) - 1, int(p * len(lat)))] * 1000 if lat else 0.0
        info = {"replies": len(lat), "fallbacks": fallbacks, "skipped_obs": skipped, "place": place,
                "p50_ms": round(pct(0.5), 3), "p99_ms": round(pct(0.99), 3), "max_ms": round(pct(1.0), 3)}
        try:
            import resource
            info["maxrss_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 1)
        except Exception:
            pass
        if pilot is not None:
            info["init_ms"] = round(pilot.init_s * 1000, 1)
            info["errors"] = pilot.errors
            info["overruns"] = pilot.overruns
            info["mod_p99_ms"] = {k: round(sorted(v)[min(len(v) - 1, int(0.99 * len(v)))] * 1000, 3)
                                  for k, v in pilot.mod_time.items() if v}
            info["mod_max_ms"] = {k: round(max(v) * 1000, 3) for k, v in pilot.mod_time.items() if v}
            b = pilot.mods.get("brain")
            if b is not None and hasattr(b, "summary"):
                try:
                    info["brain"] = b.summary(pilot.state)
                except Exception:
                    pass
        return info
    except Exception:
        return {}


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    try:
        sys.stdout.flush()
    except Exception:
        pass
    os._exit(0)
