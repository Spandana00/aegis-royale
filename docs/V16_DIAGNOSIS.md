# V16: restore V14 firing and isolate laser spacing

> Subsequent official result: V16 scored **6.25**, receipt **BB-0E038934**, and
> is now the selected champion. The original pre-submission analysis below is
> historical. See [V17](V17_DIAGNOSIS.md) for the new baseline and next comparison.

The best verified entry remains **V14, 6.19**. V15 scored **6.15** and is
rejected as a replacement. V16 is an unscored, controlled candidate for the
next official practice run.

| Entry | Exact public commit | Official result | Receipt |
| --- | --- | ---: | --- |
| V14 | `3f08bd1311f93bde3696a2f5a295fd603e9e9fa0` | 6.19 | BB-A804A35A |
| V15 | `be6c83e043e7f604aa95d7f9c4f2e2f52c556f85` | 6.15 | BB-05A9CC68 |
| V16 | Use the exact published commit with green checks | Unscored | None |

The two screenshots imply 297 versus 295 integer placement points over 48
matches: a loss of two points. They do not expose the individual matches or
the counterfactual outcome of either firing change. No exact causal attribution
is possible from those aggregate receipts. The [history](v16_official_history.json)
and [source audit](v16_source_audit.json) now include all V1–V15 records and
their actual image entrypoints; historical Python policies are not active.

The saved public board shows tigerbyte at 6.44, equivalent to 309/48. Beating
that score requires at least 310/48, displayed 6.46: thirteen more placement
points than V14. A simulator increase does not establish those thirteen points.

## What changed in the losing entry

V15 made two coupled decisions differently. Its shared aim moves the beam
off the predicted target center to recover a ready gun shot during the final
charge window. This reduces the remaining beam alignment margin, even though
the command stays inside a conservative geometric window. Its new damage
estimate can release earlier with cube damage and mortar cookoff, or hold longer
when hidden armor is conservatively assumed. Both alter movement because
charging slows the mech. These are plausible regression mechanisms, not proof
of which one lost the two official points.

The original V14 gun already held its trigger while aligned, loaded and not
reloading. There was no gun-cooldown gate to fix. The own-motion hypothesis was
disabled in V15 and cannot explain this official regression.

At the user's request, the exact V15 executable and configuration were run again.
The executable hash is pinned in [the rerun validation](v15_rerun_validation.json).
The control uses that same executable with all added switches off, reproducing
V14 firing behavior.

| New matched diagnostic cohort | V14 control | Exact V15 | Difference |
| --- | ---: | ---: | ---: |
| Moderate reconstructed pursuit, 16 seeds | 6.5625 | 5.5000 | −1.0625 |
| Faster reconstructed pursuit, 16 seeds | 4.8750 | 5.3750 | +0.5000 |
| Pooled, 32 seeds per policy | 5.71875 | 5.43750 | −0.28125 |

The paired bootstrap sampling interval is [−0.875, +0.25], excluding simulator
and selection error. The effect reverses across opponent settings. This repeat
does not establish V15 superiority and reinforces why the earlier small local
gain should not have been treated as a reliable official forecast.

In the moderate cohort, 228/317 V15 beam releases hit a mech versus 280/367 for
the control; laser damage to mechs was 101,182 versus 127,425. These include
changes in lifespan and encounters. The denominator includes all releases,
including shots at resources, so this is not a conditional aiming-accuracy
measurement. [Trace summary](v15_rerun_trace_summary.json).

