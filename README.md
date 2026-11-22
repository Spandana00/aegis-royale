# AEGIS Royale

**Best official entry: V14, 6.19 (BB-A804A35A). V15 scored 6.15
(BB-05A9CC68). The active V16 candidate is unscored.**

V16 restores V14's complete Rust runtime and changes one strategy setting:
preferred laser range **140 → 200 m**. Its original equipment, harvesting,
recovery, zone, weak-target approach and firing rules remain together. V15's
shared aim and damage-based release changes are removed from the active source.
The MIT-licensed foundation is Automata at
`f114d641a0de0c565dc057e342b4305b8cfe6d53`.

The image runs `/usr/local/bin/automata` with `MECH_PARAMS=/bot.json`.
The [manifest](docs/v16_manifest.json) proves that only the display name and
configuration differ from the scored V14 runtime. Legacy Python policies are
retained for history and are not copied into the image.

## Evidence

The exact V15 was rerun at the user's request: 300/300 recorded checks and
840 stress observations passed. Across 32 new matched simulator seeds it
averaged 5.4375 versus V14's 5.71875. The direction reversed between opponent
settings. This repeat does not justify replacing V14.

For V16, **336 new diagnostic matches** cover that rerun, a spacing/late-threat
factorial screen, fresh comparisons, a reserved holdout and a separate FFA
sanity check. These use a reconstructed simulator, not the official house squad.

| V14-based comparison | V14 | V16 spacing | Difference |
| --- | ---: | ---: | ---: |
| Fresh moderate pursuit, 16 seeds | 5.9375 | 6.4375 | +0.5000 |
| Fresh faster pursuit, 16 seeds | 4.0000 | 4.5625 | +0.5625 |
| Reserved intermediate pursuit, 32 seeds | 5.0625 | 5.1250 | +0.0625 |
| Pooled validation, 64 seeds per policy | 5.015625 | 5.312500 | +0.296875 |

The reserved result is nearly flat. The pooled 95% sampling interval
[−0.046875, +0.671875] includes zero and excludes model error. The separate
eight-seed FFA check is small and cannot establish final-round superiority.
Combining spacing with late threat recognition performed worse than spacing
alone on the fresh seeds, so that additional setting is not selected.

The GitHub investigation requested 225 repository trees, retrieved 218 and
reviewed 44 candidate result files. Five Aegis-labelled sources did not
substantiate official 6.20+ scores. The stronger Automata/GMUNVIS family remains
the relevant source evidence; the 6.44 leader's scored code mapping is unknown.
The [full diagnosis](docs/V16_DIAGNOSIS.md) distinguishes these limits from
verified receipts and source equality. No 6.44+ result is claimed.

## Validation and submission

[Validation](docs/v16_validation.json) records native checks and their scope.
The [workflow](.github/workflows/validate.yml) builds and tests the actual
linux/amd64 image with one CPU, 512 MiB, no network, a read-only filesystem
and an unprivileged user. Require green checks on the exact public commit.

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

Submit [Spandana00/aegis-royale](https://github.com/Spandana00/aegis-royale)
with the exact public V16 commit whose checks passed. Keep **V14's 6.19
selected** until a higher official result is returned. The saved leader score
of 6.44 requires thirteen additional total placement points over V14 to beat;
the first possible higher displayed score is 6.46.

[Analysis](docs/V16_DIAGNOSIS.md) · [All match rows](docs/v16_matches.jsonl.gz) ·
[Summaries](docs/v16_experiments.json) · [Source hashes and settings](docs/v16_match_sources.json) ·
[Research](docs/v16_research.json) · [History](docs/v16_official_history.json) ·
[Attribution](THIRD_PARTY.md)
