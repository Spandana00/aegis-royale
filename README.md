# AEGIS Royale

**V13 scored 5.79 (BB-EDE179C7) and remains our selected best entry.
V14 is a new, unscored candidate targeting at least 6.20.**

V14 reproduces the complete MIT-licensed
[Automata policy](https://github.com/jason-scheffel/automata/tree/f114d641a0de0c565dc057e342b4305b8cfe6d53),
with its original configuration. The only implementation edit is the display name.
The final image runs `/usr/local/bin/automata` with `MECH_PARAMS=/bot.json`.
[Source hashes](docs/automata_manifest.json) verify all 35 imported files.
Attribution and dependency notices are in [THIRD_PARTY.md](THIRD_PARTY.md).

The public GMUNVIS tree names this source; the official board shows that team
at 6.23 and Team 67 at 6.29. The board does not reveal their submitted commit IDs.
These are corroborating source-family results, **not V14's score**.

## Selection evidence

We reviewed 220 public repository records and 167 available READMEs, rechecked
our V1–V13 history, and ran 368 new diagnostic matches. The
[full diagnosis](docs/V14_DIAGNOSIS.md) distinguishes official receipts, public
score claims, source equivalence and reconstructed simulator results.

| Policy | Fresh moderate squad, 24 matches | Fresh faster squad, 24 matches | Pooled proxy mean |
| --- | ---: | ---: | ---: |
| V13 baseline | 5.0833 | 3.7500 | 4.4167 |
| Public Go 6.17 snapshot | 6.8333 | 3.0417 | 4.9375 |
| Complete Rust configuration: V14 | 6.2500 | 3.8750 | **5.0625** |
| Rust plus earlier safety bundle | 5.2917 | 4.2083 | 4.7500 |

The paired Rust–V13 difference is +0.6458, with bootstrap sampling interval
[-0.25, 1.54]. Model and selection error are additional. A 16-seed FFA check
gave V14 9.125 versus V13 9.750, an inconclusive difference. These diagnostics
cannot predict official score.

The initial factorial screen showed a negative gear × harvesting interaction:
their separate gains did not add. The extra safety bundle looked better on that
screen, then lost its advantage on fresh seeds. We therefore preserve the
complete public configuration instead of promoting screen-winning switches.
The image includes coordinated laser acquisition, persistent loot memory,
resource harvesting, threat-aware physics planning and weapon-specific firing.

Raw [match rows](docs/v14_matches.jsonl.gz), [source/settings metadata](docs/v14_match_sources.json),
[experiment summaries](docs/v14_experiments.json), [repository scan](docs/v14_repository_scan.json)
and [official history](docs/v14_official_history.json) are retained.

## Validation

111 Python provenance/regression tests and 19 Rust tests pass; one optional
upstream Rust test is ignored. Rust tests use the actual campus map and recorded
observations, including 400 synthetic stress cases. Native conformance passes
300/300 with no missed budgets, dropped replies, wrong ticks or bad lines.
Native maximum response time was 12.8 ms. All 368 diagnostic matches had zero
late replies and zero tracebacks. See [validation](docs/v14_validation.json).

GitHub Actions validates the actual final image under one CPU, 512 MiB,
no network, an unprivileged user and a read-only filesystem. Check the workflow
on the exact submitted commit.

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

Native builds require Rust 1.95.0 and the locked dependencies. The
[workflow](.github/workflows/validate.yml) supplies fixture paths for the full
Rust test suite. Reproducing the external match comparisons is described in the
[diagnosis](docs/V14_DIAGNOSIS.md). `sentinel/`, `pilot/` and the root Python bot
remain available for historical checks and are excluded from the final image.
The old Python timing utility requires an explicit `--policy sentinel`, `pilot`
or `v9`; it does not benchmark V14.

## Submit

Submit [Spandana00/aegis-royale](https://github.com/Spandana00/aegis-royale)
with the exact validated public V14 commit. Keep V13's **5.79** selected until
a new official result beats it. At 48 matches, reaching at least 6.20 requires
298 integer placement points, displayed as **6.21**: 20 more than V13's 278.
