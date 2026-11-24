# ViralClip Radar product and engineering specification

The original specification below preserves the product scope, technical contracts and milestone order. Sections 0, 10 and 11 record the initial workflow and bootstrap. Follow the current [repository instructions](../WORKFLOW.md) and [status](../PROJECT_STATUS.md) for session work.

> **Project:** ViralClip Radar
> **Status:** New open-source Python project (November 2026)
> **Primary goal:** Predict which Twitch clips will become unusually popular using only information available early in each clip's lifetime.
> **First case study:** Grand Theft Auto VI; support other Twitch games/categories without changing the architecture.
> **Most urgent priority:** START COLLECTING REAL TIME-SERIES DATA AS SOON AS A CORRECT MINIMAL COLLECTOR IS READY. Historical Twitch clip view-count curves cannot be reconstructed through the normal API.

## 0. Instructions to reviewer: how to work in this repository

- Read [PROJECT_STATUS.md](../PROJECT_STATUS.md) at the beginning of each session for current progress, verified results, blockers and next steps. Update its milestone checklists and dated evidence log after meaningful work; never mark live acceptance complete based only on mocked tests. This file remains the product and engineering specification.
- Treat this file as the product and engineering specification. Implement it **incrementally**, not as one giant unreviewed change.
- **On the first implementation request, build Milestone 0 (collector MVP) first.** Do not start with Streamlit, LightGBM, a web frontend, or an elaborate microservice system.
- The user works in VS Code on **Windows 11**. Everything needed for the first local run must work on Windows; add an optional Linux `systemd` deployment path for 24/7 use.
- Prefer readable, typed Python and simple dependencies. Use Python **3.11+**, `uv`, `httpx`, standard-library `sqlite3`, `pytest`, `ruff`, and an installable `pyproject.toml`.
- Tests must not depend on Twitch being reachable. Use mocked HTTP responses, deterministic timestamps and a synthetic demo dataset. Do not fabricate live collection success or ML performance.
- Keep API secrets out of git. Use `.env.example` (never commit `.env`, actual tokens, or real Twitch databases).
- Do not execute `git push`, provision paid infrastructure, or perform other external actions without the user's explicit request. Never assume the user's API credentials exist.
- Check existing files before overwriting them; prefer minimal, targeted changes.
- At the end of each phase: run tests/lint (if available), describe what changed, exact commands to run, and any blockers. Do not claim it has run continuously if it has not.
- Clarify a requirement only when essential and genuinely blocking; otherwise make a safe, documented implementation choice.

## 1. Product scope

This section defines the scope of M0–M4. The [long-term product vision](LONG_TERM_PRODUCT_VISION.md) describes proposals for later milestones.

### What it DOES
1. Discover publicly listed Twitch clips for configurable game categories through the official Helix API.
2. Record view-count observations and their **real observation timestamps** as append-only snapshots.
3. Revisit known clips at ~10, 30, 60, 360, and 1440 minutes after their creation.
4. Preserve discovery lag, API coverage metadata, missing observations and operational errors.
5. Create early-popularity features and rank clips through simple baselines before training ML.
6. Once enough prospective observations exist, train/evaluate models (e.g. logistic regression and LightGBM) with leakage-free temporal splits.
7. Offer a local, read-only web UI linking to the original Twitch clip and showing prediction vs subsequent outcome (React + TypeScript with a FastAPI backend, owner decision 2026-11-24; originally Streamlit).
8. Ship an open-source, understandable, easy-to-run repo with synthetic sample data and reproducible benchmark code.

### What it DOES NOT do
- Download, record, repost, edit, or upload other people's Twitch/YouTube videos.
- Publish videos to TikTok, Instagram, or YouTube; build a social-posting network; scrape web pages; bypass API restrictions.
- Promise a clip will go viral, or equate current popularity with future success.
- Redistribute real Twitch API data, derived data products, or trained weights without determining whether that publication is permitted under applicable terms.
- Require access agreements with streamers for *public clip metadata* obtained via an authorized API endpoint. Other uses may require additional rights.

