"""Aim and fire. OWNER: combat.

`step(state, intent, threats) -> CombatOut` (a `CombatOutX`, which only ADDS fields). Never raises: on any
internal error it returns a hold-fire output that keeps the current aim (a charging laser then releases where
it points, which is the least bad option).

Pipeline per decision:
  1. read our mech (aim, slew rates, muzzle, weapons per slot, cubes multiplier)
  2. candidate targets: tracked mechs / npcs (+ crates when allowed); per target, per weapon, an aim solution
     and the hit probability *at the aim the torso will actually have when the shot leaves* (one sim tick of
     slew toward the commanded aim, ballistics.slew)
  3. pick the target by expected damage rate x priority (killable, danger, rear exposure, intent.target_id),
     with hysteresis and a penalty for turning our back on the most dangerous enemy
  4. the primary weapon decides the commanded aim; every slot then fires only when its own hit probability
     at the predicted actual aim clears a threshold (gun), the target is the arc's nearest eligible victim
     (lightning), the ballistic arc is clear and cannot splash us (mortar), or the laser state machine says
     release (laser)
  5. no target: face the danger (threats.face_yaw), else intent.face, else heard contacts, else scan.

Weapon facts used (rulebook + replay verification, see docs/combat.md and ballistics.py).
"""
from __future__ import annotations

import json
import math
import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from . import ballistics as B
from .state import CombatOut, Intent, Threats, WorldState
from .threats import effective_flip_rate, telegraph_factor

TICK = 0.05
_HUNTER_ON = os.environ.get("MECH_HUNTER", "1") not in ("0", "false", "no")
_STATS_DIR = os.environ.get("MECH_COMBAT_STATS_DIR")   # eval only: dump summary() there every 50 decisions


def _log(*a):
    try:
        print("[combat]", *a, file=sys.stderr, flush=True)
    except Exception:
        pass


@dataclass
class CombatOutX(CombatOut):
    weapon: str = ""                 # primary weapon this decision
    p_hit: float = 0.0               # primary weapon's hit probability at the predicted actual aim
    laser_charging: bool = False     # our laser trigger is held (movement is halved while charging)
    laser_charge: float = 0.0
    dumping: bool = False            # releasing a laser charge into the sky (heal requested mid-charge)
    damaging: bool = False           # a trigger that can deal damage is pulled (resets regen if it hits)
    reason: str = ""


# ============================================================================== helpers
class _Me:
    __slots__ = ("pos", "vel", "aim", "yr", "pr", "minp", "maxp", "muzzle", "height", "radius", "mult", "slots",
                 "energy", "cubes", "launch_pos")

    def __init__(self, state: WorldState):
        me = state.me or {}
        self.pos = tuple(state.pos)
        self.vel = tuple(state.vel)
        a = me.get("aim") or (0.0, 0.0)
        self.aim = (float(a[0]), float(a[1]))
        self.yr = state.stat("turn_rate", 4.0)
        self.pr = state.stat("pitch_rate", 3.0)
        self.minp = state.stat("min_pitch", -0.7)
        self.maxp = state.stat("max_pitch", 1.3)
        self.muzzle = state.stat("muzzle_height", 7.0)
        self.height = state.stat("height", 9.0)
        self.radius = state.stat("radius", 2.5)
        self.cubes = int(me.get("cubes", 0) or 0)
        dpc = float(state.cfg.get("cubes", {}).get("damage_per_cube", 0.04))
        cap = float(state.cfg.get("cubes", {}).get("stat_cap", 10))
        self.mult = 1.0 + dpc * min(self.cubes, cap)
        self.energy = float(state.energy)
        self.slots: Dict[str, Tuple[int, Dict[str, Any]]] = {}
        for i, w in enumerate(me.get("weapons") or []):
            if w and w.get("kind"):
                self.slots[w["kind"]] = (i, w)
        # where we are when the shot effectively leaves (one tick later)
        self.launch_pos = (self.pos[0] + self.vel[0] * TICK, self.pos[1] + self.vel[1] * TICK, self.pos[2] + self.vel[2] * TICK)

    def stats(self, kind: str, state: WorldState) -> Dict[str, float]:
        s = dict(state.cfg.get("weapons", {}).get(kind, {}))
        if kind in self.slots:
            s.update(self.slots[kind][1].get("stats") or {})
        return s


class _Tgt:
    __slots__ = ("id", "kind", "pos", "vel", "lead_vel", "radius", "height", "hp", "hp_frac", "los", "dist", "agility",
                 "airborne", "rear", "mortar", "charging", "danger", "visible", "age", "threat", "facing_me", "bearing",
                 "flip_rate", "since_flip", "flip_min_gap", "jumpy")

    def __init__(self):
        self.agility = 0.3
        self.flip_rate = 0.0
        self.since_flip = None
        self.flip_min_gap = None
        self.jumpy = 0.0
        self.airborne = False
        self.rear = False
        self.mortar = False
        self.charging = False
        self.danger = 0.0
        self.visible = True
        self.age = 0.0
        self.threat = None
        self.facing_me = False
        self.lead_vel = (0.0, 0.0, 0.0)


def _mem(state: WorldState) -> Dict[str, Any]:
    m = state.scratch.get("combat")
    if m is None:
        m = {"tgt": None, "tgt_t": -1e9, "scan": 0.0, "laser_full_t": None, "last_laser_c": 0.0,
             "shots": 0, "hits": 0, "fires": {}, "arena_calls": 0}
        state.scratch["combat"] = m
    return m


def _clear(state: WorldState, a, b, mem) -> bool:
    ar = state.arena
    if ar is None:
        return True
    mem["arena_calls"] = mem.get("arena_calls", 0) + 1
    try:
        return bool(ar.shot_clear(a, b))
    except Exception:
        return True


def _ground(state: WorldState, x: float, y: float, z: float) -> float:
    ar = state.arena
    if ar is None:
        return -1e9
    try:
        return float(ar.ground_z(x, y, z))
    except Exception:
        return -1e9


# ============================================================================== solutions
def fire_tick(cooldown: float) -> int:
    """Which sim tick of the coming decision a held trigger fires on: 1 if the weapon is ready within the
    first tick, else 2 (the sim accumulates cooldown, so a 0.24 s gun alternates ticks 1 and 2)."""
    return 1 if cooldown <= TICK + 1e-6 else 2


