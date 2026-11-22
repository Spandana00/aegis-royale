use super::*;
use crate::proto::{ActorKind, ActorObs, Obs, UpgradeDef, WeaponObs};

fn scenario(beam: bool, motion: bool, cubes: f64, hp: f64, mortar: bool) -> (Brain, Obs) {
    let mut hello = proto::Hello::default();
    hello.config.upgrades = vec![serde_json::from_str::<UpgradeDef>(
        r#"{"id":"armor","max":3,"effects":[{"path":"mech.armor","add":0.08}]}"#,
    ).unwrap()];
    let world = crate::world::World::empty();
    let nav = crate::nav::Nav::build(&world, &hello.config.mech);
    let shared = Arc::new(Shared { world, nav });
    let mut p = Params::default();
    p.beam_damage_fix = beam;
    p.aim_motion_fix = motion;
    let mut b = Brain::with_params(&hello, shared, p);
    b.mode = Mode::Fight;
    b.target = Tgt::Mech(2);
    let mut o = Obs::default();
    o.tick = 1000;
    o.t = 50.0;
    o.alive = 16;
    o.me.id = 1;
    o.me.pos = [0.0; 3];
    o.me.hp = 1400.0;
    o.me.max_hp = 1400.0;
    o.me.energy = 100.0;
    o.me.max_energy = 100.0;
    o.me.in_zone = true;
    o.me.grounded = true;
    o.me.cubes = cubes;
    o.me.stats = hello.config.mech.clone();
    o.me.aim = [0.0, (-2.5f64).atan2(80.0)];
    o.me.weapons = [None, Some(WeaponObs { kind: WeaponKind::Laser, charge: 0.15,
        stats: hello.config.weapons.laser.clone(), ..Default::default() })];
    o.mechs.push(ActorObs { id: 2, kind: ActorKind::Mech, pos: [80.0,0.0,0.0],
        vel: [0.0;3], aim: [std::f64::consts::PI,0.0], hp: Some(hp), max_hp: Some(1736.0),
        cubes: 6.0, weapons: if mortar { vec![WeaponKind::Gun,WeaponKind::Mortar] } else { vec![WeaponKind::Gun] },
        charging: false });
    b.mem.update(&o, &b.shared.world, &b.cfg);
    (b, o)
}

fn fire(b: &mut Brain, o: &Obs) -> super::aim::FireOut {
    let shared = b.shared.clone();
    b.fire_control(o, &shared.world)
}

#[test]
fn partial_beam_does_not_claim_a_kill_that_hidden_armor_prevents() {
    // 0.15 s gives 151.2 raw damage but only 114.912 after three armor stacks.
    let (mut old, o) = scenario(false, false, 0.0, 130.0, false);
    assert!(!fire(&mut old, &o).fire[1]);
    let (mut fixed, o) = scenario(true, false, 0.0, 130.0, false);
    assert!(fire(&mut fixed, &o).fire[1], "hold: the 130-HP target survives this partial beam");
}

#[test]
fn cube_damage_and_cookoff_allow_conservative_early_finishes() {
    let (mut old, o) = scenario(false, false, 10.0, 145.0, false);
    assert!(fire(&mut old, &o).fire[1]);
    let (mut cubes, o) = scenario(true, false, 10.0, 145.0, false);
    assert!(!fire(&mut cubes, &o).fire[1], "160.8768 effective damage covers HP plus 15");
    let (mut cookoff, o) = scenario(true, false, 0.0, 160.0, true);
    assert!(!fire(&mut cookoff, &o).fire[1], "mortar cookoff covers HP plus 15");
}

#[test]
fn rounded_full_charge_releases_even_when_partial_damage_is_not_lethal() {
    let (mut b, mut o) = scenario(true, false, 0.0, 1300.0, false);
    let w = o.me.weapons[1].as_mut().unwrap();
    w.stats.charge = 0.5625;
    w.charge = 0.56;
    assert!(!fire(&mut b, &o).fire[1]);
}