Both configured V15 conformance and stress checks passed again: 300/300 and
840 observations, zero late or invalid answers. The existing exact-commit
[container workflow](https://github.com/Spandana00/aegis-royale/actions/runs/44966716742)
was rechecked and is successful. These checks measure transport and timing,
not placement. The supplied 300-observation recording has only a gun in the
entrant's inventory, so it cannot validate real laser-duel performance. No new
official submission was made by the rerun.

## Public repository verification

The broader scan requested 225 repository trees, retrieved 218 and reviewed
44 candidate score/experiment files. Seven trees were unavailable. This is a
documented corpus, not every GitHub repository. [Scan](v16_repository_scan.json)
and [research conclusions](v16_research.json) retain paths and blob identifiers.

Five genuine Aegis-labelled sources were inspected:

| Public source | What its published record supports |
| --- | --- |
| [AkChetti06](https://github.com/AkChetti06/aegis-mech-royale) | Local 2.9–3.1; no official 6.20+ evidence |
| [Rizwanzaman70](https://github.com/Rizwanzaman70/Bizz01-MechRoyale) | Explicitly does not claim verified leaderboard improvement |
| [Osca-K](https://github.com/Osca-K/builders-buildit-mech-royale) | Published best baseline 4.25; later tweaks below it |
| [ppetit8](https://github.com/ppetit8/mech-royale_bot) | Aegis design; published official baseline 3.56 |
| [heeseo937](https://github.com/heeseo937/mech-royal) | Published official 3.69, then 2.13 despite local gains |

None substantiates the requested average of 6.20+. Other 6.2–6.5 text hits were
targets, simulator means, timing figures or another team's score. No algorithm
is attributed to the 6.44 leader: the public standings do not expose its scored
repository and commit.

The strongest relevant source-family evidence remains Automata and the linked
GMUNVIS implementation. V14's exact runtime has our own 6.19 receipt. GMUNVIS is
6.23 on the saved public board, and its attributed source matches the same
Automata family; its exact scored commit is not exposed. Team 67's 6.29 mapping
is an inference from attribution and timing. Arnav's published Go snapshot is
6.17, with wide salt-draw variation, not a verified 6.20+ policy average.

The newer public [Automata configuration](https://github.com/jason-scheffel/automata/blob/c337f1e5bcd12d3f67a0cb4c80b17edb2738d5dc/bot.json)
contains `range_laser=200` and `gear_late_s=120`, among other settings. Its new
configuration has no verified score mapping. We tested those two strategy
settings separately and together rather than importing its newer runtime.

## One strategy change on the intact baseline

Every original Rust algorithm is restored to V14, including the firing code.
Only the display name and JSON configuration differ. V15's implementation and
its added firing test module are removed from the active tree; their exact
historical source remains available at the V15 commit.

The sole selected behavior change is **preferred laser range 140 → 200 m**.
The original rules still bring us closer to weak, harmless targets and preserve
gun-only range, loot, harvesting, recovery and zone priorities. The hypothesis
is that an armed mech can spend less time in a dangerous close duel while still
using the 280 m beam. There is a real tradeoff: 200 m is beyond the original
gun's 0.82 × 230 = 188.6 m firing-distance gate, so some accompanying gun shots
are sacrificed. Source equality, not a gun-only replay, proves firing is restored.

| Fresh factorial comparison, 32 seeds per arm | Proxy mean | Difference from control |
| --- | ---: | ---: |
| V14 control | 4.96875 | — |
| Longer laser spacing | 5.50000 | +0.53125 |
| Late threat recognition at 120 s | 5.21875 | +0.25000 |
| Both together | 5.28125 | +0.31250 |

The interaction is −0.46875 proxy points. The combination adds less than spacing
alone despite both separate point estimates being positive. The initial
sixteen-seed screen had a different ordering; it is retained in the raw data.
This is evidence against stacking the settings, not an official causal result.

Spacing alone was selected before the reserved 9300–9331 cohort, with no retuning
on those seeds. [Selection record](v16_selection.json).

| Spacing comparison | V14 | V16 configuration | Difference |
| --- | ---: | ---: | ---: |
| Fresh moderate pursuit, 16 seeds | 5.9375 | 6.4375 | +0.5000 |
| Fresh faster pursuit, 16 seeds | 4.0000 | 4.5625 | +0.5625 |
| Reserved intermediate pursuit, 32 seeds | 5.0625 | 5.1250 | +0.0625 |
| All three, 64 seeds per policy | 5.015625 | 5.312500 | +0.296875 |

The reserved result is nearly flat. The pooled sampling interval
[−0.046875, +0.671875] includes zero and omits model error. This supports a narrow
next official experiment, not a claim of a proven improvement or a 6.44+ score.
Keep V14's selected entry until an official result exceeds 6.19.

There was one late reply in spacing's exploratory screen (seed 9009, 67.09 ms),
and zero in the subsequent 64-seed selected validation. All timing and invalid
action checks on the final configured image are reported separately in
[validation](v16_validation.json). A small FFA sanity cohort is separately
reported in the experiment JSON and is not pooled into practice comparisons.

## Reproduction and limits

[Match rows](v16_matches.jsonl.gz), [cohort summaries](v16_experiments.json),
[commands, configurations and executable hashes](v16_match_sources.json), and
the [source manifest](v16_manifest.json) are versioned. The manifest reverses
the two allowed modifications to recover every original upstream Git blob.

The local referee is JuanQuenga/buildathon-mech-royale at
`b50b794522c134d9eb54cc2e9bc4782f4f4a3da9`. Configuration fields match the
organizer's recording; opponent behavior and escalation remain reconstructed.
Wall-clock planning budgets introduce some replay variation. The frozen V14
binary used for strategy comparisons has SHA-256
`7d2ca9820ba97edf2b4af939cd91b11b34e5f600d394e14d48b22ca2331c707e`.

Build the V14 worktree with Rust 1.95.0, then run from this repository with a
new output path:

```sh
python3 -B check/study_v16.py --arms control,spacing --seeds 9300-9331 \
  --pursuit .8 --executable /path/to/v14-automata --traces \
  --out local-results/reproduction.jsonl
```

The final image is built and checked by the GitHub workflow under one CPU,
512 MiB, no network, a read-only filesystem and UID 65534. Submit the exact
public candidate commit only after those checks pass. Its official result
remains unknown until the organizer scores it.