def gun_solution(me: _Me, tg: _Tgt, st: Dict[str, float], g: float = 22.0, k: int = 1):
    """(yaw, pitch, t_flight, aim_point, dist) for the gun against a target, or None.

    Timing (sim; consistent with the replay): a shot leaving on tick k of the decision spawns at the muzzle
    after both mechs moved k ticks and flies one tick in that same tick, so the target is effectively
    observed (k-1) ticks before launch."""
    speed = float(st.get("speed", 252.0))
    center = (tg.pos[0], tg.pos[1], tg.pos[2] + 0.5 * tg.height)
    # lead velocity: telegraph model (direction reversals at rate flip_rate): expected displacement
    # over the flight is v * f(tau), f = (1 - e^{-2 r tau}) / (2 r tau). Straight movers: f ~ 1.
    d0 = math.dist(center, me.launch_pos)
    tf0 = d0 / speed
    f = telegraph_factor(effective_flip_rate(tg.flip_rate, tg.since_flip, tg.flip_min_gap, tf0), tf0)
    lv = (f * tg.vel[0], f * tg.vel[1], tg.vel[2] if tg.airborne else 0.0)
    tacc = (0.0, 0.0, -g if (tg.airborne and tg.vel[2] < 0) else (-0.5 * g if tg.airborne else 0.0))
    extra = (k - 1) * TICK
    lp = me.launch_pos if k == 1 else (me.pos[0] + me.vel[0] * k * TICK, me.pos[1] + me.vel[1] * k * TICK, me.pos[2] + me.vel[2] * k * TICK)
    origin = B.shot_origin(lp, me.aim[0], me.aim[1], me.muzzle)
    sol = B.lead_aim(origin, center, lv, speed, extra, tacc)
    if sol is None:
        return None
    yaw, pitch, tf, ap = sol
    # recompute origin with the solved yaw (3 m horizontal offset) once
    origin = B.shot_origin(lp, yaw, pitch, me.muzzle)
    sol = B.lead_aim(origin, center, lv, speed, extra, tacc)
    if sol is None:
        return None
    yaw, pitch, tf, ap = sol
    return yaw, pitch, tf, ap, math.dist(origin, ap)


def gun_p(me: _Me, tg: _Tgt, sol, fire_aim, st: Dict[str, float]) -> float:
    if sol is None:
        return 0.0
    yaw, pitch, tf, ap, dist = sol
    if dist > float(st.get("range", 230.0)) - 1.0:
        return 0.0
    hd = math.hypot(ap[0] - me.pos[0], ap[1] - me.pos[1])
    lat = B.wrap(fire_aim[0] - yaw) * max(1.0, hd)
    vert = (fire_aim[1] - pitch) * max(1.0, dist)
    sig = math.radians(float(st.get("spread_deg", 0.6)))
    spd = math.hypot(tg.vel[0], tg.vel[1])
    ps = B.motion_sigma(tf, spd, 58.5, tg.agility)
    if tg.kind == "crate":
        ps = 0.05
    pv = 0.5 * ps + tg.jumpy * min(3.0, 0.5 * 22.0 * tf * tf + 2.0 * tf)
    return B.hit_probability(lat, vert, dist, tg.radius, tg.height, sig, ps, 0.0015, pv)


def laser_solution(me: _Me, tg: _Tgt, delay: float = TICK):
    """Hitscan aim at the target's center as it will be when the beam fires (one tick later)."""
    c = (tg.pos[0] + tg.vel[0] * delay, tg.pos[1] + tg.vel[1] * delay, tg.pos[2] + 0.5 * tg.height + (tg.vel[2] * delay if tg.airborne else 0.0))
    o = (me.launch_pos[0], me.launch_pos[1], me.launch_pos[2] + me.muzzle)
    yaw, pitch = B.dir_to_aim((c[0] - o[0], c[1] - o[1], c[2] - o[2]))
    return yaw, pitch, math.dist(o, c), c


def laser_p(me: _Me, tg: _Tgt, sol, fire_aim, rng: float) -> float:
    yaw, pitch, dist, c = sol
    if dist > rng - 1.0:
        return 0.0
    hd = math.hypot(c[0] - me.pos[0], c[1] - me.pos[1])
    lat = B.wrap(fire_aim[0] - yaw) * max(1.0, hd)
    vert = (fire_aim[1] - pitch) * max(1.0, dist)
    ps = 0.25 + 0.4 * tg.agility * math.hypot(tg.vel[0], tg.vel[1]) * TICK
    return B.hit_probability(lat, vert, dist, tg.radius, tg.height, 0.0, ps, 0.0015)


def mortar_solution(state: WorldState, me: _Me, tg: _Tgt, st: Dict[str, float], mem, need_clear: bool = True):
    """Best mortar shot (low arc first, high arc for indirect fire). Returns dict or None.

    Never returns a shot whose predicted impact is within (splash_radius + our radius + 2.5 m) of where we will
    be, or whose first 12 m are blocked (that would blow up in our face)."""
    v = float(st.get("speed", 72.0))
    g = float(st.get("gravity", 22.0))
    sr = float(st.get("splash_radius", 7.0))
    tube = me.height + 0.5
    hd = math.hypot(tg.pos[0] - me.pos[0], tg.pos[1] - me.pos[1])
    safe = sr + me.radius + 2.5
    if hd < safe + 1.0:
        return None
    # aim low on the body: a body hit = direct (200 + splash), a near miss lands at its feet (splash)
    aim_z = tg.pos[2] + min(1.0, 0.3 * tg.height)
    f = telegraph_factor(tg.flip_rate, hd / (0.8 * v) + 0.3)
    tv = (tg.vel[0] * f, tg.vel[1] * f, 0.0)
    if tg.kind == "crate":
        tv = (0.0, 0.0, 0.0)
    best = None
    for high in (False, True):
        sol = B.mortar_solve(me.launch_pos, (tg.pos[0], tg.pos[1], aim_z), tv, v, g, tube, me.radius + 0.5, high,
                             0.0, me.minp, me.maxp)
        if sol is None:
            continue
        yaw, pitch, tf, ip = sol
        # self-splash guard: where will we be (keep moving) when it lands
        fut = (me.pos[0] + me.vel[0] * min(tf, 1.5), me.pos[1] + me.vel[1] * min(tf, 1.5))
        if math.hypot(ip[0] - fut[0], ip[1] - fut[1]) < safe or math.hypot(ip[0] - me.pos[0], ip[1] - me.pos[1]) < safe:
            continue
        if not need_clear:
            best = (yaw, pitch, tf, ip, high)
            break
        # arc clearance: piecewise segments; the first one guards against blowing up next to us
        o = B.shot_origin(me.launch_pos, yaw, pitch, tube, me.radius + 0.5)
        n = 5 if not high else 6
        ok = True
        prev = o
        for k in range(1, n + 1):
            tt = tf * k / n
            if k == n:
                tt = tf * 0.97
            p = B.shell_point(o, yaw, pitch, v, g, tt)
            if not _clear(state, prev, p, mem):
                ok = False
                break
            prev = p
        if ok:
            best = (yaw, pitch, tf, ip, high)
            break
    if best is None:
        return None
    yaw, pitch, tf, ip, high = best
    # probability the blast catches the target (2-D Gaussian displacement vs splash disc)
    spd = math.hypot(tg.vel[0], tg.vel[1])
    s = B.motion_sigma(tf, spd, 58.5, max(0.25, tg.agility)) if tg.kind != "crate" else 0.3
    s = math.hypot(s, 0.004 * hd + 0.3)
    rr = sr * 0.6 + tg.radius
    p_splash = 1.0 - math.exp(-rr * rr / (2 * s * s))
    p_direct = 1.0 - math.exp(-tg.radius * tg.radius / (2 * s * s))
    dmg = float(st.get("damage", 200.0)) * p_direct + float(st.get("splash", 160.0)) * 0.65 * p_splash
    return {"yaw": yaw, "pitch": pitch, "tf": tf, "impact": ip, "high": high, "p": p_splash, "dmg": dmg}


