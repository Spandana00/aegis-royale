# AEGIS Royale

**Selected official champion: V17, 6.27 (BB-961EADA2), commit
`e45e734215354fc4f938af15c984a666f446a426`. V18 is an unscored candidate.**

V18 changes one strategy setting: **`gear_easy_range` 55 → 70 metres**.
This is the approach distance used against opponents the equipment policy
classifies as harmless and that do not hold a laser. The previous close-in
override could pull a laser-equipped bot down to 55 m despite its 200 m laser
preference. A 70 m setting won our comparisons; 85 m was less consistent.
These are preferred distances, not guaranteed separation from every opponent.

V17's complete upgrade order, including charge priority after plating, armor
and nanites, is retained. Laser duel spacing remains 200 m. All Rust algorithms,
firing, acquisition, harvesting, recovery and seed rules are unchanged.
The [manifest](docs/v18_manifest.json) reverses the display-name and configuration
edits to reproduce every original Automata source blob.

## Evidence

The official history is **V14 6.19 → V15 6.15 → V16 6.25 → V17 6.27**.
Aggregate scores alone cannot isolate every match-level cause. The exact scored
champion and its successful container checks are pinned in [champion.json](champion.json).

**288 new diagnostic policy matches** compare the champion, a Lightning-only
guard, and 70/85 m approach settings. These use a reconstructed simulator,
not the official squad or a forecast of the next submission.

| Comparison | V17 setting | V18 setting | Difference |
| --- | ---: | ---: | ---: |
| Fresh moderate pursuit, 24 seeds | 6.0417 | 6.0417 | 0.0000 |
| Fresh faster pursuit, 24 seeds | 4.3333 | 5.7917 | +1.4583 |
| Reserved intermediate pursuit, 32 seeds | 5.40625 | 6.15625 | +0.75000 |
| Pooled validation, 80 seeds per policy | 5.2750 | 6.0125 | +0.7375 |
| Separate FFA sanity cohort, 8 seeds | 10.125 | 11.500 | +1.375 |

The pooled 95% sampling interval is [+0.1125, +1.3875]; it excludes model error
and feature-selection uncertainty. The reserved comparison's interval includes
zero. Every diagnostic match had zero late replies and zero tracebacks. Some
individual seeds regress; this is evidence for a controlled official experiment.

The Lightning-only guard scored −0.125 on development seeds and was removed.
The 85 m option scored only +0.0417 across fresh comparisons. The retained
70 m setting is the only behavioral change. No combination is assumed additive.

## Public research

The previous audit enumerated 287 repositories and reviewed 176 new or changed
README/result files. This refresh checked 15 recently updated repositories,
their available trees and new experiment logs. Public authors report gains
from laser access, sensible spacing and safe supply drops; they also report
regressions from wider loot collection, earlier hiding and controller rewrites.
Several repositories share an implementation, so they are not independent
evidence for every feature.

The live board confirms **team 2696 at 6.58**. It does not publish that entry's
repository or commit, and our searches did not identify one. We cannot attribute
6.58 to a particular public feature. See the pinned
[research ledger](docs/v18_research.json) and [diagnosis](docs/V18_DIAGNOSIS.md).

## Validation and submission

The image runs `/usr/local/bin/automata` with `MECH_PARAMS=/bot.json`.
The MIT-licensed foundation is Automata
`f114d641a0de0c565dc057e342b4305b8cfe6d53`; see [attribution](THIRD_PARTY.md).

[Native checks](docs/v18_validation.json): 112 Python tests, 19 Rust tests with
one optional test ignored, 300/300 protocol replies on time, and 840 stress
observations without invalid or late actions. The
[workflow](.github/workflows/validate.yml) builds and checks the actual
linux/amd64 container under one CPU, 512 MiB, no network, a read-only filesystem
and an unprivileged user. Require successful checks on the exact public commit.

Submit [Spandana00/aegis-royale](https://github.com/Spandana00/aegis-royale) with
the exact V18 commit whose checks passed. **Keep the selected 6.27 entry until
a higher official result.** The candidate's official score remains unknown.

Beating 6.58 requires at least **317 placement points in 48 games**, displayed
6.60: 16 more than V17. The saved official cutoff is **11:00 AM Eastern on
Sunday, November 22, 2026**.

[Match rows](docs/v18_matches.jsonl.gz) · [Results](docs/v18_experiments.json) ·
[Settings and hashes](docs/v18_match_sources.json) ·
[Selection](docs/v18_selection.json) · [Official history](docs/v18_official_history.json)
