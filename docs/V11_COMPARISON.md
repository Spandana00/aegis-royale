# V11: finish arming during a fight

## Scored reference

V10 scored **5.33**, receipt `BB-DC5BDF45`, in the user's submission screenshot.
It improved on V9's 4.77 by 0.56. That was a complete policy replacement; the
gain cannot be attributed to any one navigation or combat feature. V10 is
preserved at `d75253a91ccb4d199d4374c076ee0d58c383e590`.

At 48 matches, 5.33 corresponds to 256 placement points. At least 5.50 needs
eight additional points; 6.00 needs 32. Neither is a promised V11 result.

## The specific failure

A reproducible V10 decision has full health, a gun-only loadout, one attacker
80 m away and a laser 20 m in the opposite direction. It returns `engage`,
with no movement goal for the laser. An otherwise favorable fight can repeatedly
override its equipment destination. The new regression verifies that V11
returns a weapon destination and keeps the gun firing in this situation.

The [newer upstream log](https://github.com/JuanQuenga/buildathon-mech-royale/blob/b50b794522c134d9eb54cc2e9bc4782f4f4a3da9/docs/REVIEW.md)
also identifies delayed arming and a pending arm-first experiment. Its reported
laser-peeking draws average about the same as the base, target commitment ties
the base, and isolation has only one reported draw. Those are author reports,
not independently verified scores. V11 does not import the whole newer policy
or treat its expected scores as measured outcomes.

## Implemented change

During an otherwise favorable gun-only fight, V11 can retain a useful weapon
destination within 150 m. Health must exceed 35%, at most one active attacker
may be within 60 m, and a killable target gets finishing priority. The existing
zone emergency still runs first, and existing retreat decisions are preserved.

Weapons use the existing equipment values and travel-time estimate. A current
destination gets 40% preference to limit switching, while a sufficiently better
candidate can replace it. The commitment expires after 20 s; that pickup is
then blacklisted for 60 s. Gone items, newly acquired equipment, blacklists,
height and future-zone checks remain active. Long detours that end substantially
closer to a nearby attacker are rejected. Inventory also sorts overlapping
pickups by usefulness before selecting one.

V11 keeps firing its existing gun while collecting. It does not change firing
solutions, strafing, terrain routing, upgrades, healing thresholds or the
independent process deadline guard.

The proxy runs additionally exposed a zero denominator in fight assessment
when a live observation reports HP 0. V11 floors effective HP at 1 for that
denominator. A regression checks the zero boundary and verifies that the
normal-health ratio still matches V10. We do not know whether this boundary
caused any official-run failures.

## Verification and limits

The raw matched diagnostic results and trial distinctions are recorded in
[v11_match_comparison.json](v11_match_comparison.json). They use reconstructed
house bots and public, locally chosen seeds, not the private official scorer.
They test arming consistency and reveal errors; their point averages do not
predict the next official score.

The final candidate acquires a secondary in 38/40 matched cases versus V10's
35/40. Its combined proxy mean is 4.475 versus 4.375. The moderate model's
paired difference is slightly negative and the faster-escalation model's is
positive; neither establishes an official gain. No module errors or late
replies occur in these final runs. Earlier trial results remain separate.

An added straight-line proximity filter was rejected: it can misrepresent
routes that bend around buildings, and its trial hurt one proxy setting.
V11 retains V10's actual route planner and threat steering instead. That rejected
trial is recorded separately so its measurements are not presented as the
shipping candidate's results.

Behavior tests cover collecting while firing, destination persistence, timeout,
gone items, zone priority, low health, multiple attackers, kill finishing,
inventory ordering, acquiring the weapon and zero-health arithmetic. The
provenance tests protect the other brain functions and all other runtime modules.
Hashes and exact modifications are in [reference_manifest.json](reference_manifest.json).

Timing and protocol checks are in [v11_validation.json](v11_validation.json).
GitHub Actions additionally builds the actual image and runs the organizer's
checker under the competition sandbox limits. These checks do not establish
placement. Keep the 5.33 entry selected until an official V11 score improves it.
