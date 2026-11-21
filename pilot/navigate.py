"""Movement: path following, local steering, stall recovery, zone timing. OWNER: nav.

step(state, intent, threats) -> NavOut  (the only source of move / boost / jump)
eta(state, goal) -> seconds along the real path (inf if unreachable)
safe_route(state) -> dict(point, eta, leave_by, inside_now, t_edge) for the zone

Budget: p99 < 3 ms per call. Planning is budgeted (Arena.plan keeps unfinished searches and resumes them on
the next call); while a plan is pending we steer straight with wall probing. Nothing here raises: step()
catches everything and falls back to straight-line steering toward the goal.
"""
from __future__ import annotations

import math
import random
import time
from typing import Any, Dict, List, Optional, Tuple

from .state import Intent, NavOut, Threats, WorldState, ang_diff, dist2d, unit2

PLAN_BUDGET_MS = 1.0
REPLAN_S = 4.0
WP_REACH = 2.5
STALL_WINDOW = 1.2          # s of history used to detect a stall
STALL_MIN_FRAC = 0.2        # moved less than this fraction of the expected distance => stalled
ENERGY_RESERVE = 35.0       # keep this much for jets / escapes unless urgent
ROUTE_AVOID = False         # exposure-aware A* (Arena.plan_full avoid=); see _avoid_list
JET_CAP = 40.0              # max climb (m) the planner may use; energy is waited for at the hop base
JET_TIMEOUT = 5.0
PROBE_ANGLES = (0.0, 0.35, -0.35, 0.7, -0.7, 1.05, -1.05, 1.4, -1.4, 1.9, -1.9, 2.6, -2.6)


JUKE_MIN_RANGE = float(__import__("os").environ.get("MECH_JUKE_RANGE", "1e9"))   # juke OFF: sim squad A/B +0.47 without it (our own hit rate drops); "80" re-enables
NAVLOG = bool(__import__("os").environ.get("MECH_NAVLOG"))


def _hop_legacy() -> bool:
    """A/B (brain profile `hop_legacy`): good-3's jet-hop energy rules (2 m/energy plan cost, urgent hops at 60 %
    energy, no 'impossible hop' drop, no smaller jet caps after failures). good-5 vs good-3 official: -0.42."""
    try:
        from .brain import P as BP
        return bool(BP.get("hop_legacy", False))
    except Exception:
        return False


def _mem(state: WorldState) -> Dict[str, Any]:
    m = state.scratch.get("nav")
    if m is None:
        m = {"goal": None, "path": [], "plan_t": -1e9, "hist": [], "stall_t": None, "recover": None,
             "strafe_sign": 1.0, "strafe_t": 0.0, "last_move": (0.0, 0.0), "blocked_since": None,
             "pending": False, "offmesh_goal": None, "jet_until": -1e9, "stats": {"replans": 0, "stalls": 0,
                                                                                    "jets": 0, "ms_max": 0.0}}
        state.scratch["nav"] = m
    return m


def _cubes(state: WorldState) -> float:
    try:
        return float(state.me.get("cubes") or 0)
    except Exception:
        return 0.0


def _walk_speed(state: WorldState) -> float:
    return max(1.0, state.stat("walk_speed", 11.7))


# ============================================================================== public API
def _finite3(p) -> bool:
    try:
        return p is not None and len(p) >= 2 and all(math.isfinite(float(v)) for v in p[:3])
    except Exception:
        return False


