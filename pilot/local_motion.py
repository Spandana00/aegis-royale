"""Bounded motion lookahead for grounded fights, inspired by aqilc's public kiter.

Independently implemented: compare short acceleration-limited trajectories using
projectile closest approach, landing shells, weapon spacing, walls and the zone.
All travel, roof routes, retreat and healing remain with the existing navigator.
"""
import math
import time


def choose(state, intent, threats, base, size_class):
    target = state.tracks.get(intent.target_id)
    if target is None or not state.me.get("grounded", True):
        return None
    if state.t - target.last_seen_t > 1.5:
        return None
    start = time.perf_counter()
    pos = state.pos
    ar = state.arena
    walk = state.stat("walk_speed", 11.7)
    charging = any(w and w.get("kind") == "laser" and w.get("charge", 0) > 0
                   for w in state.me.get("weapons") or [])
    if charging:
        walk *= float(state.cfg.get("mech", {}).get("charge_move_mult", .5))
    accel = state.stat("ground_accel", 58.5)
    cubes = state.me.get("cubes", 0)
    radius = state.stat("radius", 2.5 * (1 + .05 * cubes))
    height = state.stat("height", 9.0 * (1 + .05 * cubes))
    want = intent.desired_range or math.dist(pos[:2], target.pos[:2])
    dt, steps = .1, 6
    horizon = dt * steps
    tc = (target.pos[0] + target.vel[0] * horizon, target.pos[1] + target.vel[1] * horizon)
    zone_c, zone_r = state.zone_circle_at(state.t + horizon)
    shots = []
    shells = []
    gravity = float(state.cfg.get("mech", {}).get("gravity", 22.0))
    weapon_cfg = state.cfg.get("weapons", {})
    for p in state.obs.get("projectiles", []):
        pp, pv = p["pos"], p["vel"]
        if p.get("kind") == "mortar":
            disc = pv[2] ** 2 + 2 * gravity * max(0., pp[2] - pos[2])
            impact = (pv[2] + math.sqrt(disc)) / max(gravity, 1e-6)
            if 0 < impact <= horizon + .1:
                shells.append((impact, pp[0] + pv[0] * impact, pp[1] + pv[1] * impact))
            continue
        speed2 = pv[0] ** 2 + pv[1] ** 2
        if speed2 < 1:
            continue
        time_to = ((pos[0] - pp[0]) * pv[0] + (pos[1] - pp[1]) * pv[1]) / speed2
        if -.05 < time_to < horizon + .2:
            shots.append((time_to, p))
    shots.sort(key=lambda pair: pair[0])
    shots = [p for _, p in shots[:16]]
    beams = [e for e in threats.enemies if e.kind == "mech" and e.charging and e.visible][:3]
    angle = math.atan2(base[1], base[0])
    candidates = [base]
    candidates.extend((math.cos(angle + k * math.pi / 4), math.sin(angle + k * math.pi / 4))
                      for k in (1, -1, 2, -2, 3, -3, 4))
    candidates.append((0., 0.))
    best, lowest = base, math.inf
    evaluated = 0
    for direction in candidates:
        if evaluated and time.perf_counter() - start > .002:
            break
        x, y = pos[:2]
        vx, vy = state.vel[:2]
        path = [(x, y)]
        blocked = False
        for _ in range(steps):
            ax, ay = direction[0] * walk - vx, direction[1] * walk - vy
            length = math.hypot(ax, ay)
            frac = min(1., accel * dt / max(length, 1e-9))
            vx, vy = vx + ax * frac, vy + ay * frac
            nx, ny = x + vx * dt, y + vy * dt
            if ar is not None and getattr(ar, "ok_nav", False) and not ar.walk_line(x, y, nx, ny, size_class):
                blocked = True
                vx = vy = 0.
            else:
                x, y = nx, ny
            path.append((x, y))
        score = 60. if blocked else 0.
        distance = math.hypot(x - tc[0], y - tc[1])
        score += .015 * (distance - want) ** 2
        score += .5 * (1. - direction[0] * base[0] - direction[1] * base[1])
        outside = math.hypot(x - zone_c[0], y - zone_c[1]) - max(0., zone_r - radius - 2.)
        if outside > 0:
            score += 100. + 20. * outside
        for p in shots:
            pp, pv = p["pos"], p["vel"]
            risk = 0.
            for j in range(steps):
                t = j * dt
                rx, ry = pp[0] + pv[0] * t - path[j][0], pp[1] + pv[1] * t - path[j][1]
                rvx = pv[0] - (path[j+1][0] - path[j][0]) / dt
                rvy = pv[1] - (path[j+1][1] - path[j][1]) / dt
                closest = min(dt, max(0., -(rx * rvx + ry * rvy) / max(1e-9, rvx**2 + rvy**2)))
                z = pp[2] + pv[2] * (t + closest)
                if pos[2] - .5 <= z <= pos[2] + height + .5:
                    miss = math.hypot(rx + rvx * closest, ry + rvy * closest)
                    risk = max(risk, min(1., max(0., (radius + 1.3 - miss) / 1.2)))
            damage = 25. if p.get("kind") == "npc" else float(weapon_cfg.get("gun", {}).get("damage", 45.))
            score += 1.5 * damage * risk
        mortar = weapon_cfg.get("mortar", {})
        splash_r = float(mortar.get("splash_radius", 7.)) + radius
        for impact, sx, sy in shells:
            at = path[min(steps, max(1, round(impact / dt)))]
            d = math.hypot(at[0] - sx, at[1] - sy)
            if d < splash_r:
                score += float(mortar.get("splash", 160.)) * (1 - .7 * d / splash_r)
        for e in beams:
            yaw = e.aim[0] if hasattr(e, "aim") else (state.tracks.get(e.id).aim[0] if state.tracks.get(e.id) else 0.)
            ux, uy = math.cos(yaw), math.sin(yaw)
            ex, ey = x - e.pos[0], y - e.pos[1]
            along, across = ex * ux + ey * uy, abs(ex * uy - ey * ux)
            if 0 < along < 280. and across < radius + 4.:
                score += 100. * (1 - across / (radius + 4.))
        if ar is not None and hasattr(ar, "shot_clear"):
            muzzle = (x, y, pos[2] + .8 * height)
            aim = (tc[0], tc[1], target.pos[2] + 4.5)
            if not ar.shot_clear(muzzle, aim):
                score += 18.
        if score < lowest:
            best, lowest = direction, score
        evaluated += 1
    stats = state.scratch.setdefault("motion", {})
    stats["calls"] = stats.get("calls", 0) + 1
    stats["candidates"] = stats.get("candidates", 0) + evaluated
    return best
