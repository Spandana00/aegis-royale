"""Pure ballistics / aiming maths. OWNER: combat. Standard library only, no state.

Conventions: meters, seconds, radians; x east, y north, z up; yaw CCW from +x; pitch up-positive.

Facts verified against the public 10 Hz replay (mechanics-v2-16.jsonl.gz), see docs/combat.md:
  * Projectiles do NOT inherit the shooter's velocity (gun speeds 140.00 +- 0.05 in that replay's
    config, mortar launch speed 72 regardless of shooter speed up to 15 m/s).
  * Shot origin: horizontal offset (radius + 0.5) * cos(pitch) along the aim yaw, vertical = muzzle
    height (gun) / height + 0.5 (mortar) above the feet -- the 3 m offset has NO vertical part
    (mortar fit residual = -3 sin(pitch) otherwise; with it removed residuals are < 0.1 m over 3.7 s).
  * Timing: a projectile fired on decision tick N is, at match time t_N + tau, at
    origin + v * tau (- g tau^2 / 2 for shells): it is effectively launched at the decision time
    from where the shooter is one sim tick (0.05 s) later.
  * Gun spread: per-axis Gaussian with sigma ~= spread_deg (measured 0.58 deg per axis, which
    includes the 0.01 rad aim rounding of the replay).
  * Torso slew is a per-axis clamp: yaw turn_rate, pitch pitch_rate rad/s (0.4 / 0.3 per decision).
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

Vec3 = Tuple[float, float, float]
TICK = 0.05          # one sim tick
DECISION = 0.1       # one decision (2 ticks)
TWO_PI = 2.0 * math.pi


def wrap(a: float) -> float:
    """Angle into (-pi, pi]."""
    return (a + math.pi) % TWO_PI - math.pi


def aim_dir(yaw: float, pitch: float) -> Vec3:
    cp = math.cos(pitch)
    return (cp * math.cos(yaw), cp * math.sin(yaw), math.sin(pitch))


def dir_to_aim(d: Sequence[float]) -> Tuple[float, float]:
    h = math.hypot(d[0], d[1])
    return math.atan2(d[1], d[0]), math.atan2(d[2], h)


def slew(actual: Sequence[float], cmd: Sequence[float], yaw_rate: float, pitch_rate: float,
         dt: float, min_pitch: float = -0.7, max_pitch: float = 1.3) -> Tuple[float, float]:
    """Actual torso aim after `dt` seconds of slewing from `actual` toward `cmd` (per-axis clamp)."""
    cp = min(max_pitch, max(min_pitch, cmd[1]))
    dy = wrap(cmd[0] - actual[0])
    my = yaw_rate * dt
    if dy > my:
        dy = my
    elif dy < -my:
        dy = -my
    dp = cp - actual[1]
    mp = pitch_rate * dt
    if dp > mp:
        dp = mp
    elif dp < -mp:
        dp = -mp
    return wrap(actual[0] + dy), actual[1] + dp


def slew_time(actual: Sequence[float], cmd: Sequence[float], yaw_rate: float, pitch_rate: float) -> float:
    """Seconds until the torso reaches `cmd` from `actual`."""
    return max(abs(wrap(cmd[0] - actual[0])) / max(1e-6, yaw_rate), abs(cmd[1] - actual[1]) / max(1e-6, pitch_rate))


def ang_between(a: Sequence[float], b: Sequence[float]) -> float:
    """Angle between two aims [yaw, pitch] (radians)."""
    da, db = aim_dir(a[0], a[1]), aim_dir(b[0], b[1])
    c = da[0] * db[0] + da[1] * db[1] + da[2] * db[2]
    return math.acos(max(-1.0, min(1.0, c)))


def shot_origin(pos: Sequence[float], yaw: float, pitch: float, height: float, offset: float = 3.0) -> Vec3:
    """Where a shot leaves: `height` above the feet, `offset` * cos(pitch) out horizontally."""
    h = offset * math.cos(pitch)
    return (pos[0] + h * math.cos(yaw), pos[1] + h * math.sin(yaw), pos[2] + height)


# ----------------------------------------------------------------------------- straight projectiles
def intercept_time(rel_p: Sequence[float], rel_v: Sequence[float], speed: float) -> Optional[float]:
    """Smallest t > 0 with |rel_p + rel_v t| = speed * t, or None."""
    a = rel_v[0] ** 2 + rel_v[1] ** 2 + rel_v[2] ** 2 - speed * speed
    b = 2.0 * (rel_p[0] * rel_v[0] + rel_p[1] * rel_v[1] + rel_p[2] * rel_v[2])
    c = rel_p[0] ** 2 + rel_p[1] ** 2 + rel_p[2] ** 2
    if abs(a) < 1e-9:
        if abs(b) < 1e-12:
            return None
        t = -c / b
        return t if t > 0 else None
    disc = b * b - 4 * a * c
    if disc < 0:
        return None
    s = math.sqrt(disc)
    t1, t2 = (-b - s) / (2 * a), (-b + s) / (2 * a)
    ts = [t for t in (t1, t2) if t > 1e-6]
    return min(ts) if ts else None


def lead_aim(origin: Sequence[float], target: Sequence[float], tvel: Sequence[float], speed: float,
             extra_t: float = 0.0, tacc: Sequence[float] = (0.0, 0.0, 0.0), iters: int = 2):
    """Aim [yaw, pitch] and flight time to hit a point moving with `tvel` (+ optional acceleration),
    where the target is observed `extra_t` seconds before the shot is effectively launched.

    Returns (yaw, pitch, t_flight, aim_point) or None when no solution."""
    p = (target[0] + tvel[0] * extra_t, target[1] + tvel[1] * extra_t, target[2] + tvel[2] * extra_t)
    rel = (p[0] - origin[0], p[1] - origin[1], p[2] - origin[2])
    t = intercept_time(rel, tvel, speed)
    if t is None:
        return None
    for _ in range(iters if (tacc[0] or tacc[1] or tacc[2]) else 0):
        # refine with acceleration term (fixed point)
        q = (rel[0] + tvel[0] * t + 0.5 * tacc[0] * t * t, rel[1] + tvel[1] * t + 0.5 * tacc[1] * t * t,
             rel[2] + tvel[2] * t + 0.5 * tacc[2] * t * t)
        t = math.sqrt(q[0] ** 2 + q[1] ** 2 + q[2] ** 2) / speed
    ap = (p[0] + tvel[0] * t + 0.5 * tacc[0] * t * t, p[1] + tvel[1] * t + 0.5 * tacc[1] * t * t,
          p[2] + tvel[2] * t + 0.5 * tacc[2] * t * t)
    yaw, pitch = dir_to_aim((ap[0] - origin[0], ap[1] - origin[1], ap[2] - origin[2]))
    return yaw, pitch, t, ap


def closest_approach(p: Sequence[float], v: Sequence[float], q: Sequence[float], w: Sequence[float] = (0, 0, 0),
                     tmax: float = 10.0) -> Tuple[float, float]:
    """Time in [0, tmax] and distance of closest approach between points p+v t and q+w t."""
    rp = (p[0] - q[0], p[1] - q[1], p[2] - q[2])
    rv = (v[0] - w[0], v[1] - w[1], v[2] - w[2])
    vv = rv[0] ** 2 + rv[1] ** 2 + rv[2] ** 2
    t = 0.0 if vv < 1e-12 else -(rp[0] * rv[0] + rp[1] * rv[1] + rp[2] * rv[2]) / vv
    t = min(tmax, max(0.0, t))
    d = math.sqrt((rp[0] + rv[0] * t) ** 2 + (rp[1] + rv[1] * t) ** 2 + (rp[2] + rv[2] * t) ** 2)
    return t, d


def ray_cylinder_miss(origin: Sequence[float], d: Sequence[float], feet: Sequence[float], height: float) -> Tuple[float, float]:
    """For a straight ray (unit d) against a vertical cylinder axis from feet to feet+height:
    returns (horizontal miss distance of the ray from the axis at closest horizontal approach,
             vertical offset outside [0, height] of the ray at that point (0 if inside)).
    """
    hx, hy = d[0], d[1]
    hh = hx * hx + hy * hy
    rx, ry = feet[0] - origin[0], feet[1] - origin[1]
    if hh < 1e-9:
        return math.hypot(rx, ry), 0.0
    s = (rx * hx + ry * hy) / hh  # ray parameter (in units of |d|) at closest horizontal approach
    s = max(0.0, s)
    mx, my = origin[0] + hx * s - feet[0], origin[1] + hy * s - feet[1]
    z = origin[2] + d[2] * s - feet[2]
    dz = 0.0 if 0.0 <= z <= height else (z if z < 0 else z - height)
    return math.hypot(mx, my), dz


# ----------------------------------------------------------------------------- hit probability
def _phi(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def interval_prob(mu: float, sigma: float, half: float) -> float:
    """P(|N(mu, sigma)| < half)."""
    if sigma < 1e-6:
        return 1.0 if abs(mu) < half else 0.0
    return max(0.0, _phi((half - mu) / sigma) - _phi((-half - mu) / sigma))


def hit_probability(lat_err: float, vert_err: float, dist: float, radius: float, height: float,
                    spread_sigma_rad: float, pred_sigma: float = 0.0, aim_sigma_rad: float = 0.0,
                    vert_sigma: Optional[float] = None) -> float:
    """Probability a shot hits a cylinder seen side-on as a (2 radius x height) rectangle.

    lat_err / vert_err: deterministic offset (m) of the expected impact from the target center
    (lateral, vertical), dist: range (m), spread_sigma_rad: per-axis angular sigma of the weapon,
    pred_sigma: target-motion prediction sigma (m) per axis, aim_sigma_rad: extra angular aim noise.
    The effective half-width is shrunk a bit for the projectile's own radius being tiny (0.3 m adds).
    """
    s_ang = math.hypot(spread_sigma_rad, aim_sigma_rad) * dist
    s = math.hypot(s_ang, pred_sigma)
    sv = math.hypot(s_ang, pred_sigma * 0.5 if vert_sigma is None else vert_sigma)  # vertical: ground / gravity
    return interval_prob(lat_err, s, radius + 0.3) * interval_prob(vert_err, sv, 0.5 * height + 0.3)


def motion_sigma(t: float, speed: float, accel: float = 58.5, agility: float = 0.5) -> float:
    """Std-dev (m) of a target's displacement error after t seconds if it may change velocity.

    worst = min(accel t^2 / 2, 2 v t) is how far a reversal can take it from the constant-velocity
    prediction. Fitted in the sim (tests/combat/duel_harness.py hitrate, gun at 100-190 m vs walk / strafe /
    juke / jump targets): sigma ~= (0.28 + 0.6 agility) * worst for moving targets, ~0.08 * worst for
    stationary ones (they may start moving). agility = reversal rate / 2 (threats.EnemyX.agility)."""
    worst = min(0.5 * accel * t * t, 2.0 * max(speed, 3.0) * t)
    base = 0.28 if speed > 2.0 else 0.08
    return (base + 0.6 * agility) * worst + 0.15


# ----------------------------------------------------------------------------- mortar
def mortar_pitches(dx: float, dz: float, v: float, g: float) -> List[float]:
    """Launch pitches (low first) to hit a point dx horizontally and dz above the origin."""
    if dx < 1e-3:
        return [math.pi / 2] if dz >= 0 else []
    v2 = v * v
    disc = v2 * v2 - g * (g * dx * dx + 2.0 * dz * v2)
    if disc < 0:
        return []
    s = math.sqrt(disc)
    lo = math.atan2(v2 - s, g * dx)
    hi = math.atan2(v2 + s, g * dx)
    return [lo, hi] if hi - lo > 1e-6 else [lo]


def mortar_solve(pos: Sequence[float], target: Sequence[float], tvel: Sequence[float], v: float, g: float,
                 tube_h: float, offset: float = 3.0, high: bool = False, delay: float = 0.0,
                 min_pitch: float = -0.7, max_pitch: float = 1.3, iters: int = 4):
    """Solve a mortar shot from shooter feet `pos` (already advanced to launch time) to a target point
    moving with `tvel` (horizontal lead only; z of target kept unless tvel[2] given).

    `delay`: seconds between the target observation and the effective launch.
    Returns (yaw, pitch, flight_time, impact_point) or None."""
    tx, ty, tz = target[0] + tvel[0] * delay, target[1] + tvel[1] * delay, target[2] + tvel[2] * delay
    t_f = 0.0
    yaw = math.atan2(ty - pos[1], tx - pos[0])
    pitch = 0.6 if high else 0.2
    px, py, pz = tx, ty, tz
    for _ in range(iters):
        px, py, pz = tx + tvel[0] * t_f, ty + tvel[1] * t_f, tz + tvel[2] * t_f
        yaw = math.atan2(py - pos[1], px - pos[0])
        o = shot_origin(pos, yaw, pitch, tube_h, offset)
        dx = math.hypot(px - o[0], py - o[1])
        dz = pz - o[2]
        sols = mortar_pitches(dx, dz, v, g)
        if not sols:
            return None
        pitch = sols[-1] if high else sols[0]
        if pitch < min_pitch - 1e-9 or pitch > max_pitch + 1e-9:
            return None
        ch = v * math.cos(pitch)
        t_f = dx / ch if ch > 1e-6 else 0.0
    o = shot_origin(pos, yaw, pitch, tube_h, offset)
    return yaw, pitch, t_f, (px, py, pz)


def shell_point(origin: Sequence[float], yaw: float, pitch: float, v: float, g: float, t: float) -> Vec3:
    cp = math.cos(pitch)
    return (origin[0] + v * cp * math.cos(yaw) * t, origin[1] + v * cp * math.sin(yaw) * t,
            origin[2] + v * math.sin(pitch) * t - 0.5 * g * t * t)


def ballistic_impact(p: Sequence[float], vel: Sequence[float], g: float, ground, tmax: float = 7.0,
                     dt: float = 0.05, solid=None) -> Tuple[Vec3, float]:
    """Integrate a visible shell (position p, velocity vel) until it meets the ground.

    ground(x, y, z) -> surface height under (x, y) at or below z. solid(a, b) -> True if the segment
    a->b is blocked (optional, expensive; checked every 4 steps). Returns (impact point, time)."""
    vx, vy, vz = vel
    t = 0.0
    prev = (p[0], p[1], p[2])
    chunk = prev
    k = 0
    while t < tmax:
        t += dt
        nx, ny = p[0] + vx * t, p[1] + vy * t
        nz = p[2] + vz * t - 0.5 * g * t * t
        gz = ground(nx, ny, max(nz, prev[2]) + 0.5)
        if nz <= gz:
            # interpolate the crossing between prev and this step
            h0 = prev[2] - ground(prev[0], prev[1], prev[2] + 0.5)
            h1 = nz - gz
            f = h0 / max(1e-6, h0 - h1)
            f = min(1.0, max(0.0, f))
            ip = (prev[0] + (nx - prev[0]) * f, prev[1] + (ny - prev[1]) * f, prev[2] + (nz - prev[2]) * f)
            return ip, t - dt + dt * f
        k += 1
        cur = (nx, ny, nz)
        if solid is not None and k % 4 == 0:
            if solid(chunk, cur):
                return cur, t
            chunk = cur
        prev = cur
    return prev, tmax


def splash_damage(dist: float, splash: float, radius: float, edge: float) -> float:
    """Splash at distance `dist` from the blast: full at 0, `edge` fraction at `radius`, 0 beyond.
    Linear falloff assumed (rulebook: 'falling to 30% at splash_radius')."""
    if dist >= radius:
        return 0.0
    return splash * (1.0 - (1.0 - edge) * dist / radius)


# ----------------------------------------------------------------------------- laser
def laser_damage(charge: float, full: float, charge_s: float, min_frac: float, min_charge: float) -> float:
    """Damage of a laser shot released at `charge` seconds (released before min_charge fires at min_charge)."""
    c = max(min_charge, min(charge, charge_s))
    return full * (min_frac + (1.0 - min_frac) * c / max(1e-6, charge_s))