def mortar_aim_ok(me: _Me, msol, fire_aim) -> float:
    """How well the predicted actual aim matches the mortar solution (1 good .. 0 bad)."""
    dy = abs(B.wrap(fire_aim[0] - msol["yaw"]))
    dp = abs(fire_aim[1] - msol["pitch"])
    # at 72 m/s a 0.01 rad pitch error moves the impact ~ v^2/g * 2 * 0.01 = ~4.7 m at 45 deg: be strict
    hd = math.hypot(msol["impact"][0] - me.pos[0], msol["impact"][1] - me.pos[1])
    lat_m = dy * hd
    rng_m = dp * 72.0 * 72.0 / 22.0 * abs(math.cos(2 * msol["pitch"])) * 2.0 + dp * 10
    err = math.hypot(lat_m, rng_m)
    return max(0.0, 1.0 - err / 5.0)


# ============================================================================== targets
def _targets(state: WorldState, intent: Intent, threats: Threats, me: _Me, mem) -> List[_Tgt]:
    out: List[_Tgt] = []
    for e in threats.enemies:
        if getattr(e, "age", 0.0) > 5.0:
            continue
        if not e.visible:
            continue
        tg = _Tgt()
        tg.id, tg.kind = e.id, e.kind
        tg.pos, tg.vel = tuple(e.pos), tuple(e.vel)
        tg.lead_vel = tuple(getattr(e, "lead_vel", e.vel))
        tg.radius = getattr(e, "radius", 2.5 if e.kind == "mech" else 1.8)
        tg.height = getattr(e, "height", 9.0 if e.kind == "mech" else 3.5)
        tg.hp = e.hp
        tg.hp_frac = getattr(e, "hp_frac", 1.0)
        tg.los = bool(e.los)
        tg.dist = e.dist
        tg.agility = getattr(e, "agility", 0.3)
        tg.flip_rate = getattr(e, "flip_rate", 0.15)
        tg.since_flip = getattr(e, "since_flip", None)
        tg.flip_min_gap = getattr(e, "flip_min_gap", None)
        tg.jumpy = getattr(e, "jumpy", 0.0)
        tg.airborne = getattr(e, "airborne", False)
        tg.rear = getattr(e, "rear_exposed", False)
        tg.mortar = "mortar" in (e.weapons or [])
        tg.charging = e.charging
        tg.danger = e.danger
        tg.age = getattr(e, "age", 0.0)
        tg.facing_me = e.facing_me
        tg.bearing = math.atan2(e.pos[1] - me.pos[1], e.pos[0] - me.pos[0])
        tg.threat = e
        out.append(tg)
    # crates
    want_crate = intent.shoot_crate
    ccfg = state.cfg.get("crates", {})
    crates = state.obs.get("crates") or []
    if crates and want_crate is not None:
        cand = []
        for c in crates:
            try:
                d = math.dist(c["pos"], me.pos)
            except Exception:
                continue
            if c.get("id") == want_crate:
                cand.append((0, d, c))
        cand.sort(key=lambda x: (x[0], x[1]))
        for _, d, c in cand[:2]:
            tg = _Tgt()
            tg.id, tg.kind = int(c["id"]), "crate"
            tg.pos = tuple(c["pos"])
            tg.vel = (0.0, 0.0, 0.0)
            tg.radius = float(ccfg.get("radius", 1.4))
            tg.height = float(ccfg.get("height", 2.4))
            tg.hp = float(c.get("hp", 300))
            tg.hp_frac = tg.hp / float(ccfg.get("hp", 300))
            tg.dist = d
            tg.agility = 0.0
            tg.bearing = math.atan2(tg.pos[1] - me.pos[1], tg.pos[0] - me.pos[0])
            tg.los = _clear(state, (me.pos[0], me.pos[1], me.pos[2] + me.muzzle), (tg.pos[0], tg.pos[1], tg.pos[2] + 0.5 * tg.height), mem)
            out.append(tg)
    return out


def _value(tg: _Tgt, intent: Intent, threats: Threats, state: WorldState, me: _Me) -> float:
    """Priority multiplier for a target (on top of expected damage rate)."""
    if tg.kind == "mech":
        v = 1.0 + tg.danger / 120.0
        if tg.id in getattr(threats, "killable", []):
            v *= 2.5
        if tg.charging and tg.facing_me:
            v *= 1.5
        if _HUNTER_ON:
            hunters = getattr(threats, "hunters", None) or []
            if tg.id in hunters:
                v *= 2.0            # whoever is actually shooting us comes first
            elif hunters and state.mode_guess != "ffa" and tg.id not in getattr(threats, "killable", []):
                v *= 0.35           # a passive mech while a hunter is on us (practice squad: it won't shoot back)
    elif tg.kind == "npc":
        # contract (docs/INTERFACES.md): ignore drones unless they are the brain's target or shoot at us
        e = tg.threat
        hits_me = e is not None and (getattr(e, "dps_on_me", 0.0) > 0 or tg.id in threats.attackers)
        v = 0.6 if hits_me else 0.02
    else:  # crate
        v = 0.35 if intent.mode in ("loot", "rotate", "hold", "capture") else 0.15
    if tg.kind == "mech" and tg.id in (getattr(intent, "spare_ids", None) or ()):
        return 0.0          # brain: leave this one alone (squad conveyor)
    if intent.target_id is not None and tg.id == intent.target_id:
        v = max(v, 0.4) * 3.0
    if tg.kind == "crate" and intent.shoot_crate == tg.id:
        v = max(v, 1.2)
    return v


