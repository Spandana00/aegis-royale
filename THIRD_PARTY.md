# Third-party software

## V14 active policy

The `automata/` tree reproduces the MIT-licensed policy from
[jason-scheffel/automata](https://github.com/jason-scheffel/automata), commit
`f114d641a0de0c565dc057e342b4305b8cfe6d53`.
Copyright (c) 2026 Jason Scheffel. The complete license is retained in
[automata/LICENSE](automata/LICENSE) and the final container.

The only implementation change is the display name, from `automata` to
`AEGIS v14`. All 35 original source, configuration, lock and license files are
verified against [their source hashes and Git blob IDs](docs/automata_manifest.json).
The original configuration is preserved in full. Packaging and research scripts
are outside that implementation. No Go or historical Python policy is mixed into it.

The public GMUNVIS repository identifies Automata f114d64 as its source;
normalizing line endings and the name reproduces its runtime tree. The official
board shows GMUNVIS at 6.23 and Team 67 at 6.29. The board does not disclose their
submitted commit IDs, so these are corroborating source-family results, not
verified exact-commit scores or a prediction for V14.

Rust dependencies are locked in `automata/Cargo.lock`. Their MIT and applicable
Unicode license notices are retained in [RUST_LICENSES.txt](RUST_LICENSES.txt)
and copied into the final image. The final image contains the compiled Rust
policy, configuration and license notices. It does not include the retained
Python experiments or their NumPy dependency.

## V13 retained policy

The `sentinel/` package reproduces the complete MIT-licensed Oval Sentinel
recovery-v26 implementation from
[JishnuMadav/mech-royale](https://github.com/JishnuMadav/mech-royale), commit
`2054a5bb27fdd36c8b8f63eebddbcf145737694e`. Copyright (c) 2026 JishnuMadav.
The complete license is retained in [sentinel/LICENSE](sentinel/LICENSE).
The author reports 5.85 (BB-7097A598); our V13 adaptation scored **5.79**, receipt BB-EDE179C7.

`bot.py`, `survivor.py`, `navigation.py`, `combat.py` and the organizer's
`mechfight.py` wrapper are preserved. Imports become package-relative to avoid
conflicts with retained AEGIS sources, and the display name becomes AEGIS v13.
There are no tactical edits or parameter changes. Tests reverse those two
transformations and verify every original SHA-256 and Git blob ID against
[the manifest](docs/sentinel_manifest.json). The source's 13 scenario tests
are retained with import and local fixture paths adapted.

The archived V13 image copied only `sentinel/`. The `pilot/` experiments below are
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

The Python audit container installs NumPy 2.5.5, matching the upstream Docker pin. NumPy is
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
