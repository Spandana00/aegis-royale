# Initial candidate validation

Historical report for v1 before publication. The Docker build and exact sandbox
check later passed in GitHub Actions. For the current candidate, see [V2.md](V2.md).

These are local correctness and timing checks. **No official practice run has
been submitted and no leaderboard score or rank has been measured.**

| Check | Observed result |
| --- | --- |
| Tactical regression suite | 14 tests passed |
| Official recorded-stream checker, host Python | 300/300 on time; zero wrong ticks, bad lines, or debug-cap violations |
| Same checker, pinned Python image filesystem | 300/300 on time; p50 1.3 ms, p99 10.3 ms, max 13.7 ms |
| 520-observation replay and synthetic combat stress probe, one core | Zero late decisions and zero invalid actions; about 29 MiB peak process memory |
| Sampled reachable ground routes in simplified movement probe | 12/12 reached |
| Public repository | Pending publication |
| Actual Docker build and Docker sandbox check | Pending; automated workflow included |
| Official 48-match practice score | Pending submission |

The pinned-image probe used the actual Python 3.13.7 amd64 root filesystem,
user 65534, no capabilities, read-only bot and map mounts, a 64 MiB temporary
filesystem, one CPU core, and a 512 MiB address-space limit. It ran through
Bubblewrap because a Docker engine is unavailable in this workspace. Network
namespace isolation was unavailable in that probe. It does **not** substitute
for the organizer's exact Docker/cgroup sandbox. Run the included GitHub
Actions workflow or the README Docker command before scoring.

The ground probe ignores acceleration, jumping, energy, combat, and game
server collision details. Its routes are diagnostics, not evidence of match
survival or a score. Combat stress observations are synthetic. The kit checker
uses recorded observations that do not react to the bot's actions.

The initial route test found that some apparently open grid points were on
separate rooftop or cliff regions. Ground-region connectivity and destination
selection were corrected, then the reachable-route probe was rerun.

## Next experiment

Publish this exact candidate, pass the Docker workflow, and submit its commit
for one official 48-match run. Record the score and rank. Use that evidence to
choose the first policy change; preserve the best earlier submitted commit.
