"""Objectives, intent, inventory and upgrades. OWNER: integrator.

choose_intent(state, threats) -> Intent decides WHAT to do; navigate/combat decide HOW.

Priorities (highest first):
  1. zone: always know the time needed to reach the next safe circle by a real path; leave with margin.
  2. survive the current fight: fight back when the duel is favourable, otherwise retreat to cover / toward safety.
  3. heal: 45 HP/s regen after 5 s without dealing or taking damage -> break line of sight and stop shooting.
  4. take fights worth taking: squad round = every kill is +1 place, so fight isolated attackers decisively;
     FFA = avoid even fights, third-party weakened bots, finish low-HP targets.
  5. scale: secondary weapon, drones (2 cubes), crates (1 cube + 50% weapon), supply drops (3 cubes + full heal).
  6. hold: sit inside the next circle near its centre, facing the likeliest threat.

Round detection (squad vs FFA) is online: mechs dying without our kills and beams/fights not aimed at us => FFA;
many distinct attackers focusing us with no infighting => squad.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from .state import EnemyThreat, Intent, InvOut, Threats, WorldState, ang_diff, dist2d, dist3d, unit2, yaw_to

# ----------------------------------------------------------------------------- tunables (eval may override)
P: Dict[str, Any] = {
    "zone_buffer_s": 6.0,          # leave this much spare time when rotating
    "zone_path_factor": 1.25,      # path length / straight distance fudge when no planner
    "zone_margin_frac": 0.25,      # aim this deep into the next circle (fraction of its radius)
    "zone_margin_max": 35.0,
    "heal_below": 0.55,            # start a heal cycle below this HP fraction (when no fight)
    "heal_below_squad": 0.55,      # same in squad rounds (A/B: heal more often between kills)
    "retreat_needs_cover": False,  # A/B: without reachable cover (< 45 m) keep fighting instead of fleeing
    "no_cover_fight_ratio": 4.0,   # ...unless clearly hopeless (TTK ratio above this)
    "hunter_retreat": 0.0,         # A/B >0: non-FFA, >=2 hunters in sight within 160 m: break contact unless the
                                   # target's HP fraction is below this (finish it first)
    "multi_retreat": 0.0,          # >0: with >=2 attackers on us, retreat unless target HP frac < this
    "heal_until": 0.92,
    "retreat_ratio": 0.8,          # retreat if my TTK on them > ratio * their TTK on me
    "engage_ratio_squad": 1.1,     # in squad mode take fights that are roughly even (kills are the score)
    "engage_ratio_ffa": 0.6,       # in FFA only clearly favourable fights
    "loot_max_dist": 160.0,
    "loot_max_dist_weapon": 260.0,  # empty slot 1: travel further for a weapon
    "roof_weapon_dz": 25.0,
    "weapon_first_value": 60.0,
    "use_zone_field": True,        # A/B: nav's travel-time field in zone ETAs
    "drone_min_hp_frac": 0.6,
    "crate_min_hp_frac": 0.5,
    "memory_item_s": 90.0,
    "hunter_model": True,          # squad diagnosis: fight maths count hunters only (non-FFA); hunters first
    "hunter_pref": 0.6,            # ratio multiplier for targets that are hunting us (only once we hold a secondary)
    "weapon_first": True,          # squad diagnosis: 9/64 matches never found a secondary (mean 1.8 pts vs 3.8/4.4)
    "crate_value_unarmed": 45.0,   # a crate is a 50% weapon roll while slot 1 is empty
    "explore_cell": 60.0,          # exploration grid (m) while unarmed and no pickup is known
    "run_for_weapon_m": 140.0,
    "run_for_weapon_cap_s": 0.0,   # A/B >0: give up a run for a weapon under fire after this long (sim seed 20: 12 s run
                                   # onto a roof under fire from one easy bot, 1355 -> 275 HP, weapon never reached)
    "opp_min_hp": 0.6,             # start a fight with a mech that is not shooting us only above this HP fraction
    "opp_min_hp_squad": 0.6,       # ...in squad/unknown rounds (A/B 0.85: start every new fight healthy)
    "heal_after_kill": False,
    "conveyor": False,             # A/B: squad/unknown rounds: fight only hunters (mechs shooting us), spare passive
                                   # house bots unless nearly dead. Every kill adds one hunter, so killing passives while
                                   # hunters live stacks shooters (the 3-7-attacker deaths); hunters-only = a chain of 1v1s
    "conveyor_until": 300.0,       # ...until this match time (late game: everyone engages anyway)
    "cube_greed": False,           # A/B: squad: grab cubes (kill drops) within cube_grab_m before a new fight unless a
                                   # hunter is shooting; loot is devalued only near hunters; cube value cube_value_greed
    "cube_grab_m": 35.0,
    "cube_value_greed": 50.0,
    "squad_picky": False,          # A/B: squad rounds use the FFA opportunity rule (no other mech within 150 m unless
                                   # the target is busy); good-3 mostly stayed in "unknown" (picky) mode and scored 4.88
    "crate_value": 18.0,           # crate = 1 cube (+50 % weapon roll)
    "drone_value": 45.0,           # drone = 2 cubes
    "drop_max_eta": 45.0,          # supply drop = 3 cubes + full HP + full energy
    "drop_base": 30.0,
    "laser_first": False,          # A/B: laser valued above lightning (6/8 real top-4 finishers ended with a laser)
    "no_mortar": False,            # A/B: never take a mortar (sim: gun+mortar matches score ~2.8 vs ~6 with a laser)
    "drop_first": False,           # A/B: consider the supply drop before heal-hiding and opportunistic fights
    "explore_armed_until": 0.0,    # A/B: keep exploring unvisited ground for crates/drones while armed until this time
    "explore_for_laser_until": 0.0,  # A/B: armed but no laser yet: keep exploring for one until this match time
    "laser_standoff": 0.0,         # A/B >0: holding a laser, fight mechs from this range even with lightning (house
                                   # gunners hit 37-88 % inside 80 m, 20-34 % beyond; the laser is hitscan to 280 m)
    "jet_cap": 40.0,               # nav3 only: max planned jet climb (m); 0 = ground-only routes
    "hopfix3": False,              # nav3 only: good-4's stale jet-hop state fix
    "combat_hop": False,           # nav3 only: periodic jump + jet hops while fighting
    "strafe_mode": "normal",       # nav3 only: engage strafe reversals: normal 1.2-2.4 s, juke 0.3-1.0 s (>80 m), steady 3-5 s
    "nav3": False,                 # A/B: use the frozen good-3 navigation module (bot/navigate3.py)
    "hop_legacy": False,           # A/B: navigate uses good-3's jet-hop energy rules (read by navigate._hop_legacy)
    "berserk": False,              # A/B: squad/unknown rounds: never retreat from a fight (90 % of deaths came in
                                   # retreat mode; points are kills, so trade to the end on the best target)
    "berserk_max_ratio": 4.0,      # ...but still retreat from hopeless fights (TTK ratio above this)
    "hide": False,                 # A/B survival-first: squad/unknown rounds, no fight on us: break line of sight from
                                   # every visible house bot (shared vision is how the squad finds us), never hunt
    "perch": False,                # A/B: hold on a tall roof (10-35 m above the terrain) inside the next circle instead of
                                   # on the ground (ground-only routes cost -0.29 officially; roofs make pursuers jet up)
    "hide_until": 1e9,             # hybrid: hide only before this match time...
    "hide_alive_min": 0,           # ...and while more than this many mechs are alive
    "seek": False,                 # A/B: squad/unknown: with a secondary and healthy, walk to the nearest remembered
                                   # house bot instead of holding (more kills before the hunters stack up)
    "seek_min_hp": 0.8,
    "seek_sound": False,           # A/B: no remembered house bot: walk toward recent gunfire/laser sounds
    "seek_sound_m": 110.0,
    "seek_max_m": 260.0,
    "seek_mem_s": 30.0,
    "squad_standoff": 0.0,         # A/B >0: vs gun/mortar mechs in squad rounds hold this range with gun/laser
                                   # (sim: house gunners hit 37-88% inside 80 m, 20-34% beyond; our led shots drop less)      # A/B: after a kill below opp_min_hp_squad, break LOS and heal before anything else     # under fire without a secondary: run to a known weapon this close instead of fleeing
}


# Named variants for official A/B runs. The submitted image has no env, so a tag selects its variant by changing
# DEFAULT_PROFILE (one line). MECH_PROFILE=<name> overrides it locally; MECH_BRAIN then overrides single tunables.
DEFAULT_PROFILE = "laser+nav3x+fixx+steadyx"
PROFILES: Dict[str, Dict[str, Any]] = {
    "base": {},
    "greed": {"cube_greed": True},
    "seek": {"cube_greed": True, "seek": True},                       # hunt the next house bot instead of holding
    "hret": {"cube_greed": True, "hunter_retreat": 0.3},              # break contact when a 2nd hunter is in sight
    "picky": {"cube_greed": True, "squad_picky": True, "engage_ratio_squad": 0.6},  # unknown-mode fight rules in squad
    "scale": {"cube_greed": True, "crate_value": 32.0, "drone_value": 60.0, "drop_max_eta": 70.0, "drop_base": 60.0,
              "drop_first": True},                                       # cubes / drops / crates for scaling
    "laser": {"cube_greed": True, "laser_first": True},                  # prefer a laser as the first secondary
    "stack": {"cube_greed": True, "seek": True, "seek_min_hp": 0.85, "heal_after_kill": True, "opp_min_hp_squad": 0.85},   # seek + fresh
    "stack2": {"cube_greed": True, "seek": True, "seek_min_hp": 0.85, "heal_after_kill": True, "opp_min_hp_squad": 0.85, "crate_value": 32.0,
               "drone_value": 60.0, "drop_max_eta": 70.0, "drop_base": 60.0, "drop_first": True},  # seek + fresh + scale
    "farm": {"cube_greed": True, "crate_value": 32.0, "drone_value": 60.0, "explore_armed_until": 150.0, "seek": True},
    "lseek": {"cube_greed": True, "seek": True, "laser_first": True, "no_mortar": True},   # good-7 + laser2
    "lhunt": {"cube_greed": True, "seek": True, "laser_first": True, "no_mortar": True, "explore_for_laser_until": 120.0},
    "lstand": {"cube_greed": True, "seek": True, "laser_first": True, "no_mortar": True, "laser_standoff": 120.0},
    "hopx": {"hop_legacy": True},
    "nav3x": {"nav3": True},
    "berserkx": {"berserk": True},
    "aggrox": {"engage_ratio_squad": 1.6, "opp_min_hp_squad": 0.4, "heal_below_squad": 0.4, "seek_min_hp": 0.6},
    "soundx": {"seek": True, "seek_sound": True},
    "fixx": {"hopfix3": True},
    "capx": {"run_for_weapon_cap_s": 6.0},
    "ghostx": {"conveyor": True, "conveyor_until": 480.0, "seek": False, "drone_value": 0.0},
    "hopcx": {"combat_hop": True},
    "jet60x": {"jet_cap": 60.0, "roof_weapon_dz": 35.0},
    "hidex": {"hide": True, "conveyor": True, "conveyor_until": 480.0, "seek": False, "drone_value": 0.0,
              "heal_below_squad": 0.8, "heal_below": 0.7},
    "ragex": {"engage_ratio_squad": 1.6, "opp_min_hp_squad": 0.4, "heal_below_squad": 0.4, "seek": True, "seek_min_hp": 0.5,
              "seek_sound": True, "berserk": True, "seek_mem_s": 60.0, "seek_max_m": 400.0},
    "perchx": {"perch": True},
    "jukex": {"strafe_mode": "juke"},
    "steadyx": {"strafe_mode": "steady"},
    "hide240x": {"hide": True, "hide_until": 240.0, "conveyor": True, "conveyor_until": 240.0},
    "hide10x": {"hide": True, "hide_alive_min": 10, "conveyor": True, "conveyor_until": 480.0},
    "groundx": {"jet_cap": 0.0, "roof_weapon_dz": 6.0},
    "lhuntx": {"explore_for_laser_until": 120.0, "no_mortar": True},
    "hretx": {"hunter_retreat": 0.3},                                  # deltas for composing
    "standx": {"laser_standoff": 120.0},
    "snipex": {"laser_standoff": 170.0},
    "laserx": {"laser_first": True, "no_mortar": True},
    "picky_x": {"squad_picky": True, "engage_ratio_squad": 0.6},
    "laser2": {"cube_greed": True, "laser_first": True, "no_mortar": True},
    "fresh": {"cube_greed": True, "heal_after_kill": True, "opp_min_hp_squad": 0.85},  # full HP before new fights
}


def _env_overrides() -> None:
    """MECH_BRAIN='heal_below=0.7,engage_ratio_squad=0.8' overrides tunables (eval A/B only)."""
    import os
    prof = os.environ.get("MECH_PROFILE", DEFAULT_PROFILE)
    for part in prof.split("+"):          # composable: "seek+scale" applies seek, then scale
        for k, v in PROFILES.get(part.strip(), {}).items():
            if k in P:
                P[k] = v
    P["profile"] = prof
    spec = os.environ.get("MECH_BRAIN", "")
    for part in spec.split(","):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        k = k.strip()
        if k in P:
            try:
                P[k] = type(P[k])(float(v)) if not isinstance(P[k], bool) else v.strip().lower() in ("1", "true", "yes")
            except ValueError:
                pass


_env_overrides()

WEAPON_VALUE = {"lightning": 3.0, "laser": 2.8, "mortar": 1.2, "gun": 1.5}
if P["laser_first"]:
    WEAPON_VALUE["laser"] = 3.6
if P["no_mortar"]:
    WEAPON_VALUE["mortar"] = 0.0
UPGRADE_VALUE = {
    "plating": 10, "armor": 9.5, "nanites": 8, "lightning_efficiency": 7, "laser_damage": 7, "gun_damage": 6.5,
    "laser_charge": 6.5, "gun_rate": 6, "servos": 5.5, "lightning_range": 5.5, "capacitor": 5, "reactor": 5,
    "jets": 4.5, "gun_mag": 4.5, "gun_velocity": 4, "gyros": 4, "lightning_chain": 4, "sensors": 3.5,
    "mortar_reload": 3, "mortar_velocity": 2, "mortar_splash": 2, "laser_pierce": 2,
}


# ----------------------------------------------------------------------------- memory helpers
def _mem(state: WorldState) -> Dict[str, Any]:
    m = state.scratch.get("brain")
    if m is None:
        m = {"items": {}, "blacklist": {}, "heal": False, "mode": "rotate", "goal": None, "loot": None,
             "infight": 0.0, "focus": 0.0, "alive_seen": 16, "kills": 0, "foreign_deaths": 0,
             "attackers_ever": set(), "sound_yaw": None, "sound_t": -1e9, "last_threat_pos": None,
             "last_threat_t": -1e9, "modes": {}, "death_cause": None, "zone_out_s": 0.0,
             "stuck_s": 0.0, "last_pos": None, "last_progress_t": 0.0, "offers": []}
        state.scratch["brain"] = m
    return m


def init(state: WorldState) -> None:
    _mem(state)


def _remember_items(state: WorldState, m: Dict[str, Any]) -> None:
    items = m["items"]
    t = state.t
    seen = set()
    for ev in state.events:
        if ev.get("type") == "take_failed" and ev.get("reason") in ("gone", "range"):
            i = ev.get("id")
            if ev.get("reason") == "gone":
                items.pop(i, None)
            m["blacklist"][i] = t + (60.0 if ev.get("reason") == "gone" else 3.0)
    o = state.obs
    for kind, key in (("pickup", "pickups"), ("crate", "crates"), ("cube", "cubes")):
        for it in o.get(key) or []:
            i = it.get("id")
            if i is None:
                continue
            seen.add(i)
            rec = items.get(i)
            if rec is None:
                rec = {"id": i, "type": kind, "kind": it.get("kind", kind), "pos": tuple(it["pos"]), "t": t}
                items[i] = rec
            rec["pos"], rec["t"] = tuple(it["pos"]), t
            if "hp" in it:
                rec["hp"] = it["hp"]
    # forget items we should see but don't (close by) and stale ones. Weapon pickups are kept until we stood on the
    # spot without seeing them for 1.5 s: near-range LOS to an item lying in a dip can fail (seed 2: we walked to 6 m
    # of a mortar, forgot it, and dithered between three pickups for 25 s). `take` needs reach, not sight.
    near = 30.0
    gone = []
    for i, r in items.items():
        if i in seen:
            r.pop("close_t", None)
            continue
        d = dist2d(r["pos"], state.pos)
        if t - r["t"] > P["memory_item_s"]:
            gone.append(i)
        elif r["type"] == "pickup":
            if d < 3.0 and abs(r["pos"][2] - state.pos[2]) < 4.0:
                r.setdefault("close_t", t)
                if t - r["close_t"] > 1.5:
                    gone.append(i)
            elif d < near and abs(r["pos"][2] - state.pos[2]) < 8 and t - r["t"] > 20.0:
                gone.append(i)      # long unseen although close: probably taken by someone
        elif d < near and abs(r["pos"][2] - state.pos[2]) < 8:
            gone.append(i)
    for i in gone:
        del items[i]


# ----------------------------------------------------------------------------- round detection
def _update_round(state: WorldState, threats: Threats, m: Dict[str, Any]) -> None:
    t = state.t
    for ev in state.events:
        if ev.get("type") == "kill":
            m["kills"] += 1
        elif ev.get("type") == "damaged" and ev.get("by") is not None:
            m["attackers_ever"].add(ev.get("by"))
    # deaths we did not cause (zone deaths are unlikely before ~200 s): strong FFA evidence
    drop = m["alive_seen"] - state.alive
    if drop > 0:
        ours = sum(1 for ev in state.events if ev.get("type") == "kill")
        foreign = max(0, drop - ours)
        if foreign and t < 200:
            m["infight"] += 3.0 * foreign
            m["early_foreign"] = m.get("early_foreign", 0) + foreign
        m["foreign_deaths"] += foreign
        m["alive_seen"] = state.alive
    # beams not aimed at us
    me = state.pos
    for b in state.obs.get("beams") or []:
        path = b.get("path") or []
        if len(path) < 2 or b.get("by") is None:
            continue
        end = path[-1]
        if dist2d(end, me) > 20 and dist2d(path[0], me) > 20:
            # did it end near another mech?
            for tr in state.tracks.values():
                if tr.kind == "mech" and tr.id != b.get("by") and tr.visible_now and dist2d(tr.pos, end) < 8:
                    m["infight"] += 1.0
                    break
    # visible mechs aiming at other mechs while we watch (weak evidence), aiming at us (focus)
    vis = [tr for tr in state.tracks.values() if tr.kind == "mech" and tr.visible_now]
    for tr in vis:
        if _aims_at(tr.pos, tr.aim[0], me, 0.15):
            m["focus"] += 0.02
    if len(m["attackers_ever"]) >= 3 and m["infight"] < 1:
        m["focus"] += 0.05
    ev_ffa, ev_squad = m["infight"], m["focus"]
    # combat's threats module also gathers evidence (e.g. enemy HP drops we didn't cause): take the stronger
    se = getattr(threats, "squad_evidence", None)
    if isinstance(se, dict):
        ev_ffa = max(ev_ffa, float(se.get("infight", 0.0) or 0.0))
    # Sim calibration: in squad rounds unexplained enemy HP drops still happen (drones, chains), so infighting
    # evidence alone is noisy (squad runs: infight 0-15 vs focus 17-45; FFA: infight ~9 vs focus ~3).
    # A mech dying early that we did not kill is the decisive FFA signal; otherwise compare the two.
    # one unexplained early death can be the zone or a drone (seen in real lobbies): need a second, or infighting
    ef = m.get("early_foreign", 0)
    if ef >= 2 or (ef >= 1 and ev_ffa >= 2) or (ev_ffa >= 3 and ev_ffa > 1.5 * ev_squad):
        state.mode_guess = "ffa"
    elif ev_squad >= 6 and ev_ffa < ev_squad:
        state.mode_guess = "squad"
    elif ev_squad >= 2 and ev_ffa < 1.5:
        state.mode_guess = "squad"
    else:
        state.mode_guess = "unknown"
    state.mode_evidence = {"infighting": round(ev_ffa, 2), "focus_on_me": round(ev_squad, 2)}


def _aims_at(src, yaw, dst, tol) -> bool:
    return abs(ang_diff(yaw_to(src, dst), yaw)) < tol


# ----------------------------------------------------------------------------- zone
def _eta_quick(state: WorldState, goal) -> float:
    """Cheap straight-line ETA estimate (for scoring many candidates)."""
    if goal is None:
        return 0.0
    return dist2d(state.pos, goal) * P["zone_path_factor"] / max(1.0, state.stat("walk_speed", 11.7))


def _eta(state: WorldState, goal) -> float:
    """Seconds to walk to goal along a real path (nav's planner when available). Cached ~1 s per goal cell."""
    if goal is None:
        return 0.0
    cache = _mem(state).setdefault("eta_cache", {})
    key = (int(goal[0] // 8), int(goal[1] // 8), int(state.pos[0] // 8), int(state.pos[1] // 8))
    hit = cache.get(key)
    if hit is not None and state.t - hit[0] < 1.0:
        return hit[1]
    if len(cache) > 64:
        cache.clear()
    v = _eta_real(state, goal)
    cache[key] = (state.t, v)
    return v


def _nav_mod():
    if P.get("nav3"):
        from . import navigate3
        return navigate3
    from . import navigate
    return navigate


def _eta_real(state: WorldState, goal) -> float:
    try:
        navigate = _nav_mod()
        f = getattr(navigate, "eta", None)
        if f is not None:
            v = f(state, goal)
            if v is not None and v == v:
                return float(v)
    except Exception:
        pass
    speed = max(1.0, state.stat("walk_speed", 11.7))
    d = dist2d(state.pos, goal)
    if state.arena is not None:
        try:
            L = state.arena.path_len(state.pos, goal)
            if L != math.inf:
                return L / speed
            return d * 2.0 / speed + 10.0
        except Exception:
            pass
    return d * P["zone_path_factor"] / speed


def _inside_zone_soon(state: WorldState, p, margin: float = 8.0) -> bool:
    """p will still be inside the shrinking circle when we arrive (straight-line ETA) and a few s later."""
    if not state.zone:
        return True
    t_arr = state.t + _eta_quick(state, p) + 5.0
    c, r = state.zone_circle_at(t_arr)
    return dist2d(p, c) <= r - margin


def _field_eta(state: WorldState, p) -> Optional[float]:
    """Seconds of walking from p into the next circle (nav's cheap travel-time field), None if unavailable."""
    try:
        navigate = _nav_mod()
        f = getattr(navigate, "zone_eta_at", None)
        if f is None:
            return None
        v = f(state, p[0], p[1], p[2] if len(p) > 2 else None)
        if v is None or v != v:
            return None
        return float(v)
    except Exception:
        return None


def _safe_point(state: WorldState, c, r, frm=None) -> Tuple[float, float, float]:
    """Point inside circle (c, r) closest to `frm` with a margin."""
    frm = frm or state.pos
    margin = min(P["zone_margin_max"], max(4.0, P["zone_margin_frac"] * r))
    d = dist2d(frm, c)
    if d <= r - margin:
        return (frm[0], frm[1], frm[2])
    k = max(0.0, r - margin)
    if d < 1e-6:
        return (c[0], c[1], frm[2])
    return (c[0] + (frm[0] - c[0]) / d * k, c[1] + (frm[1] - c[1]) / d * k, frm[2])


def _exit_time(state: WorldState, p) -> float:
    """Match time at which point p stops being inside the (moving) safe circle. state.t if outside now."""
    z = state.zone
    if not z:
        return 1e9
    t0 = state.t
    c, r = state.zone_circle_at(t0)
    if dist2d(p, c) > r:
        return t0
    s1 = float(z["shrink_end"])
    if t0 >= s1:
        return 1e9 if dist2d(p, z["next_center"]) <= float(z["next_radius"]) else t0
    lo = max(t0, float(z["shrink_start"]))
    c1, r1 = state.zone_circle_at(s1)
    if dist2d(p, c1) <= r1:
        return _next_phase_exit(state, p)
    hi = s1
    for _ in range(18):  # bisection: inside at lo, outside at hi
        mid = 0.5 * (lo + hi)
        cm, rm = state.zone_circle_at(mid)
        if dist2d(p, cm) <= rm:
            lo = mid
        else:
            hi = mid
    return lo


def _next_phase_exit(state: WorldState, p) -> float:
    """p is inside the next circle. The phase after that has an unknown centre; estimate when p is at risk."""
    z = state.zone
    phases = state.cfg.get("zone", {}).get("phases") or []
    r1 = float(z["next_radius"])
    s1 = float(z["shrink_end"])
    # find the phase whose radius is r1, the following one gives hold/shrink/radius
    for i, ph in enumerate(phases):
        if abs(float(ph.get("radius", -1)) - r1) < 0.5 and i + 1 < len(phases):
            nxt = phases[i + 1]
            r2 = float(nxt["radius"])
            # worst case: the next centre is as far from p as possible -> p must be within r2 of it.
            # p is safe at worst if dist(p, c1) + (r1 - r2) <= r2 ... otherwise it risks being outside at the
            # end of that shrink. Use the shrink end of the following phase as a soft exit time.
            d = dist2d(p, z["next_center"])
            if d + (r1 - r2) <= r2:
                return 1e9
            return s1 + float(nxt["hold_s"]) + float(nxt["shrink_s"]) * 0.5
    return 1e9


def zone_plan(state: WorldState) -> Dict[str, Any]:
    """Where is safe, how long to get there, how long we have."""
    z = state.zone
    if not z:
        return {"must_go": False, "slack": 1e9, "target": None, "eta": 0.0, "inside_next": True}
    c1, r1 = z["next_center"], float(z["next_radius"])
    target = _safe_point(state, c1, r1)
    inside_next = dist2d(state.pos, c1) <= max(0.0, r1 - 2.0)
    eta = _eta(state, target) if not inside_next else 0.0
    if not inside_next and P["use_zone_field"]:
        fe = _field_eta(state, state.pos)  # nav's travel-time field: real walking time around buildings
        if fe is not None and fe != math.inf:
            eta = max(eta, fe)
    t_exit = _exit_time(state, state.pos)
    # arrival deadline: before the edge passes our position, and inside the next circle by shrink_end
    deadline = min(t_exit, float(z["shrink_end"])) if not inside_next else t_exit
    slack = deadline - state.t - eta * 1.15 - P["zone_buffer_s"]
    outside = not state.me.get("in_zone", True)
    return {"must_go": outside or slack < 0, "slack": slack, "target": target, "eta": eta,
            "inside_next": inside_next, "outside": outside, "deadline": deadline,
            "dps": float(z.get("dps", 0))}


def _in_safe_future(state: WorldState, p, extra_eta=0.0) -> bool:
    """Can we go to p, then still make the zone?"""
    z = state.zone
    if not z:
        return True
    c1, r1 = z["next_center"], float(z["next_radius"])
    t_here = _eta_quick(state, p)
    back = dist2d(p, _safe_point(state, c1, r1, p)) * P["zone_path_factor"] / max(1.0, state.stat("walk_speed", 11.7))
    fb = _field_eta(state, p) if P["use_zone_field"] else None
    if fb is not None:
        back = max(back, fb)
    deadline = min(float(z["shrink_end"]), _exit_time(state, p)) if dist2d(p, c1) > r1 else _exit_time(state, p)
    return state.t + t_here + extra_eta + back + P["zone_buffer_s"] < deadline


# ----------------------------------------------------------------------------- fight maths
def _wdps(kind: str, dist: float, stats: Optional[Dict[str, Any]] = None) -> float:
    s = stats or {}
    if kind == "gun":
        rng = s.get("range", 230)
        if dist > rng:
            return 0.0
        dmg, cd = s.get("damage", 45), s.get("cooldown", 0.24)
        mag, rl = s.get("mag", 12), s.get("reload", 2.4)
        sustained = dmg * mag / (mag * cd + rl)
        acc = 0.85 if dist < 60 else (0.65 if dist < 120 else 0.4)
        return sustained * acc
    if kind == "laser":
        if dist > s.get("range", 280):
            return 0.0
        return s.get("damage", 315) / (s.get("charge", 0.75) + s.get("cooldown", 1.65)) * 0.8
    if kind == "lightning":
        if dist > s.get("range", 45):
            return 0.0
        return s.get("damage", 60) / s.get("cooldown", 0.25) * 0.95
    if kind == "mortar":
        if dist > 230 or dist < 15:
            return 0.0
        return (s.get("damage", 200) * 0.5 + 60) / s.get("cooldown", 2.6) * 0.5
    if kind == "npc":
        return 25.0 * 0.5 if dist < 90 else 0.0
    return 0.0


def my_dps(state: WorldState, dist: float) -> float:
    tot = 0.0
    mult = 1.0 + state.cfg.get("cubes", {}).get("damage_per_cube", 0.04) * min(int(state.me.get("cubes", 0) or 0),
                                                                               state.cfg.get("cubes", {}).get("stat_cap", 10))
    for w in state.me.get("weapons") or []:
        if not w:
            continue
        k = w.get("kind")
        if k == "gun" and (w.get("ammo", 1) == 0 and w.get("reload", 0) > 1.0):
            tot += 0.3 * _wdps(k, dist, w.get("stats"))
        elif k == "lightning" and state.energy < 6:
            tot += 0.2 * _wdps(k, dist, w.get("stats"))
        else:
            tot += _wdps(k, dist, w.get("stats"))
    return tot * mult


def enemy_dps(e: EnemyThreat, dist: float) -> float:
    if e.kind == "npc":
        return _wdps("npc", dist)
    ws = e.weapons or ["gun"]
    if "gun" not in ws and len(ws) < 2:
        ws = list(ws) + ["gun"]
    return sum(_wdps(k, dist) for k in ws) * 1.0


def _ehp(state: WorldState) -> float:
    armor = state.stat("armor", 0.0)
    return state.hp / max(0.2, 1.0 - armor)


# ----------------------------------------------------------------------------- main decision
def choose_intent(state: WorldState, threats: Threats) -> Intent:
    m = _mem(state)
    m["threats_ref"] = threats
    if m.get("first_weapon_t") is None and (state.weapon_kinds() + [None])[1] is not None:
        m["first_weapon_t"] = round(state.t, 1)
    _remember_items(state, m)
    _update_round(state, threats, m)
    _track_sounds(state, m)
    _track_progress(state, m)
    zp = zone_plan(state)
    m["zp"] = zp
    hpf = state.hp / max(1.0, state.max_hp)

    mechs = [e for e in threats.enemies if e.kind == "mech"]
    fresh = [e for e in mechs if state.t - e.last_seen_t < 1.5]
    for e in fresh:
        m["last_threat_pos"], m["last_threat_t"] = e.pos, state.t
    attackers = set(threats.attackers)
    m["att_now"] = tuple(attackers)
    hot = [e for e in fresh if e.id in attackers or e.can_hit_me or e.dist < 60]
    if _hiding(state):   # survival-first: only mechs hunting us count as a fight
        hs = set(getattr(threats, "hunters", None) or [])
        hot = [e for e in fresh if e.id in attackers or e.id in hs or e.dist < 25]
    face = _face_yaw(state, m, fresh, zp)
    mode_g = state.mode_guess

    # ---------------------------------------------------------------- fight assessment
    fight = _assess_fight(state, threats, fresh, attackers)
    m["fight"] = fight

    # 1. zone emergency dominates everything except a fight we cannot run from
    if zp["must_go"]:
        tgt = fight.get("target")
        urg = 1.0 if (zp.get("outside") and zp["dps"] >= 35) or zp["slack"] < -5 else 0.8
        it = Intent(mode="rotate", goal=zp["target"], urgency=urg, face=face, allow_fire=True,
                    target_id=tgt.id if tgt is not None else None, reason=f"zone slack {zp['slack']:.0f}s")
        it.arrive_by = zp.get("deadline")
        return _finish(state, m, it)

    # 1b. squad: pick up nearby cubes (kill drops) before starting the next fight
    if P["cube_greed"] and state.mode_guess != "ffa" and not attackers and int(state.me.get("cubes", 0) or 0) < 10:
        cb = [r for r in m["items"].values() if r["type"] == "cube" and dist2d(r["pos"], state.pos) < P["cube_grab_m"]
              and abs(r["pos"][2] - state.pos[2]) < 4.0 and m["blacklist"].get(r["id"], -1e9) <= state.t]
        if cb:
            c = min(cb, key=lambda r: dist2d(r["pos"], state.pos))
            if m["stuck_s"] > 4.0:
                m["blacklist"][c["id"]] = state.t + 30
                m["last_progress_t"] = state.t
            return _finish(state, m, Intent(mode="loot", goal=c["pos"], loot_id=c["id"], urgency=0.3, face=face,
                                            reason=f"grab cube {c['id']}"))

    # 2. in a fight
    if hot:
        tgt = fight.get("target")
        if fight["verdict"] == "retreat":
            goal = _cover_from(state, [e.pos for e in hot], zp)
            real_cover = m.get("cover_real", False)
            # Running in the open while chased rarely saves us (FFA sim: ~12/32 deaths in the first 30 s were
            # open-ground retreats at low HP). Optionally keep trading when there is no cover to run to.
            if (P["retreat_needs_cover"] and not real_cover and tgt is not None and tgt.dist < 90
                    and fight["ratio"] < P["no_cover_fight_ratio"]):
                fight["verdict"] = "engage"
        if fight["verdict"] == "retreat" and P["weapon_first"] and state.weapon_kinds()[1] is None and hpf > 0.2:
            wk = _known_weapon(state, m, P["run_for_weapon_m"])
            if wk is not None and P["run_for_weapon_cap_s"] > 0:
                rs = m.setdefault("run_since", {})
                t0 = rs.setdefault(wk["id"], state.t)
                if state.t - t0 > P["run_for_weapon_cap_s"]:
                    m["blacklist"][wk["id"]] = state.t + 30.0
                    wk = None
            if wk is not None:
                it = Intent(mode="loot", goal=wk["pos"], loot_id=wk["id"], urgency=0.6, face=face, allow_fire=True,
                            target_id=tgt.id if tgt is not None else None, reason=f"run for weapon {wk['id']}")
                return _finish(state, m, it)
        if fight["verdict"] == "retreat":
            m["heal"] = True
            it = Intent(mode="retreat", goal=goal, urgency=0.9, face=face,
                        target_id=tgt.id if tgt is not None else None, allow_fire=True,
                        avoid=[e.pos for e in hot], reason=f"retreat r={fight['ratio']:.2f}")
            return _finish(state, m, it)
        if tgt is not None and fight["verdict"] == "engage":
            m["heal"] = False
            it = Intent(mode="engage", goal=None, target_id=tgt.id, desired_range=_desired_range(state, tgt),
                        urgency=0.5, face=yaw_to(state.pos, tgt.pos), allow_fire=True,
                        avoid=[e.pos for e in hot if e.id != tgt.id], reason=f"engage {tgt.id} r={fight['ratio']:.2f}")
            return _finish(state, m, it)

    # 2a. survival-first: stay out of sight of passive house bots
    if _hiding(state) and not hot:
        seen_by = [e for e in fresh if e.visible and e.dist < 220]
        if seen_by:
            m["last_threat_pos"], m["last_threat_t"] = seen_by[0].pos, state.t
            it = Intent(mode="heal", goal=_cover_from(state, [e.pos for e in seen_by], zp), urgency=0.5, face=face,
                        allow_fire=False, allow_boost=True, avoid=[e.pos for e in seen_by], reason="hide")
            return _finish(state, m, it)

    # 2b. shot by a mech we cannot see (behind us / beyond near range): turn to it and fight, or go to cover
    ua = getattr(threats, "unseen_attack", None) if P["hunter_model"] else None
    if ua is not None and state.t - ua[1] < 2.0 and not hot:
        b = ua[0]
        cpos = (state.pos[0] + 90 * math.cos(b), state.pos[1] + 90 * math.sin(b), state.pos[2])
        m["last_threat_pos"], m["last_threat_t"] = cpos, state.t
        if hpf < max(0.45, P["heal_below_squad"] - 0.1):
            m["heal"] = True
            it = Intent(mode="retreat", goal=_cover_from(state, [cpos], zp), urgency=0.9, face=b, allow_fire=True,
                        avoid=[cpos], reason="unseen attacker, cover")
            return _finish(state, m, it)
        # otherwise carry on (combat turns the torso to the damage bearing via threats.face_yaw)

    # 2c. supply drop first (3 cubes + full HP beats hiding to regen)
    if P["drop_first"]:
        cap = _drop_choice(state, m, fresh, zp)
        if cap is not None:
            return _finish(state, m, cap)

    # 3. heal cycle (stop shooting, break LOS, wait for regen)
    if P["heal_after_kill"] and state.mode_guess != "ffa" and any(ev.get("type") == "kill" for ev in state.events) \
            and hpf < P["opp_min_hp_squad"]:
        m["heal"] = True
    if m["heal"] and hpf >= P["heal_until"]:
        m["heal"] = False
    hb = P["heal_below_squad"] if state.mode_guess == "squad" else P["heal_below"]
    if not m["heal"] and hpf < hb:
        m["heal"] = True
    if m["heal"]:
        threat_pos = [m["last_threat_pos"]] if m["last_threat_pos"] is not None and state.t - m["last_threat_t"] < 20 else []
        goal = _cover_from(state, threat_pos, zp) if threat_pos else zp["target"]
        it = Intent(mode="heal", goal=goal, urgency=0.3, face=face, allow_fire=False, allow_boost=True,
                    reason=f"heal {hpf:.2f}")
        return _finish(state, m, it)

    # 4. opportunistic fight on a visible mech (not attacking us yet)
    tgt = fight.get("target")
    if tgt is not None and fight["verdict"] == "engage" and fight.get("opportunity"):
        it = Intent(mode="engage", target_id=tgt.id, desired_range=_desired_range(state, tgt), urgency=0.4,
                    face=yaw_to(state.pos, tgt.pos), reason=f"hunt {tgt.id} r={fight['ratio']:.2f}")
        return _finish(state, m, it)

    # 5. supply drop
    cap = _drop_choice(state, m, fresh, zp)
    if cap is not None:
        return _finish(state, m, cap)

    # 6. loot
    lt = _loot_choice(state, m, fresh, zp, hpf)
    if lt is not None:
        lt.face = lt.face if lt.face is not None else face
        return _finish(state, m, lt)

    # 6c. squad: go find the next house bot instead of waiting for the hunters to come in a pack
    sk = _seek_choice(state, m, zp, hpf, face)
    if sk is not None:
        return _finish(state, m, sk)

    # 6b. no secondary weapon (or farm profile) and nothing known to loot: explore unvisited ground inside the circle
    ex = _explore_choice(state, m, zp)
    if ex is not None:
        return _finish(state, m, ex)

    # 7. hold inside the next circle, drift toward its centre, near cover
    goal = _hold_point(state, zp)
    it = Intent(mode="hold", goal=goal, urgency=0.1, face=face, reason="hold")
    # drift silently when there's time: walking under sound.step_speed makes no step sounds
    if zp.get("slack", 0) > 25 and not (P["perch"] and goal is not None):
        it.max_speed = 0.9 * float(state.cfg.get("sound", {}).get("step_speed", 5.0))
    return _finish(state, m, it)


def _finish(state: WorldState, m: Dict[str, Any], it: Intent) -> Intent:
    th = m.get("threats_ref")
    if P["conveyor"] and th is not None:
        it.spare_ids = [e.id for e in th.enemies if e.kind == "mech" and _spare(state, th, e)]
    m["mode"] = it.mode
    m["last_reason"] = it.reason
    f = m.get("fight") or {}
    m["last_ctx"] = {"mode": it.mode, "reason": it.reason[:40], "hp": round(state.hp), "t": round(state.t, 1),
                     "n_att": len(state.scratch.get("brain", {}).get("att_now", ())), "ratio": round(f.get("ratio", 9.9), 2)}
    m["modes"][it.mode] = m["modes"].get(it.mode, 0) + 1
    if not state.me.get("in_zone", True):
        m["zone_out_s"] += state.dt
    return it


def _assess_fight(state: WorldState, threats: Threats, fresh: List[EnemyThreat], attackers) -> Dict[str, Any]:
    """Pick a target and decide engage / retreat. ratio = my TTK on target / their TTK on me (lower is better)."""
    out: Dict[str, Any] = {"verdict": "none", "target": None, "ratio": 9.9, "opportunity": False}
    if not fresh:
        return out
    ehp = _ehp(state)
    # incoming DPS from every fresh mech that can plausibly hit us
    hunters = set(getattr(threats, "hunters", None) or [])
    hm = P["hunter_model"] and state.mode_guess != "ffa"
    inc = 0.0
    for e in fresh:
        if hm and e.id not in hunters and e.id not in attackers and not e.facing_me:
            # practice squad: a non-engaged house bot does not shoot; count a little in case it turns
            inc += 0.15 * enemy_dps(e, e.dist) if (e.visible and e.dist < 120) else 0.0
            continue
        if e.id in attackers or e.can_hit_me or (e.visible and e.dist < 120):
            inc += enemy_dps(e, e.dist)
    inc = max(inc, 1.0)
    their_ttk = ehp / inc
    best, best_r = None, 1e9
    for e in fresh:
        if not e.visible and state.t - e.last_seen_t > 0.6:
            continue
        if _spare(state, threats, e):
            continue
        hp = e.hp if e.hp is not None else 1400.0
        d = e.dist
        dps = max(1.0, my_dps(state, min(d, _desired_range(state, e))))
        my_ttk = hp / dps + (0.0 if d < 150 else (d - 150) / 10.0)
        r = my_ttk / their_ttk
        if e.id in attackers:
            r *= 0.9
        if P["hunter_model"] and e.id in hunters and state.weapon_kinds()[1] is not None:
            r *= P["hunter_pref"]
        if r < best_r:
            best, best_r = e, r
    out["target"], out["ratio"] = best, best_r
    sq = state.mode_guess == "squad"
    eng = P["engage_ratio_squad"] if sq else P["engage_ratio_ffa"]
    being_hit = bool(attackers)
    if best is None:
        return out
    m = _mem(state)
    if being_hit:
        # we are in it: fight unless clearly losing; with low HP and a good ratio still finish the target.
        # Hysteresis: a recent verdict is sticky so we don't dither between running and fighting.
        thr = max(eng, 1.0) / P["retreat_ratio"]
        prev, since = m.get("fight_verdict"), m.get("fight_t", -1e9)
        if state.t - since < 3.0:
            thr *= 0.8 if prev == "retreat" else (1.25 if prev == "engage" else 1.0)
        n_att = len([a for a in attackers if a in {e.id for e in fresh}])
        tgt_frac = (best.hp if best.hp is not None else 1400.0) / max(1.0, best.max_hp or 1400.0)
        if P["berserk"] and state.mode_guess != "ffa" and best_r < P["berserk_max_ratio"]:
            out["verdict"] = "engage"
        elif best_r > thr or (state.hp / state.max_hp < 0.25 and best_r > 0.5):
            out["verdict"] = "retreat"
        elif P["multi_retreat"] > 0 and n_att >= 2 and tgt_frac > P["multi_retreat"]:
            out["verdict"] = "retreat"
        elif (P["hunter_retreat"] > 0 and state.mode_guess != "ffa" and tgt_frac > P["hunter_retreat"]
              and len([e for e in fresh if (e.id in hunters or e.id in attackers) and e.dist < 160]) >= 2):
            out["verdict"] = "retreat"
        else:
            out["verdict"] = "engage"
        if out["verdict"] != prev or state.t - since > 3.0:
            m["fight_verdict"], m["fight_t"] = out["verdict"], state.t
    else:
        hpf = state.hp / max(1.0, state.max_hp)
        others = [e for e in fresh if e.id != best.id and e.dist < 150]
        busy = _fighting_others(state, best)
        omin = P["opp_min_hp"] if state.mode_guess == "ffa" else P["opp_min_hp_squad"]
        if _spare(state, threats, best):
            return out
        if hpf > omin and (best_r < eng or (busy and best_r < eng * 1.6)) and ((sq and not P["squad_picky"]) or not others or busy):
            out["verdict"] = "engage"
            out["opportunity"] = True
        elif best.dist < 70 and best_r < 1.0 and (hpf > omin or state.mode_guess == "ffa" or best.facing_me):
            out["verdict"] = "engage"
            out["opportunity"] = True
    return out


def _hiding(state: WorldState) -> bool:
    return (P["hide"] and state.mode_guess != "ffa" and state.t < P["hide_until"]
            and state.alive > P["hide_alive_min"])


def _spare(state: WorldState, threats: Threats, e: EnemyThreat) -> bool:
    """Conveyor: leave this mech alone (it is not hunting us and not nearly dead)."""
    if not P["conveyor"] or state.mode_guess == "ffa" or state.t >= P["conveyor_until"] or e.kind != "mech":
        return False
    if P["hide"] and not _hiding(state):
        return False
    hunters = set(getattr(threats, "hunters", None) or [])
    if e.id in hunters or e.id in set(threats.attackers):
        return False
    if e.id in (getattr(threats, "killable", None) or []) or (e.hp is not None and e.hp < 0.2 * (e.max_hp or 1400.0)):
        return False
    return True


def _fighting_others(state: WorldState, e: EnemyThreat) -> bool:
    tr = state.tracks.get(e.id)
    if tr is None:
        return False
    if not _aims_at(tr.pos, tr.aim[0], state.pos, 0.35):
        for o in state.tracks.values():
            if o.id != e.id and o.kind == "mech" and o.visible_now and _aims_at(tr.pos, tr.aim[0], o.pos, 0.2):
                return True
    return False


def _desired_range(state: WorldState, e: EnemyThreat) -> float:
    kinds = [k for k in state.weapon_kinds() if k]
    their = set(e.weapons or [])
    if e.kind == "npc":
        return 40.0
    if P["laser_standoff"] > 0 and "laser" in kinds:
        return P["laser_standoff"]
    if "lightning" in kinds:
        if "mortar" in their:
            return 25.0
        return 28.0
    so = P["squad_standoff"]
    if so > 0 and state.mode_guess != "ffa" and "lightning" not in their and "laser" not in their:
        return max(so, 90.0 if "laser" in kinds else 0.0)
    if "laser" in kinds:
        if "lightning" in their:
            return 120.0
        return 90.0
    if "lightning" in their:
        return 80.0  # stay out of their arc
    return 55.0


def _cover_from(state: WorldState, threat_pos: List, zp: Dict[str, Any]):
    """A hidden spot from the threats that keeps us zone-safe; else away from threats toward the safe circle."""
    if state.arena is not None and threat_pos:
        # nearest_cover is a few ms: reuse the last answer while the threat and we haven't moved much
        m = _mem(state)
        cc = m.get("cover_cache")
        tp = threat_pos[0]
        c = None
        if cc is not None and state.t - cc[0] < 2.0 and dist2d(cc[1], tp) < 10 and dist2d(cc[2], state.pos) < 15:
            c = cc[3]
        else:
            try:
                c = state.arena.nearest_cover(state.pos, tp, 60.0)
            except Exception:
                c = None
            m["cover_cache"] = (state.t, tp, state.pos, c)
        if c is not None and _in_safe_future(state, c) and _inside_zone_soon(state, c) and dist2d(c, state.pos) < 45:
            m["cover_real"] = True
            return tuple(c)
    _mem(state)["cover_real"] = False
    # run away from the centroid of threats, biased toward the next circle
    if threat_pos:
        cx = sum(p[0] for p in threat_pos) / len(threat_pos)
        cy = sum(p[1] for p in threat_pos) / len(threat_pos)
        ax, ay = unit2(state.pos[0] - cx, state.pos[1] - cy)
    else:
        ax, ay = 0.0, 0.0
    tgt = zp.get("target") or state.pos
    bx, by = unit2(tgt[0] - state.pos[0], tgt[1] - state.pos[1])
    # Regen is disabled outside the zone: never pick a spot the (moving) circle won't cover when we get there.
    w0 = 0.5 if zp.get("slack", 99) > 20 else 1.5
    for w in (w0, 1.5, 3.0, 8.0):
        dx, dy = unit2(ax + w * bx, ay + w * by)
        if dx == 0 and dy == 0:
            return tgt
        p = (state.pos[0] + dx * 40.0, state.pos[1] + dy * 40.0, state.pos[2])
        if _inside_zone_soon(state, p):
            return p
    return tgt


def _face_yaw(state: WorldState, m: Dict[str, Any], fresh: List[EnemyThreat], zp) -> Optional[float]:
    # newest damage bearing
    for ev in reversed(state.events):
        if ev.get("type") == "damaged" and ev.get("bearing") is not None:
            m["dmg_yaw"], m["dmg_t"] = float(ev["bearing"]), state.t
            return float(ev["bearing"])
    if fresh:
        e = min(fresh, key=lambda e: e.dist)
        return yaw_to(state.pos, e.pos)
    if state.t - m.get("dmg_t", -1e9) < 4:
        return m["dmg_yaw"]
    if state.t - m["sound_t"] < 3 and m["sound_yaw"] is not None:
        return m["sound_yaw"]
    if m["last_threat_pos"] is not None and state.t - m["last_threat_t"] < 8:
        return yaw_to(state.pos, m["last_threat_pos"])
    v = state.vel
    if math.hypot(v[0], v[1]) > 2:
        # slow scan around the travel direction so the 120 deg wedge sees flanks
        return math.atan2(v[1], v[0]) + 0.9 * math.sin(state.t * 0.8)
    # standing still: sweep the full circle (~10 s per turn) so nobody walks up on our blind side
    return ((state.t * 0.6) % (2 * math.pi)) - math.pi


def _track_sounds(state: WorldState, m: Dict[str, Any]) -> None:
    pri = {"laser_charge": 5, "gun": 4, "laser": 4, "lightning": 4, "mortar": 3, "boost": 2, "step": 2, "jet": 2,
           "reload": 2, "explosion": 1}
    best, bp = None, 0
    for s in state.obs.get("sounds") or []:
        k = s.get("kind")
        p = pri.get(k, 0)
        if s.get("dist") == "near":
            p += 3
        elif s.get("dist") == "mid":
            p += 1
        if p > bp and s.get("bearing") is not None:
            best, bp = s, p
    if best is not None and bp >= 4:
        m["sound_yaw"], m["sound_t"] = float(best["bearing"]), state.t


def _track_progress(state: WorldState, m: Dict[str, Any]) -> None:
    lp = m["last_pos"]
    if lp is None or dist2d(lp, state.pos) > 3.0:
        m["last_pos"], m["last_progress_t"] = state.pos, state.t
    m["stuck_s"] = state.t - m["last_progress_t"]


def _drop_choice(state: WorldState, m, fresh, zp) -> Optional[Intent]:
    drops = state.obs.get("drops") or []
    if not drops:
        return None
    hpf = state.hp / max(1.0, state.max_hp)
    best, bs = None, -1e9
    for d in drops:
        pos = d.get("pos")
        if not pos:
            continue
        p = (pos[0], pos[1], pos[2] if len(pos) > 2 else state.pos[2])
        eta = _eta_quick(state, p)
        lands = float(d.get("lands_in", 0) or 0)
        holder = d.get("holder")
        if holder is not None and holder != state.me.get("id"):
            continue
        if eta > P["drop_max_eta"] or not _in_safe_future(state, p, 4.0):
            continue
        contest = [e for e in fresh if dist2d(e.pos, p) < 60]
        if contest and state.mode_guess != "squad" and hpf < 0.8:
            continue
        if len(contest) >= 2:
            continue
        score = P["drop_base"] + (1 - hpf) * 40 - eta - 10 * len(contest) - max(0.0, lands - eta) * 0.3
        if score > bs:
            best, bs = (d, p, eta, lands), score
    if best is None or bs < 0:
        return None
    d, p, eta, lands = best
    # don't stand in the ring early (being seen waiting there); arrive just as it lands
    return Intent(mode="capture", goal=p, loot_id=d.get("id"), urgency=0.5 if eta > lands else 0.3,
                  reason=f"drop {d.get('id')} eta {eta:.0f} lands {lands:.0f}")


def _loot_choice(state: WorldState, m, fresh, zp, hpf) -> Optional[Intent]:
    items = m["items"]
    bl = m["blacklist"]
    kinds = state.weapon_kinds()
    have = set(k for k in kinds if k)
    cubes = int(state.me.get("cubes", 0) or 0)
    best, bs = None, 0.0
    # sticky: keep the current loot target unless it vanished, to avoid dithering
    cur = m.get("loot")
    walk = max(1.0, state.stat("walk_speed", 11.7))
    for i, r in items.items():
        if bl.get(i, -1e9) > state.t:
            continue
        d = dist2d(r["pos"], state.pos)
        need_weapon = r["type"] == "pickup" and kinds[1] is None
        if d > (P["loot_max_dist_weapon"] if need_weapon else P["loot_max_dist"]):
            continue
        dz = r["pos"][2] - state.pos[2]
        # roof loot: nav can jet-hop onto roofs (~60 m climb with full energy); only worth it for a first secondary
        if dz > (P["roof_weapon_dz"] if need_weapon else 6):
            continue
        val = 0.0
        if r["type"] == "pickup":
            k = r["kind"]
            if k in have or k == "gun":
                continue
            v = WEAPON_VALUE.get(k, 1.0)
            if v <= 0:
                continue
            if kinds[1] is None:
                val = P["weapon_first_value"] * v  # a second weapon early is the biggest combat lever
            else:
                worst = min(WEAPON_VALUE.get(kinds[1], 1), WEAPON_VALUE.get(kinds[0] or "gun", 1))
                if v <= worst + 0.5:
                    continue
                val = 15 * (v - worst)
        elif r["type"] == "cube":
            val = 30.0 if cubes < 10 else 8.0
            if P["cube_greed"] and cubes < 10:
                val = P["cube_value_greed"]
        elif r["type"] == "crate":
            unarmed = P["weapon_first"] and kinds[1] is None
            if hpf < P["crate_min_hp_frac"] and not unarmed:
                continue
            val = P["crate_value"] if cubes < 10 else 6.0
            if unarmed:
                val = max(val, P["crate_value_unarmed"])
        eta = d * 1.2 / walk
        near_set = fresh
        if P["cube_greed"] and state.mode_guess != "ffa":
            hs = set(getattr(m.get("threats_ref"), "hunters", None) or [])
            near_set = [e for e in fresh if e.id in hs]
        if near_set and min(dist2d(e.pos, r["pos"]) for e in near_set) < 60:
            val *= 0.3
        score = val / (1.0 + eta / 6.0)
        if i == cur:
            score *= 1.3
        if score > bs:
            best, bs = r, score
    # drones: 2 cubes, weak shooters
    drone = _drone_choice(state, m, hpf)
    if drone is not None and drone[1] > bs:
        e, s = drone
        m["loot"] = e.id
        return Intent(mode="loot", goal=None, target_id=e.id, desired_range=40.0, urgency=0.2,
                      face=yaw_to(state.pos, e.pos), loot_id=e.id, reason=f"drone {e.id}")
    if best is None or bs < 2.0:
        m["loot"] = None
        return None
    first_weapon = best["type"] == "pickup" and kinds[1] is None
    if not _in_safe_future(state, best["pos"]) or (not first_weapon and not _inside_zone_soon(state, best["pos"], 3.0)):
        bl[best["id"]] = state.t + 15
        return None
    m["loot"] = best["id"]
    if m["stuck_s"] > 4.0 and dist2d(best["pos"], state.pos) > 5:
        bl[best["id"]] = state.t + 30
        m["last_progress_t"] = state.t
    it = Intent(mode="loot", goal=best["pos"], loot_id=best["id"], urgency=0.2, reason=f"{best['type']} {best['id']}")
    if best["type"] == "crate":
        it.shoot_crate = best["id"]
        # shoot it from where we stand if in range; walk closer otherwise
        if dist2d(best["pos"], state.pos) < 40:
            it.goal = None
        it.face = yaw_to(state.pos, best["pos"])
    return it


def _known_weapon(state: WorldState, m, max_d: float):
    """Nearest remembered weapon pickup (not a gun, reachable height) within max_d, zone-safe."""
    best, bd = None, max_d
    for i, r in m["items"].items():
        if r["type"] != "pickup" or r.get("kind") in ("gun", None) or m["blacklist"].get(i, -1e9) > state.t:
            continue
        if WEAPON_VALUE.get(r.get("kind"), 1.0) <= 0:
            continue
        if r["pos"][2] - state.pos[2] > P["roof_weapon_dz"]:
            continue
        d = dist2d(r["pos"], state.pos)
        if d < bd and _in_safe_future(state, r["pos"]):
            best, bd = r, d
    return best


def _drone_choice(state: WorldState, m, hpf) -> Optional[Tuple[EnemyThreat, float]]:
    if hpf < P["drone_min_hp_frac"]:
        return None
    best, bs = None, 0.0
    cubes = int(state.me.get("cubes", 0) or 0)
    for tr in state.tracks.values():
        if tr.kind != "npc" or tr.dead or state.t - tr.last_seen_t > 3:
            continue
        d = dist2d(tr.pos, state.pos)
        if d > 120:
            continue
        hp = tr.hp if tr.hp is not None else 350
        val = (P["drone_value"] if cubes < 10 else 10.0) * (1.4 - hp / 350.0 * 0.4)
        score = val / (1.0 + d / 11.7 / 6.0)
        if score > bs and _in_safe_future(state, tr.pos) and _inside_zone_soon(state, tr.pos, 3.0):
            best, bs = tr, score
    if best is None:
        return None
    e = EnemyThreat(id=best.id, kind="npc", pos=best.pos, vel=best.vel, hp=best.hp, max_hp=best.max_hp,
                    weapons=[], dist=dist3d(best.pos, state.pos), visible=best.visible_now, last_seen_t=best.last_seen_t)
    return e, bs


def _explore_choice(state: WorldState, m, zp) -> Optional[Intent]:
    """Unarmed (slot 1 empty): walk to the nearest unvisited grid cell inside the next circle, torso scanning, to
    find pickups and crates. Visited = we stood within ~0.7 cell of its centre (items there were in near vision)."""
    armed = state.weapon_kinds()[1] is not None
    want_laser = armed and "laser" not in state.weapon_kinds() and state.t < P["explore_for_laser_until"]
    if not P["weapon_first"] or (armed and not want_laser and
                                 (state.t > P["explore_armed_until"] or int(state.me.get("cubes", 0) or 0) >= 10)):
        return None
    cs = P["explore_cell"]
    vis = m.setdefault("visited", set())
    cx, cy = int(math.floor(state.pos[0] / cs)), int(math.floor(state.pos[1] / cs))
    vis.add((cx, cy))
    z = state.zone
    best, bd = None, 1e9
    for dx in range(-5, 6):
        for dy in range(-5, 6):
            c = (cx + dx, cy + dy)
            if c in vis or c in m.setdefault("explore_bad", {}) and m["explore_bad"][c] > state.t:
                continue
            p = ((c[0] + 0.5) * cs, (c[1] + 0.5) * cs, state.pos[2])
            d = dist2d(p, state.pos)
            if d < 0.5 * cs or d > 300:
                continue
            if z and dist2d(p, z["next_center"]) > float(z["next_radius"]) - 10:
                continue
            if d < bd:
                best, bd = (c, p), d
    if best is None:
        return None
    c, p = best
    if m.get("explore_goal") != c:
        m["explore_goal"], m["explore_since"] = c, state.t
    elif state.t - m.get("explore_since", state.t) > max(20.0, bd / 5.0) or m["stuck_s"] > 5.0:
        m.setdefault("explore_bad", {})[c] = state.t + 60.0   # can't get there: try another cell
        m["explore_goal"] = None
        m["last_progress_t"] = state.t
    if not _in_safe_future(state, p):
        return None
    return Intent(mode="loot", goal=p, urgency=0.2, face=None, reason=f"explore {c[0]},{c[1]}")


def _seek_choice(state: WorldState, m, zp, hpf, face) -> Optional[Intent]:
    if not P["seek"] or state.mode_guess == "ffa" or hpf < P["seek_min_hp"] or state.weapon_kinds()[1] is None:
        return None
    best, bd = None, P["seek_max_m"]
    for tr in state.tracks.values():
        if tr.kind != "mech" or tr.dead or state.t - tr.last_seen_t > P["seek_mem_s"]:
            continue
        d = dist2d(tr.pos, state.pos)
        if d < bd and _in_safe_future(state, tr.pos) and _inside_zone_soon(state, tr.pos, 3.0):
            best, bd = tr, d
    if best is None:
        if P["seek_sound"] and m.get("sound_yaw") is not None and state.t - m.get("sound_t", -1e9) < 6.0:
            b = m["sound_yaw"]
            p = (state.pos[0] + P["seek_sound_m"] * math.cos(b), state.pos[1] + P["seek_sound_m"] * math.sin(b), state.pos[2])
            if _in_safe_future(state, p) and _inside_zone_soon(state, p, 3.0):
                return Intent(mode="loot", goal=p, urgency=0.3, face=b, reason="seek sound")
        return None
    return Intent(mode="loot", goal=best.pos, urgency=0.3, face=yaw_to(state.pos, best.pos), reason=f"seek {best.id}")


def _perch_point(state: WorldState):
    """Nearest tall-roof spot inside the next circle (cached per zone phase). None if unavailable."""
    z, ar = state.zone, state.arena
    if not z or ar is None or not getattr(ar, "ok_nav", False):
        return None
    m = _mem(state)
    c1, r1 = z["next_center"], float(z["next_radius"])
    pc = m.get("perch_cache")
    if pc is None or pc[0] != (round(c1[0]), round(c1[1]), round(r1)) or dist2d(pc[2], state.pos) > 120:
        key = (round(c1[0]), round(c1[1]), round(r1))
        cands = []
        R = max(0.0, r1 - 15.0)
        step = 12.0
        n = int(220.0 / step)
        ox, oy = state.pos[0], state.pos[1]
        try:
            for i in range(-n, n + 1):
                for j in range(-n, n + 1):
                    x, y = ox + i * step, oy + j * step
                    if (x - c1[0]) ** 2 + (y - c1[1]) ** 2 > R * R or (i * i + j * j) * step * step > 220.0 ** 2:
                        continue
                    sz = ar.surface(x, y)
                    dz = sz - ar.height(x, y)
                    if 10.0 <= dz <= 35.0 and ar.standable(x, y, 0) and ar.clearance(x, y) >= 4.0:
                        cands.append((x, y, sz))
        except Exception:
            cands = []
        pc = (key, cands, (state.pos[0], state.pos[1]))
        m["perch_cache"] = pc
    cands = pc[1]
    if not cands:
        return None
    sp = m.get("perch_spot")
    if sp is not None and sp in cands:
        return sp
    best = min(cands, key=lambda c: (c[0] - state.pos[0]) ** 2 + (c[1] - state.pos[1]) ** 2)
    if dist2d(best, state.pos) > 220:
        return None
    m["perch_spot"] = best
    return best


def _hold_point(state: WorldState, zp):
    z = state.zone
    if not z:
        return None
    if P["perch"]:
        sp = _perch_point(state)
        if sp is not None:
            if dist2d(sp, state.pos) < 3.0 and abs(state.pos[2] - sp[2]) < 2.0:
                return None
            return sp
    c1, r1 = z["next_center"], float(z["next_radius"])
    d = dist2d(state.pos, c1)
    # stay put if comfortably inside (sitting still is silent); else drift toward the centre
    if d < max(10.0, 0.45 * r1):
        return None
    k = 0.35 * r1
    ux, uy = unit2(state.pos[0] - c1[0], state.pos[1] - c1[1])
    return (c1[0] + ux * k, c1[1] + uy * k, state.pos[2])


# ----------------------------------------------------------------------------- inventory
def inventory(state: WorldState, intent: Intent) -> InvOut:
    out = InvOut()
    m = _mem(state)
    offer = state.obs.get("offer")
    if offer and offer.get("choices"):
        out.pick = _pick_upgrade(state, offer["choices"])
    reach = float(state.cfg.get("loot", {}).get("pickup_radius", 4.0))
    kinds = state.weapon_kinds()
    ws = state.me.get("weapons") or [None, None]
    pk = list(state.obs.get("pickups") or [])
    seen_ids = {p.get("id") for p in pk}
    for r in m["items"].values():   # remembered pickups in reach that the obs does not list (LOS quirks)
        if (r["type"] == "pickup" and r["id"] not in seen_ids and dist2d(r["pos"], state.pos) < reach
                and m["blacklist"].get(r["id"], -1e9) <= state.t):
            pk.append({"id": r["id"], "kind": r.get("kind"), "pos": r["pos"]})
    for p in pk:
        k = p.get("kind")
        if k is None or k in kinds:
            continue
        if dist2d(p["pos"], state.pos) > reach - 0.3 or abs(p["pos"][2] - state.pos[2]) > 3.8:
            continue
        v = WEAPON_VALUE.get(k, 1.0)
        if v <= 0:
            continue
        if kinds[1] is None and kinds[0] is not None:
            out.take = p["id"]
            break
        if kinds[0] is None:
            out.take = p["id"]
            break
        # both full: swap out the worse slot if clearly better (never while a laser charges)
        vals = [WEAPON_VALUE.get(kinds[i] or "", 0) for i in (0, 1)]
        worst = 0 if vals[0] <= vals[1] else 1
        w = ws[worst] or {}
        if v > vals[worst] + 0.5 and not (w.get("kind") == "laser" and (w.get("charge") or 0) > 0):
            out.take, out.drop = p["id"], worst
            break
    return out


def _pick_upgrade(state: WorldState, choices: List[Dict[str, Any]]) -> int:
    best, bv = 0, -1e9
    kinds = state.weapon_kinds()
    for i, c in enumerate(choices):
        cid = c.get("id", "")
        v = UPGRADE_VALUE.get(cid, 1.0)
        if cid.startswith("gun_") and "gun" not in kinds:
            v -= 3
        if v > bv:
            best, bv = i, v
    return best


# ----------------------------------------------------------------------------- reporting
def summary(state: WorldState) -> Dict[str, Any]:
    m = _mem(state)
    last = state.damage_log[-6:]
    cause = "unknown"
    if last:
        zone = sum(a for (_, a, _, w) in last if w == "zone")
        other = sum(a for (_, a, _, w) in last if w != "zone")
        cause = "zone" if zone > other else "outgunned"
    if m.get("stuck_s", 0) > 8:
        cause += "+stuck"
    combat_stats = None
    try:
        from . import combat as _combat
        if hasattr(_combat, "summary"):
            combat_stats = _combat.summary(state)
    except Exception:
        pass
    return {"combat": combat_stats, "mode_guess": state.mode_guess, "evidence": state.mode_evidence, "modes": m["modes"],
            "kills": state.kills, "hp": round(state.hp), "t": state.t, "zone_out_s": round(m["zone_out_s"], 1),
            "cause": cause, "cubes": state.me.get("cubes", 0), "weapons": state.weapon_kinds(),
            "attackers": len(m["attackers_ever"]), "foreign_deaths": m["foreign_deaths"], "last": m.get("last_ctx"),
            "first_weapon_t": m.get("first_weapon_t"), "profile": P.get("profile")}


def debug(state: WorldState, intent: Intent, threats: Threats, nav, cmb) -> Dict[str, Any]:
    d: Dict[str, Any] = {"label": f"{intent.mode} {intent.reason}"[:78]}
    if intent.goal is not None:
        d["points"] = [{"at": [round(intent.goal[0], 1), round(intent.goal[1], 1), round(state.pos[2], 1)], "color": "#40c0ff", "size": 6}]
    return d