## 2. Read and respect current official documentation

- Clips API: https://dev.twitch.tv/docs/api/reference/clips
- Twitch API concepts, pagination, time formats and rate limits: https://dev.twitch.tv/docs/api/guide/
- OAuth app access tokens: https://dev.twitch.tv/docs/authentication/getting-tokens-oauth/
- Developer Agreement: https://legal.twitch.com/en/legal/developer-agreement/

Important, verified implementation details (re-check before changing API behaviors):
- `GET /helix/clips`: specify **exactly one** of `game_id`, `broadcaster_id`, or `id`.
- For discovery by game: use `game_id`, `started_at`, `ended_at`, `first<=100`, and cursor pagination; results are ordered by **view count**, not by creation time.
- Search windows use RFC3339 UTC timestamps and Twitch truncates start/end times to the **minute**.
- Twitch returns roughly at most 1,000 paginated clips for one search. Window partitioning reduces but cannot eliminate selection bias. Track saturation/cap indicators and page counts.
- Re-fetch snapshots using repeated `id` query parameters, **up to 100 IDs per request**. Do NOT send both `id` and `game_id`.
- A clip's current `view_count` is NOT an historical observation. Only values you record prospectively with `observed_at` are actual snapshots.
- `GET /helix/streams` can provide live `viewer_count`; it is not an historical viewer-count database. Use only observed-at-the-time values.
- App access tokens are appropriate for the public endpoints above; request new tokens when expired/invalid.
- Respect `Ratelimit-Remaining`, `Ratelimit-Reset`, HTTP 429, and `Retry-After` where present. Never assume a fixed request budget.
- API fields can be unavailable or nullable. Treat opaque IDs as **strings**.

## 3. Milestone 0 — Collector MVP (IMPLEMENT THIS FIRST)

**Objective:** A small, robust program can run for hours/days and append trustworthy clip view-count snapshots. No model is required for this milestone.

### 3.1 Minimum runnable interface

Design a small CLI (Typer optional; `argparse` is fine):

```bash
uv sync
uv run viralclip init-db
uv run viralclip collect --game "Grand Theft Auto V" --once
uv run viralclip collect --game "Grand Theft Auto V" --loop
uv run viralclip status
uv run pytest
```

- `--once` makes a real API call only if credentials are configured; otherwise prints a useful setup error.
- `--loop` runs the discovery+snapshot scheduler continuously until interrupted; gracefully close DB on Ctrl+C.
- `status` displays local DB counts, latest successful collection, due/missed jobs, and last error, **without an API token**.
- Resolve a game name to its **actual Twitch category ID** using the official API; cache the mapping locally. Never hardcode or invent a GTA VI game ID. If GTA VI is not found, report it rather than substituting GTA V.
- Support a simple `.env` or environment configuration: `TWITCH_CLIENT_ID`, `TWITCH_CLIENT_SECRET`, `VIRALCLIP_DB_PATH`, `DISCOVERY_INTERVAL_SECONDS`, `DISCOVERY_LOOKBACK_MINUTES`, and configurable game names/IDs.

### 3.2 OAuth and API client

Implement a centralized client for `POST https://id.twitch.tv/oauth2/token`, `GET /helix/search/categories`, `GET /helix/clips`, and optionally `GET /helix/streams` later.

Requirements:
- Explicit timeouts, user-agent, sane bounded retries with backoff and jitter on 5xx/network failures.
- On 401, renew the token once and retry; do not loop infinitely.
- On 429, respect rate-limit headers/reset; prioritize due snapshots over optional discovery if budget is tight.
- Separate pure parsing from HTTP calls for unit tests.
- Never log tokens, client secrets or full auth headers.
- Use UTC-aware `datetime` values for all internal logic.

### 3.3 Discovery worker

