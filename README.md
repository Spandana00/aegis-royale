# AEGIS Royale — restored V17 baseline

**Active runtime: exact V17, official best 6.27, receipt BB-961EADA2.**
Scored commit: `e45e734215354fc4f938af15c984a666f446a426`.
This research revision restores that policy; it is not a new higher-scoring bot.

V18 scored **5.94** (BB-9377CE58), versus V17 **6.27**. Its only behavioral
change was `gear_easy_range` 55 → 70 m. That change is reverted. The entire
`automata/` tree now matches V17 exactly, including display name, 55 m approach,
200 m laser preference, upgrade order, firing, harvesting, recovery and RNG.

The local simulator predicted +0.7375 points on 80 paired validation seeds;
the official result lost 16 integer placement points across 48 games. The
simulator is therefore **unqualified for strength forecasts**. More seeds or
a sampling interval excluding zero do not correct this model discrepancy.

```sh
python check/model_qualification.py
# For an automation that requires a qualified strength model:
python check/model_qualification.py --require-qualified
# Currently exits 2, intentionally blocking forecast-based promotion.
```

The refreshed research covers 27 recently updated repositories, a targeted
search for 6.4+/6.58 score claims, and original academic papers on RTS combat
and baseline-preserving improvement. No newly verified higher-scoring exact
implementation was found. Direct Google Scholar retrieval was blocked;
author-hosted and publisher papers were retrieved instead.

[Diagnosis and next experiments](docs/V19_DIAGNOSIS.md) ·
[Research sources](docs/v19_research.json) ·
[Official history](docs/v19_official_history.json) ·
[Model qualification](docs/v19_model_qualification.json) ·
[Source audit](docs/v19_source_audit.json)

The existing [container workflow](.github/workflows/validate.yml) and 112 Python
checks verify the restored source and packaging. Exact-commit GitHub checks
must pass before handoff. Prior scored V17 checks also remain available at
https://github.com/Spandana00/aegis-royale/actions/runs/44976821615.

Keep V17 selected as the final entry. V18 remains archived for diagnosis.
Promote a future candidate only after a higher official result; experimental
candidates must document uncertainty and preserve the champion.
