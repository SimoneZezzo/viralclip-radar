# ViralClip Radar

ViralClip Radar prospectively collects public Twitch clip metadata and actual
view-count observations. The first milestone is a small local collector; it
does not download or republish videos, make popularity promises, or reconstruct
historical view counts. Dashboard and machine-learning work are intentionally
out of scope until real time-series data has been collected.

## Quick start (Windows PowerShell)

Install [uv](https://docs.astral.sh/uv/), then from the repository directory:

```powershell
uv sync
Copy-Item .env.example .env
# Edit .env and set TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET.
uv run viralclip init-db
uv run viralclip collect --game "Grand Theft Auto V" --once
uv run viralclip status
uv run pytest
```

Create a Twitch application in the [Twitch Developer Console](https://dev.twitch.tv/console/apps).
Put its Client ID and Client Secret in `.env`; do not commit that file. The
collector uses an OAuth app access token and the official Helix API. No
credentials are needed for `init-db` or `status`.

The collector resolves a game name to its actual Twitch category ID. If Twitch
does not return an exact category match, collection stops with an error; it
never substitutes another GTA category. You can instead provide category IDs
using `VIRALCLIP_GAME_IDS` or repeated `--game-id ID` options.

## Continuous collection

Set `VIRALCLIP_GAMES` and optionally `VIRALCLIP_GAME_IDS` in `.env`, then run:

```powershell
uv run viralclip collect --loop
```

Leave that terminal and computer running; Ctrl+C stops cleanly. The default
discovery interval is 300 seconds with a 30-minute overlapping lookback. Tune
`DISCOVERY_INTERVAL_SECONDS` and `DISCOVERY_LOOKBACK_MINUTES` as needed. A
sleeping, shut down, or disconnected computer creates collection gaps that
cannot be recovered from historical Twitch clip view counts.
Run only one collector process against a given database at a time.

The SQLite database defaults to `data/viralclip.sqlite3`; override it with
`VIRALCLIP_DB_PATH` or the global `--db` option. SQLite uses WAL, foreign keys,
versioned migrations, append-only snapshots, and persistent per-clip jobs.

## What the observations mean

Discovery records the clip's current view count with its actual fetch time.
The collector schedules prospective observations at 10 minutes, 30 minutes,
60 minutes, 6 hours, and 24 hours after clip creation. If a clip is first
discovered after a target age, that target is marked missed; no historical
value is fabricated. A clip absent from a refresh response is recorded as
unavailable, never as zero views. Overlapping discovery can capture multiple
real observations, while duplicate observations from the same ingestion
timestamp are ignored. Twitch discovery is popularity-ordered and limited, so
the database records windows that may be truncated and does not claim
exhaustive coverage.

The API and application access remain subject to Twitch rate limits and terms.
This project stores operational clip metadata locally; review applicable Twitch
terms before redistributing collected data or derived datasets.

## Milestone and project progress

- [x] **Milestone 0 — Collector MVP:** CLI, Twitch OAuth/Helix client, SQLite
  migrations, discovery, persistent snapshot jobs, retry/rate-limit handling,
  and mocked tests are implemented. The 15-test suite and Ruff checks pass.
- [ ] **Milestone 0 — Live collection verification:** pending Twitch credentials.
  No live Twitch request or continuous collection has been run yet.
- [ ] **Milestone 1 — 24/7 operations:** not started.
- [ ] **Milestone 2 — Features and baselines:** not started.
- [ ] **Milestone 3 — Machine learning:** not started.
- [ ] **Milestone 4 — Demo and presentation:** not started.

**Next step:** configure `TWITCH_CLIENT_ID` and `TWITCH_CLIENT_SECRET` in `.env`,
run `uv run viralclip collect --game "Grand Theft Auto V" --once`, inspect
`uv run viralclip status`, and then start `uv run viralclip collect --loop`.
Live behavior and data collection remain unverified until this is done with
user-provided credentials.