# V9: acquire useful equipment while maintaining pressure

**Result:** V9 scored **4.77**. This is the historical V9 experiment; V10 uses the policy described in [V10_COMPARISON.md](V10_COMPARISON.md).

## Why change direction

V7's reported best was 4.60 (repeat 4.52). V8 also scored 4.60. Its better
forecast errors on scripted circling targets did not produce an observed
placement gain. Broader retreat changes scored 3.96, stronger dodging 4.40,
and reload detours 4.17/4.15. Those experiments are not accumulated here.

One concrete V8 behavior remains: a shootable rival inside 65 m can override
a nearby second-weapon destination even when we have only the starting gun.
It can similarly override collection of nearby kill cubes. Orbiting and firing
can then continue without collecting resources that strengthen later fights.
This is a source-level finding, not a measured frequency or cause of our deaths.

## Additional primary sources

All links pin the inspected source. Author-reported scores are not independently
verified, and none establishes that its bot is stronger than AEGIS.

| Resource | Useful evidence or feature | Decision |
| --- | --- | --- |
| [pnp6113: experiment log](https://github.com/pnp6113/mech-royale-bot/blob/ec18871d4e85821f53387a263890cc34d25d449b/docs/EXPERIMENTS.md), [brain](https://github.com/pnp6113/mech-royale-bot/blob/ec18871d4e85821f53387a263890cc34d25d449b/brain.py) | Author reports 3.79 → 4.04 after pursuing second weapons during fights, then 4.29 → 4.48 with a laser-focused package. Its local simulator was an imperfect predictor. | Independently implement equipment collection, preserve gun fire, and require an official run. Do not copy its entire policy. |
| [Not-Ethan: brain](https://github.com/Not-Ethan/oval-ghost-mech/blob/0d62979a437c9e6f79c0fc2ca3d1fcf9bb96b85a/src/brain.ts) | Separate cover, route and weapon decisions; bounded map work. | Retain our existing campus navigation rather than replace it wholesale. |
| [Epicepicdemic: doctrine](https://github.com/Epicepicdemic/buildathon-mech-royale/blob/70e4ba904c2b71917fc89ce0a4b1b40707ae21ae/mech/doctrine.py), [replay tooling](https://github.com/Epicepicdemic/buildathon-mech-royale/blob/70e4ba904c2b71917fc89ce0a4b1b40707ae21ae/tools/replays.py) | Explicit combat doctrine and diagnostics for locally captured spectator replays. | Record the diagnostic approach. These files do not supply our private practice replays or match engine. |

GitHub identifies these three snapshots as MIT licensed. No external source
code was copied or executed. Other inspected repositories and earlier research
are listed in [research_sources.json](research_sources.json).

## Implemented policy

- With only a gun or a mortar secondary, prioritize a laser/lightning pickup
  within 80 m when health is at least 52% and at most one exposed mech is
  within 115 m. Continue shooting the existing target while navigating there.
- Prioritize cubes within 20 m until the ten-cube stat cap, subject to the same
  safety conditions. Ordinary collection after the cap retains V8 behavior.
- Reject a detour whose straight approach enters an opponent's estimated
  lightning range, or a detour longer than 12 m that passes over 8 m closer
  to an exposed attacker. Future-zone, height and reachability checks apply.
  During contact, approaches over 20 m must also be directly traversable.
- Evaluate collision/reachability for at most four ranked resource candidates
  per decision. Existing navigation and projectile avoidance still execute.
- Prefer a laser without a directly shootable opponent inside 65 m; prefer
  lightning during close contact. Preserve the gun, never discard a charging
  laser, and wait four seconds after a confirmed pickup before swapping
  between useful secondaries again.
- Preserve urgent zone escape and recovery priority. Firing solutions, combat
  spacing, target selection, upgrade scoring, recovery thresholds and map
  navigation are unchanged from V8.

This changes one coherent policy family: obtaining and choosing equipment.
It changes actual movement and pickup choices rather than another aiming
parameter. A resource detour can still be a mistake: distant shared-vision
opponents can converge, and a pickup may disappear before arrival.

## Validation and limits

The policy regressions check observable actions: moving toward an available
secondary while firing, collecting a safe nearby cube, refusing approach
through an attacker, refusing a blocked long detour, preserving recovery/zone
priority, choosing secondaries by distance, and preserving a charging laser.
Mutable bot state is isolated between tactical tests.

Results from the final local checks are in [armament_validation.json](armament_validation.json).
The source audit in [run_comparison.json](run_comparison.json) checks V9's scope
against the exact scored V8 commit. GitHub Actions additionally builds the
pinned linux/amd64 image and runs the organizer's checker with one CPU,
512 MB, uid 65534, read-only root and no network.

These checks establish behavior and compatibility, not placement. We do not
have a faithful local copy of the private house-bot scorer or per-match
telemetry from our scored runs. There is no defensible forecast of 5.30 or
6.01. Score this exact candidate, record the result, and keep the earlier
4.60 entry selected unless the new official score improves it.
