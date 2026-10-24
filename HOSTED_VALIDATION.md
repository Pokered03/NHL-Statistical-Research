# NHL hosted validation — 2026-10-24

Live dashboard: https://nhl-statistical-research.streamlit.app/

Repository: https://github.com/Pokered03/NHL-Statistical-Research

Independent public publication and free deployment were authorized. No existing sports application, including Multi-Sport Value Engine, was changed.

## Software and data checks

- All 52 prepared files matched a fresh public Git clone byte for byte at de2f6f03be2f1c0b16ab4a1557e63869d74dadb3. Later terminology/team-ID corrections passed all 35 applicable isolated tests, six unrelated cases skipped; the updated public clone also passed 35 tests.
- SQLite integrity and local HTTP health/root checks passed. Four independently stored seasons (ending 2024–2027), all 32 current teams; current published final-game coverage 167 games/334 team boxes. Advanced metrics have their own smaller observed samples; complete shot reconciliation and model inputs are required before full-game xG/GSAx are published.
- Local 64-switch test: cold render 0.679s, switching p95 0.072s, process peak 143.75MiB. Cached advanced-data worker 13.52s and 206.76MiB. Database 5.70MiB. Local development targets passed; these do not certify hosted stability.

## Initial live verification

- Streamlit Community Cloud main/app.py deployment uses Python 3.12 and PyArrow 24.0.0. Independent SQLite, engine, caches and workflow.
- October 24 scheduled Anaheim–Philadelphia and Los Angeles–New Jersey comparisons rendered offense, defense, situational ranks and observed sample sizes. Last 3/5/10 switches worked.
- Manual Rangers (NYR)–Islanders (NYI) comparison, neutral venue and manual Team B spread −1.5 / total 6.5 controls worked. Team IDs now disambiguate city-only names from the source.
- Historical 2025 summaries rendered; stale retrospective confidence was suppressed. October 25 calendar selection loaded Florida–Chicago at United Center.
- A second browser session rendered independently while the original remained active; this is a basic two-session check, not a stress test.
- One controlled reboot recovered and loaded corrected goals/faceoff labels and team IDs. Ordinary restart recovery is verified; extended crash recovery is not.
- Hosted process peak sampled 170.2MiB; exposed cgroup limit 3072MiB; container samples 688.7–700.3MiB including other processes and file cache. Post-restart process peak 161.4MiB. This is an initial sample, not a sustained-load measurement.
- First hosted refresh succeeded in 33s: https://github.com/Pokered03/NHL-Statistical-Research/actions/runs/40120898566 . The live source panel displayed its 2026-10-24T18:29:26.471859+00:00 worker timestamp.

## Model results and limitations

Chronological held-out test 1,787 games: Brier 0.24478 vs 0.25 constant probability, calibration error 0.01020, margin MAE 2.17381 goals, total MAE 1.84933 goals. The simple total baseline is slightly better (1.83404); no claim of superior total accuracy. Early/later samples 167 / 1,620 use fewer than 10 vs 10+ prior fitted team games. The baseline scoring model does not use advanced tracking or confirmed goalie adjustments. Separation score is not certainty/model reliability. Spread/total categories remain PASS without verified historical market lines.

## Automatic updates

ENABLE_FREE_REFRESH=true. Daily 10:35 UTC (6:35 AM Eastern daylight time; 5:35 AM standard time), subject to GitHub schedule delays/inactivity policies. Advanced NHL event integration is enabled. Standard public ubuntu-latest runner, no paid APIs/Odds API keys, no Actions cache/artifact storage. This is a daily prepared-data refresh, not immediate live-game updating.

## Remaining work

Verified future starting goalies/current injuries, power-play opportunity and penalty-kill denominator coverage, first-half/period splits, calibrated availability/rest/player effects, actual iPhone/MacBook-specific testing, sustained multi-user load and long-term hosted stability remain incomplete. Missing statistics stay N/A. Source xG ≥0.20 chances are an explicitly defined count, not proprietary high-danger tracking. No logos are distributed. Preserve upstream attribution and rights notices.

Status: live development dashboard with initial independent hosted verification; full professional feature completion and all-six completion are not claimed. Reboot this deployment after imported engine code changes; routine data-only refresh uses database revision cache keys.
