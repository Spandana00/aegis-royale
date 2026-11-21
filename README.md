# AEGIS Royale

**Current candidate: V10. Our best reported official score: V9, 4.77.**

V10 reproduces the MIT-licensed `good-31` policy from
[JuanQuenga/buildathon-mech-royale](https://github.com/JuanQuenga/buildathon-mech-royale).
Its author reports a 5.56 best and a 5.34 average over nine same-policy draws.
Those are not independently verified results, and V10 is not yet officially scored.
The full comparison, source hashes and local evidence are in
[docs/V10_COMPARISON.md](docs/V10_COMPARISON.md).

**The active Docker entrypoint is `pilot/main.py`.** Root `bot.py` preserves V9
for comparison; it is not included in the V10 image.

## The track in simple words

Sixteen robots fight while a shrinking circle pushes them together. Our code
chooses where to move, aim and shoot ten times a second. A win gives 15 points;
being eliminated first gives zero. Practice averages 48 matches against a
cooperating house squad. Qualifying and the final are free-for-all matches
against other entries on new seeds.

## Why V10 is different

This is a substantial policy replacement, with explicit upstream credit:

- Surface-aware navigation, rooftop routes and planned jet hops.
- Resumable route searches and travel-time estimates for zone escape.
- Laser-first equipment, steady combat strafes and weapon-specific firing.
- Threat assessment, regeneration, cube collection and supply-drop decisions.
- An independent process deadline guard, targeting replies after 26 ms.

The upstream policy parameters and map cache are unchanged. Only Python package
imports and the display name were edited. Tests verify the exact source hashes.
See [THIRD_PARTY.md](THIRD_PARTY.md) and the complete [MIT notice](pilot/LICENSE).

## Our reported runs

| Version | Official score reported by our user | Experiment |
| --- | --- | --- |
| V1 | 3.75 | Initial bot |
| V2 | 4.50 | Coordinated fire, recovery and navigation bundle |
| V3 | 3.96 | Broader retreat policy |
| V4 | 4.40 | Stronger projectile dodge |
| V5 | 4.17; repeat 4.15 | Reload cover |
| V6 | 4.46 | Falling-target prediction |
| V7 | 4.60; repeat 4.52 | Weapon range control |
| V8 | 4.60 | Online aim-model selection |
| V9 | **4.77** | Tactical equipment and cube collection |
| V10 | Unscored | Attributed reproduction of upstream `good-31` |

Keep the existing 4.77 entry selected until a new official result improves it.
A native check or proxy simulator cannot establish placement or guarantee 5.50.

## Build and validate

From the repository root:

```sh
docker build --platform linux/amd64 -t aegis-royale .
python3 check/check.py --map-dir /arena -- docker run --rm -i \
  --network none --cpus 1 --memory 512m --memory-swap 512m \
  --pids-limit 128 --cap-drop ALL --read-only \
  --tmpfs /tmp:rw,size=64m --user 65534:65534 \
  -v "$PWD/arena:/arena:ro" aegis-royale
```

The image pins the Python base by digest and NumPy to 2.5.5. Runtime needs no
network or external AI service. It runs as uid 65534; the arena is mounted at
`/arena`, and writes are limited to `/tmp` by the match sandbox.

GitHub Actions builds the actual image, runs provenance and regression tests
inside it, then performs the organizer's sandbox conformance check.

For local diagnostics with Python and NumPy already installed:

```sh
python3 -B -m unittest discover -s tests -v
python3 check/check.py -- python3 -B -u pilot/main.py
python3 -B check/benchmark.py                 # active V10, 840 observations
python3 -B check/benchmark.py --policy v9     # retained V9
python3 -B check/compare_versions.py          # requires submitted git history
```

The five active-policy/provenance tests verify the imported source, navigation
cache, selected profile and fallback behavior. The other 57 regressions cover
the retained V9. The benchmark measures behavior and time, not match placement.
Its direct-policy calls do not exercise the separate process guard.

## Submit

Submit [this public repository](https://github.com/Spandana00/aegis-royale) with
the exact 40-character validated commit hash on the Builders track page.
Every submitted commit remains public. The current cutoff is Sunday,
November 22, 2026 at 11:00 AM EST. There are at most four submissions per hour.

The original AEGIS experiments and source remain available in history and at
the root. Research sources and licenses are recorded in
[docs/research_sources.json](docs/research_sources.json).
