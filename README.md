# NHL Statistical Research Dashboard

Status: **independently implemented and locally tested development build; not deployed; not complete.**

This repository is a single-sport, standalone Streamlit research application. It has no runtime dependency on another project, no imports from another dashboard, and no access to the existing Multi-Sport Value Engine. Every project has its own SQLite file, worker, model, caches, dependency specification and optional refresh workflow.

## Run locally

Python 3.12 is the tested runtime. From this repository directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m streamlit run app.py
```

The bundled `data/research.sqlite` is real research data, not a demonstration fixture. The application renders prepared summaries only and never fetches game or odds feeds during a page rerun.

## Use the dashboard

Choose a season and Eastern-time research date. Select a scheduled matchup, or choose Manual teams to compare any two registered teams. Team A is away and Team B is home unless Neutral venue is selected. Choose Last 3, Last 5 or Last 10; season, venue and available first-half splits remain visible alongside it. Swipe a wide statistical table horizontally on an iPhone. Sources, observed sample counts, ranking populations and update timestamps are exposed in the page.

Records and rankings are against covered opponents, not automatically an official league record. Historical seasons show descriptive season-end summaries, not reconstructed pregame pages. Upcoming rest is calendar days since the latest recorded final; it is not a predictive model input. No team logos are distributed pending verified usage rights.

## Refresh this sport only

Initial/full history build:

```bash
python -m research.pipeline --advanced
```

Routine active-season update:

```bash
python -m research.pipeline --seasons 2027 --advanced
```

The worker downloads cached, approved free sources, validates IDs and statuses, updates the indexed store, builds summaries and runs chronological validation outside Streamlit. It publishes one SQLite file atomically. Network failures retain the last good file; same-database overlapping refreshes are rejected by a process lock. The source cache uses ETags/Last-Modified and bounded file downloads. Historical source files are not downloaded on a routine active-season refresh.

No Odds API key is read, requested, or used. No paid data integration is enabled.

## Expanded data integrations and remaining limitations

Column-bounded published event data now supplies Corsi/Fenwick shares (all strengths, shootouts excluded), observed faceoff wins, source pre-shot xG, an explicitly defined xG ≥0.20 shot count and team aggregate pre-shot goalie GSAx. Block events belong to the blocker in the source and are attributed to the opposing shooter. Event histories must reconcile with both teams' on-target box counts; incomplete histories are excluded. Full-game xG/GSAx values require complete relevant model inputs. PP opportunities, verified future goalies and proprietary high-danger definitions remain unavailable.

Unverified injury/availability feeds, some requested advanced inputs, public redistribution permissions, account-backed deployment, active refresh schedules and actual host-limit/browser checks remain unfinished. The full specification has not been completed.

## Confidence panels

The baseline opponent-adjusted scoring model is fitted separately for this sport. Win probabilities are shown only after the empirical validation gate passes and the matchup has enough recent current-season data. A separation score is mathematically derived from calibrated probability; it is not a guarantee or a model-reliability percentage. Spread/total panels remain PASS unless both historical-line and confidence-category release gates pass. NFL historical-line tests have run and fail those gates; other sports lack integrated historical-line testing. Manual spread/total lines are supported; no betting picks are generated.

Read [METHODOLOGY.md](METHODOLOGY.md), [DATA_SOURCES.md](DATA_SOURCES.md) and [reports/backtest.json](reports/backtest.json). Backtest predictions can be regenerated; the large CSV audit output is excluded from routine Git commits.

## Independent verification

```bash
python -m pytest -q
python scripts/check_data.py
python scripts/benchmark.py
python scripts/smoke_server.py
```

Tests cover weighted aggregation, missing data, rank direction, duplicate/corrected results, postponed games, future-data leakage, invalid identities, read-only SQL, source-host restrictions, HTML escaping, app reruns, failed-source preservation and refresh locking. Tests for unrelated sport adapters are explicitly skipped.

The local target is cold AppTest render under 10 seconds, matchup switching under 2 seconds, and peak web-process RSS under 350 MiB. Worker target is under 650 MiB. These are development targets, **not verified hosting limits**. Reports record actual measurements, environment and whether a hosted resource limit was tested. AppTest is functional UI verification, not a real MacBook/iPhone browser rendering test.

## GitHub and deployment preparation

Create a new repository named `NHL-Statistical-Research` in the user’s GitHub account and push only this project. The current connected tools could not create new repositories; the browser required sign-in. No changes were made to the existing Multi-Sport Value Engine.

A locally authenticated GitHub CLI can publish this prepared repository after its source/license/privacy choices are settled:

```bash
gh repo create Pokered03/NHL-Statistical-Research --private --source . --remote origin --push
```

Use Streamlit Community Cloud with branch `main`, entry file `app.py`, and Python 3.12. The root `requirements.txt` and `.streamlit/config.toml` are included. The supplied Dockerfile is an alternative for an existing approved hosting account. Neither platform has been provisioned for this project. Do not pay for hosting without explicit approval.

Verify the free account’s app count, privacy rules, sleeping behavior, actual memory allocation and execution quota before deployment. After deployment, test scheduled selection, manual comparisons, historical seasons, missing-data cases, mobile layout, repeated switching, concurrent sessions, restarts and actual hosting memory. Record the resulting independent URL; do not invent one.

## Automatic schedule: prepared, OFF until free quota verified

`.github/workflows/refresh.yml` is independent for this repository. Its scheduled and manual jobs are guarded by `ENABLE_FREE_REFRESH == 'true'`; no jobs will run until that repository variable is explicitly enabled. This prevents unapproved private-repository Actions charges. Confirm included minutes and a spending cap before enabling. The prepared cron is listed in that file in UTC. It is daily, not a real-time end-of-game service. More frequent updates need a verified free scheduler/quota and source freshness checks.

The workflow commits the small prepared database and validation summary; Streamlit can redeploy from that commit. For long-term heavy use, monitor Git history growth and migrate the database to an independently managed approved object store. That storage integration is not configured.

Do not mark this application complete until repository publication, automated refresh, real browser checks and actual hosted resource-limit testing have all passed.