def step(state: WorldState, intent: Intent, threats: Threats) -> NavOut:
    t0 = time.perf_counter()
    m = _mem(state)
    try:
        if not _finite3(state.pos):
            return NavOut()                       # no usable position this tick: stand still
        if intent is not None and intent.goal is not None and not _finite3(intent.goal):
            intent = Intent(**{**intent.__dict__, "goal": None})
        out = _step(state, intent, threats, m)
    except Exception as e:  # never let movement die
        n = m["stats"]["errors"] = m["stats"].get("errors", 0) + 1
        if n <= 5 or n % 100 == 0:
            try:
                import sys
                import traceback
                print(f"[nav] step error #{n} {e!r} {traceback.format_exc(limit=3)}", file=sys.stderr)
            except Exception:
                pass
        out = _straight(state, intent)
    # spare time: advance the zone travel-time field
    try:
        spare = FIELD_TOTAL_MS - (time.perf_counter() - t0) * 1000
        if spare > 0.3:
            f = zone_field(state)
            if f is not None and not f.done:
                state.arena.flood_advance(f, spare)
    except Exception:
        pass
    dt = (time.perf_counter() - t0) * 1000
    st = m["stats"]
    if dt > st["ms_max"]:
        st["ms_max"] = dt
    m["last_move"] = out.move
    if NAVLOG and state.t - m.get("log_t", -1e9) >= 1.0:
        m["log_t"] = state.t
        try:
            import sys
            p = m.get("path") or []
            print(f"[navlog] t={state.t:.1f} pos=({state.pos[0]:.1f},{state.pos[1]:.1f},{state.pos[2]:.1f}) en={state.energy:.0f} "
                  f"mode={getattr(intent, 'mode', None)} urg={getattr(intent, 'urgency', 0):.1f} goal={tuple(round(v) for v in intent.goal) if intent and intent.goal else None} "
                  f"mv=({out.move[0]:.2f},{out.move[1]:.2f}) b={out.boost} j={out.jump} blk={out.blocked} jet={bool(m.get('jet'))} "
                  f"rec={bool(m.get('recover'))} jf={m.get('jet_fail', 0)} wait={state.t - m.get('hop_wait_t', -1e9) < 0.5} "
                  f"pend={m.get('pending')} unr={m.get('unreachable')} path={[(round(w[0]), round(w[1]), round(w[2]), w[3] if len(w) > 3 else '') for w in p[:2]]}",
                  file=sys.stderr)
        except Exception:
            pass
    return out


def eta(state: WorldState, goal) -> float:
    """Seconds to reach goal along the planned path at walk speed (inf if unreachable)."""
    ar = state.arena
    d = dist2d(state.pos, goal)
    v = _walk_speed(state)
    if ar is None:
        return d * 1.25 / v
    try:
        L = ar.path_len(state.pos, goal, cubes=_cubes(state), budget_ms=1.5)
    except Exception:
        return d * 1.35 / v
    if L == math.inf:
        return math.inf
    return L / v + 0.5


FIELD_TOTAL_MS = 1.5        # step() + zone-field work per decision


def zone_field(state: WorldState):
    """Arena travel-distance field to the NEXT circle (advanced a little by every step())."""
    ar = state.arena
    z = state.zone
    if ar is None or not getattr(ar, "ok_nav", False) or not z:
        return None
    c1, r1 = z["next_center"], float(z["next_radius"])
    return ar.zone_field(c1[0], c1[1], max(0.0, r1 - 5.0), cubes=_cubes(state))


def zone_eta_at(state: WorldState, x: float, y: float, z: Optional[float] = None) -> float:
    """Seconds of walking from (x, y) into the next circle (5 m margin). Uses the travel-time field when it
    has settled that spot, else a straight-line estimate x 1.3."""
    zn = state.zone
    v = _walk_speed(state)
    if not zn:
        return 0.0
    f = zone_field(state)
    if f is not None:
        c = state.arena.flood_cost(f, x, y, z)
        if c is not None:
            return c / v
    c1, r1 = zn["next_center"], float(zn["next_radius"])
    return max(0.0, math.hypot(x - c1[0], y - c1[1]) - max(0.0, r1 - 5.0)) * 1.3 / v


def zone_circle_at(z: Dict[str, Any], t: float) -> Tuple[Tuple[float, float], float]:
    c0, r0 = z["center"], float(z["radius"])
    c1, r1 = z["next_center"], float(z["next_radius"])
    s0, s1 = float(z["shrink_start"]), float(z["shrink_end"])
    if t <= s0:
        return (c0[0], c0[1]), r0
    if t >= s1 or s1 <= s0:
        return (c1[0], c1[1]), r1
    f = (t - s0) / (s1 - s0)
    return (c0[0] + (c1[0] - c0[0]) * f, c0[1] + (c1[1] - c0[1]) * f), r0 + (r1 - r0) * f


