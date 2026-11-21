# AEGIS Royale

**V12 candidate: unscored. Best reported official result: V10, 5.33. V11 scored 5.25.**

V12 retains V11's bounded weapon collection and adds grounded combat sprinting.
It was selected after feature screens and fresh-seed comparisons. The other
experiments remain disabled. See [the feature ranking and results](docs/V12_COMPARISON.md).
The 6.00 target has not been established by an official run.

**The active Docker entrypoint is `pilot/main.py`.** Root `bot.py` preserves V9
for historical comparisons and is excluded from the active image.

## Current behavior

The foundation is adapted, with MIT attribution, from Juan Quenga's `good-31`
policy: surface-aware routes, planned jet hops, zone travel estimates,
laser-first equipment, steady strafing, recovery, upgrades and an independent
26 ms process deadline guard. V11 collects a nearby useful secondary during
otherwise favorable gun-only fights while retaining fire and zone priority.

V12 sprints during grounded `engage` movement when energy exceeds 40. It does
not start a combat sprint during a laser charge; carrying lightning raises the
energy threshold to 60. Existing route, airborne boost and recovery rules apply.

| Experiment switch | Submitted default | Decision |
| --- | ---: | --- |
| `arm_commit` | true | Retain bounded V11 arming |
| `fight_boost` | 40 | Selected V12 change |
| `pickup_race` | false | Did not improve the first screen |
| `wide_band` | false | Did not improve the first screen |
| `focus_lock` | false | Did not improve the first screen |
| `pursuit_range` | false | Not promoted; one combined screen incurred zone damage |
| `predictive_move` | false | Improved one fresh pursuit model and regressed the other |

The flags support reproducible experiments through `MECH_BRAIN`. Their presence
does not activate them. Source hashes and protected function scopes are in
[reference_manifest.json](docs/reference_manifest.json). See [THIRD_PARTY.md](THIRD_PARTY.md).

## Evidence

Two fresh sets of 24 simulated squad matches compared the exact V10 checkout,
V11 and two candidate packages. V12's selected package averaged 5.458 versus
V10's 5.083 with moderate pursuit, and 3.958 versus 3.833 with faster pursuit.
The pooled difference is +0.25, with a paired 95% interval of approximately
[-0.36, +0.86]. It is a provisional experiment, not an established placement gain.

These are third-party simulations with reconstructed house AI and locally
chosen seeds. They are not leaderboard scores and cannot establish 6.00.
The [raw diagnostics](docs/v12_matches.jsonl.gz), [summaries](docs/v12_experiments.json)
and [research ledger](docs/v12_research.json) preserve the evidence and limits.

## Reported official runs

| Version | Official score reported by our user | Experiment |
| --- | --- | --- |
| V1 | 3.75 | Initial policy |
| V2 | 4.50 | Coordinated fire, recovery and navigation |
| V3 | 3.96 | Broader retreat |
| V4 | 4.40 | Stronger projectile dodge |
| V5 | 4.17; 4.15 | Reload cover |
| V6 | 4.46 | Falling-target prediction |
| V7 | 4.60; 4.52 | Weapon range control |
| V8 | 4.60 | Online aim-model selection |
| V9 | 4.77 | Tactical equipment and cube collection |
| V10 | **5.33** | Attributed upstream `good-31` reproduction |
| V11 | 5.25 | Bounded weapon commitment and pickup ordering |
| V12 | Unscored | Grounded combat boost, retaining V11 arming |

Keep the 5.33 entry selected until another official result improves it.

## Build and validate

```sh
python3 -B -m unittest discover -s tests -v
python3 check/check.py -- python3 -B -u pilot/main.py
python3 -B check/benchmark.py
docker build --platform linux/amd64 -t aegis-royale .
python3 check/check.py --map-dir /arena -- docker run --rm -i \
  --network none --cpus 1 --memory 512m --memory-swap 512m \
  --pids-limit 128 --cap-drop ALL --read-only \
  --tmpfs /tmp:rw,size=64m --user 65534:65534 \
  -v "$PWD/arena:/arena:ro" aegis-royale
```

The image pins Python by digest and NumPy to 2.5.5. GitHub Actions builds the
actual image and runs the tests and organizer's checker under the runtime limits.
The native timing benchmark covers 840 observations; it measures behavior and
time, not placement. Fifty-seven older tests cover the retained V9 policy.

## Reproduce the feature comparison

Clone the simulator separately and pin it before running. Create the exact V10
checkout, then run an experiment with a fresh output path:

```sh
git clone https://github.com/JuanQuenga/buildathon-mech-royale ../reference-juan
git -C ../reference-juan checkout b50b794522c134d9eb54cc2e9bc4782f4f4a3da9
git worktree add ../baseline-v10 d75253a91ccb4d199d4374c076ee0d58c383e590
python3 -B check/ablate.py --sim-root ../reference-juan \
  --baseline-root ../baseline-v10 --seeds 4000-4023 \
  --arms v10,v11_arm,arm_boost,arm_predictive --jobs 3 \
  --out local-results/comparison.jsonl
```

Different machine scheduling can change proxy outcomes. The harness records
per-arm source hashes, settings, raw matches and paired uncertainty.

## Submit

Submit [this public repository](https://github.com/Spandana00/aegis-royale) with
the exact validated 40-character commit hash on the Builders track page.
Practice uses 48 matches; the limit is four submissions per hour. Keep every
submitted commit public. The documented cutoff is November 22, 2026 at 11:00 AM EST.