# ============================================================================== main step
def step(state: WorldState, intent: Intent, threats: Threats) -> CombatOut:
    try:
        return _step(state, intent, threats)
    except Exception:
        import traceback
        m = state.scratch.setdefault("combat", {})
        n = m["errors"] = m.get("errors", 0) + 1
        if n <= 3 or n % 200 == 0:
            _log("step failed:", traceback.format_exc())
        try:
            a = state.me.get("aim") or (0.0, 0.0)
            return CombatOutX(aim=(float(a[0]), float(a[1])), fire=(False, False), reason="error")
        except Exception:
            return CombatOutX(aim=None, fire=(False, False), reason="error")


def _fire_aim(me: _Me, cmd) -> Tuple[float, float]:
    return B.slew(me.aim, cmd, me.yr, me.pr, TICK, me.minp, me.maxp)


def _track_stats(state: WorldState, mem) -> None:
    """Shots (from weapon state changes) and hits (from events) per weapon, for summary()."""
    st_ = mem.setdefault("stats", {"shots": {}, "hits": {}, "dmg": {}, "kills": 0})
    prev = mem.get("prev_w") or {}
    cur = {}
    for w in state.me.get("weapons") or []:
        if not w or not w.get("kind"):
            continue
        k = w["kind"]
        cur[k] = (float(w.get("ammo", 0) or 0), float(w.get("cooldown", 0) or 0), float(w.get("charge", 0) or 0))
        if k in prev:
            pa, pc, pch = prev[k]
            a, c, ch = cur[k]
            n = 0
            if k == "gun":
                n = int(max(0.0, pa - a)) if a <= pa else 0
            elif c > pc + 0.05:
                n = 1
                if k == "lightning":
                    n = 1
            if n:
                st_["shots"][k] = st_["shots"].get(k, 0) + n
    mem["prev_w"] = cur
    seen = set()
    for ev in state.events:
        if ev.get("type") == "hit":
            k = ev.get("weapon", "?")
            st_["dmg"][k] = st_["dmg"].get(k, 0.0) + float(ev.get("amount", 0) or 0)
            key = (k, ev.get("target"))
            if key in seen:
                continue
            seen.add(key)
            st_["hits"][k] = st_["hits"].get(k, 0) + 1
        elif ev.get("type") == "kill":
            st_["kills"] += 1


def summary(state: WorldState) -> Dict[str, Any]:
    """Per-weapon shots/hits/damage this match (hits counted per target per decision)."""
    m = state.scratch.get("combat") or {}
    st_ = m.get("stats") or {}
    out = {"shots": st_.get("shots", {}), "hits": st_.get("hits", {}), "dmg": {k: round(v) for k, v in (st_.get("dmg") or {}).items()},
           "errors": m.get("errors", 0), "final_gun_veto": m.get("final_gun_veto", 0)}
    out["rate"] = {k: round(out["hits"].get(k, 0) / v, 3) for k, v in out["shots"].items() if v}
    return out