def edge_time(z: Dict[str, Any], p, t_now: float) -> float:
    """Earliest time >= t_now at which a static point p is outside the zone (inf if never this phase)."""
    (cx, cy), r = zone_circle_at(z, t_now)
    if math.hypot(p[0] - cx, p[1] - cy) > r:
        return t_now
    s0, s1 = float(z["shrink_start"]), float(z["shrink_end"])
    lo, hi = max(t_now, s0), s1
    (cx, cy), r = zone_circle_at(z, hi)
    if math.hypot(p[0] - cx, p[1] - cy) <= r:
        return math.inf
    for _ in range(24):   # bisection (distance - radius is monotone enough over one linear shrink)
        mid = 0.5 * (lo + hi)
        (cx, cy), r = zone_circle_at(z, mid)
        if math.hypot(p[0] - cx, p[1] - cy) > r:
            hi = mid
        else:
            lo = mid
    return lo


def safe_route(state: WorldState, margin: Optional[float] = None, threats_pos: Optional[List] = None) -> Dict[str, Any]:
    """Where to go to be safe from the zone this phase, how long it takes, and the latest time to leave.

    point: feet position inside the NEXT circle (margin inside its edge), on walkable ground, preferring the
           point closest to us along the line to the next centre (and away from threats if given).
    eta: seconds along the path. leave_by: match time by which we must start moving (inf if we are already
    inside the next circle). t_edge: when the (shrinking) edge reaches our current spot if we stay."""
    z = state.zone
    if not z:
        return {"point": tuple(state.pos), "eta": 0.0, "leave_by": math.inf, "inside_now": True, "t_edge": math.inf}
    ar = state.arena
    c1, r1 = z["next_center"], float(z["next_radius"])
    if margin is None:
        margin = min(25.0, max(5.0, 0.18 * r1))
    p = state.pos
    d1 = math.hypot(p[0] - c1[0], p[1] - c1[1])
    t_edge = edge_time(z, p, state.t)
    (cx, cy), r = zone_circle_at(z, state.t)
    inside_now = math.hypot(p[0] - cx, p[1] - cy) <= r
    if d1 <= r1 - margin:
        return {"point": tuple(p), "eta": 0.0, "leave_by": math.inf, "inside_now": inside_now, "t_edge": t_edge}
    # candidate: straight toward the next centre to depth `margin` inside, then nudge to walkable ground
    ux, uy = unit2(c1[0] - p[0], c1[1] - p[1])
    depth = min(r1, margin) if r1 > 1 else 0.0
    tx, ty = c1[0] - ux * (r1 - depth), c1[1] - uy * (r1 - depth)
    best = (tx, ty)
    if ar is not None and getattr(ar, "ok_nav", False):
        k = ar.size_class(_cubes(state))
        if not ar.walkable(tx, ty, k):
            best = None
            for rad in (4.0, 8.0, 12.0, 18.0, 25.0):
                for a in range(12):
                    qx, qy = tx + rad * math.cos(a * math.pi / 6), ty + rad * math.sin(a * math.pi / 6)
                    if math.hypot(qx - c1[0], qy - c1[1]) <= max(r1 - 2.0, 0.5) and ar.walkable(qx, qy, k):
                        best = (qx, qy)
                        break
                if best:
                    break
            if best is None:
                best = (c1[0], c1[1])
    gz = ar.surface(best[0], best[1]) if ar is not None and getattr(ar, "ok_nav", False) else p[2]
    point = (best[0], best[1], gz)
    e = eta(state, point)
    leave_by = (min(t_edge, float(z["shrink_end"])) - e - 3.0) if e != math.inf else state.t
    return {"point": point, "eta": e, "leave_by": leave_by, "inside_now": inside_now, "t_edge": t_edge}


# ============================================================================== internals
def _straight(state: WorldState, intent: Intent) -> NavOut:
    if intent is None or intent.goal is None:
        return NavOut()
    x, y = state.pos[0], state.pos[1]
    gx, gy = intent.goal[0], intent.goal[1]
    d = math.hypot(gx - x, gy - y)
    if d < 1.5:
        return NavOut(eta=0.0)
    return NavOut(move=unit2(gx - x, gy - y), eta=d / _walk_speed(state))


def _record(state: WorldState, m) -> None:
    h = m["hist"]
    h.append((state.t, state.pos[0], state.pos[1], state.pos[2]))
    while h and h[0][0] < state.t - 3.0:
        h.pop(0)


