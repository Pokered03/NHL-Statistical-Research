# Sources, permissions and coverage

Primary integrated source: [fastRhockey / SportsDataverse](https://github.com/sportsdataverse/fastRhockey-nhl-data).

MIT repository license; original NHL data/trademark rights retained.

Only the independent NHL adapter runs. The worker uses an explicit host allowlist. No paid feeds, Odds API keys, proprietary logos, or direct ESPN scraping are used. The repository's MIT license does not grant rights in league trademarks or third-party content; preserve the upstream notice.

## Snapshot coverage at build time

```json
[
  {
    "season": 2024,
    "teams_with_completed_games": 32,
    "registered_teams": 32,
    "schedule_games": 1400,
    "latest_final": "2024-06-24"
  },
  {
    "season": 2025,
    "teams_with_completed_games": 32,
    "registered_teams": 32,
    "schedule_games": 1398,
    "latest_final": "2025-06-17"
  },
  {
    "season": 2026,
    "teams_with_completed_games": 32,
    "registered_teams": 32,
    "schedule_games": 1394,
    "latest_final": "2026-06-14"
  },
  {
    "season": 2027,
    "teams_with_completed_games": 32,
    "registered_teams": 32,
    "schedule_games": 1344,
    "latest_final": "2026-10-23"
  }
]
```

These counts describe source observations, not independently certified official membership completeness. See the live coverage table for later updates.

## Expanded integrations and remaining gaps

Column-bounded published event data now supplies Corsi/Fenwick shares (all strengths, shootouts excluded), observed faceoff wins, source pre-shot xG, an explicitly defined xG ≥0.20 shot count and team aggregate pre-shot goalie GSAx. Block events belong to the blocker in the source and are attributed to the opposing shooter. Event histories must reconcile with both teams' on-target box counts; incomplete histories are excluded. Full-game xG/GSAx values require complete relevant model inputs. PP opportunities, verified future goalies and proprietary high-danger definitions remain unavailable.

No verified current injuries or future goalie confirmations are supplied. The daily free refresh runs at 10:35 UTC (6:35 AM Eastern daylight time, 5:35 AM standard time); GitHub scheduled starts can be delayed.
