# AEGIS Royale

Current candidate: **AEGIS v2**. See [the v2 changes and validation](docs/V2.md).

A Python bot for Builders Mech Royale. No API keys, paid services, runtime
network calls, or third-party Python dependencies.

## The track, in simple words

Sixteen robots fight while a shrinking circle pushes them together. Your code
gets a picture of the situation ten times a second and chooses movement, aim,
and shooting. A win gives 15 points; being eliminated first gives zero.
Practice averages 48 matches. Practice opponents cooperate against you, while
the qualifying round and final use free-for-all matches against other entries.
Practice qualifies the entry; the final series decides the winner.

## What this bot does

- Plans routes around buildings, courtyards, bridges, and steep terrain using
  the supplied campus map. It checks whether ground destinations are reachable.
- Leads moving targets and aims at the scaled robot torso. It waits for its
  actual gun direction to line up before wasting shots.
- Uses the gun, releases charged lasers, aims ballistic mortar shells, and
  saves lightning energy when nothing is in range.
- Collects cubes and useful weapons, farms safe crates, and considers supply
  drops for healing. It prefers lightning for close fights and keeps the gun.
- Strafes, evaluates incoming projectile paths, and keeps the torso toward
  attackers to protect rear armor.
- Seeks cover and stops shooting when retreating to heal. It moves inward
  before the shrinking circle reaches it and saves energy for escapes.
- Chooses upgrades for survival, mobility, and the weapons it carries.

This is an initial candidate, not a proven leaderboard winner. The included
checker and synthetic probes cannot predict an official score or rank.

## Run the checks

From this repository's root, with Python 3.10 or newer:

```sh
python3 -B -m unittest discover -s tests -v
python3 check/check.py -- python3 -B -u bot.py
python3 -B check/benchmark.py
python3 -B check/navigation_probe.py
```

The benchmark combines 300 recorded observations with 220 synthetic busy
combat observations. The navigation probe moves through a simplified local
controller on the real campus map. Neither is a match simulator or scorer.

## Required Docker check

```sh
docker build --platform linux/amd64 -t aegis-royale .
python3 check/check.py --map-dir /arena -- docker run --rm -i \
  --network none --cpus 1 --memory 512m --read-only \
  --tmpfs /tmp:rw,size=64m --user 65534:65534 \
  -v "$PWD/arena:/arena:ro" aegis-royale
```

The root Dockerfile pins Python 3.13.7 by image digest. Its default user is
65534 and its Python bytecode cache is disabled. The map comes from the
organizer's `/arena` mount; it is not copied into the image.

The GitHub Actions workflow runs the tactical tests and this exact Docker
check on every push. Inspect its result before submitting. A successful local
Python check alone does not establish Docker conformance.

## Publish and submit

The public repository must contain **this folder's contents at its root**,
with `Dockerfile` at the top level. Do not nest the folder inside the repo.

If this folder has not already been published and GitHub CLI is authenticated:

```sh
git init -b main
git add .
git commit -m "Add AEGIS Mech Royale bot"
gh repo create aegis-royale --public --source . --remote origin --push
git rev-parse HEAD
```

Submit the public GitHub repository URL and the full 40-character commit hash
on the [Mech Royale track page](https://www.joinbuilders.org/buildathon/tracks/builders).
An exact commit makes the scored version reproducible. Keep submitted commits
public until results are published. There are at most four submissions per hour.

The cutoff is Sunday, November 22, 2026 at 11:00 AM EST.

## First-score optimization loop

1. Submit this version once; record its commit, score, rank, and official
   feedback. Wait for the 48-match run to finish.
2. Change one policy at a time. Useful comparisons are combat distance,
   weapon preference, retreat HP, and the balance between loot and fighting.
3. Pass the tactical and Docker checks, then submit the new commit. Compare
   the official score on the fixed practice seeds; timing can cause variation.
4. Preserve the earlier best commit. The system normally retains the best
   score, and earlier submissions win score ties. Do not optimize only for
   cooperative practice bots: the final uses unseen seeds and free-for-all play.

## Files and credits

`bot.py`, `world.py`, and `navigation.py` implement the new decision policy.
`tests/` contains tactical regressions; `check/benchmark.py` and
`check/navigation_probe.py` are local diagnostic tools.

The Builders starter kit supplies `mechfight.py`, `check/check.py`, the
recorded stream, schema, protocol, and campus map. Those are included for
compatibility, validation, and local map access. No other external code or
libraries are used by the bot. New code is released under the MIT License,
as required by the event.
