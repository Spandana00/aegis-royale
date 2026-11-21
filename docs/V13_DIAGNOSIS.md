# V13: regression diagnosis and feature interactions

The official V12 result is **5.02** (BB-64E9FDE1,
`9001f5d9bbbf076b65e815e29ed3d1b488ff3a2f`). V11 scored 5.25 and V10 5.33.
These are aggregate 48-match results supplied by the user. They identify a
regression in the submitted bundle, but cannot identify which encounters caused
it: we have no official per-match replays for those submissions.

| Official version | Main policy change | Reported score | Placement points across 48 matches |
| --- | --- | ---: | ---: |
| V9 | Equipment and cube collection on the original AEGIS core | 4.77 | 229 |
| V10 | Attributed good-31 navigation/combat/laser policy | **5.33** | 256 |
| V11 | Weapon commitment during gun fights, pickup ordering, numeric guard | 5.25 | 252 |
| V12 | V11 plus grounded combat sprint | 5.02 | 241 |

The integer totals follow from the two-decimal means and the specified 48-match
format. V12 lost 11 placement points versus V11 and 15 versus V10. Neither
small score differences nor the local simulator establish a causal effect on
unseen official matches.

## Cross-repository evidence

Sources were fetched through GitHub, including full implementation files,
results ledgers and the scored commit mapping. Published scores remain
author reports; a receipt written in a repository is not independent access
to the official scorer. Blob IDs and limitations are in v13_research.json.

