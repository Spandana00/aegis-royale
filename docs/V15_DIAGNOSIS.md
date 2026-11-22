# V15: improve the firing combination while preserving V14

> Subsequent official result: V15 scored 6.15 and did not replace V14's 6.19.
> The original pre-submission analysis below is historical. See [V16](V16_DIAGNOSIS.md)
> for the regression review and the requested exact-build rerun.

V14 scored **6.19**, receipt **BB-A804A35A**, at public commit
`3f08bd1311f93bde3696a2f5a295fd603e9e9fa0`. The supplied screenshot shows that
entry selected. V15 is unscored. The live public standings checked during this
analysis show IT_Professionals and tigerbyte at **6.38**. At 48 integer-scored
games, V14 has 297 placement points and those leaders have 306. Beating that
score needs at least **307 points**, displayed **6.40**: ten additional placements
across the run. Nothing in the local simulator establishes that outcome.

## What increased or decreased our official score

The source audit rechecks retained commits and hashes. These are whole
submissions, not randomized one-variable official trials; aggregate receipts
cannot identify individual-match causes.

| Version | User-reported official score(s) | Interpretation |
| --- | ---: | --- |
| V1 / V2 / V3 | 3.75 / 4.50 / 3.96 | Coordination helped the submission; broader retreat regressed. |
| V4 / V5 / V6 | 4.40 / 4.17, 4.15 / 4.46 | Dodge / reload cover / falling-target prediction. |
| V7 / V8 / V9 | 4.60, 4.52 / 4.60 / 4.77 | Range / adaptive aim / equipment and cube collection. |
| V10 | 5.33 | Intact attributed good-31 reproduction. |
| V11 | 5.25 | Arming and pickup changes: −0.08 versus V10. |
| V12 | 5.02 | Grounded sprint variant: −0.23 versus V11. |
| V13 | 5.79 | Intact recovery-v26: +0.46 versus V10. |
| V14 | **6.19** | Intact Automata configuration: +0.40 versus V13. |
| V15 | Unscored | Scoped, coordinated laser/gun firing adaptation. |

The reliable official finding is that the complete V14 policy improved our
result. The new research therefore changes firing in a bounded scope and keeps
its movement, equipment priorities, harvesting, recovery and randomness.
Historical sources and earlier local diagnostics remain in
[the V14 diagnosis](V14_DIAGNOSIS.md); exact score/receipt data is in
[v15_official_history.json](v15_official_history.json).

## Public repository verification

The refreshed search checked **225 repository records** and found **171 READMEs**.
The [scan ledger](v15_repository_scan.json) retains repository names and README
blob IDs. Decimal numbers were classified before treating them as scores.
For example, the new lmaccart README's 6.38 refers to the public board leader,
not a verified result for that repository.