def _stalled(state: WorldState, m) -> bool:
    """Commanded movement for STALL_WINDOW but displacement far below expectation."""
    h = m["hist"]
    if len(h) < 4:
        return False
    t_now = h[-1][0]
    old = None
    for e in h:
        if e[0] >= t_now - STALL_WINDOW:
            old = e
            break
    if old is None or t_now - old[0] < STALL_WINDOW * 0.8:
        return False
    moved = math.hypot(h[-1][1] - old[1], h[-1][2] - old[2])
    expect = (t_now - old[0]) * _walk_speed(state) * 0.6
    cmd = m.get("cmd_hist") or []
    commanded = sum(1 for (tt, mag) in cmd if tt >= old[0] and mag > 0.5)
    return commanded >= 4 and moved < STALL_MIN_FRAC * expect


def _probe(ar, k, x, y, dx, dy, dist=5.0, z=None) -> bool:
    try:
        return ar.walk_line(x, y, x + dx * dist, y + dy * dist, k, step=0.7)
    except Exception:
        return True


def _steer(ar, k, x, y, dx, dy, dist=5.0) -> Tuple[float, float]:
    """Desired unit direction -> closest walkable direction (probing a fan). Slides along walls."""
    if ar is None or not getattr(ar, "ok_nav", False):
        return dx, dy
    base = math.atan2(dy, dx)
    for da in PROBE_ANGLES:
        a = base + da
        cx, cy = math.cos(a), math.sin(a)
        if _probe(ar, k, x, y, cx, cy, dist):
            # scale: off-axis directions still make progress; keep full speed (wall slide)
            return cx, cy
    return dx, dy


def _need_replan(state: WorldState, m, goal) -> bool:
    g0 = m["goal"]
    if g0 is None or math.hypot(g0[0] - goal[0], g0[1] - goal[1]) > 4.0:
        return True
    if m["pending"]:
        return True
    if not m["path"]:
        return True
    if state.t - m["plan_t"] > REPLAN_S:
        return True
    # off path: far from the segment we follow
    p = m["path"][0]
    if dist2d(state.pos, p) > 60.0:
        return True
    return False


def _advance_path(state: WorldState, m, ar, k) -> None:
    path = m["path"]
    x, y = state.pos[0], state.pos[1]
    # drop reached waypoints, or waypoints we have passed (closer to the next one than this one to it)
    z = state.pos[2]
    while len(path) > 1:
        w0, w1 = path[0], path[1]
        if _is_jet(w0):
            break
        d0 = math.hypot(w0[0] - x, w0[1] - y)
        if d0 < WP_REACH and abs(z - w0[2]) < 4.0:
            path.pop(0)
            continue
        if _is_jet(w1):
            break
        seg = math.hypot(w1[0] - w0[0], w1[1] - w0[1])
        if math.hypot(w1[0] - x, w1[1] - y) < seg - 0.5 and ar is not None and ar.walk_line(x, y, w1[0], w1[1], k):
            path.pop(0)
            continue
        break
    if len(path) == 1 and not _is_jet(path[0]) and math.hypot(path[0][0] - x, path[0][1] - y) < 1.0:
        path.pop(0)


def _lookahead(state: WorldState, m, ar, k) -> Optional[Tuple[float, float, float]]:
    path = m["path"]
    if not path:
        return None
    x, y = state.pos[0], state.pos[1]
    tgt = path[0]
    if _is_jet(tgt):
        return tgt
    # look one/two waypoints further if straight-walkable (shortcut corners)
    for j in (2, 1):
        if j < len(path) and not any(_is_jet(w) for w in path[:j + 1]) and math.hypot(path[j][0] - x, path[j][1] - y) < 45.0:
            if ar.walk_line(x, y, path[j][0], path[j][1], k):
                for _ in range(j):
                    path.pop(0)
                tgt = path[0]
                break
    return tgt


