# V17: protect 6.25 and test faster-charge upgrade priority

The selected champion is **V16, 6.25**, receipt **BB-0E038934**, at
`6e6dd1310d32e79c45117b86dea00601eccf1e5e`. The new screenshot shows the
matching `6e…` prefix. This is the V16 submission handed off after reverting
V15's firing changes and increasing preferred laser spacing. V15 scored 6.15;
the version distinction matters when attributing improvements.

V16 earned 300 placement points over 48 games, three more than V14's 297.
Beating the saved leader's 6.44 requires 310 points, displayed 6.46: ten more
than the new champion. The [official standings snapshot](v17_public_standings.json)
also confirms the cutoff at **11:00 AM Eastern, Sunday November 22, 2026**.
The [updated history](v17_official_history.json) and [source audit](v17_source_audit.json)
retain V1–V16 and use 6.25 as the comparison baseline.

## The selected change

V17 changes one priority relationship: **choose Fast capacitors (`laser_charge`)
before the combat upgrades that previously preceded it**. Plating, armor and
nanites remain first, in the same order. Every relationship between the other
upgrades is preserved.

| Priority segment | Scored V16 | V17 candidate |
| --- | --- | --- |
| Defensive choices | plating → armor → nanites | plating → armor → nanites |
| Next combat choices | gun damage → gun rate → laser damage → laser charge | laser charge → gun damage → gun rate → laser damage |
| Remaining choices | Original order | Same original order |

The protocol gives Fast capacitors **25% shorter charge time per stack**, up to
two stacks. Charging slows movement, so faster charging can make a beam available
sooner and shorten each individual slow-moving charge. That is a mechanism to
test, not a measured guarantee of lower aggregate charging time or higher score.

The official offer rules restrict weapon upgrades to weapons held when the offer
is drawn. Laser upgrades therefore do not enter a gun-only opening offer. The
health prefix and all non-charge priority relationships are unchanged. The source
manifest also proves that every Rust algorithm remains identical to V16: the
only runtime-file edit is the display name. Its 200 m spacing, firing, aim,
equipment acquisition, harvesting, recovery, navigation and random seed rules
are preserved. Upgraded stats can still change encounters and outcomes.

## What the GitHub investigation supports

The refreshed search enumerated **287 repositories**, retrieved **282 recursive
trees**, and reviewed **176 new or changed README/result files** relative to the
earlier corpus. Five trees were unavailable, and no score-labelled images were
found. This is a documented search corpus, not guaranteed exhaustive GitHub
coverage. [Inventory](v17_repository_inventory.json), [trees](v17_repository_scan.json),
[file review](v17_peer_file_review.json), [conclusions](v17_research.json).

The five genuine Aegis-labelled peer projects still do not substantiate official
6.20+ averages. AkChetti's README was renamed to `README-AEGIS.md`; it was found
and inspected rather than treating the old path's 404 as a missing repository.
The public board reports best submissions, not a policy's average across repeated
draws. Decimal hits in other repositories often describe local simulations,
timing, targets or someone else's score.