| Source | Verified finding | Consequence |
| --- | --- | --- |
| [Official public board](https://www.joinbuilders.org/buildathon/tracks/builders) | 6.38 leaders, 6.29 Team 67 and 6.23 GMUNVIS in the checked snapshot. | Scores are visible, submitted repository/commit IDs are not. [Snapshot](v15_public_standings.json). |
| [Automata](https://github.com/jason-scheffel/automata) | Our V14 pins f114d64 and has its own 6.19 receipt. Newer public commits contain experimental controls, including deliberately stopping the bot. | A newer commit is not automatically a stronger policy. Keep the scored foundation. |
| [GMUNVIS](https://github.com/SuperHuyGaming/mech-royale) | The previously inspected runtime matched Automata apart from naming and line endings; a later commit edits the retained Python legacy bot. | Read the actual Docker entrypoint before attributing a feature to a scored runtime. |
| [Arnav Go history](https://github.com/Arnav-M10/BuildersMechRoyale/blob/main/dev/OVERNIGHT.md) | Reported 6.17 snapshot, then parameter and RNG variants with lower results. The gun trigger is held whenever the shot is otherwise valid. | Preserve coordinated policies and held-trigger behavior; single draws do not isolate causality. |
| [Jishnu history](https://github.com/JishnuMadav/mech-royale) | Published laser rounding, lethal release and critical-recovery gains; our own V13 subsequently scored 5.79. | Conservative firing and charge timing remain useful mechanisms, but transfers require tests. |
| IT_Professionals / tigerbyte | Their 6.38 board results are verified; no verified public source-to-submission mapping was found. | No claim that V15 reproduces or improves a known 6.38 implementation. |

The public source families provide hypotheses, not an independently verified
ranking of individual features. Private submissions and every other team's
unpublished run cannot be verified from available material.

## Simulator audit before optimization

Arnav's updated log reported a blocked-velocity bug in its custom simulator.
Our separate Juan simulator already zeros blocked horizontal velocity. A
20-tick collision probe confirms zero movement and zero reported velocity at
an impassable wall. The entire config dictionary equals the organizer's
recorded hello, including the 480-second match configuration.
[The audit](v15_simulator_audit.json) records this check.

Opponent behavior, rasterized collision details and wall-clock planning remain
approximations. Some assumptions about firing timing are also model choices.
We did not copy the other simulator's results or mistake matching config values
for an exact server reproduction. Local scores are diagnostics only.

## Initial feature screen: promising changes did not add up

Ten arms used the same sixteen squad seeds 7000–7015. The laser estimate
hypothesis accounts for own cube damage, maximum hidden armor and mortar
cookoff; the motion hypothesis projects the firing origin over command latency.
The existing mortar-rejection switch and shorter loot-pursuit timer were also
checked independently and with other changes.

| Arm | Proxy mean, n=16 |
| --- | ---: |
| V14 control | 6.3750 |
| Laser damage estimate | 7.1250 |
| Own-motion aim | 6.6250 |
| Both | 5.9375 |
| Mortar ban | 5.8750 |
| Laser estimate + mortar ban | 6.1875 |
| Motion aim + mortar ban | 6.2500 |
| All three | 6.2500 |
| Shorter loot pursuit | 5.5000 |
| Laser + motion + shorter pursuit | 6.2500 |

Laser × motion interaction was **−1.4375** proxy points. The laser-only traces
showed 304 mech-hit releases from 352 beams, versus 297 from 362 for the control
(86.4% versus 82.0%). This was a small development screen, not a final result.
There were no own mortar cookoffs in the control traces, so the blanket ban did
not address an observed control loss in this batch.

Fresh seeds 7200–7231 and 7300–7331 at two pursuit settings erased the apparent
individual gains: control, laser-only and motion-only each averaged **5.125**
over 64 matches. Their combination fell to **4.875**. An isolated mechanical
correction did not establish a placement improvement.

## Refinement: hidden armor has a cube-dependent upper bound

The original partial-beam test uses raw weapon damage. The experiment adds
own cube damage, hidden armor and mortar cookoff. Assuming three armor stacks
against every enemy can still hold the beam unnecessarily: an enemy with zero
cubes has earned zero upgrade offers. Cubes are not spent when upgrading.

V15 bounds possible armor stacks by the number of configured upgrade thresholds
already crossed by the observed enemy cube count. It still assumes the worst
legal armor within that bound, includes configured base armor, assumes no rear
bonus, includes cookoff only for a visible mortar holder, and retains a 15-HP
finish margin. NPCs and crates do not receive mech armor. Full-charge release
and its rounding tolerance remain available.

Seven scenario tests cover armor preventing a premature finish, cube and cookoff
bonuses permitting a finish, full-charge rounding, relative-motion hypotheses,
zero-cube enemies and the bound for every legal armor stack count across 22
cube counts. The cube-aware estimate substantially recovered the unbounded
variant's regression on a new 48-seed cohort, but still trailed control by
0.1042 proxy points. It was not selected alone.

A separate outside-zone charge guard tied the control across 32 squad seeds;
adding it to the earlier laser estimate did not improve that cohort. It is not
in the active V15 implementation. The source patch and results are retained.

## The useful combination: finishing logic and shared aim

V14 points at the laser target during the final charge window. A valid gun
intercept can require a slightly different direction, preventing the gun from
firing even when both weapons could hit within their existing aim windows.

V15 intersects the gun window with the **central half** of the laser's existing
alignment tolerance. It uses that common direction only when the gun is loaded,
not reloading and can be ready on the next physics tick. If the windows do not
intersect, the original laser-center command remains. Final torso-slew and
weapon-specific alignment gates still decide whether to fire. A scenario test
recovers a gun shot while releasing the beam on the same observation and checks
that a cooling gun leaves laser aim unchanged.

A later upstream aim-arbitration experiment at Automata d4c72b4 was inspected.
V15 uses its own bounded intersection and adds an explicit map ray check along
the common command, so an obstructed shared path keeps the original laser aim.
Movement-aware aiming remains disabled.

A fresh 2×2 comparison used sixteen moderate and sixteen faster squad seeds:

| Configuration | Moderate | Faster | Pooled |
| --- | ---: | ---: | ---: |
| V14 control | 5.6875 | 4.7500 | 5.21875 |
| Aim sharing alone | 5.5625 | 4.6875 | 5.12500 |
| Cube-bounded estimate alone | 5.3750 | 4.4375 | 4.90625 |
| Sharing + cube-bounded estimate | **6.6250** | **4.7500** | **5.68750** |

Both components lost slightly alone, while the combination gained **0.46875**.
The interaction was **+0.875** proxy points. Coordinating the final aim with
release timing is a plausible mechanism; the score difference does not prove
a particular sequence of official kills or rule out sampling noise.

A gun-cooldown hypothesis was rejected on source inspection: V14 already holds
the gun trigger when the shot is otherwise valid. An intermediate progress
update incorrectly described this as a missing feature; it was corrected, and
no gun-cooldown change was implemented.

## Final verification after the sightline guard

The actual final source and configuration were then checked on reserved squad
seeds 8500–8515 and 8600–8615, plus FFA seeds 8700–8715.

| Policy | Moderate squad, n=16 | Faster squad, n=16 | Pooled squad, n=32 | FFA, n=16 |
| --- | ---: | ---: | ---: | ---: |
| V14 control | 6.0625 | 4.0000 | 5.03125 | 10.7500 |
| Final V15 | **6.8125** | **4.2500** | **5.53125** | **11.0000** |

The final paired squad difference is **+0.50**, bootstrap 95% sampling interval
**[−0.09375, 1.1875]**. This interval includes no improvement and excludes model
and selection error. FFA's +0.25 is also inconclusive. These results do not
forecast a 6.40 practice score or tournament strength.

Across the final squad cohort, mean damage dealt rose from 11,147.59 to 12,257.06
and cubes at death/finish from 5.96875 to 7.625. These are complete-policy
outcomes, not proof that any one component caused those gains. The selected
candidate changes firing together and retains the rest of the scored baseline.

## Validation, reproducibility and next official run

All **111 Python** provenance/regression tests and **27 Rust** tests pass; one
optional upstream Rust test is ignored. Rust tests use the actual arena and
recorded stream. Native conformance passes 300/300, maximum 11.2 ms. The active
policy passes 840 recorded/synthetic process cases with no invalid actions or
responses above 50 ms, maximum 43.122 ms on the development host. With all new
switches off, the final executable reproduces all 300 recorded V14 actions.

GitHub Actions builds the actual image and runs both conformance and the
840-observation process benchmark under one CPU, 512 MiB, no network, read-only
root and uid 65534. Check the exact submitted commit's workflow conclusion;
host timing is not a container measurement.

The study contains **992 policy–seed matches**, not 992 independent final-candidate
samples. The final comparison has 32 paired squad seeds and 16 paired FFA seeds.
Two late replies occurred in unselected arms; final-candidate matches had zero
late replies. No arm produced a traceback.

[Raw rows](v15_matches.jsonl.gz), [source/settings metadata](v15_match_sources.json),
[cohort summaries](v15_experiments.json), [validation](v15_validation.json) and
[scoped source manifest](v15_manifest.json) retain the evidence. The large
replay files are not included in the submission. The last arm of one batch was
resumed after an executor transport interruption; completed arms were retained.

For reproduction, use the pinned Juan simulator and V14 worktree described in
the V14 report. Each `v15_*_experiment.patch` applies independently to the V14
commit to reconstruct its corresponding source snapshot. `check/study_v15.py`
accepts explicit source and executable paths and stores every setting and hash.
Timing budgets can change decisions between replays despite identical seeds.

**V15 is the next experimental official submission, not an achieved rank.
Keep V14's 6.19 selected until a new official result improves it.**
