# V10: reproduce a documented higher-scoring policy

**Result:** V10 scored **5.33**, receipt `BB-DC5BDF45`, reported in the user's
submission screenshot. It is now our scored baseline. V11's targeted follow-up
is documented in [V11_COMPARISON.md](V11_COMPARISON.md). The remainder records
the evidence available when V10 was prepared.

## Evidence and comparison

Our V9 scored **4.77**, up from V7/V8's 4.60. Broader retreat scored 3.96;
stronger dodging 4.40; reload cover 4.17/4.15. Equipment collection improved
the reported best, but reaching 5.50 still requires 35 more placement points
across 48 matches.

[JuanQuenga's results log](https://github.com/JuanQuenga/buildathon-mech-royale/blob/48288e2b84f8c96685fdd98f09b4960bf1c51876/eval/RESULTS.md)
attributes **5.56** to `good-31`. Its later
[review](https://github.com/JuanQuenga/buildathon-mech-royale/blob/48288e2b84f8c96685fdd98f09b4960bf1c51876/docs/REVIEW.md)
reports nine same-policy draws averaging **5.34** (SD 0.13). These are author
reports, not independently verified score receipts. The tag resolves to
`1f7fa6fa9204e80b7b3cb6ed9180c33b7b7aeaf3`, the reproduced source.

| Evidence | Our V9 | Upstream `good-31` | Interpretation |
| --- | ---: | ---: | --- |
| Reported official best | 4.77, from our user | 5.56, author's log | A reason to test the other policy; different evidence sources |
| Organizer protocol stream | 300/300 timely | 300/300 timely | Both implement the interface |
| Ten matched proxy seeds | 4.80 points | 4.50 points | Does not establish which is stronger officially |

The paired proxy difference is 0.30 with a 95% t interval half-width of 1.58.
Versions, seeds, settings and per-match results are in
[local_reference_comparison.json](local_reference_comparison.json).
The third-party simulator reconstructs the house-bot director and parts of
physics. It does not contain the private official seeds and cannot verify an
official score. It is used here to inspect behavior, not forecast placement.

One legacy proxy match lost 1,145 HP to the zone. A separate source-level
reproduction confirmed that V9 can choose a zone goal inside a building, project
it to ground outside safety, then discard that projection and steer toward
the wall. This is a confirmed code problem, not a measured frequency in our
official runs. The old random route probe did not cover it.

## The larger candidate

V10 uses the complete MIT-licensed policy with attribution. Its navigation
supports standing surfaces, planned roof/jet routes, resumable searches and
zone travel-time estimates. The profile also selects steady strafe reversals
and laser-first equipment. Its independent process guard targets a reply
after 26 ms when the policy is slow.

Ten runtime files, including the baked map, match upstream bytes exactly.
The remaining file changes only package imports and the display name.
Provenance tests reverse those edits and verify the original file hash.
No policy parameter is changed from `good-31`.
See [THIRD_PARTY.md](../THIRD_PARTY.md) and
[reference_manifest.json](reference_manifest.json).

V9 remains at the repository root and at its submitted commit. V10's Docker
entrypoint is `pilot/main.py`. Root `bot.py` and its old tactical tests describe
the retained V9 implementation, not the active image.

## Validation and limits

The image matches upstream's pinned Python base and NumPy 2.5.5 dependency.
The arena is mounted read-only at `/arena`; the route cache is packaged.
The local host's Python environment differs from the pinned image, so CI also
tests that image rather than assuming native checks establish compatibility.

The active policy passes all 300 organizer stream observations with no late
answers. Its 840-observation direct-policy stress check has zero invalid
actions, zero module errors and zero decisions over 50 ms (maximum 8.95 ms,
p99 3.05 ms, process RSS 87.10 MiB). That stress check does not exercise the
separate process guard. Raw results: [v10_benchmark.json](v10_benchmark.json).

There are 62 passing local tests: five active-policy/provenance checks and
57 retained V9 regressions. CI builds the image first, runs those tests with
the pinned dependency, then checks the actual entrypoint as uid 65534 with
one CPU, 512 MB, a read-only root, 64 MB `/tmp` and no network.

The official V10 result is unmeasured. The upstream best does not promise
5.50 here. Submit the validated commit and keep our existing 4.77 entry
selected unless the new result is better.