- Poll each configured category at approximately 5-minute intervals.
- Query recent creation windows using a lookback (e.g. last 15–30 minutes) with **overlap** to catch delayed indexing. Track a durable cursor/watermark/checkpoint per category and window where appropriate; restarting must not destroy coverage state.
- Use stable whole-minute RFC3339 boundaries; page through results until the cursor ends or a documented safety cap is reached.
- Track: `category_id`, window start/end, `started_at`/`finished_at`, page_count, fetched_count, unique/new clip_count, pagination/saturation flags, errors.
- When a window is highly populated or approaches 1,000 results, subdivide into smaller minute-aligned windows where feasible, respecting a finite call budget. Mark windows that may be incomplete; **do not claim exhaustive discovery**.
- Upsert clip metadata using `clip_id` as the primary key, but preserve the original `first_seen_at` (never replace it on subsequent discovery).
- The first observed `view_count` MUST also be written as a snapshot, timestamped at actual fetch/ingestion time.
- Repeated overlapping queries may generate a new *real* snapshot if deliberately recorded; must never duplicate the exact same ingestion event or modify previous snapshots.
- If a collection fails, log it, retry later, and never silently mark the window as complete.

### 3.4 Snapshot worker

- Schedule targets at clip ages: **10 min, 30 min, 60 min, 6 hours, 24 hours**, relative to Twitch `created_at`.
- The jobs are persistent and idempotent, with statuses like `pending/running/completed/missed/failed` and a bounded retry count.
- BATCH due IDs in groups <=100 for `GET /helix/clips?id=...&id=...`.
- Write observed clip `view_count` as a **new** snapshot with `observed_at` and actual `age_seconds`. Preserve the job's `target_age_seconds` separately.
- If first discovered after a target age, do NOT backdate or fabricate that snapshot. Mark the corresponding job `missed` or `late` with the reason. If the job is only slightly late, still record the *actual* observation and let dataset rules determine eligibility.
- If Twitch omits a clip in an ID batch (deleted/unavailable), mark it unavailable for that job; **do not treat missing as zero views**.
- On process restart, recover overdue jobs carefully: take a real current observation if useful, but never label it as an on-time 10/30/60m observation.
- Distinguish `scheduled_at`, `fetched_at`, and `observed_at` as needed. Timestamps must reflect the actual measurements.

### 3.5 SQLite: minimum persistence contract

Create versioned, additive migrations (a lightweight SQL migration mechanism is fine). Prefer SQLite WAL, foreign keys, useful indexes, transactions, a single logical DB writer and UTC ISO-8601 timestamps.

Suggested tables (adjust names/columns when needed, but preserve semantics):

`games`
- `game_id TEXT PRIMARY KEY`, `name`, `last_resolved_at`.

`clips`
- `clip_id TEXT PRIMARY KEY`, `game_id`, `broadcaster_id`, `broadcaster_name`, `creator_id`, `title`, `url`, `created_at`, `first_seen_at`, `duration_seconds`, `language`, `status`, `last_seen_at`, metadata fields where helpful.

`clip_snapshots`
- `snapshot_id INTEGER PRIMARY KEY`, `clip_id`, `observed_at`, `age_seconds`, `view_count`, `source` (`discovery`/`scheduled`), `target_age_seconds NULL`, `collection_run_id NULL`. **Append-only measurements**.

`jobs`
- `job_id PRIMARY KEY`, `clip_id`, `job_type`, `target_age_seconds`, `due_at`, `status`, `attempts`, `last_error`, `completed_at`; unique constraint to prevent duplicate jobs per clip and target.

`collection_runs`
- `run_id PRIMARY KEY`, `game_id`, `window_start`, `window_end`, `started_at`, `finished_at`, `request_count`, `pages_seen`, `clips_seen`, `new_clips`, `status`, `potentially_truncated`, `error_summary`.

Later: `stream_snapshots`, `predictions`, `model_runs`, `evaluation_results`.

Store times in consistent UTC RFC3339 format, with safe conversion helpers. Avoid collecting extra personal information not needed for research.

### 3.6 Collector acceptance tests

