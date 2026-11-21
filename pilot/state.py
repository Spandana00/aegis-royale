"""Shared world-state and interface types. Owned by the integrator (brain/main).

Every module codes against the types in this file. Fields may be ADDED; existing fields keep their
names and meaning (see docs/INTERFACES.md). Standard library only.

Conventions: meters, seconds, radians; x east, y north, z up; yaw CCW from +x; positions are feet.
Vectors are plain tuples/lists of floats.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

Vec2 = Tuple[float, float]
Vec3 = Tuple[float, float, float]

MODES = ("rotate", "loot", "engage", "retreat", "heal", "hold", "capture")


# ----------------------------------------------------------------------------- module outputs
@dataclass
class Intent:
    """What the brain wants this decision. Produced by brain.choose_intent, read by navigate + combat."""
    mode: str = "rotate"                 # one of MODES
    goal: Optional[Vec3] = None          # where to go (feet position); None = stay / nav decides
    target_id: Optional[int] = None      # preferred enemy (mech or npc id) to shoot, or None
    desired_range: Optional[float] = None  # engage: preferred distance to target_id (m)
    urgency: float = 0.0                 # 0 relaxed .. 1 life-or-death (nav may boost/jet when high)
    face: Optional[float] = None         # yaw the torso should favour when not shooting (front-arc armor)
    allow_fire: bool = True              # False = do not shoot (healing: dealing damage resets regen)
    allow_boost: bool = True             # False = conserve energy
    avoid: List[Vec3] = field(default_factory=list)  # positions to keep away from (threat centroids)
    loot_id: Optional[int] = None        # pickup/cube/crate/drop id the goal refers to, if any
    shoot_crate: Optional[int] = None    # crate id combat may shoot when no enemy to fight
    arrive_by: Optional[float] = None    # match time t by which goal must be reached (zone)
    reason: str = ""                     # short debug text
    max_speed: Optional[float] = None    # cap ground speed (m/s); < sound.step_speed (5) = silent movement
    spare_ids: List[int] = field(default_factory=list)  # mechs combat must not shoot (squad: passive house bots)


@dataclass
class NavOut:
    """navigate.step output: the only source of move/boost/jump."""
    move: Vec2 = (0.0, 0.0)
    boost: bool = False
    jump: bool = False
    eta: Optional[float] = None          # seconds to intent.goal along the planned path (None = unknown)
    blocked: bool = False                # nav thinks it is stuck / cannot make progress


@dataclass
class CombatOut:
    """combat.step output: the only source of aim/fire/reload."""
    aim: Optional[Vec2] = None           # [yaw, pitch]; None = keep previous commanded aim
    fire: Tuple[bool, bool] = (False, False)
    reload: bool = False
    target_id: Optional[int] = None      # who combat actually aimed at (for logging)


@dataclass
class InvOut:
    """brain.inventory output: the only source of pick/take/drop."""
    pick: Optional[int] = None
    take: Optional[int] = None
    drop: Optional[int] = None


# ----------------------------------------------------------------------------- threats (combat fills)
@dataclass
class EnemyThreat:
    id: int
    kind: str                            # "mech" | "npc"
    pos: Vec3
    vel: Vec3
    hp: Optional[float]
    max_hp: Optional[float]
    weapons: List[str]
    dist: float                          # horizontal-ish 3D distance from self
    visible: bool                        # in obs.mechs this tick (includes 5 s memory tracking)
    last_seen_t: float
    los: bool = False                    # we have shot line-of-sight right now (muzzle->center)
    can_hit_me: bool = False             # it plausibly has a line of fire on us with a weapon in range
    facing_me: bool = False              # its torso aim points at us (within ~25 deg)
    charging: bool = False               # laser charging
    danger: float = 0.0                  # combat's per-enemy danger score (bigger = worse), roughly DPS on us
    dps_on_me: float = 0.0               # recent observed damage per second from this id


@dataclass
class ProjectileRisk:
    id: int
    kind: str
    t_impact: float                      # seconds to closest approach
    miss_dist: float                     # predicted closest distance to our body axis (m)
    dodge: Vec2 = (0.0, 0.0)             # unit horizontal direction that best increases miss distance


@dataclass
class Threats:
    enemies: List[EnemyThreat] = field(default_factory=list)       # mechs AND npcs we track
    incoming: List[ProjectileRisk] = field(default_factory=list)   # projectiles that will hit if we stand still
    dodge: Optional[Vec2] = None          # suggested evasive move (unit), or None
    attackers: List[int] = field(default_factory=list)  # ids that damaged us in the last ~3 s
    total_danger: float = 0.0
    beam_risk: bool = False               # a visible laser is charging at us

    def by_id(self, i: int) -> Optional[EnemyThreat]:
        for e in self.enemies:
            if e.id == i:
                return e
        return None

    def mechs(self) -> List[EnemyThreat]:
        return [e for e in self.enemies if e.kind == "mech"]


# ----------------------------------------------------------------------------- persistent memory
@dataclass
class Track:
    """Memory of one mech/npc across ticks (state.py maintains it; anyone may read it)."""
    id: int
    kind: str
    pos: Vec3
    vel: Vec3
    last_seen_t: float
    first_seen_t: float
    hp: Optional[float] = None
    max_hp: Optional[float] = None
    cubes: int = 0
    weapons: List[str] = field(default_factory=list)
    aim: Vec2 = (0.0, 0.0)
    charging: bool = False
    visible_now: bool = False
    dmg_to_me: float = 0.0               # cumulative damage it did to us
    dmg_from_me: float = 0.0             # cumulative damage we did to it
    last_hit_me_t: float = -1e9
    aimed_at_me_ticks: int = 0           # count of ticks it was seen aiming at us
    shot_others: int = 0                 # evidence it fights someone other than us (FFA signal)
    dead: bool = False


class WorldState:
    """Everything the bot knows. Built once on hello, updated once per obs by main (state.update)."""

    def __init__(self, hello: Dict[str, Any], arena: Any = None):
        self.hello = hello
        self.cfg: Dict[str, Any] = hello.get("config", {})
        self.slot: int = int(hello.get("slot", 0))
        self.seed: int = int(hello.get("seed", 0))
        self.arena = arena                   # bot.arena.Arena or None if it failed to load
        self.obs: Dict[str, Any] = {}
        self.tick: int = 0
        self.t: float = 0.0
        self.dt: float = 0.1
        self.alive: int = 16
        self.me: Dict[str, Any] = {}
        self.pos: Vec3 = (0.0, 0.0, 0.0)
        self.vel: Vec3 = (0.0, 0.0, 0.0)
        self.hp: float = 1400.0
        self.max_hp: float = 1400.0
        self.energy: float = 100.0
        self.tracks: Dict[int, Track] = {}
        self.events: List[Dict[str, Any]] = []       # this tick's events
        self.damage_log: List[Tuple[float, float, Optional[int], str]] = []  # (t, amount, by, weapon), last 30 s
        self.last_combat_t: float = -1e9      # last time we dealt or took (non-zone) damage -> regen timer
        self.last_zone_dmg_t: float = -1e9
        self.kills: int = 0
        self.prev_action: Dict[str, Any] = {}
        self.prev_intent: Optional[Intent] = None
        self.n_obs: int = 0
        self.missed_ticks: int = 0            # gaps in tick sequence (we were late / skipped)
        # round detection (squad vs ffa) -- brain maintains
        self.mode_guess: str = "unknown"      # "squad" | "ffa" | "unknown"
        self.mode_evidence: Dict[str, float] = {"focus_on_me": 0.0, "infighting": 0.0}
        self.scratch: Dict[str, Any] = {}     # free-form per-module memory: use your module name as key

    # ------------------------------------------------------------------ update
    def update(self, obs: Dict[str, Any]) -> None:
        prev_tick = self.tick
        self.obs = obs
        self.tick = int(obs.get("tick", 0))
        if self.n_obs and self.tick - prev_tick > 2:
            self.missed_ticks += (self.tick - prev_tick) // 2 - 1
        t = float(obs.get("t", self.tick / 20.0))
        self.dt = max(0.05, t - self.t) if self.n_obs else 0.1
        self.t = t
        self.n_obs += 1
        self.alive = int(obs.get("alive", self.alive))
        me = obs.get("self") or {}
        self.me = me
        self.pos = tuple(me.get("pos", self.pos))  # type: ignore[assignment]
        self.vel = tuple(me.get("vel", self.vel))  # type: ignore[assignment]
        self.hp = float(me.get("hp", self.hp))
        self.max_hp = float(me.get("max_hp", self.max_hp))
        self.energy = float(me.get("energy", self.energy))
        self.events = list(obs.get("events") or [])

        seen = set()
        for m in obs.get("mechs") or []:
            i = m.get("id")
            if i is None:
                continue
            seen.add(i)
            tr = self.tracks.get(i)
            pos = tuple(m.get("pos", (0, 0, 0)))
            vel = tuple(m.get("vel", (0, 0, 0)))
            if tr is None:
                tr = Track(id=i, kind=m.get("kind", "mech"), pos=pos, vel=vel, last_seen_t=t, first_seen_t=t)  # type: ignore[arg-type]
                self.tracks[i] = tr
            tr.pos, tr.vel, tr.last_seen_t, tr.visible_now = pos, vel, t, True  # type: ignore[assignment]
            tr.dead = False
            if "hp" in m:
                tr.hp = m.get("hp")
                tr.max_hp = m.get("max_hp", tr.max_hp)
            if "cubes" in m:
                tr.cubes = int(m.get("cubes") or 0)
            if "weapons" in m:
                tr.weapons = list(m.get("weapons") or [])
            if "aim" in m:
                tr.aim = tuple(m["aim"])  # type: ignore[assignment]
                if tr.kind == "mech" and self._aims_at_me(tr):
                    tr.aimed_at_me_ticks += 1
            tr.charging = bool(m.get("charging", False))
        for i, tr in self.tracks.items():
            if i not in seen:
                tr.visible_now = False

        for ev in self.events:
            ty = ev.get("type")
            if ty == "damaged":
                by = ev.get("by")
                w = ev.get("weapon", "")
                amt = float(ev.get("amount", 0))
                self.damage_log.append((t, amt, by, w))
                if w == "zone" or by is None:
                    self.last_zone_dmg_t = t
                    self.last_combat_t = max(self.last_combat_t, t)  # zone also resets regen timer
                else:
                    self.last_combat_t = t
                    tr = self.tracks.get(by)
                    if tr is not None:
                        tr.dmg_to_me += amt
                        tr.last_hit_me_t = t
            elif ty == "hit":
                self.last_combat_t = t
                tr = self.tracks.get(ev.get("target"))
                if tr is not None:
                    tr.dmg_from_me += float(ev.get("amount", 0))
            elif ty == "kill":
                self.kills += 1
                tr = self.tracks.get(ev.get("target"))
                if tr is not None:
                    tr.dead = True
        if self.damage_log and self.damage_log[0][0] < t - 30:
            self.damage_log = [d for d in self.damage_log if d[0] >= t - 30]
        # forget long-unseen tracks' liveness is unknowable; keep them but brain treats old ones as stale

    def _aims_at_me(self, tr: Track) -> bool:
        dx, dy = self.pos[0] - tr.pos[0], self.pos[1] - tr.pos[1]
        if dx * dx + dy * dy < 1e-6:
            return False
        return abs(ang_diff(math.atan2(dy, dx), tr.aim[0])) < 0.3

    # ------------------------------------------------------------------ helpers anyone may use
    @property
    def zone(self) -> Dict[str, Any]:
        return self.obs.get("zone") or {}

    def weapon(self, slot: int) -> Optional[Dict[str, Any]]:
        ws = self.me.get("weapons") or [None, None]
        return ws[slot] if slot < len(ws) else None

    def weapon_kinds(self) -> List[Optional[str]]:
        return [(w or {}).get("kind") if w else None for w in (self.me.get("weapons") or [None, None])]

    def stat(self, name: str, default: float = 0.0) -> float:
        s = self.me.get("stats") or {}
        if name in s:
            return float(s[name])
        return float(self.cfg.get("mech", {}).get(name, default))

    def regen_in(self) -> float:
        """Seconds until passive regen starts (0 = regenerating now if inside the zone)."""
        return max(0.0, self.stat("regen_delay", 5.0) - (self.t - self.last_combat_t))

    def recent_damage(self, window: float = 3.0, include_zone: bool = False) -> float:
        lo = self.t - window
        return sum(a for (tt, a, by, w) in self.damage_log if tt >= lo and (include_zone or w != "zone"))

    def zone_circle_at(self, t: float) -> Tuple[Vec2, float]:
        """Safe circle (center, radius) at match time t, from the current obs.zone (current phase only)."""
        z = self.zone
        if not z:
            return (0.0, 0.0), 1e9
        c0, r0 = z["center"], float(z["radius"])
        c1, r1 = z["next_center"], float(z["next_radius"])
        s0, s1 = float(z["shrink_start"]), float(z["shrink_end"])
        if t <= s0:
            return (c0[0], c0[1]), r0
        if t >= s1 or s1 <= s0:
            return (c1[0], c1[1]), r1
        f = (t - s0) / (s1 - s0)
        return (c0[0] + (c1[0] - c0[0]) * f, c0[1] + (c1[1] - c0[1]) * f), r0 + (r1 - r0) * f

    def track_age(self, i: int) -> float:
        tr = self.tracks.get(i)
        return 1e9 if tr is None else self.t - tr.last_seen_t


# ----------------------------------------------------------------------------- small math helpers
def ang_diff(a: float, b: float) -> float:
    """Signed smallest difference a-b in (-pi, pi]."""
    d = (a - b + math.pi) % (2 * math.pi) - math.pi
    return d


def dist2d(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def dist3d(a, b) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def unit2(x: float, y: float) -> Vec2:
    n = math.hypot(x, y)
    return (x / n, y / n) if n > 1e-9 else (0.0, 0.0)


def yaw_to(a, b) -> float:
    return math.atan2(b[1] - a[1], b[0] - a[0])