#[test]
fn translating_laser_duel_aims_at_relative_motion() {
    let (mut b, mut o) = scenario(false, true, 0.0, 1300.0, false);
    o.me.vel = [0.0,11.7,0.0];
    o.mechs[0].vel = o.me.vel;
    o.me.weapons[1].as_mut().unwrap().charge = 0.70;
    b.mem.update(&o, &b.shared.world, &b.cfg);
    let fc = fire(&mut b, &o);
    assert!(fc.aim[0].abs() < 1e-12, "equal lateral velocities cancel during command latency");
}

#[test]
fn gun_projects_the_origin_for_latency_without_inheriting_shooter_velocity() {
    let (mut b, mut o) = scenario(false, true, 0.0, 1300.0, false);
    o.me.vel = [0.0,11.7,0.0];
    o.me.weapons = [Some(WeaponObs { kind: WeaponKind::Gun, ammo: 12.0,
        stats: b.cfg.weapons.gun.clone(), ..Default::default() }),None];
    let fc = fire(&mut b, &o);
    let expected = (-11.7 * 0.05f64).atan2(80.0);
    assert!((fc.aim[0]-expected).abs() < 1e-10);
}

#[test]
fn cube_budget_does_not_invent_armor_for_a_zero_cube_hunter() {
    let (mut b, mut o) = scenario(true, false, 0.0, 130.0, false);
    o.mechs[0].cubes = 0.0;
    b.mem.update(&o, &b.shared.world, &b.cfg);
    assert!(fire(&mut b, &o).fire[1], "unbounded estimate holds unnecessarily");
    Arc::make_mut(&mut b.p).beam_armor_budget = true;
    assert!(!fire(&mut b, &o).fire[1], "zero cubes cannot have earned an armor offer");
    o.mechs[0].cubes = 1.0;
    b.mem.update(&o, &b.shared.world, &b.cfg);
    assert!(fire(&mut b, &o).fire[1], "one earned armor stack can prevent the finish");
}

#[test]
fn cube_bounded_estimate_is_safe_for_every_legal_armor_stack_count() {
    let (mut b, mut o) = scenario(true, false, 0.0, 130.0, false);
    Arc::make_mut(&mut b.p).beam_armor_budget = true;
    for cubes in 0..22 {
        o.mechs[0].cubes = cubes as f64;
        b.mem.update(&o, &b.shared.world, &b.cfg);
        let tr = b.mem.tracks.iter().find(|tr| tr.id == 2).unwrap();
        let lower = b.aim_target(tr).beam_mult;
        let offers = b.cfg.cubes.upgrade_thresholds.iter().filter(|&&n| n <= cubes as f64).count();
        for armor_stacks in 0..=offers.min(3) {
            let actual = 1.0 - 0.08 * armor_stacks as f64;
            assert!(lower <= actual + 1e-12, "{cubes} cubes and {armor_stacks} armor stacks");
        }
    }
}

#[test]
fn shared_aim_preserves_laser_release_and_recovers_a_ready_gun_shot() {
    let (mut b, mut o) = scenario(false, false, 0.0, 1300.0, false);
    o.mechs[0].cubes = 0.0;
    o.mechs[0].vel = [0.0,7.6,0.0];
    o.me.weapons[0] = Some(WeaponObs { kind: WeaponKind::Gun, ammo: 12.0,
        stats: b.cfg.weapons.gun.clone(), ..Default::default() });
    o.me.weapons[1].as_mut().unwrap().charge = 0.70;
    b.mem.tracks.clear();
    b.mem.update(&o, &b.shared.world, &b.cfg);
    let original = fire(&mut b, &o);
    assert!(!original.fire[0]);
    assert!(!original.fire[1], "the laser releases");
    Arc::make_mut(&mut b.p).aim_share = true;
    let combined = fire(&mut b, &o);
    assert!(combined.fire[0], "gun fires without delaying the beam");
    assert!(!combined.fire[1], "the laser still releases");
    let ty = (2.0f64).atan2((80.0f64*80.0+2.5*2.5).sqrt());
    assert!(super::math::adiff(combined.aim[0],original.aim[0]).abs()*original.aim[1].cos() <= 0.5*ty+1e-9);
    o.me.weapons[0].as_mut().unwrap().cooldown = 0.4;
    assert_eq!(fire(&mut b, &o).aim, original.aim, "cooling gun does not pull laser off center");
}