def _step(state: WorldState, intent: Intent, threats: Threats) -> CombatOutX:
    mem = _mem(state)
    mem["arena_calls"] = 0
    try:
        _track_stats(state, mem)
        if _STATS_DIR and state.n_obs % 50 == 0:
            with open(os.path.join(_STATS_DIR, f"combat_{os.getpid()}.json"), "w") as f:
                json.dump(summary(state), f)
    except Exception:
        pass
    me = _Me(state)
    t = state.t
    allow = bool(getattr(intent, "allow_fire", True))
    mode = getattr(intent, "mode", "rotate")
    urgency = float(getattr(intent, "urgency", 0.0) or 0.0)
    shorted = t < float(getattr(threats, "shorted_until", -1.0))
    # our own 'short' (lightning) events also arrive here directly
    for ev in state.events:
        if ev.get("type") == "effect" and ev.get("effect") == "short":
            mem["short_until"] = t + float(state.cfg.get("weapons", {}).get("lightning", {}).get("short_s", 2.0))
    shorted = shorted or t < mem.get("short_until", -1.0)

    tgts = _targets(state, intent, threats, me, mem)
    gun = me.slots.get("gun")
    las = me.slots.get("laser")
    lig = me.slots.get("lightning")
    mor = me.slots.get("mortar")
    gst = me.stats("gun", state) if gun else {}
    lst = me.stats("laser", state) if las else {}
    zst = me.stats("lightning", state) if lig else {}
    mst = me.stats("mortar", state) if mor else {}
    g = state.stat("gravity", 22.0)
    rear_mult = 1.5
    cook = float(lst.get("cookoff", 0.6)) if las else 0.0

    gun_ready = bool(gun) and float(gun[1].get("ammo", 0) or 0) > 0 and float(gun[1].get("reload", 0) or 0) <= 0
    gun_k = fire_tick(float(gun[1].get("cooldown", 0) or 0)) if gun else 1
    las_c = float(las[1].get("charge", 0) or 0) if las else 0.0
    las_cd = float(las[1].get("cooldown", 0) or 0) if las else 9.0
    las_ready = bool(las) and (las_c > 0 or (las_cd <= 0.1 and not shorted))
    lig_ready = bool(lig) and float(lig[1].get("cooldown", 0) or 0) <= 0.1 and me.energy >= float(zst.get("energy", 3)) + 1
    mor_ready = bool(mor) and float(mor[1].get("cooldown", 0) or 0) <= 0.1

    # ---- evaluate each target: best weapon dps at its own solution, slew cost
    best = None
    evals = []
    cur = mem.get("tgt")
    for tg in tgts[:8]:
        mult = me.mult * (rear_mult if tg.rear else 1.0)
        opts = {}
        if not tg.los and tg.kind != "crate":
            # no line of fire: only an indirect mortar (memory gives the real position for 5 s)
            if mor_ready and tg.kind == "mech" and tg.dist < 230 and tg.age < 3.0:
                ms = mortar_solution(state, me, tg, mst, mem)
                if ms is not None and ms["high"]:
                    opts["mortar"] = (ms["dmg"] * mult / 2.6, (ms["yaw"], ms["pitch"]), ms)
        else:
            if tg.kind == "crate" and not tg.los:
                continue
            if gun_ready or (gun and tg.dist < 230):
                gs = gun_solution(me, tg, gst, g, gun_k)
                if gs is not None and gs[4] < float(gst.get("range", 230.0)) - 2:
                    p0 = gun_p(me, tg, gs, (gs[0], gs[1]), gst)
                    rate = float(gst.get("damage", 45)) / max(0.1, float(gst.get("cooldown", 0.24)))
                    opts["gun"] = (rate * p0 * mult * (1.0 if gun_ready else 0.3), (gs[0], gs[1]), gs)
            if las_ready:
                ls = laser_solution(me, tg)
                if ls[2] < float(lst.get("range", 280.0)) - 2:
                    dmg = float(lst.get("damage", 315)) * (1 + (cook if tg.mortar else 0.0))
                    opts["laser"] = (dmg * 0.9 * mult / 1.2, (ls[0], ls[1]), ls)
            if lig_ready and tg.dist <= float(zst.get("range", 45.0)) - 1.0:
                bonus = 1.6 if (tg.charging and tg.kind == "mech") else 1.0
                opts["lightning"] = (float(zst.get("damage", 60)) / max(0.1, float(zst.get("cooldown", 0.25))) * 0.95 * mult * bonus,
                                     (tg.bearing, 0.0), None)
            if mor_ready and tg.dist < 235 and (tg.kind != "mech" or math.hypot(tg.vel[0], tg.vel[1]) < 4.0 or not gun_ready):
                ms = mortar_solution(state, me, tg, mst, mem)
                if ms is not None:
                    opts["mortar"] = (ms["dmg"] * mult / 1.3, (ms["yaw"], ms["pitch"]), ms)
        if not opts:
            continue
        wbest = max(opts, key=lambda k: opts[k][0])
        dps, aim, _ = opts[wbest]
        slew_t = B.slew_time(me.aim, aim, me.yr, me.pr)
        val = _value(tg, intent, threats, state, me)
        score = dps * val / (1.0 + 1.5 * slew_t)
        # front-arc: don't turn our back on the worst other threat
        worst = None
        for e in threats.enemies:
            if e.kind == "mech" and e.id != tg.id and e.danger > 30 and (worst is None or e.danger > worst.danger):
                worst = e
        if worst is not None:
            wb = math.atan2(worst.pos[1] - me.pos[1], worst.pos[0] - me.pos[0])
            if abs(B.wrap(wb - aim[0])) > math.radians(85):
                score *= 0.55
        if cur is not None and tg.id == cur:
            score *= 1.3
        evals.append((score, tg, wbest, opts))
        if best is None or score > best[0]:
            best = (score, tg, wbest, opts)

    out = CombatOutX(aim=None, fire=(False, False))
    fire = [False, False]
    cmd = None
    tg = None
    ua = getattr(threats, "unseen_attack", None) if _HUNTER_ON else None
    if ua is not None and best is not None and t - ua[1] < 1.5:
        _, btg, _, _ = best
        hunters = getattr(threats, "hunters", None) or []
        if btg.kind != "mech" or (btg.id not in hunters and btg.id not in getattr(threats, "killable", [])):
            best = None     # face the attacker (threats.face_yaw = damage bearing) instead
    if best is not None and best[0] > 0.5:
        _, tg, wbest, opts = best
        if mem.get("tgt") != tg.id:
            mem["tgt"] = tg.id
            mem["tgt_t"] = t
        out.target_id = tg.id
        out.weapon = wbest
        cmd = opts[wbest][1]
        # while the laser charges with the gun as the primary, keep the gun lead; at release use the beam aim
        if las and las_c > 0 and "laser" in opts:
            full = float(lst.get("charge", 0.75))
            if las_c >= full - 0.06 or wbest == "laser":
                cmd = opts["laser"][1]
                out.weapon = "laser"
        elif wbest == "lightning" and "gun" in opts:
            cmd = opts["gun"][1]     # gun lead keeps the target well inside the arc cone
    else:
        mem["tgt"] = None

    # ---- no target: where to look
    if cmd is None:
        cmd = _idle_aim(state, intent, threats, me, mem)
        out.reason = "idle"
    fa = _fire_aim(me, cmd)

    # ---- gun
    if gun and tg is not None and allow and gun_ready and "gun" in best[3]:
        gs = best[3]["gun"][2]
        fa_g = B.slew(me.aim, cmd, me.yr, me.pr, gun_k * TICK, me.minp, me.maxp)
        fa_g0 = B.slew(me.aim, cmd, me.yr, me.pr, (gun_k - 1) * TICK, me.minp, me.maxp)
        p = 0.5 * (gun_p(me, tg, gs, fa_g, gst) + gun_p(me, tg, gs, fa_g0, gst))
        ammo = float(gun[1].get("ammo", 0) or 0)
        thr = 0.22
        if tg.dist < 60 or (tg.kind == "mech" and tg.id in getattr(threats, "killable", [])):
            thr = 0.12
        if ammo <= 3:
            thr = max(thr, 0.3)
        if tg.kind == "crate":
            thr = 0.5
        if tg.kind == "npc" and _value(tg, intent, threats, state, me) < 0.2:
            thr = 1.1
        if p >= thr:
            fire[gun[0]] = True
            out.damaging = True
        if out.weapon == "gun":
            out.p_hit = p

    # ---- lightning
    if lig and allow and lig_ready:
        reserve = 40.0 if (mode in ("retreat", "heal") or urgency >= 0.7) else 20.0   # keep jets for the escape
        if tg is not None and (tg.kind == "mech" and (tg.id in getattr(threats, "killable", []) or tg.charging or tg.dist < 25)):
            reserve = 6.0
        nav_m = state.scratch.get("nav") or {}
        if state.t - nav_m.get("hop_wait_t", -1e9) < 0.5 and not (tg is not None and tg.kind == "mech" and tg.dist < 25):
            reserve = max(reserve, float(nav_m.get("hop_need", 0.0)))  # nav is saving up for a jet hop
        if me.energy >= float(zst.get("energy", 3)) + reserve:
            victim = _arc_victim(state, me, fa, float(zst.get("range", 45.0)), threats, mem)
            if victim is not None:
                vid, vkind = victim
                ok = (tg is not None and vid == tg.id) or vkind == "mech" or \
                     (vkind == "npc" and any(e.id == vid and (e.danger > 5 or vid == intent.target_id) for e in threats.enemies)) or \
                     (vkind == "crate" and (tg is not None and tg.kind == "crate"))
                if ok:
                    fire[lig[0]] = True
                    out.damaging = True

    # ---- mortar
    if mor and allow and mor_ready and tg is not None and "mortar" in best[3]:
        ms = best[3]["mortar"][2]
        if out.weapon == "mortar":
            q = min(mortar_aim_ok(me, ms, fa), mortar_aim_ok(me, ms, me.aim))
            if q > 0.5 and ms["p"] > (0.15 if tg.kind == "mech" else 0.5):
                # re-check self-splash with the aim we will actually fire along
                if _mortar_safe(state, me, fa, mst, mem):
                    fire[mor[0]] = True
                    out.damaging = True
                    out.p_hit = ms["p"]

    # ---- laser state machine
    if las:
        trig, cmd2, dump, why = _laser_ctrl(state, intent, threats, me, mem, las, lst, tg, best, allow, shorted, urgency, mode, cmd)
        fire[las[0]] = trig
        out.laser_charging = trig
        out.laser_charge = las_c
        out.dumping = dump
        if cmd2 is not None:
            cmd = cmd2
            fa = _fire_aim(me, cmd)
        if why:
            out.reason = (out.reason + " " + why).strip()
        if not trig and las_c > 0 and not dump:
            out.damaging = True

    # The laser may replace the gun's lead with a hitscan direction above. A
    # previously valid gun trigger must be checked against the aim actually sent.
    if gun and fire[gun[0]] and tg is not None and best is not None:
        from .brain import P
        if P["final_fire"] and "gun" in best[3]:
            gs = best[3]["gun"][2]
            fa_g = B.slew(me.aim, cmd, me.yr, me.pr, gun_k * TICK, me.minp, me.maxp)
            fa_g0 = B.slew(me.aim, cmd, me.yr, me.pr, (gun_k - 1) * TICK, me.minp, me.maxp)
            final_p = .5 * (gun_p(me, tg, gs, fa_g, gst) + gun_p(me, tg, gs, fa_g0, gst))
            if final_p < thr:
                fire[gun[0]] = False
                mem["final_gun_veto"] = mem.get("final_gun_veto", 0) + 1

    # ---- reload
    out.reload = _want_reload(state, threats, me, gun, gst, tg, best, fire)

    out.aim = (B.wrap(cmd[0]), min(me.maxp, max(me.minp, cmd[1])))
    out.fire = (bool(fire[0]), bool(fire[1]))
    return out