A useful new source is [recursive-builders' published ledger](https://github.com/sonalrajapaksha/recursive-builders/blob/main/EXPERIMENTS.md).
It reports 6.10 → 6.21 after enabling safe supply-drop collection at
`0984e87ad2b0c297fbac8e9500ef212b6af1b302`, then 6.25 after tuning its drop value
at `863fa4e85d7fefb93fec4d0bbaaa8a4b61cad967`. Other settings tied or regressed.
The exact latter commit's [Dockerfile](https://github.com/sonalrajapaksha/recursive-builders/blob/863fa4e85d7fefb93fec4d0bbaaa8a4b61cad967/Dockerfile)
runs Go; its default branch still has an older Python image. We inspected the
referenced implementation rather than attributing the result to that older code.
The public board also lists `recursive` at 6.25, but exposes no scored commit;
the exact mapping remains author-reported.

Across the stronger documented families, the repeated design themes are useful
second-weapon acquisition, health/armor/repair, converting resources into upgrades,
and coordinating movement with weapon-specific firing and recovery. These are
shared design principles, not isolated causal explanations of the 6.44 leader.
Its scored source mapping remains unverified.

We already have supply-drop capture. In 64 traced V16 validation matches it began
three captures and completed two; only one was interrupted. A capture-hold rewrite
is therefore not supported as the present bottleneck and was not added. Similarly,
the latest Automata rooftop/safety bundle is unscored at an exact verified commit
and was not imported over our independently scored 6.25 configuration.

In those same 64 V16 traces, 22 gun upgrades and 17 laser upgrades were chosen
while holding a laser. Gun upgrades remain useful, especially against targets
approached closely. These counts justify comparing priorities; they do not prove
that the existing choices were wasted.

## Independent and combined comparisons

All arms use the frozen V16 executable, SHA-256
`792d7ef93528b12f597bb8d8e751ad6842334f6caf1fe527f9e4fa8e30ad56c8`,
the complete V16 configuration, and the same seeds within each cohort. Only the
listed upgrade order differs. The health prefix and 200 m range are fixed.

| Initial screen, 16 seeds per arm | Proxy mean | Difference |
| --- | ---: | ---: |
| V16 control | 7.0000 | — |
| Laser damage first | 6.8125 | −0.1875 |
| Laser charge first | 7.0625 | +0.0625 |
| Both laser upgrades first | 7.2500 | +0.2500 |

The joint arm looked strongest in the initial screen. It did not hold up on the
fresh comparisons:

| Fresh comparison, 24 seeds per setting | V16 | Charge only | Both laser priorities |
| --- | ---: | ---: | ---: |
| Moderate reconstructed pursuit | 5.5417 | 6.0000 | 5.5417 |
| Faster reconstructed pursuit | 4.6250 | 4.3750 | 4.4167 |
| Pooled, 48 seeds per arm | 5.0833 | 5.1875 | 4.9792 |

Thus, the combined change lost 0.1042 proxy points while charge alone gained
0.1042. Neither establishes an official effect. The faster setting is a real
counterexample to an unconditional improvement claim. The combined priority is
rejected; charge only was selected before examining the reserved cohort.
[Selection record](v17_selection.json).

| Selected candidate comparison | V16 | Charge only | Difference |
| --- | ---: | ---: | ---: |
| Reserved intermediate pursuit, 32 seeds | 4.87500 | 5.15625 | +0.28125 |
| Fresh plus reserved, 80 seeds per policy | 5.00000 | 5.17500 | +0.17500 |

The pooled paired bootstrap 95% sampling interval is **[−0.15, +0.5125]**. It
includes zero and does not account for simulator error or feature selection.
This is a controlled next official experiment, not a proven winner or a 6.44+
forecast. Charge-upgrade picks rose from 11 to 19 across the 80 traced matches,
confirming activation; aggregate charging fractions were not uniformly lower.

A separate eight-seed FFA sanity cohort gave 9.50 for V16 and 10.625 for the
candidate. This is too small and too approximate to establish final-round
superiority. It is not pooled into practice comparisons. There were zero late
replies or tracebacks in the 288 diagnostic policy matches.

## Preserve the best scored version

[champion.json](../champion.json) points to the immutable 6.25 commit and receipt.
The candidate's audit must reference that champion and retain its 200 m spacing.
An unscored candidate cannot replace the champion based on simulator results.
Promotion requires a higher official result, an exact public commit, and passing
container checks. Keep the selected 6.25 entry until that happens; apply the same
rule after passing 6.44. This protects the scored submission while allowing
separate, reviewable experiments. It cannot guarantee a score on new final seeds.

## Validation and reproduction

[Validation](v17_validation.json) records native checks; the GitHub workflow builds
and checks the actual image with the competition CPU, memory, filesystem and user
limits. Protocol checks do not measure placement. The 300-observation fixture is
gun-only, so source equality and explicit priority constraints matter here.

[All 288 match rows](v17_matches.jsonl.gz), [summaries and trace counters](v17_experiments.json),
[source/settings metadata](v17_match_sources.json), and [manifest](v17_manifest.json)
are versioned. The referee is JuanQuenga/buildathon-mech-royale at
`b50b794522c134d9eb54cc2e9bc4782f4f4a3da9`. Its opponent behavior and escalation
are reconstructed, and wall-clock planning budgets can introduce replay variation.

Build the scored V16 worktree with Rust 1.95.0 and use a fresh output filename:

```sh
python3 -B check/study_v17.py --arms control,charge --seeds 10300-10331 \
  --pursuit .8 --executable /path/to/v16-automata --traces \
  --out local-results/reproduction.jsonl
```

The candidate remains unscored until the organizer evaluates its exact public
commit. A successful local or container check must not be described as a new
official practice result.
