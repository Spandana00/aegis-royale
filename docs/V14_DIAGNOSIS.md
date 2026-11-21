# V14: evidence, interactions and candidate selection

V13's official **5.79**, receipt **BB-EDE179C7**, is our new baseline. It is
0.77 above V12 and 0.46 above our earlier best V10. V14 is unscored. Its goal
is at least 6.20; 48 integer placement scores require 298 total points
(6.20833, displayed 6.21), versus V13's 278. We need 20 additional placements
across the run, not a cosmetic improvement in latency.

## What can be verified

The user supplied V13's receipt and leaderboard screenshots. We also fetched
the public [official standings](https://www.joinbuilders.org/buildathon/tracks/builders)
and retained the extracted data plus the HTML hash in
[v14_public_standings.json](v14_public_standings.json). That snapshot shows
IT_Professionals 6.33, kyoto-max 6.31, Team 67 6.29, @GMUNVIS 6.23 and
giddygiddyboy 6.19. It does not expose those teams' submitted commit IDs.

The public repository search discovered **220 distinct repositories** and
**167 available READMEs**. Twenty-two contained decimal numbers that required
review: several were latency or local FFA results, not official practice scores.
The [scan ledger](v14_repository_scan.json) records each repository and available
README blob ID. We reviewed published histories and pinned promising source
trees. We cannot independently verify private runs or recover exact causes from
aggregate official scores. No claim here means every other team's submission
was replayed on the official server.

| Source | Published evidence | Verification and use |
| --- | --- | --- |
| [JishnuMadav](https://github.com/JishnuMadav/mech-royale/tree/2054a5bb27fdd36c8b8f63eebddbcf145737694e) | Recovery-v26 reports 5.85, BB-7097A598; twenty-run history reviewed previously | V13 reproduces this policy and now has its own verified 5.79 receipt. Earlier run ledger remains in the V13 report. |
| [JuanQuenga](https://github.com/JuanQuenga/buildathon-mech-royale) | Version/family histories and experiment results | Our V10–V12 establish that small additions to its intact foundation regressed. Its external simulator is diagnostic, with reconstructed opponents. |
| [Arnav-M10](https://github.com/Arnav-M10/BuildersMechRoyale/blob/main/dev/OVERNIGHT.md) | Go snapshot 3ec3a38 reports 6.17, BB-F0805900; older snapshot 5.25; newer 5.67 | Exact 3ec3a382f256e55519f0fd05baad489af7b429ec compiled, checked and compared against V13 on matched seeds. Public team Larpers also shows 6.17. The receipt is an author's report. |
| [Automata](https://github.com/jason-scheffel/automata/tree/f114d641a0de0c565dc057e342b4305b8cfe6d53) | Public Rust source and MIT license | Thirty-five source/configuration/lock/license files pinned; only the display name changes in V14. |
| [GMUNVIS public source](https://github.com/SuperHuyGaming/mech-royale/commit/553516f5d4742878c555a282eab60c9223d137b2) | Commit explicitly identifies Team 67's Automata f114d64 | All thirty Rust runtime source files match after normalizing line endings and display name. Board verifies team score 6.23, but not the exact scored commit. |
| Team 67 timing | Best run 15:22:47 EST falls after Automata 154ead5 and before f114d64 | Associating 6.29 with the earlier safety configuration is an inference. We tested that bundle rather than treating the timestamp as proof. |
| Other board leaders | Scores verified in public standings | No verified public source mapping for IT_Professionals or kyoto-max. No algorithm is attributed to them. |

The historical Go policy was public and MIT licensed when copied by its source
repositories; its original repository is now unavailable. It is an external
comparison here. No Go implementation is included in V14. Opaque binary-only
entries were excluded from source-based feature conclusions.

## Rechecking all our versions

Scores below are user-reported historical official results; the V13 receipt is
visible in the supplied screenshot. The source audit retains each earlier
commit and hashes. These were different complete submissions, not controlled
one-variable official experiments.

| Version | Official score(s) | Main change or interpretation |
| --- | ---: | --- |
| V1 | 3.75 | Initial bot |
| V2 | 4.50 | Coordinated fighting improved the complete submission |
| V3 | 3.96 | Broader retreat regressed |
| V4 | 4.40 | Projectile dodge recovered part of the loss |
| V5 | 4.17, 4.15 | Reload-cover variant did not improve the score |
| V6 | 4.46 | Falling-target prediction |
| V7 | 4.60, 4.52 | Range changes; repeated draws differed |
| V8 | 4.60 | Adaptive aim did not establish a gain |
| V9 | 4.77 | Tactical equipment/cube collection |
| V10 | 5.33 | Intact attributed good-31 reproduction |
| V11 | 5.25 | Bounded arming and pickup ordering: −0.08 versus V10 |
| V12 | 5.02 | Grounded combat boost: −0.23 versus V11 |
| V13 | **5.79** | Intact recovery-v26 policy: +0.46 versus V10 |
| V14 | Unscored | Intact attributed Automata f114d64 configuration |

The history favors preserving coordinated equipment, movement, firing and
recovery rules. It does not prove that every rule in the winning policy is
individually beneficial. [The V13 diagnosis](V13_DIAGNOSIS.md) retains the
previous 472 local cases and published experiment histories.

## Which features stand out

| Feature | Evidence | V14 decision |
| --- | --- | --- |
| Laser acquisition and weapon-specific firing | Repeated across stronger public families. Rust acquisition ablation reduced laser ownership by 30 s from 10/16 to 5/16, ever owning one from 15/16 to 10/16; proxy points fell 5.4375→5.1875. | Keep original long-range acquisition, sight/aim gates and weapon preferences together. |
| Charge rounding and lethal partial release | Jishnu's public history reports gains; our intact V13 subsequently reached 5.79. That does not isolate their contribution to our receipt. | Preserve V13 as fallback; avoid transplanting its firing rules into another policy's timing model. |
| Health recovery, energy and zone planning | Stronger policies coordinate these with offense. On 48 fresh squad seeds, complete Rust took mean zone damage 29.19 versus V13 75.77, while dealing 11114 versus 10150 damage. | Use the complete physics planner, resource rules and retreat/zone priorities. |
| Gear and harvesting | Factorial screen below shows beneficial separate effects versus disabling both, with a negative interaction. | Preserve public configuration; no disable switch is promoted from a sixteen-seed screen. |
| Extra early-fight safety rules | Screen mean 6.125 versus complete Rust 5.4375; fresh pooled means reverse to 4.750 versus 5.0625. | Do not add the earlier safety bundle. |
| Always boosting / arbitrary target weights | Our V12 regressed. Arnav reports Go 6.17→5.67 after changing only HP weight .21→.18 and loot radius 150→120; a later .25/180 combination reports 5.85. Single draws remain noisy. | Avoid porting isolated numbers across policy families. |

Language alone is not evidence of a score improvement: V13 already met response
deadlines. Rust's faster computation supports this particular planner, but the
policy change is the candidate, not a claim that compilation adds placement points.

## Interaction screen

Eight arms used the same sixteen squad seeds 6000–6015 with reconstructed pursuit
`join_per_loss=.6`. Every arm used the same official configuration fields; we
verified the simulator's config dictionary against the organizer's recorded
hello. Opponent behavior is still reconstructed.

| Arm | Proxy mean, n=16 |
| --- | ---: |
| V13 | 5.4375 |
| Go 6.17 snapshot | 6.8750 |
| Complete Rust | 5.4375 |
| Rust gear disabled; harvesting retained | 6.0625 |
| Rust harvesting disabled; gear retained | 5.8750 |
| Both disabled | 4.6875 |
| Rust laser acquisition disabled | 5.1875 |
| Rust earlier safety bundle | 6.1250 |

Gear alone adds 1.1875 and harvesting alone adds 1.3750 versus both off, but both
together add only 0.7500. The factorial interaction is **−1.8125** proxy points:
`both − gear_only − harvesting_only + neither`. Competing movement goals are a
plausible explanation, not an official causal finding. Disabling a module also
changes paths and encounters. The screen cannot establish a reliable optimal switch set.

Screen event traces show Rust owning a laser at some point in 15/16 matches
versus V13 13/16; both reach 10/16 by 30 seconds. Rust is not demonstrably faster
to its first laser than V13. Rust spent 0.30% of live frames below 20 energy,
versus V13 1.73%, while having fewer cubes at 30 seconds. These observations
support examining resource timing and energy conservation; they do not prove a
single explanation for official scores. Full trace-derived rows are archived
in the experiment JSON; large replay files stay outside the submission.

## Fresh comparisons and final selection

Fresh squad batches used 6200–6223 at pursuit .6 and 6300–6323 at pursuit 1.0.
They were reserved from the screen. All four policies received the same seeds,
spawn slots and settings. A separate FFA sanity batch used 6400–6415.

| Policy | Moderate, n=24 | Faster, n=24 | Pooled squad, n=48 | FFA, n=16 |
| --- | ---: | ---: | ---: | ---: |
| V13 | 5.0833 | 3.7500 | 4.4167 | 9.7500 |
| Go snapshot | 6.8333 | 3.0417 | 4.9375 | Not run |
| Complete Rust | 6.2500 | 3.8750 | **5.0625** | 9.1250 |
| Rust safety bundle | 5.2917 | 4.2083 | 4.7500 | 9.3750 |

Complete Rust–V13 paired difference: **+0.6458**, paired bootstrap 95% sampling
interval **[−0.25, 1.54]**. The FFA difference is −0.625 with interval
[−3.875, 2.625]. These wide intervals, simulator errors and candidate selection
prevent forecasting an official improvement or claiming FFA superiority.

Complete Rust nevertheless has the strongest combined basis for the next
practice submission: corroborating 6.23 source-family evidence, a favorable
fresh pooled squad result, intact source equivalence, and correct deadline
behavior. The stronger initial Go screen and earlier safety screen do not
survive both fresh squad conditions. We choose **unmodified f114d64 parameters**,
not an inferred Team 67 snapshot or a new feature mixture.

Across fresh squad matches, cubes at death/finish increased from 4.1042 to 5.75
and mean zone damage decreased from 75.77 to 29.19. No new official score is
available. Keep the selected V13 5.79 until V14 actually scores higher.

## Reproduce and inspect

[v14_matches.jsonl.gz](v14_matches.jsonl.gz) contains all 368 match rows.
[v14_match_sources.json](v14_match_sources.json) pins source hashes, commands,
configurations, simulator commit and seed batches. Runs use three workers;
process timing and wall-clock planning budgets can change behavior between
replays even with fixed seeds.

Clone JuanQuenga/buildathon-mech-royale at
`b50b794522c134d9eb54cc2e9bc4782f4f4a3da9` into `../reference-juan`, Automata
at `f114d641a0de0c565dc057e342b4305b8cfe6d53` into `../reference-automata`,
and Arnav-M10/BuildersMechRoyale at
`3ec3a382f256e55519f0fd05baad489af7b429ec` into `../reference-arnav`.
Create `../baseline-v13` at `5cf4fe8b8bf0992517575fe76ed35abb21f9ecc1`.
Build Rust release with `cargo build --release --locked` in its reference tree.
Build Go with Go 1.26.1 using `go build -o ../runtime-tools/giddy3-bot ./cmd/bot`.
Then run, using a new output filename:

```sh
python3 -B check/study_v14.py --arms v13,go617,rust_full,rust_safety \
  --seeds 6200-6223 --jobs 3 --out local-results/reproduction.jsonl
```

The original Automata Rust tests are preserved. With the real map, stream and
navigation paths set, 19 pass and one optional upstream test is ignored.
111 retained Python and provenance tests pass. Native conformance passes all
300 recorded observations, maximum 12.8 ms, with no late/dropped/invalid lines.
The GitHub workflow also builds and checks the actual final image in the
competition's one-CPU sandbox. The pinned source audit confirms no tactical
transplants or parameter changes in V14.
