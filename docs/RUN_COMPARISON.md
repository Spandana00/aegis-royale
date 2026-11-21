# Official run comparison and next experiment

## What the submitted runs show

Scores below come from the user's submission screenshots. Every comparison is
against the best scored version, **V2 at 4.50**, rather than simply against the
previous submission. V3–V6 each used V2 as their semantic code baseline; they
did not accumulate every earlier experiment, even though git history retains
all the submitted commits.

| Version | Reported score | Difference from V2 | Change being tested |
| --- | ---: | ---: | --- |
| V1 | 3.75 | −0.75 | Initial bot |
| V2 | **4.50** | — | Coordinated gun/laser/lightning fire; tighter aim; weapon-specific distance; weapon upgrade priorities; persistent recovery; navigation fixes |
| V3 | 3.96 | −0.54 | Earlier and broader recovery, stricter fights and loot, different cover, healing drops, earlier rotations |
| V4 | 4.40 | −0.10 | Acceleration-aware projectile dodging and fourfold dodge priority |
| V5 | 4.17; repeat 4.15 | −0.33; −0.35 | Short cover trips during gun reloads |
| V6 | 4.46 | −0.04 | Gun prediction for falling targets and landings |

The two V5 screenshots show the same `1f…` commit prefix, matching the V5
commit in this repository. The one-point difference across 48 matches rounds
to 0.02 score. This demonstrates some run variation; it does not provide a
statistical error bound. V6's small difference from V2 should not be treated
as proof that correcting falling-target aim is harmful.

## Which features have evidence behind them

The only observed aggregate improvement is the **V1 → V2 bundle**, worth 0.75
points. Several things changed together, so these results cannot identify the
individual placement contribution of aim, upgrades, healing, or navigation.
Code regressions established specific V1 failures independently of score:

- A ready laser could take over the common aim while the gun still needed
  its projectile intercept. V2 schedules those triggers separately.
- Lightning's yaw cone was incorrectly gated by another weapon's pitch.
- Recovery could restart combat just above half health and reset its regen.
- Combat movement could ignore an obstacle route, or reject every long
  movement candidate and fail to take a safe short step.

These fixes are retained. V2 also increased the preferred gun/laser distances
and gave magazine and weapon-damage upgrades higher priority. Their individual
score effects remain unmeasured, but they belong to the only improved bundle.

V3's broad retreat changes and V5's reload detours scored materially below V2.
The V4 evasion and V5 exposure probes improved their local metrics without
improving official placement. Those probes should remain correctness tools,
not a basis for forecasting a score.

## V7: optimize an existing V2 feature

V7 restores **V2's exact firing, target selection, upgrade priorities, loot,
healing, zone policy, projectile dodge cost, and map navigation**. It tests
only combat range control against a lightning opponent when keeping distance
can deny that opponent's short-range weapon.

Two concrete problems exist in V2's implementation of that feature:

1. At the intended firing distance, V2 chooses an almost purely sideways
   orbit. It does not compensate for a pursuer moving toward it. Even at its
   maximum backward setting, its diagonal orbit requests only about two
   thirds of its available speed away from the opponent.
2. One Tesla coil increases lightning reach from 45 m to 54 m, but V2's
   preferred distance remains `0.82 × 54 = 44.28 m`, inside an unupgraded
   opponent's 45 m reach. It gives away its upgrade's range advantage.

V7 adds the observed opponent's radial velocity to the distance controller.
It uses remaining horizontal speed for strafing and leaves projectile and
charging-laser avoidance active. It uses V2's existing boost policy and the
actual speed after laser charging penalties; it does not add escape detours
or pause ordinary firing.

When its own lightning has enough range advantage, V7 stays near the outer
part of that range. The opponent's possible reach is conservatively bounded
by assuming every offer unlocked by its cube count could have been a Tesla
coil, up to the configured stack cap. Height difference also limits our own
usable horizontal reach. The late-zone distance cap remains active.

This change trades some sideways speed for backward speed against a closing
short-range opponent. That can make gun leading easier for an enemy; local
projectile avoidance can also pull the bot away from the desired distance.
Only an official run can determine the net placement effect. No new proxy
score or claim of a 5.30 result is being used to justify the candidate.

## Source cross-check and evaluation

`check/compare_versions.py` reads every submitted revision, records hashes of
the runtime files, and compares method syntax trees against V2. For V7 it
rejects changes outside `engagement_distance`, `steer`, and the new
`enemy_lightning_range` helper. It also checks that the map reader, navigator,
protocol wrapper, and Dockerfile are byte-identical to V2.

```sh
python3 -B check/compare_versions.py > docs/run_comparison.json
python3 -B -m unittest discover -s tests -v
python3 check/check.py -- python3 -B -u bot.py
python3 -B check/benchmark.py
```

The 31 tests include closing and stationary opponents, preserving aligned gun
fire, conservative enemy upgrade bounds, actual lightning range advantage,
and late-zone constraints. These validate scope and behavior, not placement.
All 300 recorded protocol observations were answered within the deadline.
The single-core 600-observation stress check had no invalid actions or answers
over 50 ms (p99 13.12 ms, maximum 18.69 ms on this host). The published GitHub
workflow builds linux/amd64 and runs the Docker sandbox conformance check.

Keep V2's 4.50 entry selected while scoring V7 once. Across 48 matches, 4.50
represents 216 placement points. Reaching at least 5.30 requires at least 255,
or 39 more total placement points. If V7 does not improve the official result,
reject this change rather than combining it with more unmeasured changes.