def _arc_victim(state: WorldState, me: _Me, fa, rng: float, threats: Threats, mem):
    """Who the lightning arc would hit: nearest mech/npc/crate within range and +-30 deg of the aim yaw
    with line of sight. Returns (id, kind) only if that victim is also within +-13 deg (so it is hit under
    either reading of cone_deg: half-angle 30 or full 30)."""
    cone = math.radians(float(state.cfg.get("weapons", {}).get("lightning", {}).get("cone_deg", 30.0)))
    safe_cone = min(cone * 0.45, math.radians(13))
    muzzle = (me.launch_pos[0], me.launch_pos[1], me.launch_pos[2] + me.muzzle)
    cands = []
    for e in threats.enemies:
        if not e.visible:
            continue
        c = (e.pos[0], e.pos[1], e.pos[2] + 0.5 * getattr(e, "height", 9.0))
        d = math.dist(c, muzzle)
        if d > rng + getattr(e, "radius", 2.5):
            continue
        b = math.atan2(c[1] - muzzle[1], c[0] - muzzle[0])
        off = abs(B.wrap(b - fa[0]))
        if off <= cone:
            cands.append((d, off, e.id, e.kind, c, getattr(e, "radius", 2.5)))
    for cr in state.obs.get("crates") or []:
        try:
            c = (cr["pos"][0], cr["pos"][1], cr["pos"][2] + 1.2)
        except Exception:
            continue
        d = math.dist(c, muzzle)
        if d > rng + 1.4:
            continue
        b = math.atan2(c[1] - muzzle[1], c[0] - muzzle[0])
        off = abs(B.wrap(b - fa[0]))
        if off <= cone:
            cands.append((d, off, int(cr.get("id", -1)), "crate", c, 1.4))
    cands.sort(key=lambda x: x[0])
    for d, off, i, k, c, r in cands[:3]:
        if not _clear(state, muzzle, c, mem):
            continue
        # the nearest one with LOS is the victim
        tol = safe_cone + math.atan2(r, max(1.0, d))
        if off <= tol:
            return i, k
        return None
    return None


def _mortar_safe(state: WorldState, me: _Me, fa, mst, mem) -> bool:
    """Simulate our own shell along the actual fire aim: impact must be far from us and the tube clear."""
    v = float(mst.get("speed", 72.0))
    g = float(mst.get("gravity", 22.0))
    sr = float(mst.get("splash_radius", 7.0))
    o = B.shot_origin(me.launch_pos, fa[0], fa[1], me.height + 0.5, me.radius + 0.5)
    # first 0.25 s of flight (~18 m) must be clear
    p1 = B.shell_point(o, fa[0], fa[1], v, g, 0.25)
    if not _clear(state, (me.pos[0], me.pos[1], me.pos[2] + me.height * 0.9), p1, mem):
        return False

    def ground(x, y, z):
        gz = _ground(state, x, y, z)
        return gz if gz > -1e8 else me.pos[2] - 50.0
    vel = (v * math.cos(fa[1]) * math.cos(fa[0]), v * math.cos(fa[1]) * math.sin(fa[0]), v * math.sin(fa[1]))
    ip, ti = B.ballistic_impact(o, vel, g, ground, tmax=float(mst.get("ttl", 7.0)), dt=0.1)
    fut = (me.pos[0] + me.vel[0] * min(ti, 1.5), me.pos[1] + me.vel[1] * min(ti, 1.5), me.pos[2])
    lim = sr + me.radius + 2.0
    return math.hypot(ip[0] - fut[0], ip[1] - fut[1]) > lim and math.hypot(ip[0] - me.pos[0], ip[1] - me.pos[1]) > lim


