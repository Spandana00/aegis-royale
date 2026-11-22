# AEGIS Royale — V20 official experiment

Champion: **V17, 6.27, BB-961EADA2**, commit
`e45e734215354fc4f938af15c984a666f446a426`. Keep it selected until a higher official score.

V20 adds one bounded decision change on V17: briefly defer resource goals
when an already charged laser is aligned with a fresh, visible, low-HP enemy
that the firing policy also selects. The window lasts at most **0.6 seconds**
and never renews for the same target. It does not change firing/release logic.

The deferral requires target HP at most half the weapon's listed damage,
full charge, line of sight, weapon range and alignment. This conservative
estimate is not a guaranteed kill: misses, enemy armor and later state changes
remain possible. A stale target, unready shot or different firing target rejects
it. Urgent zone movement, retreat, healing, multiple recent attackers, and an
active supply-drop capture retain priority. Gun-only behavior is unchanged.

V17's 55 m approach, 200 m laser preference, full upgrade order, equipment
preferences, aim mechanics and randomization are retained. V18's failed 70 m
setting remains reverted. No model-based score forecast is made; V20 is an
**unscored official probe**, not a promoted champion.

Five focused Rust scenarios verify actual cube-goal deferral, timer expiry,
shot readiness, freshness, target agreement, aim, capture, retreat and zone
priority. Native and container checks additionally exercise the full map,
recorded protocol and synthetic stress observations.

[Manifest](docs/v20_manifest.json) · [Validation](docs/v20_validation.json) ·
[Source audit](docs/v20_source_audit.json) · [Previous diagnosis](docs/V19_DIAGNOSIS.md)

Submit the exact V20 commit after its GitHub checks pass. Do not change the
selected champion merely because compilation and conformance pass.
