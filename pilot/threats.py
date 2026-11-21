"""Threat assessment. OWNER: combat.

`assess(state) -> Threats` (a `ThreatsX`, which only ADDS fields to `state.Threats`):

* enemies: every tracked mech / npc (obs memory gives real positions for 5 s after LOS is lost), with
  LOS (one `Arena.shot_clear` per enemy, nearest first, capped), `can_hit_me`, `facing_me`, `charging`,
  a per-enemy `danger` (model of the DPS it can put on us now), `dps_on_me` (observed, last 5 s),
  plus extras on `EnemyX`: aim, agility (how much it jukes), lead velocity, rear exposure, size, ...
* contacts: enemies we cannot see, inferred from sounds (bearing sigma 7 deg + range bucket), beams
  (exact shooter muzzle) and damage events (bearing + attacker id).
* incoming: visible bullets (straight) and mortar shells (ballistic, impact predicted against
  terrain/roofs) that will hit us if we keep our velocity, with a dodge direction and urgency;
  laser chargers aiming at us appear as kind "laser".
* dodge: one combined evasive unit vector (or None), `dodge_urgency` 0..1.
* mode_guess: "squad" (practice: house bots never fight each other) / "ffa" / "unknown".
* killable: mech ids we can probably finish in ~3 s; safe_dirs: [(yaw, score)] best first for
  disengaging; face_yaw: where the torso should point to keep the front arc on the danger.

Never raises (the integrator also wraps it); cost is bounded (<= MAX_LOS shot_clear calls, one
ballistic integration per visible shell).
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from . import ballistics as B
from .state import EnemyThreat, ProjectileRisk, Threats, WorldState

MAX_LOS = 8              # shot_clear calls per tick for enemies
CONTACT_TTL = 6.0        # seconds an inferred contact lives
SOUND_RANGE = {"near": 35.0, "mid": 110.0, "far": 230.0}
ENEMY_SOUNDS = ("gun", "mortar", "laser", "laser_charge", "lightning", "step", "boost", "jet", "reload")

# Rough effective DPS of a weapon in the hands of a competent bot (before hit probability):
# gun 12 x 45 per (12 x 0.24 + 2.4) s; laser 315 per (0.75 + 1.65) s; lightning 60 / 0.25 s while energy lasts;
# mortar (200 + 160) / 2.6 s; npc 25 / 1 s.
# Hunter model (squad diagnosis 11-21: most bad squad matches were lost to ONE engaged house bot while we shot
# passive ones or faced a passive bot with our back to the attacker). A "hunter" hit us recently or keeps aiming at
# us; everyone else's modelled danger is discounted, strongly when the round looks like the practice squad.
import os as _os
HUNTER_S = 8.0                        # a mech that hit us within this many seconds is a hunter
AIM_HUNTER_S = 0.8                    # ...or one that kept its aim on us (visible) this long
PASSIVE_MULT = {"squad": 0.2, "unknown": 0.45, "ffa": 0.75}
HUNTER_ON = _os.environ.get("MECH_HUNTER", "1") not in ("0", "false", "no")

BASE_DPS = {"gun": 102.0, "laser": 131.0, "lightning": 200.0, "mortar": 138.0, "npc": 25.0}
RANGE = {"gun": 230.0, "laser": 280.0, "lightning": 45.0, "mortar": 235.0, "npc": 90.0}


def _log(*a):
    try:
        print("[threats]", *a, file=sys.stderr, flush=True)
    except Exception:
        pass


@dataclass
class EnemyX(EnemyThreat):
    aim: Tuple[float, float] = (0.0, 0.0)
    cubes: int = 0
    radius: float = 2.5
    height: float = 9.0
    agility: float = 0.3                  # 0 straight-line mover .. 1 constant juking
    lead_vel: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    flip_rate: float = 0.0                # estimated direction reversals per second (strafing)
    since_flip: Optional[float] = None    # seconds since its last reversal
    flip_min_gap: Optional[float] = None  # shortest gap between its reversals (periodic strafers)
    jumpy: float = 0.0                    # fraction of the last 3 s it was airborne
    airborne: bool = False
    rear_exposed: bool = False            # its back (outside its front arc) faces us: our hits x1.5
    age: float = 0.0                      # seconds since last in obs
    charge_t: float = 0.0                 # how long we've seen it charging (laser)
    shorted: bool = False
    holds_mortar: bool = False
    hp_frac: float = 1.0
    bearing: float = 0.0                  # yaw from us to it
    model_dps: float = 0.0
    hunter: bool = False                  # hit us within HUNTER_S or kept aiming at us (see HUNTER_S)
    last_hit_me_t: float = -1e9


@dataclass
class Contact:
    pos: Tuple[float, float, float]
    sigma: float                          # position uncertainty (m)
    t: float                              # match time of the evidence
    kind: str                             # weapon/sound kind
    id: Optional[int] = None              # attacker id when known
    source: str = "sound"                 # sound | beam | damage


@dataclass
class ThreatsX(Threats):
    contacts: List[Contact] = field(default_factory=list)
    dodge_urgency: float = 0.0
    dodge_shell: Optional[Tuple[float, float]] = None   # evasive unit vector for mortar shells only
    shell_urgency: float = 0.0
    mode_guess: str = "unknown"
    killable: List[int] = field(default_factory=list)
    safe_dirs: List[Tuple[float, float]] = field(default_factory=list)
    face_yaw: Optional[float] = None
    n_can_hit: int = 0                    # enemies (mechs) with a line of fire on us now
    incoming_damage: float = 0.0          # expected damage of the predicted projectile hits
    rear_threat: bool = False             # we were hit from behind in the last 2 s or a danger sits behind us
    shorted_until: float = -1.0           # our laser is shorted until this match time
    squad_evidence: Dict[str, float] = field(default_factory=dict)
    hunters: List[int] = field(default_factory=list)       # ids of hunters (visible or not)
    unseen_attack: Optional[Tuple[float, float, int]] = None   # (bearing, t, by): hit by a mech we do not see now


def _mem(state: WorldState) -> Dict[str, Any]:
    m = state.scratch.get("threats")
    if m is None:
        m = {"vhist": {}, "contacts": [], "charge_start": {}, "infight": 0.0, "focus": set(), "shorted_until": -1.0,
             "hp_seen": {}, "beam_seen": set()}
        state.scratch["threats"] = m
    return m


def _wcfg(state: WorldState, kind: str, key: str, default: float) -> float:
    try:
        return float(state.cfg.get("weapons", {}).get(kind, {}).get(key, default))
    except Exception:
        return default


def _shot_clear(state: WorldState, a, b) -> bool:
    ar = state.arena
    if ar is None:
        return True
    try:
        return bool(ar.shot_clear(a, b))
    except Exception:
        return True


def _ground(state: WorldState):
    ar = state.arena
    if ar is None:
        return lambda x, y, z=None: -1e9 if z is None else min(z, state.pos[2] - 3.0)
    def g(x, y, z=None):
        try:
            return float(ar.ground_z(x, y, z))
        except Exception:
            try:
                return float(ar.height(x, y))
            except Exception:
                return -1e9
    return g


def _flip_stats(hist, t: float, window: float = 4.0):
    """(reversals per second, time of the last reversal or None, shortest gap between reversals or None)
    over the last `window` s of visible velocity samples.

    A reversal = the (speed > 2.5 m/s) velocity turned by more than ~100 deg within 1.2 s. Prior: 0.1 flips
    over a 0.5 s pseudo-window (straight-line movers stay near 0.02/s)."""
    pts = [h for h in hist if t - h[0] <= window]
    flips = []
    last = None
    for (tt, vx, vy) in pts:
        sp = math.hypot(vx, vy)
        if sp < 2.5:
            continue        # mid-reversal samples are slow: compare fast samples up to 1.2 s apart
        if last is not None:
            lt, lx, ly = last
            c = (vx * lx + vy * ly) / (sp * math.hypot(lx, ly))
            if c < -0.2 and tt - lt <= 1.2:
                flips.append(tt)
        last = (tt, vx, vy)
    span = (pts[-1][0] - pts[0][0]) if len(pts) >= 2 else 0.0
    gaps = [b - a for a, b in zip(flips, flips[1:])]
    return (len(flips) + 0.1) / (span + 0.5), (flips[-1] if flips else None), (min(gaps) if gaps else None)


def _flip_rate(hist, t: float, window: float = 4.0) -> float:
    return _flip_stats(hist, t, window)[0]


def effective_flip_rate(rate: float, since_flip: Optional[float], min_gap: Optional[float], tau: float) -> float:
    """Periodic strafers don't reverse again right after a reversal: if the whole flight ends before
    0.75 x the shortest observed gap since the last reversal, use no reversal (full lead)."""
    if since_flip is not None and min_gap is not None and since_flip + tau < 0.75 * min_gap:
        return 0.0
    return rate


def telegraph_factor(rate: float, tau: float) -> float:
    """E[displacement] / (v tau) for a velocity that reverses at Poisson rate `rate`: (1-e^{-2 r tau}) / (2 r tau)."""
    x = 2.0 * rate * tau
    if x < 1e-4:
        return 1.0
    return (1.0 - math.exp(-x)) / x


def gun_hit_p(dist: float) -> float:
    """Typical hit probability of a bot's gun at a range (house bots in the replay hit ~57% overall)."""
    if dist > 230:
        return 0.0
    return max(0.1, min(0.9, 0.95 - dist / 300.0))