def _laser_ctrl(state, intent, threats, me: _Me, mem, las, lst, tg, best, allow, shorted, urgency, mode, cmd):
    """Laser trigger state machine. Returns (hold_trigger, aim_override or None, dumping, reason).

    Rules (protocol 7, detailed prose): holding charges up to `charge` s; letting go fires the hitscan beam along
    the ACTUAL aim at that moment (damage min_frac..1 by charge); letting go before `min_charge` fires as soon
    as min_charge is reached; a full charge held `hold_s` more fires by itself; then `cooldown`. Charging halves
    our movement; a lightning hit ('short') cancels the charge and blocks charging for short_s."""
    slot, w = las
    c = float(w.get("charge", 0) or 0)
    cd = float(w.get("cooldown", 0) or 0)
    full = float(lst.get("charge", 0.75))
    hold_s = float(lst.get("hold_s", 2.0))
    rng = float(lst.get("range", 280.0))
    t = state.t
    if c <= 0:
        mem["laser_full_t"] = None
    elif c >= full - 1e-3 and mem.get("laser_full_t") is None:
        mem["laser_full_t"] = t
    full_t = mem.get("laser_full_t")
    auto_in = (full_t + hold_s - t) if full_t is not None else (full - c) + hold_s

    las_opt = best[3].get("laser") if (best is not None and tg is not None) else None
    p = 0.0
    if las_opt is not None:
        ls = las_opt[2]
        fa = _fire_aim(me, las_opt[1])
        p = min(laser_p(me, tg, ls, fa, rng), laser_p(me, tg, ls, me.aim, rng))

    if c > 0:
        # ----- charging: decide release
        if not allow:
            # healing requested mid-charge: a kill shot is still worth it, otherwise dump into the sky
            if tg is not None and tg.kind == "mech" and tg.id in getattr(threats, "killable", []) and p >= 0.7:
                return False, las_opt[1], False, "laser-kill-before-heal"
            yaw = me.aim[0]
            if me.aim[1] >= 0.75:
                return False, (yaw, me.maxp), True, "laser-dump"
            return True, (yaw, me.maxp), True, "laser-dump-raise"
        dmg_now = B.laser_damage(c, float(lst.get("damage", 315)), full, float(lst.get("min_frac", 0.35)), float(lst.get("min_charge", 0.15)))
        if tg is not None and las_opt is not None and tg.los:
            kill_now = tg.hp is not None and dmg_now * me.mult * (1.5 if tg.rear else 1.0) * (1.6 if tg.mortar else 1.0) >= float(tg.hp)
            threat_now = getattr(threats, "beam_risk", False) or getattr(threats, "incoming_damage", 0.0) > 100
            if c >= full - 0.02 and p >= 0.72:
                return False, las_opt[1], False, "laser-release"
            if (kill_now or (threat_now and c >= 0.45)) and p >= 0.75:
                return False, las_opt[1], False, "laser-early"
            if auto_in <= 0.15:
                return False, las_opt[1], False, "laser-forced"
            if (mode in ("retreat", "heal") or urgency >= 0.7) and p >= 0.4:
                return False, las_opt[1], False, "laser-release-to-run"   # charging halves our speed
            return True, las_opt[1], False, "laser-track"
        # no target in the beam: keep holding until just before the auto-fire, then release where we point
        if auto_in <= 0.15:
            return False, None, False, "laser-forced-blind"
        if mode in ("retreat", "heal") or urgency >= 0.7:
            return False, None, False, "laser-drop-to-run"           # full speed beats a blind charge
        return True, None, False, "laser-hold"

    # ----- not charging: start?
    if not allow or shorted or cd > 0.1:
        return False, None, False, ""
    if mode in ("retreat", "heal") or urgency >= 0.7:
        return False, None, False, ""
    if tg is None:
        if _precharge_ok(state, intent, threats, mode, urgency, rng):
            return True, None, False, "laser-precharge"
        return False, None, False, ""
    if tg.kind == "crate":
        return False, None, False, ""
    if tg.kind == "npc" and _value(tg, intent, threats, state, me) < 0.3:
        return False, None, False, ""
    if tg.dist > rng - 5:
        return False, None, False, ""
    if las_opt is None and not (mode == "engage" and tg.kind == "mech"):
        return False, None, False, ""
    return True, None, False, "laser-charge"


def _precharge_ok(state, intent, threats, mode, urgency, rng) -> bool:
    """Charge the laser before peeking: engaging a mech seen in the last 2 s, within range, calm legs."""
    if mode != "engage" or urgency >= 0.5 or intent.target_id is None:
        return False
    e = threats.by_id(intent.target_id)
    if e is None or e.kind != "mech" or getattr(e, "age", 9.0) > 2.0 or e.dist > rng - 20:
        return False
    return True


def _want_reload(state: WorldState, threats: Threats, me: _Me, gun, gst, tg, best, fire) -> bool:
    if not gun:
        return False
    w = gun[1]
    ammo = float(w.get("ammo", 0) or 0)
    mag = float(gst.get("mag", 12))
    if float(w.get("reload", 0) or 0) > 0 or ammo >= mag:
        return False
    if ammo <= 0:
        return True
    if fire[gun[0]]:
        return False
    gun_target = tg is not None and best is not None and "gun" in best[3]
    close = [e for e in threats.enemies if e.kind == "mech" and e.visible and e.los and e.dist < 120]
    if gun_target and ammo >= 2:
        return False
    if not close and ammo <= 0.75 * mag:
        return True
    if not close and not gun_target and ammo < mag and not threats.attackers:
        return True
    if ammo <= 2 and not gun_target:
        return True
    return False


def _idle_aim(state: WorldState, intent: Intent, threats: Threats, me: _Me, mem) -> Tuple[float, float]:
    """Aim when there is nothing to shoot: face danger, else intent.face, else contacts, else scan."""
    t = state.t
    fy = getattr(threats, "face_yaw", None)
    if fy is not None:
        # pitch toward the most dangerous enemy's center if known
        worst = max((e for e in threats.enemies if e.danger > 0), key=lambda e: e.danger, default=None)
        pitch = 0.0
        if worst is not None:
            hd = max(1.0, math.hypot(worst.pos[0] - me.pos[0], worst.pos[1] - me.pos[1]))
            pitch = math.atan2(worst.pos[2] + 4.5 - (me.pos[2] + me.muzzle), hd)
        return fy, pitch
    if intent.face is not None:
        return float(intent.face), 0.0
    cs = [c for c in getattr(threats, "contacts", []) if t - c.t < 4.0]
    if cs:
        c = cs[0]
        return math.atan2(c.pos[1] - me.pos[1], c.pos[0] - me.pos[0]), 0.0
    # scan around the direction of travel (vision is a 120 deg wedge around the torso yaw)
    sp = math.hypot(me.vel[0], me.vel[1])
    base = math.atan2(me.vel[1], me.vel[0]) if sp > 1.0 else mem.get("scan_base", me.aim[0])
    if sp <= 1.0:
        mem["scan_base"] = base
    mem["scan"] = mem.get("scan", 0.0) + 0.35
    return B.wrap(base + 0.9 * math.sin(mem["scan"])), 0.0