Using mocked Twitch API responses and a frozen clock, show that:
1. Game ID lookup works and gracefully handles missing categories.
2. OAuth credentials are read from env, not embedded in source; token renewal works.
3. Two overlapping discovery calls create one clip row and preserve `first_seen_at`.
4. Snapshot rows are appended, not overwritten, when view count changes.
5. Jobs are generated at the correct ages; late discovery never creates fake historical values.
6. Batch requests include <=100 repeated `id` parameters and preserve ID-to-result mapping despite unordered responses.
7. API 429/5xx leads to safe delay/retry, not a tight loop.
8. An unavailable clip is treated as missing, not zero.
9. Restarting the scheduler recovers persisted work without duplicate scheduled jobs.
10. `status` runs without Twitch credentials.
11. All created file paths are portable across Windows and Linux.

**Milestone 0 is COMPLETE when:** with actual user-provided Twitch credentials, the documented commands run and SQLite receives unique clips plus multiple timestamped view-count observations; mocked tests are green. If credentials are unavailable, clearly state live collection is unverified and provide precise setup steps.

## 4. Milestone 1 — Reliable 24/7 service

- Add structured logging, useful status/health reporting (last successful discovery, snapshot lateness, missing ratio, rate-limit pressure, potential truncation).
- Include an example Linux `systemd` unit file and setup instructions; restart after failure, environment configuration, persistent DB location and a simple backup/restore procedure.
- Keep Windows local usage functional. Explain that sleep/reboots create unrecoverable gaps; do not disable system settings without user consent.
- Provide configurable game list, bounded API work and priorities: due snapshots first, then discovery, then optional enrichment.
- Avoid multiple independent collector processes writing the same database concurrently unless explicit locking/coordination is implemented.
- For backups use SQLite's supported online backup mechanisms or safe shutdown, not a blind copy of a live WAL DB.

## 5. Milestone 2 — Features, baselines, and labels

### Primary research question
> Can we identify top-performing Twitch clips at 24 hours using only observations available by the first hour?

### Two related tasks
1. **Absolute popularity:** rank clips by predicted 24-hour view count or predicted membership in the top 10% *within a pre-defined comparable cohort*.
2. **Relative breakout:** identify clips that outperform what is normal for their creator/creator size, defined from **past-only** behavior. Handle creators with insufficient history.

### Dataset rules
- Prediction cutoff = `created_at + 60 minutes`, with an explicit documented tolerance (e.g. observations at 55–65 min). All feature inputs MUST have `observed_at <= prediction cutoff` for a strict as-of experiment. If tolerance extends past the cutoff, explicitly label this a **65-minute prediction**, or choose only previous observations; never silently use future data.
- Prefer feature engineering using actual snapshot ages/deltas rather than pretending snapshots occur exactly on schedule.
- Eligibility: clip discovered soon enough, necessary early observations exist, 24-hour label observed within a specified outcome window, API coverage adequate. Report how many samples are excluded and why.
- Never reconstruct view-count history from today's clip count. Do not interpolate missing observations and call them ground truth.
- Cohorts: compare clips from the same game and time window; also stratify by known creator-size bands when possible. Define thresholds **using training-period information only**, or use time-specific cohort definitions without leaking future outcomes into prediction features.
- Be explicit about incomplete API discovery and potential label censoring.

### Feature candidates
- Views around 10/30/60 minutes; actual observation age; `first_seen_at-created_at` (discovery lag).
- Absolute growth and growth per actual elapsed minute; log-transformed counts; short-term acceleration when observations allow.
- Clip length, game, language where available.
- Past-only creator clip counts / historical median view counts / popularity baselines.
- `Get Streams` viewer count only if the system really observed it at or before the cutoff; record provenance and missingness. No backfilled viewer counts.

### Baselines BEFORE fancy ML
- Views at 60 minutes.
- Views per minute, using actual timestamps.
- Creator size / historical popularity only, where data exists.
- Simple normalized heuristic.
- Optionally logistic regression before LightGBM.

