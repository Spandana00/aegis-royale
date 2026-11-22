# AEGIS Royale

**Selected official champion: V16, 6.25 (BB-0E038934), commit
`6e6dd1310d32e79c45117b86dea00601eccf1e5e`. V17 is an unscored candidate.**

V17 preserves the champion's 200 m laser spacing and complete Rust algorithms.
Its only strategy change is upgrade order: choose **Fast capacitors
(`laser_charge`) after plating, armor and nanites**, ahead of the combat upgrades
that previously preceded it. All other priority relationships remain intact.
Weapon upgrades are offered only for weapons held when the offer is drawn, so
the gun-only opening choices are preserved.

The image runs `/usr/local/bin/automata` with `MECH_PARAMS=/bot.json`.
The MIT-licensed foundation is Automata
`f114d641a0de0c565dc057e342b4305b8cfe6d53`.
The [manifest](docs/v17_manifest.json) pins every original source blob and proves
that only the display name and configuration differ from V16. Existing aim,
firing, equipment, harvesting, recovery, movement and seed rules are retained.

## Comparison

**288 new diagnostic policy matches** compare individual and combined upgrade
priorities, fresh opponent settings, a reserved holdout and a separate FFA
sanity cohort. These use a reconstructed simulator, not the official house squad.

| Charge-priority comparison | V16 | V17 configuration | Difference |
| --- | ---: | ---: | ---: |
| Fresh moderate pursuit, 24 seeds | 5.5417 | 6.0000 | +0.4583 |
| Fresh faster pursuit, 24 seeds | 4.6250 | 4.3750 | −0.2500 |
| Reserved intermediate pursuit, 32 seeds | 4.87500 | 5.15625 | +0.28125 |
| Pooled validation, 80 seeds per policy | 5.000 | 5.175 | +0.175 |

The effect is mixed across opponent settings. The pooled 95% sampling interval
[−0.15, +0.5125] includes zero and does not account for simulator error or
feature selection. This is a controlled next official experiment, not a proven
improvement or a 6.44+ forecast. Prioritizing laser damage and charge together
looked strongest on the initial screen but regressed on fresh comparisons, so
that combination is rejected.

The refreshed GitHub search enumerated 287 repositories, retrieved 282 trees
and reviewed 176 new or changed README/result files. Five genuine Aegis-labelled
peer sources did not substantiate 6.20+ official averages. A new author-documented
6.25 Go implementation attributes gains to safe supply drops; our bot already
has that feature. The [full diagnosis](docs/V17_DIAGNOSIS.md) separates public
claims, verified receipts, source equality and local diagnostic results.

## Preserve the champion

[champion.json](champion.json) keeps the exact 6.25 commit and receipt. Promotion
requires a higher official result, an exact public commit and passing container
checks. Local simulations cannot promote an unscored candidate. Keep the selected
6.25 entry while testing V17, and use the same rule after exceeding 6.44.

Beating 6.44 requires 310 placement points across 48 games, displayed 6.46:
ten more than V16. The saved official cutoff is **11:00 AM Eastern on Sunday,
November 22, 2026**.

## Validation and submission

[Validation](docs/v17_validation.json) records the native checks and their scope.
The [workflow](.github/workflows/validate.yml) builds and checks the actual
linux/amd64 image under one CPU, 512 MiB, no network, a read-only filesystem and
an unprivileged user. Require green checks on the exact public commit.

```sh
python3 -B -m unittest discover -s tests -v
python3 -B check/compare_versions.py
docker build --platform linux/amd64 -t aegis-royale .
python3 check/check.py --map-dir /arena -- docker run --rm -i \
  --network none --cpus 1 --memory 512m --memory-swap 512m \
  --pids-limit 128 --cap-drop ALL --read-only \
  --tmpfs /tmp:rw,size=64m --user 65534:65534 \
  -v "$PWD/arena:/arena:ro" aegis-royale
```

Submit [Spandana00/aegis-royale](https://github.com/Spandana00/aegis-royale) with
the exact public V17 commit whose checks passed. Its official result remains
unknown until the organizer evaluates it.

[Analysis](docs/V17_DIAGNOSIS.md) · [All match rows](docs/v17_matches.jsonl.gz) ·
[Summaries](docs/v17_experiments.json) · [Settings and hashes](docs/v17_match_sources.json) ·
[Research](docs/v17_research.json) · [History](docs/v17_official_history.json) ·
[Attribution](THIRD_PARTY.md)
