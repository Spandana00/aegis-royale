# AEGIS Royale

**V13 candidate: unscored. Our best official result remains V10: 5.33. V11 scored 5.25; V12 scored 5.02.**

V13 uses the complete MIT-licensed Oval Sentinel recovery-v26 policy from
[JishnuMadav/mech-royale](https://github.com/JishnuMadav/mech-royale), pinned at
`2054a5bb27fdd36c8b8f63eebddbcf145737694e`. The author reports **5.85** with
receipt BB-7097A598. That is the source repository's reported result, not our score.
Only package imports and the display name change. Tests verify every original
source hash after reversing those transformations; see [the manifest](docs/sentinel_manifest.json).

**The competition image runs `python3 -B -u -m sentinel.main`.** It copies only
`sentinel/`. Earlier `pilot/` and root V9 sources are retained for comparisons.
Their experimental switches do not control V13.

## Why this candidate

The [regression diagnosis](docs/V13_DIAGNOSIS.md) covers 472 local diagnostic
matches, historical official results and public repository evidence. Our small
feature transplants did not establish a dependable improvement. V13 preserves
an intact, publicly scored combination of equipment, firing, loot, navigation
and recovery rules.

- Early laser equipment and weapon-specific distance.
- Rounded-charge release and conservative lethal partial beams.
- Supply capture that stays in the ring for uninterrupted full repair.
- Critical-health recovery below 25%, ending at 60%, with retained safe shelter.
- Energy recharge hysteresis and obstacle-aware zone departure.
- No new movement-halving laser charge during urgent zone escape.

In 48 fresh matched squad diagnostics across two reconstructed pursuit settings,
the intact policy averaged **4.9375** versus exact V10's **4.2500**. The paired
difference was +0.6875, with an approximate sampling interval [0.04, 1.33].
This interval excludes simulator model error; it cannot forecast official score.
The eight-seed FFA sanity check gave V13 11.25 versus V10 11.625, an inconclusive
small-sample difference. The [raw results](docs/v13_matches.jsonl.gz),
[summaries](docs/v13_experiments.json) and [research ledger](docs/v13_research.json)
retain the evidence and limitations.

**Keep the existing 5.33 entry selected until a new official result improves it.**
The 5.50/6.00 targets remain unproven for this adaptation.

## Validation

All **108 tests pass**, including 13 upstream scenario tests and source equivalence
checks. Native conformance answers 300/300 observations on time. The active timing
benchmark covers 840 recorded/synthetic cases with no invalid actions or responses
above 50 ms. GitHub Actions is configured to validate the pinned container;
the V13 container run is pending publication approval.

```sh
python3 -B -m unittest discover -s tests -v
python3 check/check.py -- python3 -B -u -m sentinel.main
python3 -B check/benchmark.py
python3 -B check/compare_versions.py
docker build --platform linux/amd64 -t aegis-royale .
python3 check/check.py --map-dir /arena -- docker run --rm -i \
  --network none --cpus 1 --memory 512m --memory-swap 512m \
  --pids-limit 128 --cap-drop ALL --read-only \
  --tmpfs /tmp:rw,size=64m --user 65534:65534 \
  -v "$PWD/arena:/arena:ro" aegis-royale
```

The active policy uses the Python standard library. The existing image still
installs pinned NumPy so retained policy tests run in that same pinned environment.
See [THIRD_PARTY.md](THIRD_PARTY.md) for attribution and [validation](docs/v13_validation.json).

## Reproduce local comparisons

Clone the external simulator separately and pin it; it is not in the image.

```sh
git clone https://github.com/JuanQuenga/buildathon-mech-royale ../reference-juan
git -C ../reference-juan checkout b50b794522c134d9eb54cc2e9bc4782f4f4a3da9
git worktree add ../baseline-v10 d75253a91ccb4d199d4374c076ee0d58c383e590
python3 -B check/ablate.py --sim-root ../reference-juan \
  --baseline-root ../baseline-v10 --seeds 5500-5523 \
  --arms v10,sentinel --join-per-loss 1 --jobs 3 \
  --out local-results/new-comparison.jsonl
```

The archived moderate comparison uses the exact upstream source before namespacing;
the faster and FFA comparisons use the equivalent `sentinel/` adaptation. Timing
and reconstructed house AI limit repeatability. Retained feature experiments are
available through `MECH_BRAIN` when running `pilot/main.py` explicitly.

## Reported official history

| Version | User-reported official score | Main change |
| --- | --- | --- |
| V1 / V2 / V3 | 3.75 / 4.50 / 3.96 | Initial policy / coordinated fighting / broader retreat |
| V4 / V5 / V6 | 4.40 / 4.17, 4.15 / 4.46 | Projectile dodge / reload cover / falling-target prediction |
| V7 / V8 / V9 | 4.60, 4.52 / 4.60 / 4.77 | Range / adaptive aim / tactical equipment and cubes |
| V10 | **5.33** | Attributed good-31 reproduction |
| V11 | 5.25 | Bounded arming and pickup ordering |
| V12 | 5.02 | Grounded combat sprint |
| V13 | Unscored | Intact attributed Oval Sentinel recovery-v26 policy |

## Submit

Submit [this public repository](https://github.com/Spandana00/aegis-royale) with
the exact validated 40-character commit hash on the Builders track page.
Practice uses 48 matches, with four submissions per rolling hour. Keep every
submitted commit public. The documented cutoff is November 22, 2026 at 11:00 AM EST.