def _engage_dir(state: WorldState, intent: Intent, m) -> Optional[Tuple[float, float]]:
    """Keep desired_range to the target while strafing (switch side every 1.2-2.4 s)."""
    tid = intent.target_id
    if tid is None:
        return None
    tr = state.tracks.get(tid)
    if tr is None:
        return None
    x, y = state.pos[0], state.pos[1]
    dx, dy = tr.pos[0] - x, tr.pos[1] - y
    d = math.hypot(dx, dy)
    if d < 1e-3:
        return None
    ux, uy = dx / d, dy / d
    want = intent.desired_range or d
    radial = max(-1.0, min(1.0, (d - want) / 15.0))
    if state.t >= m["strafe_t"]:
        m["strafe_sign"] = -m["strafe_sign"]
        # Beyond ~80 m random reversals every 0.3-1.0 s ("juke") cut incoming gun damage far more than a slow
        # strafe (sim duel harness vs expert gun: 93 -> 56 dmg/s at 120 m, 72 -> 27 at 180 m). Up close
        # nothing helps much, so keep the steadier strafe there (more of our own shots land).
        if d > JUKE_MIN_RANGE:
            m["strafe_t"] = state.t + 0.3 + 0.7 * random.random()
            m["juking"] = True
        else:
            m["strafe_t"] = state.t + 1.2 + 1.2 * random.random()
            m["juking"] = False
    s = m["strafe_sign"]
    tx, ty = -uy * s, ux * s
    w_t = 0.85 if abs(radial) < 0.7 else 0.4
    vx, vy = ux * radial + tx * w_t, uy * radial + ty * w_t
    return unit2(vx, vy)


def _offmesh_escape(state: WorldState, m, ar, k) -> Optional[Tuple[float, float]]:
    """We stand somewhere that is not on the main walkable component (stadium bowl, roof, pit, noise):
    head to the nearest main-component node; jump/jet over whatever is in the way (handled by stall logic)."""
    x, y = state.pos[0], state.pos[1]
    if ar.walkable(x, y, k):
        m["offmesh_goal"] = None
        return None
    og = m.get("offmesh_goal")
    if og is None or dist2d(og, state.pos) > 80.0:
        n = ar.snap(x, y, k, max_r=12, need_line=False)
        if n < 0:
            return None
        og = ar._node_xy(n, k)
        m["offmesh_goal"] = og
    return og


