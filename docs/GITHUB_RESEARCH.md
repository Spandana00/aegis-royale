# GitHub bot research and the V8 adaptation

Research date: 2026-11-21. Queries included `mechfight`, `mech royale`, and
`robocode wave surfing`. Six public repositories were inspected at pinned
commits. Full source links, commit IDs, inspected files, and license findings
are recorded in [research_sources.json](research_sources.json).

## Feature ledger

| Repository and inspected source | Useful features found | License in inspected snapshot | Decision |
| --- | --- | --- | --- |
| [Voidious/Diamond: VirtualGunsManager](https://github.com/Voidious/Diamond/blob/2d1c6a2b911cf077c5f13d2baa45da7d18d6babb/voidious/gun/VirtualGunsManager.java) and [MeleeMover](https://github.com/Voidious/Diamond/blob/2d1c6a2b911cf077c5f13d2baa45da7d18d6babb/voidious/move/MeleeMover.java) | Per-opponent ratings for competing aiming models; risk-ranked movement destinations and penalties for revisiting positions | Modified zlib; LICENSE inspected | Adopt the general model-comparison idea through an independent forecast-error implementation. Movement remains V7. |
| [caioplcerda/oval-pilot](https://github.com/caioplcerda/oval-pilot/blob/5b018c72a050d46b57dd111fc08d9eca8c29bdad/bot.py) | Map rasterization, incremental A*, laser/lightning loadout preference, cube collection and cover memory | MIT; original and modification notices inspected | Record alternatives; retain our current navigation and loadout for this experiment. |
| [shreypatel1/quokka-lattice-7f3k](https://github.com/shreypatel1/quokka-lattice-7f3k/blob/c56e4afa920f5f3495f29407fa718fca9b4fba62/bot.py) | Enemy tracks, flow-based navigation, projectile leading, gun-preserving weapon swaps, holding laser charge after losing sight | MIT; LICENSE inspected | Tracking and gun-preserving swaps are already present in AEGIS. Charge preservation is a separate possible experiment. |
| [nguyenphuquang1234567/kestrel: combat](https://github.com/nguyenphuquang1234567/kestrel/blob/c1c53d120145ef3235664adf981e72dc93ae37d8/bot/combat.py) and [brain](https://github.com/nguyenphuquang1234567/kestrel/blob/c1c53d120145ef3235664adf981e72dc93ae37d8/bot/brain.py) | Barrel-offset interception, mortar arcs, projectile danger vectors, laser-charge retention and pickup-failure handling | No repository license detected | Concepts recorded; no source code ported. Preserve V7's other weapon behavior. |
| [sphugne/mech-royale-bot](https://github.com/sphugne/mech-royale-bot/blob/3018b5d8996e71c1cf0c0f824e545f4cb0b6ff33/README.md) | Separate movement, combat, evasion, recovery and firing experiments | No repository license detected | Its README self-reports 2.19 for a duel variant and lower results for some retreat changes. These are unverified author reports, not evidence of a stronger bot than AEGIS. |
| [mahathio/mechfight](https://github.com/mahathio/mechfight/blob/497f4647b978ec649d22a22cd3d06b7eabbd41d1/our_bot_trial3.py) | Low-health target priority, position-difference lead, alternating strafes | No repository license detected | Useful basic comparison; no implementation adopted. |

These are feature observations from source, not independently verified Mech
Royale rankings. Diamond is a different, two-dimensional game. None of the
inspected repositories establishes that copying a feature will achieve 5.30
in this event.

The [oval-pilot simulator](https://github.com/caioplcerda/oval-pilot/blob/5b018c72a050d46b57dd111fc08d9eca8c29bdad/tools/sim.py)
explicitly describes itself as approximate and unsuitable for predicting the
real score. It was read but not executed or adopted as an official scorer.

## What V8 actually implements

V8 keeps V7's scored range control, fight selection, healing, upgrades, loot,
navigation, and shared-weapon firing schedule. It adds a small, independent
Python module that compares two horizontal aiming forecasts within a match:

- The existing constant-velocity linear forecast.
- A circular forecast based on recent observed changes in the target's heading.

At most six nearby mech tracks receive new forecasts each observation. The
learner stores bounded predictions for the approximate bullet arrival time.
Only after that time has passed does it compare predictions with interpolated
observed positions. Lateral error matters most; radial error has lower weight.
No future observation is used when issuing a forecast.

Linear aim remains the default. Circular aim requires at least six completed
forecast comparisons, three consecutive turning observations, sufficient
heading change, and a material measured error reduction. Visibility gaps or
large position discontinuities reset learning. NPC and crate aim is unchanged.
An obstructed, out-of-range, or invalid learned aim can fall back to V7's
original firing solution. The existing torso-alignment gate still controls
whether the gun fires.

This is inspired by virtual-gun model comparison. It is not a port of
Diamond's wave, scoring, or clustering implementation. All new runtime code
was independently written; no third-party source is included in the image.
The other inspected features were not silently combined into this candidate.

## Rejected trial and limitations

An unpublished four-model trial also included damped and head-on forecasts.
It reduced errors on circling paths but increased lateral forecast error on
the reversing-path diagnostic from 2.9311 m to 3.1341 m RMS. Those alternatives
were removed rather than submitted. Its raw diagnostic is retained in
[aiming_four_model_diagnostic.json](aiming_four_model_diagnostic.json).

The final two-model diagnostic covered 117 scripted eight-second trajectories
and 9,360 online forecasts. Straight-line and reversing-path forecasts stayed
at the baseline. Circular-path RMS lateral error decreased from 1.9862 m to
1.0578 m over the complete sequences, including learning time. Raw results are
in [aiming_validation.json](aiming_validation.json).

These measurements are forecast errors, **not actual hit rates, kills, damage,
or placement points**. The diagnostic omits torso slew, spread, buildings,
enemy decisions, health and strategic interaction. Future enemy steering can
change after an observation, and a learned model can still be wrong in a match.

## Runtime and validation

- Standard-library Python; no network or model service at runtime.
- At most 16 learned tracks and 12 pending forecast groups per track.
- 42 tests pass, including temporal ordering, bounded state, cold-start
  equivalence, linear motion, circular interception and blocked-aim fallback.
- All 300 official recorded protocol observations were answered in time.
- The single-core benchmark handles 720 observations, including 104 with a
  learned model selected: p99 13.11 ms, maximum 17.43 ms, zero over 50 ms,
  peak process RSS 32.24 MiB on this host.
- The pinned linux/amd64 Docker image copies `aiming.py`, and the build allowlist
  includes it. GitHub Actions runs
  the exact uid-65534, read-only, network-disabled competition sandbox check.

Reproduce the diagnostics from the repository root:

```sh
python3 -B check/compare_versions.py > docs/run_comparison.json
python3 -B -m unittest discover -s tests -v
python3 -B check/aiming_probe.py
taskset -c 0 python3 -B check/benchmark.py
```

V7's user-reported scores are **4.60** and **4.52**. V8 is unscored. Keep V7's
4.60 submission selected until an official run provides a better result.
