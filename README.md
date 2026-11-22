# AEGIS Royale

**Our selected official baseline is V14: 6.19, receipt BB-A804A35A. V15 is unscored.**
The checked public leaders reached 6.38; exceeding that rounded score requires
307 placement points across 48 games (displayed 6.40), ten more than V14.

V15 keeps V14's movement, equipment priorities, harvesting, recovery and random
seed rules. It adds a coordinated firing change to the MIT-licensed Automata
foundation: cube-aware laser damage, an armor bound from the enemy's earned
upgrade offers, and a common aim that permits gun fire during the final laser
charge window. The common aim remains inside the central half of the laser's
alignment tolerance and must pass an explicit map sightline check.

**The image runs `/usr/local/bin/automata` with `MECH_PARAMS=/bot.json`.**
`aim_share`, `beam_damage_fix` and `beam_armor_budget` are enabled;
`aim_motion_fix` is disabled. The original gear and movement parameters remain.
The scoped [source manifest](docs/v15_manifest.json) reconstructs every original
upstream Git blob after reversing the documented changes.

## Why these changes together

We refreshed 225 public repository records and 171 available READMEs, audited the
V1–V14 scores and ran **992 new diagnostic matches**. The [full analysis](docs/V15_DIAGNOSIS.md)
separates official evidence, public claims, physics tests and simulator outcomes.
The repository scan did not identify a verified source-to-submission mapping for
the 6.38 leaders. V14's own 6.19 receipt is the baseline.

| Final configuration | Moderate squad, 16 seeds | Faster squad, 16 seeds | Pooled proxy mean |
| --- | ---: | ---: | ---: |
| V14 control | 6.0625 | 4.0000 | 5.03125 |
| V15 | 6.8125 | 4.2500 | **5.53125** |

The paired difference is +0.50, with bootstrap 95% sampling interval
[-0.09375, 1.1875]. A separate 16-seed FFA check gave 11.00 versus 10.75.
These small results remain uncertain and cannot predict an official score.

Earlier individual laser and motion fixes tied V14 over 64 fresh squad seeds;
their combination regressed. A more precise laser estimate still did not win
alone. On a separate factorial comparison, aim sharing and that estimate each
lost slightly alone, but together gained 0.46875 proxy points. The final sightline
guard was then checked on reserved seeds. Full raw results, hashes, settings and
rejected combinations are retained, including two late replies in unselected
arms and zero late replies in final-candidate matches.

## Validation

- **111 Python tests** pass, including source provenance and retained policies.
- **27 Rust tests** pass with the real arena and recorded observations; one
  optional upstream test remains ignored.
- Native official conformance: **300/300** on time, no dropped replies, wrong
  ticks or bad lines; maximum 11.2 ms on the development host.
- Configured native policy: **840 recorded/synthetic observations**, no invalid
  actions or responses above 50 ms; maximum 43.122 ms on the development host.
- With all new switches off, the final executable reproduces **300/300 V14
  recorded actions exactly**.

The [workflow](.github/workflows/validate.yml) builds the actual final image and
runs both conformance and the 840-observation benchmark with one CPU, 512 MiB,
no network, a read-only filesystem and an unprivileged user. Check its result
on the exact submitted commit. Host timings are not container measurements.

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

For a native Rust 1.95.0 release build, run `check/benchmark.py --policy automata
--executable <binary>`. `--command` can instead launch the competition container;
the workflow shows the required map mount. Historical Python benchmarks require
an explicit `--policy sentinel`, `pilot` or `v9`.

## Evidence and submission

[Analysis](docs/V15_DIAGNOSIS.md) · [Match rows](docs/v15_matches.jsonl.gz) ·
[Settings and source hashes](docs/v15_match_sources.json) ·
[Summaries](docs/v15_experiments.json) · [Validation](docs/v15_validation.json) ·
[Attribution](THIRD_PARTY.md)

Submit [Spandana00/aegis-royale](https://github.com/Spandana00/aegis-royale)
with the exact public V15 commit whose checks passed. Keep **V14's 6.19 selected**
until a new official result improves it. V15's score and a result above 6.38
remain unverified.