def _step(state: WorldState, intent: Intent, threats: Threats, m) -> NavOut:
    ar = state.arena
    nav_ok = ar is not None and getattr(ar, "ok_nav", False)
    if ar is not None:
        try:
            ar.new_tick(state.tick)
        except Exception:
            pass
    _record(state, m)
    k = ar.size_class(_cubes(state)) if nav_ok else 0
    x, y, z = state.pos
    grounded = bool(state.me.get("grounded", True))
    energy = state.energy
    walk_v = _walk_speed(state)
    urgency = float(intent.urgency or 0.0) if intent else 0.0
    allow_boost = bool(intent.allow_boost) if intent else True
    goal = intent.goal if intent else None
    out = NavOut()
    want: Optional[Tuple[float, float]] = None
    speed = 1.0
    eta_s: Optional[float] = None

    # ---------------- stale hop state: a hop is only executed while its waypoint leads the path. If the path or
    # goal changed mid-hop, m["jet"] used to stay set forever, which disabled replanning (straight-line steering
    # into pits and walls: sim zone deaths). Clear it once the hop is over or abandoned.
    j = m.get("jet")
    if j is not None:
        if not grounded:
            j["air"] = True
        lead = (m.get("path") or [None])[0]
        if (state.t - j["t0"] > JET_TIMEOUT or (grounded and j.get("air")) or
                (grounded and lead is not j.get("to") and state.t - j["t0"] > 0.5)):
            m["jet"] = None
    # ---------------- recovery in progress
    rec = m.get("recover")
    if rec is not None and state.t < rec["until"]:
        mv = rec["dir"]
        out.move = mv
        out.jump = rec.get("jump", False) and grounded
        # recovery jets only clear low obstacles: stop climbing ~7 m above the start (no accidental roofs)
        out.boost = rec.get("jet", False) and energy > 8 and z < rec.get("z0", z) + 7.0
        out.blocked = True
        if rec.get("jet"):
            m["stats"]["jets"] += 1
        _cmd(m, state, 1.0)
        return out
    if rec is not None:
        m["recover"] = None

    # ---------------- choose desired direction
    mode = intent.mode if intent else "hold"
    if goal is not None and nav_ok:
        goal = _reachable_goal(state, m, ar, goal, k)
    if goal is not None:
        gx, gy = goal[0], goal[1]
        dgoal = math.hypot(gx - x, gy - y)
        if mode == "engage" and intent.target_id is not None and intent.desired_range:
            want = _engage_dir(state, intent, m)
        if want is None:
            if dgoal < 1.2:
                want = None
                eta_s = 0.0
            else:
                tgt = None
                if nav_ok:
                    if True:
                        if m.get("jet") is None and _need_replan(state, m, goal):
                            # After failed hops, stop planning big climbs (and finally plan as a smaller mech:
                            # the size-class lattices are conservative). Sim: an 8-cube mech beside a 37 m
                            # building retried a 35 m hop it could never finish for 30 s outside the zone.
                            jf = m.get("jet_fail", 0) if not _hop_legacy() else 0
                            if jf and state.t - m.get("jet_fail_t", -1e9) > 25.0:
                                m["jet_fail"] = jf = 0
                            cap = JET_CAP if jf == 0 else (16.0 if jf == 1 else 0.0)
                            cub = _cubes(state) if jf < 3 else 0.0
                            st_, path = ar.plan_full(state.pos, goal, cubes=cub, budget_ms=PLAN_BUDGET_MS,
                                                     jet_cap=cap, avoid=_avoid_list(state, threats, intent),
                                                     smooth_ms=0.8)
                            if st_ == "fail" and jf:
                                st_, path = ar.plan_full(state.pos, goal, cubes=0.0, budget_ms=PLAN_BUDGET_MS,
                                                         jet_cap=JET_CAP, avoid=(), smooth_ms=0.8)
                            m["stats"]["replans"] += 1
                            m["goal"] = tuple(goal)
                            m["plan_t"] = state.t
                            m["pending"] = st_ == "pending"
                            m["path"] = list(path) if st_ == "ok" else []
                            m["unreachable"] = st_ == "fail"
                            if st_ == "fail" and not ar.walkable(x, y, k):
                                og2 = _offmesh_escape(state, m, ar, k)
                                if og2 is not None:
                                    m["path"] = [(og2[0], og2[1], ar.surface(og2[0], og2[1]), "walk", 0.0)]
                        _advance_path(state, m, ar, k)
                        tgt = _lookahead(state, m, ar, k)
                        if tgt is not None and _is_jet(tgt):
                            jo = _jet_hop(state, m, ar, tgt, urgency)
                            if jo is not None:
                                return jo
                        if tgt is None:
                            tgt = (gx, gy)
                else:
                    tgt = (gx, gy)
                want = unit2(tgt[0] - x, tgt[1] - y)
                # slow down on the final approach so we stop on the goal
                if dgoal < 4.0:
                    speed = max(0.35, dgoal / 4.0)
                # eta along remaining path
                L = 0.0
                px, py = x, y
                for w in (m["path"] if nav_ok and m["path"] else [(gx, gy)]):
                    L += math.hypot(w[0] - px, w[1] - py)
                    px, py = w[0], w[1]
                eta_s = L / walk_v
    elif mode == "engage" and intent is not None and intent.target_id is not None:
        want = _engage_dir(state, intent, m)

    # ---------------- dodge incoming projectiles
    dodge = threats.dodge if threats is not None else None
    if mode == "engage" and m.get("juking") and threats is not None and hasattr(threats, "dodge_shell"):
        # while juking, reacting to bullets makes us predictable: only dodge mortar shells
        dodge = getattr(threats, "dodge_shell", None)
    if dodge is not None and (dodge[0] or dodge[1]):
        soon = min((p.t_impact for p in (threats.incoming or [])), default=1.0)
        w = 1.0 if soon < 0.6 else 0.5
        if want is None:
            want = unit2(dodge[0], dodge[1])
        else:
            want = unit2(want[0] * (1 - w) + dodge[0] * w * 1.5, want[1] * (1 - w) + dodge[1] * w * 1.5)

    # ---------------- avoid list (keep away from threat centroids when retreating)
    if want is not None and intent is not None and intent.avoid and mode in ("retreat", "heal"):
        ax = ay = 0.0
        for p in intent.avoid[:4]:
            d = math.hypot(x - p[0], y - p[1])
            if 1e-3 < d < 60.0:
                ax += (x - p[0]) / d * (60.0 - d) / 60.0
                ay += (y - p[1]) / d * (60.0 - d) / 60.0
        if ax or ay:
            want = unit2(want[0] + 0.6 * ax, want[1] + 0.6 * ay)

    if want is None:
        _cmd(m, state, 0.0)
        m["stall_t"] = None
        out.eta = eta_s
        return out

    # ---------------- wall probing / sliding
    dx, dy = _steer(ar, k, x, y, want[0], want[1], 5.0 if grounded else 3.0) if nav_ok and ar.walkable(x, y, k) else want

    # ---------------- speed caps (silent movement) and boost
    if intent is not None and intent.max_speed is not None:
        speed = min(speed, max(0.0, intent.max_speed / walk_v))
    boost = False
    if speed >= 0.99 and grounded and allow_boost:
        far = eta_s is not None and eta_s > 2.0
        if urgency >= 0.7 and energy > 12 and far:
            boost = True
        elif mode in ("retreat",) and energy > ENERGY_RESERVE:
            boost = True
        elif urgency >= 0.4 and energy > 80 and far:
            boost = True
    out.move = (dx * speed, dy * speed)
    out.boost = boost
    out.eta = (eta_s * walk_v / (state.stat("boost_speed", 19.5) if boost else walk_v)) if eta_s is not None else None
    _cmd(m, state, speed)

    # ---------------- stall detection -> recovery
    if goal is not None and _stalled(state, m) and math.hypot(goal[0] - x, goal[1] - y) < 3.5:
        # pressed against something right next to the goal: we are within pickup reach, stop pushing
        m["hist"] = m["hist"][-1:]
        m["cmd_hist"] = []
        out.move = (0.0, 0.0)
        out.boost = False
        out.eta = 0.0
        return out
    if _stalled(state, m):
        m["stats"]["stalls"] += 1
        m["hist"] = m["hist"][-1:]
        m["cmd_hist"] = []
        n = m.get("n_stall", 0) + 1
        m["n_stall"] = n
        m["path"] = []          # force replan
        if n % 3 == 1:
            # back off and sidestep
            s = 1.0 if (state.tick // 20) % 2 else -1.0
            bx, by = -dx * 0.6 - dy * 0.8 * s, -dy * 0.6 + dx * 0.8 * s
            m["recover"] = {"until": state.t + 0.6, "dir": unit2(bx, by), "jump": False, "jet": False}
        else:
            # jump + jet toward where we want to go (over the obstacle)
            jet = energy > (15 if urgency >= 0.7 else 30)
            m["recover"] = {"until": state.t + (1.4 if jet else 0.5), "dir": (want[0], want[1]), "jump": True, "jet": jet,
                            "z0": z}
        out.blocked = True
        out.jump = grounded and m["recover"]["jump"]
    else:
        if state.t - (m.get("last_ok_t") or 0) > 3.0:
            m["n_stall"] = 0
        m["last_ok_t"] = state.t if m.get("n_stall", 0) == 0 else m.get("last_ok_t", state.t)
    # In the air `boost` means JET. Outside an explicit jet hop / jet recovery never jet: walking off a roof
    # edge (planned drop) with boost held would rocket us onto the next roof.
    if not grounded and m.get("jet") is None:
        rec = m.get("recover")
        if not (rec is not None and rec.get("jet")):
            out.boost = False
    return out


def _avoid_list(state: WorldState, threats: Threats, intent: Intent) -> List:
    """Threat feet positions whose sight lines the route should avoid (not while engaging).
    Off by default (ROUTE_AVOID): measured on 12 routes, it cut exposed metres by 2-18 % for +1-15 % length at
    10-30x the planning cost (docs/nav.md)."""
    if not ROUTE_AVOID or intent is None or intent.mode == "engage" or threats is None:
        return []
    cand = []
    for e in threats.enemies or []:
        if e.kind != "mech" or state.t - e.last_seen_t > 6.0:
            continue
        if e.dist > 220.0:
            continue
        cand.append((-(e.danger or 0.0), e.dist, e.pos))
    cand.sort(key=lambda c: (c[0], c[1]))
    return [c[2] for c in cand[:3]]


def _reachable_goal(state: WorldState, m, ar, goal, k):
    """If the goal point itself can't be stood on (item against a wall, on a ledge/roof edge), use the nearest
    standable spot within pickup reach (Arena.reach_spot), cached per goal."""
    key = (round(goal[0], 1), round(goal[1], 1), round(goal[2], 1) if len(goal) > 2 else 0.0, k)
    c = m.get("reach_cache")
    if c is not None and c[0] == key:
        return c[1]
    gz = float(goal[2]) if len(goal) > 2 else ar.surface(goal[0], goal[1])
    out = goal
    if not ar.standable(goal[0], goal[1], k) or abs(ar.surface(goal[0], goal[1]) - gz) > 2.0:
        r = ar.reach_spot((goal[0], goal[1], gz), horiz=3.2, vert=3.8, cubes=_cubes(state))
        if r is not None:
            out = r
    m["reach_cache"] = (key, out)
    return out


def _is_jet(w) -> bool:
    return len(w) > 3 and w[3] == "jet"


def _jet_hop(state: WorldState, m, ar, wp, urgency: float) -> Optional[NavOut]:
    """Execute a planned jump+jet hop to waypoint wp=(x, y, z, 'jet', climb). Returns the NavOut to use, or
    None when the hop is finished/aborted (caller continues normal steering)."""
    x, y, z = state.pos
    grounded = bool(state.me.get("grounded", True))
    energy = state.energy
    climb = float(wp[4]) if len(wp) > 4 else max(0.0, wp[2] - z)
    # plan cost is 2.0/m; replays and the sim show ~2.4/m in practice: start only with the realistic amount
    legacy = _hop_legacy()
    if legacy:
        need = ar.jet_energy(climb) if ar is not None else 2.0 * climb + 6.0
    else:
        need = max(ar.jet_energy(climb) if ar is not None else 0.0, 2.4 * max(0.0, climb - 2.0) + 8.0)
    emax = float(state.me.get("max_energy", 100.0) or 100.0)
    if not legacy and need > emax * 0.98 and m.get("jet") is None:
        m["path"] = []
        m["jet_fail"] = m.get("jet_fail", 0) + 1
        m["jet_fail_t"] = state.t
        return None
    j = m.get("jet")
    d = math.hypot(wp[0] - x, wp[1] - y)
    dirx, diry = unit2(wp[0] - x, wp[1] - y)
    if j is None:
        if not grounded:
            return NavOut(move=(dirx, diry), boost=energy > 5)
        if energy < need and not (legacy and urgency >= 0.8 and energy >= 0.6 * need):
            # wait at the base for energy (regen starts energy_regen_delay after the last spend);
            # combat reads hop_wait_t/hop_need and stops spending lightning energy meanwhile
            if not legacy:
                m["hop_wait_t"], m["hop_need"] = state.t, need
            return NavOut(move=(0.0, 0.0), eta=(need - energy) / 18.0 + 1.0)
        m["jet"] = {"t0": state.t, "z0": z, "climb": climb, "to": wp, "air": False}
        m["stats"]["jets"] += 1
        return NavOut(move=(dirx, diry), jump=True, boost=True, eta=2.0)
    # in progress
    if not grounded:
        j["air"] = True
    top = j["z0"] + j["climb"] + 1.0
    if state.t - j["t0"] > JET_TIMEOUT or (grounded and j["air"]):
        m["jet"] = None
        landed_ok = abs(z - wp[2]) < 2.5 and d < 8.0
        if landed_ok:
            if m["path"] and m["path"][0] is wp:
                m["path"].pop(0)
        else:
            m["path"] = []        # failed hop: replan from where we are
            m["jet_fail"] = m.get("jet_fail", 0) + 1
            m["jet_fail_t"] = state.t
        return None
    if grounded and not j["air"] and state.t - j["t0"] > 0.4:
        # jump did not take (blocked?): retry once next tick
        return NavOut(move=(dirx, diry), jump=True, boost=True, blocked=True)
    boost = z < top and energy > 1.0
    # until the feet clear the edge, push gently toward the wall; once above, go for the landing spot
    mv = (dirx, diry) if z >= top - 1.0 or d > 3.0 else (dirx * 0.5, diry * 0.5)
    return NavOut(move=mv, boost=boost, jump=False, eta=1.0)


def _cmd(m, state: WorldState, mag: float) -> None:
    ch = m.setdefault("cmd_hist", [])
    ch.append((state.t, mag))
    while ch and ch[0][0] < state.t - 3.0:
        ch.pop(0)
