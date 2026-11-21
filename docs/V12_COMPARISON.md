# V12: feature evidence and selected candidate

**Selected experiment: retain bounded V11 arming and add grounded combat boost.**
V12 has no official score. The target is 6.00; the measurements below do not
establish that target. V10's reported official 5.33 remains the best entry.

## Official baseline

| Version | Exact commit | User-reported official score | Receipt |
| --- | --- | ---: | --- |
| V10 | `d75253a91ccb4d199d4374c076ee0d58c383e590` | 5.33 | BB-DC5BDF45 |
| V11 | `be5f383d11735740a283aa730d0a66344b496e85` | 5.25 | BB-524096D2 |

The difference is four placement points over 48 matches. With only one result
per policy it does not isolate the effect of V11's arming behavior. A 6.00 run
needs 288 placement points, 32 above V10's 256 and 36 above V11's 252.

## What the stronger public repositories actually establish

Repository searches returned 127 candidate repositories; 55 source trees were
inspected. Unrelated games and repositories without a useful score history
were excluded from competitive score conclusions. Pinned sources are recorded
in [v12_research.json](v12_research.json).

| Repository / policy | Available score evidence | Mean and limits |
| --- | --- | --- |
| [aqilc, far5](https://github.com/aqilc/mech-royale/blob/fdfe7a609cc55eb338f277dfc68560cb944a71ef/bots/gang/brain.ts) | Source comments report 5.67 and 5.60 for the `8ed48da` source | **5.635 over two reported draws**; no independent receipts or complete submission history |
| [aqilc, farx](https://github.com/aqilc/mech-royale/blob/fdfe7a609cc55eb338f277dfc68560cb944a71ef/bots/farxk/brain.ts) | Author reports 5.71; fare 5.69 and their combination 5.58 | Single draws of different policies, not a repeated-policy average; combining features can lose points |
| [JuanQuenga, good-31 family](https://github.com/JuanQuenga/buildathon-mech-royale/blob/b50b794522c134d9eb54cc2e9bc4782f4f4a3da9/docs/REVIEW.md) | Nine reported family draws, including the 5.56 best | **5.341** mean; this was not a 5.60-average reference |
| [justnau, giddygiddyboy](https://github.com/justnau/giddygiddyboy-mech-royale) | [Another participant](https://github.com/Arnav-M10/BuildersMechRoyale/blob/d177f3c3b4174d5523a11ba29a688db3d5b6c8ce/dev/OVERNIGHT.md) reports 5.54 then 6.00 with different squad settings | No verified same-policy average. The newer inspected source removes the historical combat-boost setting |

No inspected repository supplied a verified complete history proving a 5.60+
average across all its runs. The two-draw far5 mean is the closest supported
reference; author reports remain distinct from verified official receipts.

The actual far5 source at `8ed48da5e0ca7b01097019d1a1038c892e1fd174`
passed the organizer's checker with Node 24.22.3. Eight matched proxy seeds
3200-3207 gave far5 5.125 versus the exact V10's 5.500. The paired difference
was -0.375 with an interval approximately [-2.32, +1.57]. This small sample
does not rank the policies. The original reference image uses Bun; the local
Node run is an additional runtime difference.

## Feature ranking and adaptation decisions

This ranking is for the next experiment, not a claimed causal contribution to
official score. New behavior is independently implemented in Python; the
existing MIT-licensed Juan Quenga foundation retains its original attribution.

| Priority | Feature | Reference / comparison with ours | Decision |
| --- | --- | --- | --- |
| 1 | Grounded combat sprint while retaining bounded arming | Giddy's historical `FightBoost=40`; V10/V11 do not sprint during ordinary engage strafing | **Enable in V12**: positive point estimate on both fresh pursuit models |
| 2 | Acceleration and projectile motion lookahead | Far5 predicts candidate paths; our navigator blends a range controller with a dodge vector | Keep disabled: moderate model improves, faster pursuit regresses |
| 3 | Pursuer-aware range control | Our original V7 tracked radial closing speed; current V10 navigator does not | Keep disabled: combined development screen improves, but incurs 108.6 mean zone damage; no fresh confirmation |
| 4 | Missing/contested pickup rejection | Farx stops chasing a pickup absent from a clear view or likely to be claimed first; ours retains pickups until a close check or timeout | Keep disabled: first screen below control; do not assume a rival's straight-line distance proves it will arrive first |
| 5 | Stronger target commitment | Giddy gives a large score preference to its current target; ours chooses a damage-race target every observation | Keep disabled: first screen below control; our implementation changes selection preference without falsifying the actual damage-race ratio |
| 6 | Wider engagement bands | Far5 widens selected gun/laser fights; ours already has weapon-specific ranges and prioritizes lightning reach | Keep disabled: first screen below control; preserve lightning reach and late-circle contraction |

The previously scored AEGIS experiments also discourage blindly adding stronger
dodging, reload-cover trips or broader retreat. V4 scored 4.40, V5 4.17/4.15,
and V3 3.96 versus V2's 4.50. V7's range change scored 4.60/4.52; V8's adaptive
aim tied 4.60; V9's equipment family scored 4.77. V10's policy replacement
scored 5.33. Those are bundle comparisons, not isolated feature effect sizes.

## Development screens

All values below are **local proxy placement points**, not official results.
The first screen uses 16 seeds 3300-3315 and a control with V11 inventory
ordering and the zero-HP guard, but arming disabled. It is not byte-identical V10.

| First-screen arm | Mean | Difference from same control |
| --- | ---: | ---: |
| Control | 4.8750 | — |
| Bounded arming | 5.1875 | +0.3125 |
| Combat boost only | 5.1250 | +0.2500 |
| Pursuer-aware range only | 5.0000 | +0.1250 |
| Pickup race / missing item checks | 4.6875 | -0.1875 |
| Target commitment | 4.6250 | -0.2500 |
| Wider engagement bands | 4.5625 | -0.3125 |

The structural screen reuses these development seeds but loads the **exact V10
checkout** as its baseline. Candidates retain V11 inventory ordering and the
numeric guard. Therefore the package differences below do not isolate only
the feature in the row name.

| Structural-screen package | Mean | Difference from exact V10 |
| --- | ---: | ---: |
| Exact V10 | 4.6250 | — |
| V11 arming package | 5.0000 | +0.3750 |
| Lookahead without arming | 5.0625 | +0.4375 |
| Arming + lookahead | 5.6250 | +1.0000 |
| **Arming + combat boost** | **5.7500** | **+1.1250** |
| Arming + pursuer-aware range | 5.5625 | +0.9375 |

These screens selected two finalists. They were not used to forecast official
score. Early harness parsing failures are excluded from these tables; the
published raw file contains the completed experiments only.

## Fresh-seed validation

The simulator is pinned at `b50b794522c134d9eb54cc2e9bc4782f4f4a3da9`.
Both models use the production process guard. Moderate pursuit uses
`join_per_loss=0.6`, seeds 4000-4023; faster pursuit uses 1.0, seeds 4100-4123.
Each row plays 24 matches per model with the same seeds, spawn slot and setup.

| Package | Moderate pursuit | Faster pursuit | Pooled mean, 48 matches |
| --- | ---: | ---: | ---: |
| Exact V10 | 5.0833 | 3.8333 | 4.4583 |
| V11 arming package | 5.4167 | 3.7917 | 4.6042 |
| **V12: arming + combat boost** | **5.4583** | **3.9583** | **4.7083** |
| Arming + lookahead | 5.7083 | 3.6250 | 4.6667 |

V12's pooled paired difference from V10 is **+0.2500**, with a 95% interval
approximately **[-0.3622, +0.8622]**. It wins 23 seeds, ties 11 and loses 14.
The interval includes zero: this is a provisional selection, not proof of a
placement improvement. Its increment over the V11 package is only +0.1042
in the pooled proxy mean.

The selected package obtains a second weapon in 47/48 cases versus V10's 45/48;
40/48 versus 34/48 arm by 30 seconds. It has zero recorded zone damage in these
48 cases. These diagnostics describe the simulated matches and do not explain
the four official placement points lost by V11.

The FFA sanity check uses 16 additional paired seeds 4200-4215 against the
simulator's infighting built-ins. V10 averages 11.5625; V12 averages 11.6250.
The difference is +0.0625 with an interval about [-2.05, +2.17]. This rules out
no subtle regression and does not evaluate the actual qualifying field.

## Implementation and verification

Only the combat-sprint experiment is newly enabled relative to V11. It applies
to grounded engage movement at full requested movement speed with energy above
40. An active laser charge blocks it; lightning raises the threshold to 60.
Airborne movement, route boosts and the existing recovery/zone priorities keep
their original control paths.

All other new switches default off. The independent lookahead module is kept
for reproducible experiments, and is not imported during ordinary V12 decisions.
Provenance checks protect unchanged modules and all functions outside the
documented brain/navigation scope. The manifest also checks the shipping defaults.

There are **86 passing tests**, including behavior tests for the new features
and guards. Native conformance answers 300/300 recorded observations on time.
The active timing stress test covers 840 observations; see
[v12_benchmark.json](v12_benchmark.json) for measured latency and memory.
GitHub Actions additionally builds and validates the pinned competition image.

The completed feature screens and squad validation contain 400 match results;
the FFA check adds 32. Raw data, per-arm source hashes, settings and summaries
are in [v12_experiments.json](v12_experiments.json) and
[v12_matches.jsonl.gz](v12_matches.jsonl.gz). The separate public-reference
comparison adds 16 diagnostic matches. Reproduction commands are in the README.

The simulator reconstructs house AI and several physics details. It does not
know the private practice seeds. Its uncertainty intervals describe simulated
paired outcomes and omit model error. Only submitting the exact V12 commit can
measure its official score. Keep the existing 5.33 entry selected until then.
