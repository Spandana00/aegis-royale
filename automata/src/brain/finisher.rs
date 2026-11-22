//! One bounded resource deferral for an already charged, aligned laser shot.
use super::{Brain, memory::Track, math::*};
use crate::{proto::{ActorKind, Obs, WeaponKind}, world::World};

impl Brain {
    pub(crate) fn finish_resource_grace(&mut self, obs: &Obs, world: &World, tr: Option<&Track>) -> bool {
        if self.p.finish_grace_s <= 0.0 { return false; }
        let Some(tr) = tr else { self.finish_window = None; return false };
        if self.finish_window.is_some_and(|(id, _)| id != tr.id) { self.finish_window = None; }
        if tr.kind != ActorKind::Mech || !(tr.hp > 0.0) || obs.t - tr.last_seen > 0.15 { return false; }
        // A capture already in progress keeps its established priority.
        if obs.drops.iter().any(|d| d.holder == Some(obs.me.id) && d.progress > 0.0) { return false; }
        let Some(w) = obs.me.weapons.iter().flatten().find(|w| w.kind == WeaponKind::Laser) else { return false };
        if w.cooldown > 0.1 || w.charge < w.stats.charge.max(0.05) - 0.051
            || tr.hp > w.stats.damage * 0.5 { return false; }
        let muzzle = up(obs.me.pos, obs.me.stats.muzzle_height);
        let Some((at, allow)) = self.pick_fire_target(obs, world, muzzle) else { return false };
        if !allow || at.id != tr.id { return false; }
        let rel = sub(up(at.feet, at.height * 0.5), muzzle);
        let d = len(rel).max(0.1);
        if d > w.stats.range * 0.98 || world.ray(muzzle, up(at.feet, at.height * 0.5)).is_some() { return false; }
        let direct = dir_to_aim(add(rel, scale(at.vel, self.p.laser_latency)));
        let pred = slew(obs.me.aim, direct, obs.me.stats.turn_rate * 0.05, obs.me.stats.pitch_rate * 0.05);
        if adiff(pred[0], direct[0]).abs() * direct[1].cos().max(0.2) > (at.radius * self.p.aim_tol).atan2(d)
            || (pred[1] - direct[1]).abs() > (at.height * 0.5 * self.p.aim_tol).atan2(d) { return false; }
        let (_, until) = *self.finish_window.get_or_insert((tr.id, obs.t + self.p.finish_grace_s.min(0.6)));
        // Never extend the window each tick if a shot misses or the target survives.
        obs.t < until
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{Shared, nav, proto};
    use super::super::{Params, Tgt, Mode};
    use std::sync::Arc;

    fn fixture() -> (Brain, Obs, Track) {
        let h = proto::Hello::default();
        let world = World::empty();
        let shared = Arc::new(Shared { nav: nav::Nav::build(&world, &h.config.mech), world });
        let mut p = Params::default(); p.finish_grace_s = 0.6;
        let mut b = Brain::with_params(&h, shared, p);
        let mut o = Obs::default(); o.t = 10.0; o.me.id = 0;
        o.me.hp = 1400.0; o.me.max_hp = 1400.0; o.me.in_zone = true; o.me.energy = 100.0;
        o.me.stats = h.config.mech.clone();
        o.me.weapons[1] = Some(proto::WeaponObs { kind: WeaponKind::Laser,
            charge: h.config.weapons.laser.charge, stats: h.config.weapons.laser.clone(), ..Default::default() });
        let tr = Track { id: 1, kind: ActorKind::Mech, pos: [30.0,0.0,0.0], vel: [0.0;3], acc: [0.0;3],
            aim: [0.0;2], hp: 100.0, max_hp: 1400.0, cubes: 0.0, weapons: vec![WeaponKind::Gun],
            charging: false, charge_since: 0.0, last_seen: o.t, dmg_to_us: 0.0, last_dmg_t: o.t };
        b.mem.tracks.push(tr.clone()); b.target = Tgt::Mech(1);
        (b,o,tr)
    }

    #[test]
    fn ready_visible_aligned_shot_activates_once_and_expires() {
        let (mut b,mut o,mut tr) = fixture(); let world = World::empty();
        assert!(b.finish_resource_grace(&o,&world,Some(&tr)));
        o.t += 0.7; tr.last_seen = o.t; b.mem.tracks[0] = tr.clone();
        assert!(!b.finish_resource_grace(&o,&world,Some(&tr)));
        assert!(!b.finish_resource_grace(&o,&world,Some(&tr)));
    }

    #[test]
    fn rejects_unready_or_nonlethal_or_stale_shot() {
        let (mut b,mut o,mut tr) = fixture(); let world = World::empty();
        o.me.weapons[1].as_mut().unwrap().charge = 0.0;
        assert!(!b.finish_resource_grace(&o,&world,Some(&tr)));
        o.me.weapons[1].as_mut().unwrap().charge = 1.0; tr.hp = 1000.0;
        assert!(!b.finish_resource_grace(&o,&world,Some(&tr)));
        tr.hp = 100.0; tr.last_seen = o.t - 1.0;
        assert!(!b.finish_resource_grace(&o,&world,Some(&tr)));
    }

    #[test]
    fn disabled_feature_and_different_firing_target_preserve_baseline() {
        let (mut b,o,tr) = fixture(); let world = World::empty();
        Arc::make_mut(&mut b.p).finish_grace_s = 0.0;
        assert!(!b.finish_resource_grace(&o,&world,Some(&tr)));
        Arc::make_mut(&mut b.p).finish_grace_s = 0.6; b.mem.tracks.clear();
        assert!(!b.finish_resource_grace(&o,&world,Some(&tr)));
    }

    #[test]
    fn preserves_capture_and_rejects_bad_alignment() {
        let (mut b,mut o,tr) = fixture(); let world = World::empty();
        o.drops.push(proto::DropObs { holder: Some(o.me.id), progress: 2.0, ..Default::default() });
        assert!(!b.finish_resource_grace(&o,&world,Some(&tr)));
        o.drops.clear(); o.me.aim[0] = std::f64::consts::PI;
        assert!(!b.finish_resource_grace(&o,&world,Some(&tr)));
    }

    #[test]
    fn defers_actual_cube_goal_but_preserves_urgent_zone_and_retreat() {
        let (mut b,mut o,_) = fixture();
        Arc::make_mut(&mut b.p).gear_on = 1.0;
        o.zone = proto::ZoneObs { radius: 1000.0, next_radius: 900.0,
            shrink_start: 200.0, shrink_end: 300.0, ..Default::default() };
        b.mem.cubes.push(super::super::memory::Item { id: 5000, pos: [5.0,5.0,0.0], hp: 0.0,
            kind: WeaponKind::Unknown, last_seen: o.t, misses: 0 });
        let shared = b.shared.clone();
        Arc::make_mut(&mut b.p).finish_grace_s = 0.0;
        b.decide(&o, &shared.world, &shared.nav);
        assert_eq!(b.mode, Mode::Loot); assert_eq!(b.goal_id, 5000);
        Arc::make_mut(&mut b.p).finish_grace_s = 0.6;
        b.decide(&o, &shared.world, &shared.nav);
        assert_eq!(b.mode, Mode::Fight); assert_eq!(b.target, Tgt::Mech(1));
        o.me.in_zone = false;
        b.decide(&o, &shared.world, &shared.nav);
        assert_eq!(b.mode, Mode::Zone);
        o.me.in_zone = true; o.me.hp = 200.0; b.mode = Mode::Retreat;
        b.decide(&o, &shared.world, &shared.nav);
        assert_eq!(b.mode, Mode::Retreat);
    }
}