# ============================================================================== valuation API (for the brain)
WEAPONS = ("gun", "laser", "lightning", "mortar")


def our_hit_rate(kind: str, dist: float) -> float:
    """Hit rates we expect from this controller (model; see docs/combat.md for measured numbers)."""
    if kind == "gun":
        if dist > 230:
            return 0.0
        return max(0.15, min(0.92, 1.0 - dist / 260.0))
    if kind == "laser":
        return 0.0 if dist > 280 else (0.9 if dist < 150 else 0.75)
    if kind == "lightning":
        return 0.0 if dist > 45 else 0.95
    if kind == "mortar":
        return 0.0 if (dist > 235 or dist < 12) else (0.45 if dist < 100 else 0.3)
    return 0.0


def weapon_dps(kind: str, dist: float, ours: bool = True) -> float:
    """Effective sustained DPS of a weapon at a range (hit rate included, no cubes)."""
    base = {"gun": 12 * 45 / (11 * 0.24 + 2.4), "laser": 315 / (0.75 + 1.65), "lightning": 60 / 0.25 * 0.8,
            "mortar": (200 + 0.65 * 160) / 2.6}.get(kind, 0.0)
    if ours:
        return base * our_hit_rate(kind, dist)
    from .threats import weapon_threat
    return weapon_threat(kind, dist, True)


def weapon_value(kind: str, context: Optional[Dict[str, Any]] = None) -> float:
    """Utility of holding `kind` (higher = better), for loot / swap decisions.

    context (all optional): t (match time), zone_radius, dist (typical engagement range), enemy_weapons
    (list of kinds seen on enemies), other (kind in the other slot), mode_guess ('squad'|'ffa')."""
    c = context or {}
    zr = float(c.get("zone_radius", 380.0))
    dist = float(c.get("dist", 40.0 if zr < 100 else (70.0 if zr < 250 else 110.0)))
    v = 0.0
    # expected dps over a spread of ranges around the typical one
    for f, wgt in ((0.4, 0.25), (1.0, 0.5), (1.8, 0.25)):
        v += wgt * weapon_dps(kind, dist * f)
    ew = list(c.get("enemy_weapons") or [])
    n = max(1, len(ew))
    frac = {k: ew.count(k) / n for k in WEAPONS} if ew else {k: 0.0 for k in WEAPONS}
    if kind == "laser":
        v *= 1.0 + 0.4 * frac["mortar"] - 0.3 * frac["lightning"]
    elif kind == "lightning":
        v *= 1.0 + 0.4 * frac["laser"] - 0.3 * frac["mortar"]
        if zr < 100:
            v *= 1.15
    elif kind == "mortar":
        v *= 1.0 + 0.4 * frac["lightning"] - 0.35 * frac["laser"]
        v *= 0.8  # self-splash risk + it makes us cook-off bait
    other = c.get("other")
    if other == kind:
        return 0.0
    return v


def loadout_value(kinds, context: Optional[Dict[str, Any]] = None) -> float:
    ks = [k for k in kinds if k]
    if len(set(ks)) != len(ks):
        return 0.0
    return sum(weapon_value(k, context) for k in ks) + (8.0 if "gun" in ks else 0.0)  # gun: no energy, long range


def recommend_loadout(context: Optional[Dict[str, Any]] = None) -> List[Tuple[Tuple[str, str], float]]:
    """All 2-weapon loadouts sorted best first: [((a, b), value)]."""
    out = []
    for i, a in enumerate(WEAPONS):
        for b in WEAPONS[i + 1:]:
            out.append(((a, b), loadout_value((a, b), context)))
    out.sort(key=lambda x: -x[1])
    return out


def _get(o, k, d=None):
    if isinstance(o, dict):
        return o.get(k, d)
    return getattr(o, k, d)


def duel_estimate(me: Any, enemy: Any, dist: Optional[float] = None) -> Dict[str, float]:
    """1v1 estimate. `me`: WorldState or dict {hp, weapons:[kinds], cubes, armor}; `enemy`: EnemyThreat or
    dict {hp, weapons, cubes, dist}. Returns {win_p, ttk_me (s for us to kill it), ttk_them (s for it to
    kill us), my_dps, their_dps}."""
    try:
        if isinstance(me, WorldState):
            my_hp = float(me.hp)
            my_w = [k for k in me.weapon_kinds() if k]
            my_cubes = int(me.me.get("cubes", 0) or 0)
            my_armor = me.stat("armor", 0.0)
        else:
            my_hp = float(_get(me, "hp", 1400))
            my_w = [k for k in (_get(me, "weapons", ["gun"]) or []) if k]
            my_cubes = int(_get(me, "cubes", 0) or 0)
            my_armor = float(_get(me, "armor", 0.0) or 0.0)
        e_hp = _get(enemy, "hp", None)
        e_hp = float(e_hp) if e_hp is not None else 1400.0
        e_w = [k for k in (_get(enemy, "weapons", None) or ["gun"]) if k]
        e_cubes = int(_get(enemy, "cubes", 0) or 0)
        d = float(dist if dist is not None else (_get(enemy, "dist", 100.0) or 100.0))
        my_mult = 1.0 + 0.04 * min(my_cubes, 10)
        e_mult = 1.0 + 0.04 * min(e_cubes, 10)
        my_dps = 0.0
        for k in my_w:
            x = weapon_dps(k, d, True)
            if k == "laser" and "mortar" in e_w:
                x *= 1.6
            my_dps += x
        their = 0.0
        for k in e_w:
            x = weapon_dps(k, d, False)
            if k == "laser" and "mortar" in my_w:
                x *= 1.6
            if k == "laser" and "lightning" in my_w and d < 45:
                x *= 0.4   # we short it
            if k == "lightning" and "mortar" in my_w and d > 15:
                x *= 0.6   # concussion keeps it out / drains energy
            their += x
        my_dps *= my_mult
        their *= e_mult * (1.0 - my_armor)
        ttk_me = e_hp / max(1e-3, my_dps)
        ttk_them = my_hp / max(1e-3, their)
        r = math.log(max(1e-3, ttk_them) / max(1e-3, ttk_me))
        win = 1.0 / (1.0 + math.exp(-2.5 * r))
        return {"win_p": win, "ttk_me": ttk_me, "ttk_them": ttk_them, "my_dps": my_dps, "their_dps": their}
    except Exception:
        return {"win_p": 0.5, "ttk_me": math.inf, "ttk_them": math.inf, "my_dps": 0.0, "their_dps": 0.0}
