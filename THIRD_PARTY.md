# Third-party software

## V10 active policy

The `pilot/` package is adapted from
[JuanQuenga/buildathon-mech-royale](https://github.com/JuanQuenga/buildathon-mech-royale),
commit `1f7fa6fa9204e80b7b3cb6ed9180c33b7b7aeaf3` (tag `good-31`).
Copyright (c) 2026 Juan Quenga. MIT licensed; the complete original copyright
and permission notice is retained in [pilot/LICENSE](pilot/LICENSE).

Combat, objectives, geometry, navigation and the map cache are copied unchanged.
`main.py` changes the Python package name from `bot` to `pilot` and the display
name to `AEGIS v10`. No policy parameter is changed. File hashes are recorded
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
not copied into the V10 image and are not its entrypoint.

Other repositories in the research ledger were reviewed for evidence and ideas;
their code is not included in the image.
