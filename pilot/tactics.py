"""Bounded resource and shelter experiments; firing and navigation remain separate."""
from __future__ import annotations

from .state import Intent, dist2d, yaw_to


def _count(m, name):
    stats = m.setdefault("tactics_stats", {})
    stats[name] = stats.get(name, 0) + 1


def cube_detour(state, m, threats, hot, fight, zp):
    """Keep firing while collecting cheap health/damage/upgrade value near a fight."""
    from . import brain
    cubes = int(state.me.get("cubes", 0) or 0)
    cap = int(state.cfg.get("cubes", {}).get("stat_cap", 10))
    target = fight.get("target")
    if (cubes >= cap or not hot or fight.get("verdict") != "engage" or target is None
            or target.id in (getattr(threats, "killable", None) or [])
            or state.hp < .35 * state.max_hp):
        return None
    incoming = sum(brain.enemy_dps(e, e.dist) for e in hot if e.can_hit_me or e.id in threats.attackers)
    speed = max(1., state.stat("walk_speed", 11.7))
    if any(w and w.get("kind") == "laser" and w.get("charge", 0) > 0 for w in state.me.get("weapons") or []):
        speed *= .5
    best, best_cost = None, float("inf")
    for item in m["items"].values():
        if (item["type"] != "cube" or m["blacklist"].get(item["id"], -1e9) > state.t
                or abs(item["pos"][2] - state.pos[2]) > 3.):
            continue
        distance = dist2d(state.pos, item["pos"])
        if distance > 18. or state.t - item["t"] > 2.:
            continue
        # Pickup is automatic inside its configured radius, so count only travel to that disc.
        radius = float(state.cfg.get("cubes", {}).get("pickup_radius", 4.))
        eta = max(0., distance - radius) * 1.25 / speed
        cost = incoming * eta
        if cost > min(90., .12 * state.hp) or eta > 2. or not brain._inside_zone_soon(state, item["pos"]):
            continue
        # Reject obstructed detours rather than replacing a productive fight with a new route.
        if state.arena is not None:
            try:
                k = state.arena.size_class(cubes)
                if not state.arena.walk_line(state.pos[0], state.pos[1], item["pos"][0], item["pos"][1], k):
                    continue
            except (AttributeError, TypeError):
                continue
        if cost + distance < best_cost:
            best, best_cost = item, cost + distance
    if best is None:
        return None
    _count(m, "cube_detours")
    return Intent(mode="loot", goal=best["pos"], loot_id=best["id"], target_id=target.id,
                  face=yaw_to(state.pos, target.pos), allow_fire=True, urgency=.5,
                  reason=f"combat cube {best['id']}")


def recovery(state, m, threats, fresh, fight, zp):
    """Rest in verified shelter below 25% HP; resume at 60%, with a bounded attempt."""
    from . import brain
    hpf = state.hp / max(1., state.max_hp)
    active = m.get("critical")
    if active and (hpf >= .60 or state.t - active["started"] > 22.):
        m.pop("critical", None)
        m["critical_retry"] = state.t + 8.
        return None
    target = fight.get("target")
    if target is not None and target.id in (getattr(threats, "killable", None) or []):
        return None
    if not active and (hpf >= .25 or state.t < m.get("critical_retry", -1e9)):
        return None
    if state.arena is None:
        return None
    shooters = [e for e in fresh if e.can_hit_me or e.id in threats.attackers]
    if any(e.dist < 45. for e in shooters):
        return None
    points = [tuple(e.pos) for e in sorted(shooters, key=lambda e: e.dist)[:3]]
    if active is None:
        if not points:
            return None
        cover = state.arena.nearest_cover(state.pos, points, 30., cubes=state.me.get("cubes", 0), budget_ms=2.)
        if cover is None or dist2d(state.pos, cover) > 24. or not brain._inside_zone_soon(state, cover):
            m["critical_retry"] = state.t + 2.
            return None
        active = {"goal": tuple(cover), "started": state.t}
        m["critical"] = active
        _count(m, "recovery_starts")
    goal = active["goal"]
    if not brain._inside_zone_soon(state, goal):
        m.pop("critical", None)
        return None
    _count(m, "recovery_decisions")
    return Intent(mode="heal", goal=goal, urgency=.6, allow_fire=False,
                  face=yaw_to(state.pos, points[0]) if points else None,
                  avoid=points, reason=f"critical recover {hpf:.2f}")