def weapon_threat(kind: str, dist: float, los: bool) -> float:
    """Expected DPS from one weapon at `dist` (before cube/rear multipliers)."""
    r = RANGE.get(kind, 0.0)
    if dist > r * 1.05:
        return 0.0
    if kind == "gun":
        p = gun_hit_p(dist)
    elif kind == "laser":
        p = 0.55 if dist < 200 else 0.35
    elif kind == "lightning":
        p = 0.95
    elif kind == "mortar":
        if dist < 12:
            return 0.0
        p = 0.35 if dist < 120 else 0.2
        return BASE_DPS[kind] * p * (1.0 if los else 0.7)  # can lob over cover
    elif kind == "npc":
        p = 0.5
    else:
        p = 0.3
    return BASE_DPS.get(kind, 50.0) * p * (1.0 if los else 0.0)


def assess(state: WorldState) -> Threats:
    try:
        return _assess(state)
    except Exception:
        import traceback
        _log("assess failed:", traceback.format_exc())
        out = ThreatsX()
        try:
            for tr in state.tracks.values():
                if tr.dead or state.t - tr.last_seen_t > 5.5:
                    continue
                d = math.dist(tr.pos, state.pos)
                out.enemies.append(EnemyX(id=tr.id, kind=tr.kind, pos=tr.pos, vel=tr.vel, hp=tr.hp, max_hp=tr.max_hp,
                                          weapons=list(tr.weapons), dist=d, visible=tr.visible_now,
                                          last_seen_t=tr.last_seen_t, los=tr.visible_now))
        except Exception:
            pass
        return out