| Reference | What its record supports | Consequence for this bot |
| --- | --- | --- |
| [JuanQuenga](https://github.com/JuanQuenga/buildathon-mech-royale/blob/main/eval/RESULTS.md) | good-31 family mean 5.34 over nine reported draws; navigation family improvement around 0.3–0.4 | Preserve our best official V10 core: surface routes, jet-hop fix, laser preference, steady strafing |
| Same record | Slow combat movement scored 4.77; standing scored 4.19; isolate scored 5.48/5.44/5.17; isolate + recovery scored 5.21 | Preserve movement speed; do not combine individually promising cover/recovery features on reputation alone |
| [Arnav-M10](https://github.com/Arnav-M10/BuildersMechRoyale/blob/main/dev/OVERNIGHT.md) | Combat-sprint draws 4.73/4.90/4.79 versus a reported base mean near 4.93; several simulator predictions disagreed with official runs | Disable V12 sprint; treat proxy score rankings as supporting diagnostics |
| [JishnuMadav](https://github.com/JishnuMadav/mech-royale/blob/main/results.json) | Reports supply capture 5.10→5.46, laser rounding fix→5.73, lethal partial release→5.81, narrow recovery/zone escape→5.85 | Audit these mechanisms before transplanting. Our laser already releases within 0.02 s of full charge, releases lethal partials and blocks new charges during urgent rotation |

The current Jishnu README includes November 22 reporting although this task's
date is November 21. Its score/date claims are recorded without independently
verifying their timing. Giddy's formerly public repository now returns 404;
the older 6.00 claim is a third-party report, not a verified repeated-policy mean.

## Confirmed implementation faults

1. **Final gun aim.** Combat decides a gun trigger using projectile lead. A
   subsequent early laser release can override that command with a hitscan
   direction without rechecking the gun. A reproducible 120 m lateral-moving
   target scenario sends a gun shot along the wrong direction. `final_fire`
   checks the actual final command, preserves the laser release and vetoes the
   misaligned gun trigger. It leaves aligned gun shots enabled.
2. **Retreat shelter.** `_cover_from` accepts multiple threats but passes only
   the first to `nearest_cover`. `cover_all` checks the nearest three and
   invalidates cached shelter when that group changes. This corrects the
   geometry criterion; it is not proof that a longer retreat improves placement.

## Independent experiments

`combat_cube` permits a fresh cube within 18 m during a favorable fight, keeps
the selected target and shooting, and rejects blocked paths, unsafe zone
destinations, capped cube stats and detours whose estimated incoming damage
exceeds the smaller of 90 HP or 12% of current HP. A killable target takes
priority. Charging speed is included in travel cost.

`critical_recover` starts below 25% HP only with nearby verified shelter and no
attacker inside 45 m, resumes at 60%, and bounds the attempt to 22 seconds.
It yields to zone emergencies and killable targets. It is an experiment, not
an automatic adoption of the other repository's thresholds.

The historical controls use immutable V10/V11/V12 checkouts. Individual feature
arms use one current tree with every other new switch off. The screen includes
all four combinations of weapon commitment and combat sprint, so their
interaction can be measured instead of assuming their benefits add.

## What the experiments showed

All numbers below are **local proxy placement points**, not official scores.
The first screen uses 16 matched seeds 5100–5115. Its historical V10 control is
an immutable checkout; the current control retains V11 pickup ordering and the
zero-HP guard. The combination screen uses the same development seeds in a
separate invocation. Clock-limited routes and process fallbacks introduce noise.

| Development arm | Proxy mean |
| --- | ---: |
| Exact V10 | 5.2500 |
| Current control, no new switches | 5.3750 |
| V11 weapon commitment | 5.8750 |
| Sprint without commitment | 4.9375 |
| V12: commitment + sprint | 5.3125 |
| All-threat cover | 4.9375 |
| Final-aim gun gate | 5.0000 |
| Short combat cube detours | 5.5000 |
| Critical-health recovery | 5.3125 |
| Cover + gun gate | 4.8750 |
| Cover + cube detours | 5.1250 |
| Cover + gun gate + cubes | 5.0000 |
| Weapon commitment + cubes | 5.7500 |

The development interaction estimate for commitment × sprint is -0.125 points:
there is no evidence that their separate gains add. The gun veto never activated
in this screen, despite a different score from its control; that directly exposes
scheduling noise. Correcting a geometric or firing criterion does not establish a
placement gain. The cover experiment's cache was later corrected to reuse shelter
under small threat movements; its original screen does not score that correction.

Two fresh 24-seed sets used moderate pursuit (5400–5423, join_per_loss=0.6) and
faster pursuit (5500–5523, join_per_loss=1.0), with the production process guards
for retained pilot arms and PYTHONHASHSEED=0 throughout.

| Fresh package | Moderate | Faster | Pooled, 48 cases |
| --- | ---: | ---: | ---: |
| Exact V10 | 4.8333 | 3.6667 | 4.2500 |
| Exact V11 | 5.3750 | 4.1667 | 4.7708 |
| Cubes without commitment | 5.4583 | 3.7500 | 4.6042 |
| Commitment + cubes | 5.3333 | 4.1667 | 4.7500 |
| **Intact Sentinel recovery-v26** | **5.4167** | **4.4583** | **4.9375** |

Neither adding cubes to V11 nor combining the individual fixes established a
stronger policy. Cube-only's +0.3542 over exact V10 remains uncertain. These
experiments are retained for reproducibility and are **not enabled in the image**.

## Selected implementation: preserve a scored combination

V13 imports the complete MIT-licensed Oval Sentinel recovery-v26 policy from
JishnuMadav's exact commit `2054a5bb27fdd36c8b8f63eebddbcf145737694e`, with its license.
The author reports 5.85 and BB-7097A598. Package imports and the display name are
the only runtime source transformations; there are no tactical or parameter edits.
All original normalized source SHA-256s and Git blob IDs are checked in tests.
Our earlier policy and all experiment flags remain outside the competition image.

The features that have the strongest *published bundle comparisons* are:

| Coherent feature family | Source's reported score progression | Integration preserved in V13 |
| --- | --- | --- |
| Supply repair and escape | 5.10 → 5.46 | Capture residence, repair value, contest checks and zone priority together |
| Laser release timing | 5.46 → 5.73 → 5.81 | Rounded full charge, conservative armor/margin for lethal partials, correct release aim |
| Narrow recovery and zone escape | 5.81 → 5.85 | Enter below 25%, resume at 60%, retain occupied safe cover, stop new laser charges during escape |
| Supporting equipment/movement | Part of the full policy | Laser priorities, matchup-aware distance, energy recharge hysteresis and bounded obstacle routes |

Those progressions are single reported submissions of different bundles, not
repeat-controlled causal effect sizes. Our old policy already had rounded charge
and early release, with different damage estimates and priorities; merely copying
those labels would not reproduce the reported policy.

Across 48 fresh matched proxy cases, the intact policy gains +0.6875 over V10,
with a paired sampling interval approximately [0.04, 1.33] (25 better, 6 tied,
17 worse). Its smaller +0.1667 over V11 remains uncertain. The moderate set runs
the exact upstream source, and the faster set runs the equivalent namespace-only
adaptation. Eight additional development seeds gave upstream 5.25 vs V10 5.625;
that small comparison did not rank them.

FFA sanity uses eight new seeds 5600–5607: V13 11.25 versus V10 11.625, with three
versus two wins and no missed/late replies or tracebacks. The paired interval is
wide (about -4.32 to +3.57), so this establishes no FFA improvement or equivalence.
It only checks that the policy runs in that format without an obvious collapse.

## Validation and submission decision

- 472 local diagnostic match results are archived in v13_matches.jsonl.gz, with
  experiment settings and hashes in v13_experiment_metadata.json.gz.
- 108 tests pass, including 13 source scenario tests and exact source equivalence.
- Active native protocol check: 300/300 on time, max 3.6 ms, zero bad/stale ticks.
- Active 840-case timing stress: max 5.186 ms, no invalid actions or >50 ms cases.
- The Docker build allowlist and entrypoint both select only `sentinel/`.
- GitHub Actions is configured to check the actual linux/amd64 image under
  competition limits. This V13 run is pending publication approval; no local
  container runtime is available.

The simulator's house AI is guessed, its route budgets are clock-sensitive, and
its confidence interval excludes model error and selection effects. This cannot
prove an official 5.50+ result. Keep the existing **5.33** entry selected until
V13 is officially scored higher. V13 is a stronger next experiment with a
publicly reported intact policy and fresh proxy support, not a promised score.
