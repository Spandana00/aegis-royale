# V18: preserve V17 and test approach distance

V17's official 6.27 is the selected champion: BB-961EADA2,
`e45e734215354fc4f938af15c984a666f446a426`. Its exact-commit
[container run passed](https://github.com/Spandana00/aegis-royale/actions/runs/44976821615).
The screenshot's `e4` prefix corresponds to that handed-off commit. The public
board now shows team 2696 at 6.58, but does not expose its repository or commit.
The next candidate has no official score yet.

## What the official history establishes

| Version | Official score | Total points, assuming 48 integer placements | Relevant change |
| --- | ---: | ---: | --- |
| V14 | 6.19 | 297 | Complete pinned Automata policy, display-name adaptation |
| V15 | 6.15 | 295 | Aim-sharing and cube/armor-aware partial release bundle |
| V16 | 6.25 | 300 | V14 firing restored; laser preference 140 → 200 m |
| V17 | 6.27 | 301 | Laser charge priority after plating, armor and nanites |

Every earlier result and exact commit remains in
[the source audit](v18_source_audit.json) and [history](v18_official_history.json).
V15's aggregate regression does not isolate which component hurt. V16's
configuration differs from V14 only in laser range, and V17 differs from V16
only in priority. Those official gains support retaining their settings, but
are not randomized repetitions or per-match causal explanations. The V14
gun trigger already remained held while aligned and loaded: there was no
cooldown-zero gate to repair.

## New public evidence

The [previous inventory](v17_repository_inventory.json) enumerated 287 repositories;
282 trees were available, with 176 new or changed result/readme files reviewed.
The [new refresh](v18_research.json) covers 15 recent repositories, 12 available
trees and 11 available root READMEs, plus updated experiment ledgers.
Searches for team 2696, 6.58 and Mech Royale did not reveal a scored-source mapping.
This is broad coverage of discoverable public sources, not a claim to have read
every GitHub repository or private entry.

Useful primary author records include:

- [Recursive Builders' experiment ledger](https://github.com/sonalrajapaksha/recursive-builders/blob/0e4ee97191f449cd1fe98ead19e2a71cfd03fb16/EXPERIMENTS.md):
  safe drops 6.10 → 6.21, tuned drop settings 6.25; larger drop priority 6.23,
  wider loot radius 6.06, keeping a hiding profile 5.23, kill-regeneration 6.25 tie,
  and retreating to a landing drop 6.19. Their guessed predictive-controller
  replacements scored 5.15/5.35 against 6.10. These are author-reported official
  outcomes for their Go implementation, not measurements of our Rust policy.
- [BattleRoyale tuning log](https://github.com/SandeepMadhavarapu/BattleRoyale/blob/45e788b45be7cd59910f7a8149976806a78906b1/TUNING.md):
  baseline 6.19, broad sound-awareness addition 5.73 twice, late hiding 6.25,
  earlier hiding 5.83, and best hiding plus drops 6.21. The source is another
  Giddy-family adaptation. Its late-game combination is not assumed useful here.
- [Apex experiment ledger](https://github.com/ahmad-ovh/Buildathon/blob/a484109a70db447abd390ffe871c32026cd15d7e/docs/EXPERIMENTS.md):
  a local anti-Lightning ablation improved modeled outcomes by 0.34 over 96
  matches. That is a mechanism to test, not a verified 6.58 official result.
- [Luke's implementation notes](https://github.com/lukejwaszyn/mech-royale/blob/0300cee44419a942c1606fdc2d6ae259f312486e/README.md):
  local diagnostics emphasize laser access, long-distance combat and close
  contacts, but describe several plausible steering/loot tweaks as noise or
  losses. No 6.58 official claim was found in those notes.

File blob IDs and lookup paths are in the research ledger. Public score claims
are separate from our verified receipt. Shared source families are not
independent replications.

## Diagnosis and hypotheses

In 80 saved V17 modeled fresh/holdout traces, gun hits account for 172,831.5 of
211,787.6 incoming hit damage, about 81.6%. Lightning accounts for 911.6, about
0.43%, across six matches. These figures exclude zone damage and are simulator
evidence. Most incoming gun damage occurred while carrying a laser; gun-only
opponents caused 113,040.7 of the gun damage. Distances use saved replay frames,
not perfect hit-time geometry. See [baseline diagnosis](v18_baseline_diagnosis.json).

The existing strategy computes a weapon preference and then applies
`gear_range`. For a target classified harmless and without a laser,
`gear_range` clamps the preference to `gear_easy_range=55`. That can replace our
200 m laser preference with 55 m. The clamp also overrides the anti-Lightning
floor for a not-yet-dangerous Lightning carrier. The planner's distance band is
8 m; no analysis assumes a 12 m band or that preferred range is a hard boundary.

Four individual arms were screened on 16 shared seeds 12000–12015:

| Arm | Mean modeled points | Difference from V17 setting |
| --- | ---: | ---: |
| Control 55 m | 5.1250 | 0 |
| Lightning-only 70 m floor | 5.0000 | −0.1250 |
| General approach 70 m | 5.9375 | +0.8125 |
| General approach 85 m | 5.5000 | +0.3750 |

The guard's implementation and four focused tests are saved as
[a rejected patch](v18_rejected_guard.patch). It is absent from active source.
The screening binary and source patch hashes are recorded separately; fresh
comparisons use the actual frozen V17 executable, avoiding any experimental
algorithm in the selected comparison.

## Selection and reserved confirmation

Both 70 m and 85 m were compared against control on 24 new moderate-pursuit seeds
12100–12123 and 24 new faster-pursuit seeds 12200–12223. The 70 m arm tied moderate
control and gained 1.4583 in faster pursuit: pooled +0.7292. The 85 m arm lost 0.5
in moderate and gained 0.5833 in faster pursuit: pooled +0.0417. More distance
was not uniformly better. We selected 70 m and recorded that decision before
running the reserved seeds.

On 32 untouched intermediate-pursuit seeds 12300–12331, control averaged 5.40625
and 70 m averaged 6.15625, a +0.75 difference. The paired sampling interval
[−0.25, +1.875] includes zero; the nonnegative point-estimate criterion passed.
The predeclared selection and seed settings are in [selection](v18_selection.json).

Pooling fresh and reserved comparisons gives 80 seeds per policy:
5.275 → 6.0125, **+0.7375**, with a paired bootstrap 95% interval
[+0.1125, +1.3875]. Those intervals quantify sampling variation under this
model, not model error or feature-selection uncertainty. A separate eight-seed
FFA cohort improves 10.125 → 11.5; it is a small sanity check, not evidence of
official final-tournament strength. Across all 288 policy matches: zero late
replies and zero bot tracebacks. Individual seeds still regress.

The selected comparison retained early laser access (46 → 48 matches with a
laser by 30 seconds, 69/80 ever for both) and increased mean cubes at finish/death
6.8625 → 7.9125. It also survived longer and dealt more damage. However, incoming
gun damage per live second and geometric close-opponent frequency did **not**
fall. We therefore do not claim reduced global gun exposure as the demonstrated
mechanism. The supported result is a better modeled placement/kill outcome from
one parameter, with secondary counts reflecting changed encounters and survival.
See [replay associations](v18_validation_mechanisms.json).

## Final source and release rule

Only `gear_easy_range` 55 → 70 changes behavior relative to V17. The display name
becomes AEGIS v18. The complete 22-item upgrade priority, 200 m laser spacing,
firing, aim, harvest, equipment, recovery, navigation and randomization remain
byte-identical or configuration-identical to the champion. Lightning rush at
30 m is still below both approach caps and retains its existing rule.

[The manifest](v18_manifest.json) reconstructs every original source Git blob;
[the audit](v18_source_audit.json) covers all 17 scored versions. Native checks:
112 Python passes, 19 Rust passes/one optional ignore, 300/300 protocol replies
on time, 840 stress observations without late or invalid actions. Actual sandbox
validation must pass on the exact pushed commit before handoff.

The official champion remains 6.27. New local evidence does not promote V18 or
predict 6.58. Keep the selected V17 receipt unless an official higher result is
returned. Exceeding the current 316/48 leader requires 317/48, displayed 6.60:
16 extra placement points over V17. Deadline: Sunday, November 22 at 11 AM Eastern.