def _assess(state: WorldState) -> ThreatsX:
    mem = _mem(state)
    out = ThreatsX()
    t = state.t
    me = state.me or {}
    pos = state.pos
    vel = state.vel
    my_r = state.stat("radius", 2.5)
    my_h = state.stat("height", 9.0)
    my_center = (pos[0], pos[1], pos[2] + 0.5 * my_h)
    my_muzzle = (pos[0], pos[1], pos[2] + state.stat("muzzle_height", 7.0))
    my_aim = tuple(me.get("aim") or (0.0, 0.0))
    size_per_cube = float(state.cfg.get("cubes", {}).get("size_per_cube", 0.05))
    base_r = float(state.cfg.get("mech", {}).get("radius", 2.5))
    base_h = float(state.cfg.get("mech", {}).get("height", 9.0))
    base_muzzle = float(state.cfg.get("mech", {}).get("muzzle_height", 7.0))
    dmg_per_cube = float(state.cfg.get("cubes", {}).get("damage_per_cube", 0.04))
    cube_cap = float(state.cfg.get("cubes", {}).get("stat_cap", 10))
    rear_mult = state.stat("rear_mult", 1.5)
    armor = state.stat("armor", 0.0)

    # ---------------------------------------------------------------- events: short, damage directions
    rear_recent = False
    for ev in state.events:
        ty = ev.get("type")
        if ty == "effect" and ev.get("effect") == "short":
            mem["shorted_until"] = t + _wcfg(state, "lightning", "short_s", 2.0)
        elif ty == "damaged" and ev.get("by") is not None and ev.get("bearing") is not None:
            by = int(ev["by"])
            if ev.get("rear"):
                mem["last_rear_t"] = t
            if by < 100:
                mem["focus"].add(by)
            tr = state.tracks.get(by)
            if tr is None or not tr.visible_now:
                # unseen attacker: contact along the bearing at a range guess from the weapon
                w = ev.get("weapon", "gun")
                rng = {"lightning": 30.0, "npc": 40.0, "laser": 120.0, "mortar": 120.0}.get(w, 100.0)
                b = float(ev["bearing"])
                mem["contacts"].append(Contact(pos=(pos[0] + rng * math.cos(b), pos[1] + rng * math.sin(b), pos[2]),
                                               sigma=rng * 0.5, t=t, kind=w, id=by, source="damage"))
    out.shorted_until = mem["shorted_until"]
    if t - mem.get("last_rear_t", -1e9) < 2.0:
        rear_recent = True

    # ---------------------------------------------------------------- beams: exact shooter muzzle
    for bm in state.obs.get("beams") or []:
        try:
            by = bm.get("by")
            path = bm.get("path") or []
            if by is None or not path:
                continue
            p0 = path[0]
            tr = state.tracks.get(by)
            if tr is None or not tr.visible_now:
                mem["contacts"].append(Contact(pos=(p0[0], p0[1], p0[2] - base_muzzle), sigma=3.0, t=t - float(bm.get("age", 0)),
                                               kind=bm.get("kind", "laser"), id=int(by), source="beam"))
            # infighting evidence: beam ends near another mech, far from us
            end = path[-1]
            if math.dist(end, my_center) > 12.0:
                for o in state.tracks.values():
                    if o.id != by and o.kind == "mech" and not o.dead and t - o.last_seen_t < 1.0 \
                            and math.dist(end, (o.pos[0], o.pos[1], o.pos[2] + 4.5)) < 6.0:
                        mem["infight"] += 1.0
                        break
        except Exception:
            continue

    # ---------------------------------------------------------------- sounds -> contacts
    noise = math.radians(float(state.cfg.get("sound", {}).get("bearing_noise_deg", 7.0))) * state.stat("hearing", 1.0)
    sounds = state.obs.get("sounds") or []
    known_b = [math.atan2(tr.pos[1] - pos[1], tr.pos[0] - pos[0]) for tr in state.tracks.values()
               if not tr.dead and tr.kind == "mech" and t - tr.last_seen_t <= 5.0] if sounds else []
    tol_b = 3 * noise + 0.05
    for s in sounds[:40]:
        try:
            kind = s.get("kind")
            if kind not in ENEMY_SOUNDS:
                continue
            b = float(s.get("bearing"))
            rng = SOUND_RANGE.get(s.get("dist", "far"), 230.0)
            # attribute to a known track if one is roughly on that bearing
            if any(abs(B.wrap(tb - b)) < tol_b for tb in known_b):
                continue
            mem["contacts"].append(Contact(pos=(pos[0] + rng * math.cos(b), pos[1] + rng * math.sin(b), pos[2]),
                                           sigma=max(10.0, rng * (0.45 + noise)), t=t - float(s.get("age", 0)),
                                           kind=kind, source="sound"))
        except Exception:
            continue
    # merge/expire contacts (keep the newest per ~bearing sector)
    cs = [c for c in mem["contacts"] if t - c.t < CONTACT_TTL]
    cs.sort(key=lambda c: -c.t)
    merged: List[Contact] = []
    for c in cs:
        dup = False
        for m in merged:
            if (c.id is not None and c.id == m.id) or math.dist(c.pos[:2], m.pos[:2]) < max(15.0, 0.5 * min(c.sigma, m.sigma)):
                dup = True
                break
        if not dup:
            merged.append(c)
        if len(merged) >= 12:
            break
    mem["contacts"] = merged
    out.contacts = merged

    # ---------------------------------------------------------------- enemies
    vh = mem["vhist"]
    dmg5: Dict[int, float] = {}
    last_hit: Dict[int, float] = {}
    lo5 = t - 5.0
    for (tt, a, by, w) in state.damage_log:
        if by is not None and w != "npc":
            last_hit[by] = max(last_hit.get(by, -1e9), tt)
        if by is not None and tt >= lo5:
            dmg5[by] = dmg5.get(by, 0.0) + a
    rmode = getattr(state, "mode_guess", "unknown") or "unknown"
    passive_mult = PASSIVE_MULT.get(rmode, 0.45) if HUNTER_ON else 0.75
    aim_since = mem.setdefault("aim_since", {})
    cand = []
    for tr in state.tracks.values():
        if tr.dead:
            continue
        age = t - tr.last_seen_t
        if age > 5.5:
            continue
        cand.append((math.dist(tr.pos, pos), tr, age))
    cand.sort(key=lambda x: (x[1].kind != "mech", x[0]))   # LOS budget: mechs first, nearest first
    los_budget = MAX_LOS
    focus_on_me = 0
    for d, tr, age in cand:
        e = EnemyX(id=tr.id, kind=tr.kind, pos=tuple(tr.pos), vel=tuple(tr.vel), hp=tr.hp, max_hp=tr.max_hp,
                   weapons=list(tr.weapons or []), dist=d, visible=tr.visible_now, last_seen_t=tr.last_seen_t)
        e.age = age
        e.aim = tuple(tr.aim) if tr.aim else (0.0, 0.0)
        e.cubes = int(tr.cubes or 0)
        scale = 1.0 + size_per_cube * e.cubes
        if tr.kind == "npc":
            e.radius = float(state.cfg.get("npc", {}).get("radius", 1.8))
            e.height = float(state.cfg.get("npc", {}).get("height", 3.5))
        else:
            e.radius, e.height = base_r * scale, base_h * scale
        e.bearing = math.atan2(tr.pos[1] - pos[1], tr.pos[0] - pos[0])
        # velocity history -> reversal rate (telegraph model) -> agility
        hist = vh.setdefault(tr.id, [])
        if tr.visible_now and (not hist or hist[-1][0] < t - 1e-6):
            hist.append((t, tr.vel[0], tr.vel[1]))
            if len(hist) > 50:
                del hist[0]
        e.flip_rate, lf, e.flip_min_gap = _flip_stats(hist, t)
        e.since_flip = (t - lf) if lf is not None else None
        nair = sum(1 for h in hist[-30:] if t - h[0] <= 3.0)
        if tr.visible_now:
            air = mem.setdefault("air", {}).setdefault(tr.id, [])
            air.append((t, abs(tr.vel[2]) > 0.8))
            if len(air) > 30:
                del air[0]
            e.jumpy = sum(1 for (ta, a) in air if a and t - ta <= 3.0) / max(1, nair)
        e.agility = max(0.05, min(1.0, e.flip_rate / 2.0))
        e.lead_vel = tuple(tr.vel)
        e.airborne = abs(tr.vel[2]) > 0.8
        if tr.max_hp:
            e.hp_frac = float(tr.hp or 0) / max(1.0, float(tr.max_hp))
        e.charging = bool(tr.charging)
        cs_ = mem["charge_start"]
        if e.charging:
            cs_.setdefault(tr.id, t)
            e.charge_t = t - cs_[tr.id]
        else:
            cs_.pop(tr.id, None)
        e.holds_mortar = "mortar" in e.weapons
        # facing
        back = math.atan2(pos[1] - tr.pos[1], pos[0] - tr.pos[0])   # yaw from it to us
        off = abs(B.wrap(e.aim[0] - back))
        e.facing_me = off < max(0.25, math.atan2(my_r + 1.0, max(d, 1.0)) + 0.15)
        e.rear_exposed = tr.kind == "mech" and off > math.pi / 2 + 0.05
        if tr.kind == "mech" and e.facing_me and tr.visible_now:
            focus_on_me += 1
        if tr.kind == "mech":
            if e.facing_me and tr.visible_now:
                aim_since.setdefault(tr.id, t)
            elif tr.visible_now or age > 1.0:
                aim_since.pop(tr.id, None)
            e.last_hit_me_t = last_hit.get(tr.id, -1e9)
            e.hunter = (t - e.last_hit_me_t < HUNTER_S) or (t - aim_since.get(tr.id, t) >= AIM_HUNTER_S)
        # line of fire (symmetric approximation: our muzzle -> its center)
        if tr.visible_now and los_budget > 0 and d < 300:
            los_budget -= 1
            e.los = _shot_clear(state, my_muzzle, (tr.pos[0], tr.pos[1], tr.pos[2] + 0.5 * e.height))
        else:
            e.los = False
        # danger model
        mult = (1.0 + dmg_per_cube * min(e.cubes, cube_cap)) * (1.0 - armor)
        weps = e.weapons if tr.kind == "mech" else ["npc"]
        if tr.kind == "mech" and not weps:
            weps = ["gun"]
        dps = 0.0
        for w in weps:
            dps += weapon_threat(w, d, e.los or (age < 0.3 and d < 45))
        if tr.kind == "mech":
            dps *= mult
            if not e.facing_me and not e.hunter:
                dps *= passive_mult  # needs to turn first (<= ~0.8 s); in the practice squad most never will
            elif not e.facing_me:
                dps *= 0.75
        else:
            # drones shoot at mechs within 45 m of them or whoever attacked them
            aggro = tr.dmg_from_me > 0 or t - tr.last_hit_me_t < 3.0 or d < 45.0
            dps *= 1.0 if aggro else 0.1
        if age > 0.5:
            dps *= max(0.2, 1.0 - age / 6.0)
        if e.charging and e.facing_me and e.los and "laser" in weps:
            dps += 150.0
        if tr.kind == "mech" and not e.los and age < 3.0:
            # no line of fire right now, but it can peek around the corner any moment
            latent = 0.2 * sum(weapon_threat(w, d, True) for w in weps) * mult
            dps = max(dps, latent)
        e.model_dps = dps
        # observed damage per second on us
        obs_dmg = dmg5.get(tr.id, 0.0)
        e.dps_on_me = obs_dmg / 5.0
        e.danger = max(dps, e.dps_on_me * 1.2)
        rng_max = max((RANGE.get(w, 0.0) for w in weps), default=0.0)
        e.can_hit_me = (e.los or ("mortar" in weps and age < 5.0)) and d <= rng_max
        if tr.kind == "mech" and e.can_hit_me:
            out.n_can_hit += 1
        out.enemies.append(e)
        # beam risk
        if e.charging and e.facing_me and e.los:
            out.beam_risk = True
            side = (-math.sin(back), math.cos(back))
            # dodge across its aim line, the side we already move to
            sgn = 1.0 if (vel[0] * side[0] + vel[1] * side[1]) >= 0 else -1.0
            out.incoming.append(ProjectileRisk(id=tr.id, kind="laser", t_impact=max(0.0, 0.65 - e.charge_t),
                                               miss_dist=0.0, dodge=(sgn * side[0], sgn * side[1])))

    # attackers: ids that hit us in the last 3 s
    out.attackers = sorted({int(by) for (tt, a, by, w) in state.damage_log if by is not None and tt >= t - 3.0})
    out.hunters = sorted({e.id for e in out.enemies if e.kind == "mech" and e.hunter} |
                         {int(by) for by, tt in last_hit.items() if t - tt < HUNTER_S and by < 100})
    # hit by a mech we cannot see right now (behind us, beyond near range): remember the bearing
    vis_ids = {e.id for e in out.enemies if e.visible}
    for (tt, a, by, w) in reversed(state.damage_log):
        if tt < t - 2.0:
            break
        if by is not None and w not in ("zone", "npc") and by not in vis_ids:
            for c in mem["contacts"]:
                if c.id == by and c.source == "damage":
                    out.unseen_attack = (math.atan2(c.pos[1] - pos[1], c.pos[0] - pos[0]), tt, int(by))
                    break
            if out.unseen_attack is not None:
                break

    # ---------------------------------------------------------------- incoming projectiles
    g_mortar = _wcfg(state, "mortar", "gravity", 22.0)
    splash_r = _wcfg(state, "mortar", "splash_radius", 7.0)
    splash = _wcfg(state, "mortar", "splash", 160.0)
    direct = _wcfg(state, "mortar", "damage", 200.0)
    gun_dmg = _wcfg(state, "gun", "damage", 45.0)
    npc_dmg = float(state.cfg.get("npc", {}).get("damage", 25.0))
    ground = _ground(state)
    dodge_x = dodge_y = 0.0
    sh_x = sh_y = sh_u = 0.0
    urg = 0.0
    inc_dmg = 0.0
    walk = max(1.0, state.stat("walk_speed", 11.7))
    n_shell = 0
    for pr in state.obs.get("projectiles") or []:
        try:
            p = pr["pos"]
            v = pr["vel"]
            kind = pr.get("kind", "gun")
            if kind == "mortar":
                n_shell += 1
                if n_shell > 4:
                    continue
                # a shell's path is fixed once fired: integrate it once, keep the absolute impact time
                sc = mem.setdefault("shell_cache", {})
                pid_ = pr.get("id")
                hit_c = sc.get(pid_)
                if hit_c is None:
                    ip, ti = B.ballistic_impact(p, v, g_mortar, ground, tmax=7.0, dt=0.05)
                    sc[pid_] = (ip, t + ti)
                    if len(sc) > 64:
                        for k_ in list(sc)[:32]:
                            del sc[k_]
                else:
                    ip, ti = hit_c[0], max(0.0, hit_c[1] - t)
                # where will we be at impact if we keep moving
                fut = (pos[0] + vel[0] * ti, pos[1] + vel[1] * ti)
                dd = math.hypot(ip[0] - fut[0], ip[1] - fut[1])
                dz = abs(ip[2] - pos[2])
                reach = splash_r + my_r
                if dd < reach + 2.0 and dz < splash_r + my_h:
                    away = B.dir_to_aim((fut[0] - ip[0], fut[1] - ip[1], 0.0))[0] if dd > 0.3 else \
                        math.atan2(vel[1], vel[0]) if math.hypot(vel[0], vel[1]) > 1 else math.atan2(-v[1], -v[0])
                    dvec = (math.cos(away), math.sin(away))
                    need = max(0.0, reach + 1.0 - dd) / walk + 0.15
                    u = min(1.0, need / max(0.05, ti))
                    exp = (direct if dd < my_r else 0.0) + B.splash_damage(max(0.0, dd - my_r), splash, splash_r, 0.3)
                    out.incoming.append(ProjectileRisk(id=int(pr.get("id", -1)), kind="mortar", t_impact=ti,
                                                       miss_dist=dd, dodge=dvec))
                    w = max(0.2, u)
                    dodge_x += dvec[0] * w
                    dodge_y += dvec[1] * w
                    sh_x += dvec[0] * w
                    sh_y += dvec[1] * w
                    sh_u = max(sh_u, u)
                    urg = max(urg, u)
                    inc_dmg += exp
            else:
                # straight bullet relative to our (constant-velocity) body
                rel_v = (v[0] - vel[0], v[1] - vel[1], v[2] - vel[2])
                sp = math.sqrt(rel_v[0] ** 2 + rel_v[1] ** 2 + rel_v[2] ** 2)
                if sp < 1.0:
                    continue
                u3 = (rel_v[0] / sp, rel_v[1] / sp, rel_v[2] / sp)
                miss, dz = B.ray_cylinder_miss(p, u3, pos, my_h)
                # time to closest horizontal approach
                hh = u3[0] ** 2 + u3[1] ** 2
                s = ((pos[0] - p[0]) * u3[0] + (pos[1] - p[1]) * u3[1]) / max(1e-9, hh)
                if s <= 0:
                    continue
                ti = s / sp
                if ti > 2.5:
                    continue
                if miss < my_r + 0.3 + 1.2 and dz < 1.0:
                    # dodge perpendicular to its horizontal path, to the side that grows the miss
                    hx, hy = u3[0], u3[1]
                    n = math.hypot(hx, hy) or 1.0
                    px_, py_ = -hy / n, hx / n
                    cx = p[0] + u3[0] * s - pos[0]
                    cy = p[1] + u3[1] * s - pos[1]
                    side = -(cx * px_ + cy * py_)  # point away from where the ray passes
                    if abs(side) < 0.2:
                        side = vel[0] * px_ + vel[1] * py_ or 1.0
                    sg = 1.0 if side > 0 else -1.0
                    dvec = (sg * px_, sg * py_)
                    need = (my_r + 0.4 - miss) / walk
                    u = min(1.0, max(0.1, need / max(0.05, ti)))
                    out.incoming.append(ProjectileRisk(id=int(pr.get("id", -1)), kind=kind, t_impact=ti,
                                                       miss_dist=miss, dodge=dvec))
                    w = 0.5 * u
                    dodge_x += dvec[0] * w
                    dodge_y += dvec[1] * w
                    urg = max(urg, 0.5 * u)
                    if miss < my_r + 0.3:
                        inc_dmg += npc_dmg if kind == "npc" else gun_dmg
        except Exception:
            continue
    for r in out.incoming:
        if r.kind == "laser":
            dodge_x += r.dodge[0] * 0.3
            dodge_y += r.dodge[1] * 0.3
            urg = max(urg, 0.3)
    nd = math.hypot(dodge_x, dodge_y)
    if nd > 1e-6 and urg > 0:
        out.dodge = (dodge_x / nd, dodge_y / nd)
        out.dodge_urgency = urg
    out.incoming_damage = inc_dmg
    ns = math.hypot(sh_x, sh_y)
    if ns > 1e-6 and sh_u > 0:
        out.dodge_shell = (sh_x / ns, sh_y / ns)
        out.shell_urgency = sh_u

    # ---------------------------------------------------------------- aggregate
    mechs = [e for e in out.enemies if e.kind == "mech"]
    out.total_danger = sum(e.danger for e in out.enemies)
    # contacts count a bit (unseen shooters)
    for c in out.contacts:
        if c.source in ("damage", "beam") and t - c.t < 3.0:
            out.total_danger += 40.0
    # face: weighted circular mean of the top dangers if they fit in a ~150 deg arc, else the worst
    dz_ = sorted((e for e in out.enemies if e.danger > 1.0), key=lambda e: -e.danger)[:4]
    if dz_:
        worst = dz_[0]
        sx = sy = 0.0
        for e in dz_:
            if abs(B.wrap(e.bearing - worst.bearing)) < math.radians(75):
                sx += e.danger * math.cos(e.bearing)
                sy += e.danger * math.sin(e.bearing)
        out.face_yaw = math.atan2(sy, sx) if (sx or sy) else worst.bearing
    else:
        recent = [c for c in out.contacts if c.source in ("damage", "beam") and t - c.t < 3.0]
        if recent:
            c = recent[0]
            out.face_yaw = math.atan2(c.pos[1] - pos[1], c.pos[0] - pos[0])
    if HUNTER_ON and out.unseen_attack is not None:
        ua_b, ua_t, ua_by = out.unseen_attack
        ua_dps = dmg5.get(ua_by, 0.0) / 5.0 * 1.2
        top = max((e.danger for e in out.enemies if e.visible and e.hunter), default=0.0)
        if ua_dps >= 0.8 * top:
            out.face_yaw = ua_b
    if out.face_yaw is not None:
        out.rear_threat = rear_recent or abs(B.wrap(out.face_yaw - my_aim[0])) > math.pi / 2
    else:
        out.rear_threat = rear_recent

    # killable: what we can deal in ~3 s with what we hold vs its HP
    burst = _my_burst(state, 3.0)
    for e in mechs:
        if e.hp is None or e.age > 2.0:
            continue
        hp = float(e.hp)
        mult = rear_mult if e.rear_exposed else 1.0
        if hp <= burst * mult * (0.9 if e.dist < 120 else 0.6) or e.hp_frac < 0.2:
            out.killable.append(e.id)

    # safe directions (16): avoid heading toward danger, prefer directly away
    dirs = []
    for k in range(16):
        yaw = -math.pi + k * (2 * math.pi / 16)
        cx, cy = math.cos(yaw), math.sin(yaw)
        sc = 0.0
        for e in out.enemies:
            if e.danger <= 0.5:
                continue
            bx, by_ = math.cos(e.bearing), math.sin(e.bearing)
            c = cx * bx + cy * by_   # +1 = straight at it
            sc -= e.danger * (c + 0.3 * max(0.0, c)) / max(1.0, e.dist / 60.0)
        for c_ in out.contacts:
            if t - c_.t > 3.0:
                continue
            b = math.atan2(c_.pos[1] - pos[1], c_.pos[0] - pos[0])
            sc -= 20.0 * (cx * math.cos(b) + cy * math.sin(b))
        dirs.append((yaw, sc))
    dirs.sort(key=lambda x: -x[1])
    out.safe_dirs = dirs

    # ---------------------------------------------------------------- squad / ffa guess
    my_kills = state.kills
    other_deaths = max(0, 16 - int(state.alive) - my_kills - 0)
    ev = state.mode_evidence if isinstance(getattr(state, "mode_evidence", None), dict) else {}
    # HP drops of visible enemies we did not cause (and not zone: inside the current circle)
    hs = mem["hp_seen"]
    hit_now = {int(e_.get("target")) for e_ in state.events if e_.get("type") == "hit" and e_.get("target") is not None}
    zc, zr = state.zone_circle_at(t) if state.zone else ((0.0, 0.0), 1e9)
    for e in mechs:
        if not e.visible or e.hp is None:
            continue
        prev = hs.get(e.id)
        hs[e.id] = float(e.hp)
        if prev is not None and float(e.hp) < prev - 1.0 and e.id not in hit_now:
            if math.hypot(e.pos[0] - zc[0], e.pos[1] - zc[1]) < zr - 5:
                mem["infight"] += 0.5
    mem["focus_now"] = focus_on_me
    infight = mem["infight"] + (2.0 * other_deaths if t < 300 else 0.0)
    if infight >= 2.0:
        guess = "ffa"
    elif t > 60 and infight < 0.75:
        guess = "squad"
    else:
        guess = "unknown"
    out.mode_guess = guess
    out.squad_evidence = {"infight": infight, "other_deaths": float(other_deaths), "attackers_total": float(len(mem["focus"])),
                          "focus_now": float(focus_on_me)}
    try:
        if isinstance(ev, dict):
            ev["infighting"] = infight
            ev["focus_on_me"] = float(len(mem["focus"]))
    except Exception:
        pass
    return out


def _my_burst(state: WorldState, secs: float) -> float:
    """Rough damage we can deal in `secs` with current weapons (hit rate ~0.6)."""
    mult = 1.0 + float(state.cfg.get("cubes", {}).get("damage_per_cube", 0.04)) * min(int(state.me.get("cubes", 0) or 0), 10)
    tot = 0.0
    for w in state.me.get("weapons") or []:
        if not w:
            continue
        k = w.get("kind")
        st = w.get("stats") or {}
        if k == "gun":
            shots = min(float(w.get("ammo", 12) or 0), secs / max(0.1, float(st.get("cooldown", 0.24))))
            tot += 0.6 * shots * float(st.get("damage", 45))
        elif k == "laser":
            tot += 0.8 * float(st.get("damage", 315)) * (1 if secs < 2.5 else 2)
        elif k == "lightning":
            tot += 0.9 * float(st.get("damage", 60)) * min(secs / 0.25, float(state.energy) / max(1.0, float(st.get("energy", 3))))
        elif k == "mortar":
            tot += 0.3 * (float(st.get("damage", 200)) + float(st.get("splash", 160)))
    return tot * mult
