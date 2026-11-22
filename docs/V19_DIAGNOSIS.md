# V18 failure and V17 restoration

V17 remains our champion: 6.27, BB-961EADA2, exact commit
e45e734215354fc4f938af15c984a666f446a426. The new screenshot confirms V18
at 5.94, BB-9377CE58, matching the handed-off fe635846 commit prefix.
V18 changed only the approach cap from 55 to 70 m, besides its display name.
At 48 integer-placement games, the rounded scores correspond to 301 versus
285 points: a loss of 16, or 0.3333 per game. No official replay is available,
so the particular deaths, loot diversions or enemy activations remain unknown.

The restored `automata/` tree is byte-identical to V17. Existing manifests and
112 tests verify source identity, full configuration, attribution and packaging.
The V18 experiment and all its raw result rows remain archived. The champion
receipt is not replaced by an unscored candidate.

## Why the previous decision was inadequate

The modeled comparison favored V18 by 0.7375 over 80 fresh/reserved seeds.
Its confidence interval only measured sampling variation inside an invented
opponent model. It did not establish transfer to the official squad. The
official result reverses the sign of that comparison. Extending preferred
distance can also change kill completion, loot collection and encounter timing;
it is not merely a reduction in incoming fire. Our own modeled gun damage per
second had not fallen. The previous recommendation gave insufficient weight
to those limits.

`check/model_qualification.py` now exposes this failed comparison and blocks
strength-forecast workflows with `--require-qualified`. It is a conservative
screening rule, not an implementation of a theoretical RL guarantee. Before
relying on simulator rankings again, check known V15/V14, V16/V14, V17/V16 and
V18/V17 comparisons, then additional official results held out from simulator
tuning. Do not tune against V18 and call that independent validation.

## Updated GitHub evidence

The refresh covers 27 recently pushed repositories and separate searches for
6.58 and 6.4+ claims. Results, file hashes and unavailable README records are
saved in `v19_research.json`. The earlier 287-repository audit remains archived.
No new exact source with a substantiated official result above our baseline was
identified. This is a search outcome, not a claim that such sources do not exist.

The apparent 6.4 search match, ParishruthiGanesh/mech-royale, actually reports
a best of 5.25. A keyword hit is not a verified score. Several new repositories
contain the same source families; their existence does not multiply independent
evidence. The public 6.58 leader still lacks a verified repository mapping here.

Recursive Builders' latest author ledger adds useful negative evidence:
moving toward a future drop scored 5.71 versus 6.25, inward late cover 6.19,
and RNG-only variants 5.65, 5.54 and 5.38. These claims are author-reported and
belong to their Go implementation. None justifies adding those mechanisms to
V17. Existing supply-drop, laser-acquisition and health priorities are retained.

## Scholarly evidence and practical implications

Direct Google Scholar query retrieval failed. Original author/publisher versions
were retrieved instead; the research JSON records access and source limits.

1. Churchill, Lin and Synnaeve (2017), *An Analysis of Model-Based Heuristic
   Search Techniques for StarCraft Combat Scenarios*:
   https://davechurchill.ca/publications/pdf/aiide17_churchill_facebook.pdf.
   Their real-engine comparisons show that model accuracy strongly affects
   whether combat search transfers. Their scripts offer small, interpretable
   target-selection and cooldown-motion comparisons. Our inference: use bounded
   behavioral probes, not a new rollout controller based on an uncalibrated model.
2. Laroche et al. (ICML 2019), *Safe Policy Improvement with Baseline Bootstrapping*:
   https://proceedings.mlr.press/v97/laroche19a/laroche19a.pdf.
   The method retains baseline behavior where data are insufficient. Our inference:
   protect the working V17 path and demand evidence for narrowly scoped deviations.
   We lack logged official state/action coverage, so its performance guarantees
   cannot be claimed for this bot or our screening rule.
3. Wagenmaker et al. (NeurIPS 2024), *Overcoming the Sim-to-Real Gap*:
   https://arxiv.org/html/2410.20254v1. Simulator-assisted exploration and direct
   policy transfer are distinct. Our inference: local matches remain useful for
   hypotheses and failures, but cannot authorize champion promotion.
4. Churchill and Buro (2013), *Portfolio Greedy Search and Simulation for
   Large-Scale Combat in StarCraft*:
   https://davechurchill.ca/publications/pdf/combat13.pdf. Small portfolios can
   limit the action search space; this does not establish a Mech Royale score gain.

## Next probes, in priority order

- Diagnose baseline decisions on recorded observations: distinguish time spent
  acquiring a target, firing, reloading, seeking a weapon and completing loot.
  The supplied 300-observation recording has no meaningful upgraded laser duel
  coverage; do not mistake it for a strength benchmark.
- Compare narrowly bounded target commitment or kill-completion decisions while
  leaving V17's approach distance and movement intact. Confirm a real decision
  conflict first; strongest/weakest-target scripts in papers are hypotheses,
  not pre-approved upgrades. Do not repeat V15's partial-release bundle.
- Evaluate resource decisions only with visible danger and arrival feasibility.
  Preserve existing acquisition/harvesting instead of globally increasing loot
  radius, pulling early toward drops or changing RNG streams.
- Every proposed feature needs an exact source diff, affected-state examples,
  fresh comparisons with V17, interactions with existing actions, and a separately
  labeled official experiment. Only a higher official result can promote it.

No newly supported combat feature clears that standard in this refresh. The
concrete release is the restored champion plus corrected evaluation tooling,
not another speculative strategy bundle or a claimed 6.58 forecast.
