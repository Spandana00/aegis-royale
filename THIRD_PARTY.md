# Third-party software

## V13 active policy

The `sentinel/` package reproduces the complete MIT-licensed Oval Sentinel
recovery-v26 implementation from
[JishnuMadav/mech-royale](https://github.com/JishnuMadav/mech-royale), commit
`2054a5bb27fdd36c8b8f63eebddbcf145737694e`. Copyright (c) 2026 JishnuMadav.
The complete license is retained in [sentinel/LICENSE](sentinel/LICENSE).
The author reports 5.85 (BB-7097A598); our adaptation has no official score.

`bot.py`, `survivor.py`, `navigation.py`, `combat.py` and the organizer's
`mechfight.py` wrapper are preserved. Imports become package-relative to avoid
conflicts with retained AEGIS sources, and the display name becomes AEGIS v13.
There are no tactical edits or parameter changes. Tests reverse those two
transformations and verify every original SHA-256 and Git blob ID against
[the manifest](docs/sentinel_manifest.json). The source's 13 scenario tests
are retained with import and local fixture paths adapted.

The active image copies only `sentinel/`. The `pilot/` experiments below are
historical diagnostics and do not run in the competition image. V13 source
selection, local comparisons and limitations are in
[the diagnosis](docs/V13_DIAGNOSIS.md).

## V10 foundation and V11/V12 adaptations

The `pilot/` package is adapted from
[JuanQuenga/buildathon-mech-royale](https://github.com/JuanQuenga/buildathon-mech-royale),
commit `1f7fa6fa9204e80b7b3cb6ed9180c33b7b7aeaf3` (tag `good-31`).
Copyright (c) 2026 Juan Quenga. MIT licensed; the complete original copyright
and permission notice is retained in [pilot/LICENSE](pilot/LICENSE).

V10 initially copied combat, objectives, geometry, navigation and the map cache
unchanged. V11 adds bounded weapon commitment, pickup ordering, diagnostics
and a zero-HP arithmetic guard in `brain.py`. The process entrypoint changes
the package name from `bot` to
`pilot` and the display name to `AEGIS v12`. V12 enables grounded combat boost
and retains V11's arming behavior. Other experiments remain behind disabled
switches in `brain.py` and `navigate3.py`. At V12, ballistics, combat, threats,
state, arena geometry, the navigation cache and the process guard retained V10.
V13's retained diagnostic copy adds the scoped combat/cover experiments described
in its manifest; those files are excluded from the active image.
File hashes and the tactical change scope are recorded
in [docs/reference_manifest.json](docs/reference_manifest.json).

This is an attributed policy reproduction, not an original implementation of
those modules. The author's reported score is not a score for this repository.

## NumPy

The container installs NumPy 2.5.5, matching the upstream Docker pin. NumPy is
BSD licensed; its distribution includes its license notices.
Source: [NumPy v2.5.5](https://github.com/numpy/numpy/releases/tag/v2.5.5).

## Builders kit and earlier AEGIS versions

`mechfight.py`, the protocol/schema, organizer checker and recorded stream,
and the campus arena originate from the Builders starter kit. Root `bot.py`,
`aiming.py`, `navigation.py` and `world.py` preserve AEGIS V9's source. They are
not copied into the active image and are not its entrypoint.

Other repositories in the research ledger were reviewed for evidence and ideas;
their code is not included in the image.

## V12 research and independent experiments

The movement-lookahead, pickup-race and range experiments were independently
implemented after studying the MIT-licensed
[aqilc/mech-royale](https://github.com/aqilc/mech-royale), inspected at
`fdfe7a609cc55eb338f277dfc68560cb944a71ef`. The scored `far5` reference is
`8ed48da5e0ca7b01097019d1a1038c892e1fd174`. No TypeScript code was copied into
this Python runtime. `pilot/local_motion.py` is the independent lookahead
experiment and is disabled in the submitted defaults.

Grounded combat boost and target commitment were studied in the MIT-licensed
[justnau/giddygiddyboy-mech-royale](https://github.com/justnau/giddygiddyboy-mech-royale),
inspected at `207fc1c9695cea4baa4a18ac3738877531a8898d`. No Go source was copied.
The historical 6.00 score is another participant's report and does not establish
a same-policy average. Pinned evidence and experiment decisions are in
[docs/v12_research.json](docs/v12_research.json).

The external simulator used for V12 diagnostics is Juan Quenga's MIT-licensed
repository at `b50b794522c134d9eb54cc2e9bc4782f4f4a3da9`. It is cloned separately
for analysis and is not included in this repository or its competition image.