### Labels and metrics
- At first, 24-hour actual views or top-decile membership for a well-defined eligible cohort; do not treat deleted/unavailable clips as failures.
- Rank metrics `Precision@K`, `NDCG@K`, `Recall@K` with consistent candidate pools; regression metrics only if predicting counts.
- Train/validation/test separated chronologically. Group all observations from a clip in the same split; consider a label maturity embargo and future validation on entirely unseen creators.
- Compare models on identical candidate sets, report sample size, coverage, uncertainty and baseline results. No invented uplift or "95% accuracy" claims.
- Save the model version, feature cutoff, prediction timestamp and score as immutable records; never rewrite a past prediction after seeing the outcome.

## 6. Milestone 3 — Machine learning

- First implement clean, tested feature-extraction and evaluation code; then train scikit-learn logistic regression and LightGBM if sufficient observations exist.
- Use time-based validation, tuning only on training/validation; leave a genuine held-out later period for final evaluation.
- Add a creator holdout experiment as a separate test of generalization.
- Include feature importance and optionally SHAP later; check whether the model merely learned streamer size.
- Verify calibration before labeling raw scores as actual probabilities.
- If data is insufficient, expose a heuristic ranking and a status of `not_trained_yet` rather than fabricating a model.

## 7. Milestone 4 — Open-source demo / GitHub presentation

- Local web dashboard (React + TypeScript, FastAPI; originally Streamlit) with game selection, emerging clip ranking, direct **original Twitch links**, growth timeline, prediction cutoff, and later the observed 24-hour outcome.
- Demo must work offline with generated synthetic rows clearly labeled `SYNTHETIC / NOT REAL TWITCH DATA`.
- README in **English**: succinct question, demo/GIF when available, 60-second quickstart, technical architecture, model/evaluation methodology, limitations, data usage notes, and roadmap.
- Include `.env.example`, reasonable `.gitignore`, MIT code license, tests, GitHub Actions for lint/tests, and contributing guidance.
- Don't bundle a real collected Twitch DB, raw exports, derived rankings or real trained weights in the public repository without reviewing applicable Twitch terms. Use synthetic fixtures by default.
- No need for an hosted public dashboard, social autoposter, or paid service.

## 8. Suggested repository layout (grow into this incrementally)

```text
viralclip-radar/
├── WORKFLOW.md
├── pyproject.toml
├── .env.example
├── .gitignore
├── README.md
├── src/viralclip/
│   ├── cli.py
│   ├── config.py
│   ├── twitch/
│   │   ├── auth.py
│   │   ├── client.py
│   │   └── discovery.py
│   ├── collector/
│   │   ├── scheduler.py
│   │   └── snapshots.py
│   ├── storage/
│   │   ├── database.py
│   │   └── schema.sql
│   ├── features/
│   ├── models/
│   └── evaluation/
├── dashboard/app.py
├── examples/
├── tests/
├── deploy/viralclip-collector.service
└── docs/
```

Do not scaffold empty modules just to satisfy the future layout. Build functioning vertical slices.

## 9. The intended execution order

1. Obtain/create Twitch developer application credentials (user action required).
2. Implement a single real `Get Clips` discovery call and verify JSON parsing with mocks.
3. Initialize SQLite; save clips + first observed snapshots.
4. Implement persistent snapshot jobs and batched `id` refreshes.
5. Make one continuous collector loop reliable with restart and rate-limit handling.
6. Start collecting immediately, locally then on an always-on system if the user chooses.
7. Improve observability and assess actual coverage/lag.
8. Only then implement rankings, labels, ML, dashboard, and GitHub polish.

## 10. Initial reviewer task to perform when the user says "start"

**Implement Milestone 0 now** using the existing repository, or initialize a minimal Python package if it is empty. Generate runnable code, schema, config template, CLI, tests and a concise README. Focus on producing trustworthy time-stamped observations before UI or ML. Run the mocked test suite and report exact commands for the user to add Twitch credentials and start the collector. Do not start a VPS, spend money, or claim to have accessed Twitch without valid credentials.

## 11. Done means evidence, not intention

At the end of a phase, output:
- Implemented files and key design choices.
- Actual tests/commands executed and results.
- Known constraints or API uncertainty.
- One next concrete action to take.

Remember: **a simple working 24/7 collector creates data that cannot be recovered later. A polished but non-running repository does not.**
