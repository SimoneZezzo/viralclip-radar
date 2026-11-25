# Project status and session handoff

Last updated 2026-11-25 (Europe/Rome). This file holds only the current state,
open gates and next actions. Past results live in the
[evidence log](docs/PROJECT_HISTORY.md#evidence-log). How the system works is in
the [project manual](docs/PROJECT_MANUAL.md). Live production state beyond the
dated samples below is **UNKNOWN**.

## Product objectives in priority order

1. **Live ranking.** Generate and record clip rankings at the prediction cutoff.
2. **Absolute popularity.** Rank clips by predicted 24-hour views or top-decile
   membership within a comparable cohort.
3. **Relative breakout.** Identify clips that outperform their creator's usual
   results using only history available before prediction.

[Priority decision](docs/PROJECT_HISTORY.md#2026-11-24-product-objective-priorities) ·
[Creator workflows after M4](docs/LONG_TERM_PRODUCT_VISION.md)

## Milestones

| Milestone | Status and remaining gate |
| --- | --- |
| 0. Collector MVP | **GO**, 2026-11-18. |
| 1. Reliable 24/7 service | **PARTIAL**. Both collectors and reliability timers are active and enabled at boot. Paired 48-hour journal check PASS (November 24). Reboot rehearsal authorized for November 27 09:00 UTC. Open: reboot rehearsal and cold-start recovery. M1-01 PARTIAL under the off-VPS backup waiver; M1-02 cancelled. |
| 2. Features, baselines and labels | **PARTIAL**. 2A and 2B implemented. No game has enough admissible mature days for chronological scoring. |
| 3. Machine learning | Pending validated baselines and enough mature labels. How much to invest is decided at the end of M2. |
| 4. Portfolio demo | Version 1 scope (November 24): clip selection only, with the Twitch link handed to an external editor the user picks and pays for. Synthetic page and prediction registry implemented locally; the clip card offers the clip link, Copy clip link, Open on Twitch and external editor links, with no media handling. The demo is a React + TypeScript app (Vite, Tailwind CSS, TanStack Query) served by FastAPI; strict verification adds ESLint, TypeScript, Vitest, the Vite build and Playwright checks. The collector-backed ranking registry (`rank`, `link-outcomes`, `shortlist`) is implemented and tested on fixtures only; the demo now reads it over a labeled synthetic collector database. Real ranking data and the owner's trial (clip link in an external editor, manual publication) remain pending. |

## Open gates

**M1 closeout PENDING.** The paired 48-hour journal check passed on
November 24: 577 monitor samples per collector, no gap over six minutes and
no unexplained service events. The candidate reboot window is November 27 at
09:00 UTC, chosen to protect the November 24–25 cohorts. The owner authorized
the rehearsal on November 24; it still requires a fresh preflight, the
runbook steps and console recovery access.
[Journal check](docs/PROJECT_HISTORY.md#2026-11-24-m1-48-hour-journal-check-passed) ·
[Closeout sequence](docs/PROJECT_HISTORY.md#2026-11-24-m1-gate-and-m2-calendar-preparation) ·
[M1 closure gate](docs/M1_RELIABILITY_HARDENING.md#proposed-m1-closure-gate)

**M2 readiness PARTIAL.** At the common 09:39:48 UTC watermark on November 24,
November 22–24 yielded zero primary calendar candidates and zero feasible
split pairs for either game. The observed-at-cutoff replay of GTA VI
November 19–21 returned `INSUFFICIENT DATA` at all cutoffs because of declared
outages. The preliminary 60m calendar is:

| Split | Creation days (UTC) | Notes |
| --- | --- | --- |
| Train | November 24–25 | |
| Validation | November 28–29 | starts November 28 00:00 |
| Test | December 2–3 | complete December 5 00:05 |

Each day still needs audited admissibility and the 24h+5m embargo. Replace an
excluded day with the first later admissible date and move later boundaries
before reading metrics.
[Calendar and audit](docs/PROJECT_HISTORY.md#2026-11-24-m1-gate-and-m2-calendar-preparation) ·
[M2 audit](docs/M2_COHORT_AUDIT.md)

**GTA VI primary coverage BLOCKED.** The primary policy counts only verified
legacy search seconds, and GTA VI discovery now uses the structural ledger. No
independent, verifiable category-wide ID roster was found. GTA V days accepted
under policy v1 failed the v2 coverage replay after a legacy run labeled
completed missed two known clips.
[Coverage trace](docs/PROJECT_HISTORY.md#2026-11-23-m2-primary-coverage-trace-after-the-canary) ·
[Cohort definitions](docs/PROJECT_MANUAL.md#6-pipeline-di-ricerca)

**GTA V stays active** as a temporary research source until its approved
experiment and reproducibility gates are met.
[GTA V gates](docs/CHRONOLOGICAL_EVALUATION.md#research-readiness-and-gta-v-retirement)

## Latest production evidence

- **November 25, 08:44 UTC.** Read-only disk check: 29 GB of 38 GB
  available; GTA VI database 3.2 GB growing about 0.6 GB/day, total about
  0.63–0.66 GB/day, so the disk fills in early January 2027 without action.
  The formal capture to December 16 fits. Owner decision: upgrade to VPS-3
  only when the forecast requires it; check daily growth after each new
  category.
  [Disk check](docs/PROJECT_HISTORY.md#2026-11-25-feature-and-generalization-plan-approved)
- **November 24, 16:27 UTC.** A read-only `health` run over SSH reported
  both collectors HEALTHY. GTA V: discovery 41 s old, 0 overdue jobs, 0
  operational errors in the last hour. GTA VI: 63 overdue jobs (oldest
  12.1 s), 0 execution failures, 0 operational errors; coverage remains
  uncertified. Both services active and enabled with 0 restarts; both
  reliability timers scheduled; 29 GB free.
  [Health check](docs/PROJECT_HISTORY.md#2026-11-24-read-only-health-check-demo-on-the-registry-and-doc-trimming)
- **November 24, 15:46 UTC.** Both collectors and reliability timers were
  active and enabled with zero restarts, zero failed jobs and no 429s in the
  last hour. GTA VI stayed DEGRADED only for recorded incomplete scan attempts.
  Sealed copies at a 15:46:16 UTC watermark matched their receipts and passed
  integrity and foreign-key checks.
  [Journal check](docs/PROJECT_HISTORY.md#2026-11-24-m1-48-hour-journal-check-passed)
- **November 24, 09:39:48 UTC watermark.** Sealed GTA V and GTA VI copies
  matched their receipts and passed integrity and foreign-key checks. The
  GTA VI eight-page canary roster had 20/20 valid 60m features and 20/20 valid
  24h labels. [Canary labels](docs/PROJECT_HISTORY.md#2026-11-24-gta-vi-canary-labels-measured)
- **November 23, 12:26 UTC.** One by-ID retry batch recovered 0 of 3 omitted
  24h labels. Retry effectiveness is inconclusive and the pipeline is
  unchanged. [Retry probe](docs/PROJECT_HISTORY.md#2026-11-23-bounded-gta-vi-label-retry-probe)
- **November 23, 11:30 UTC.** Both collectors advanced with zero failed jobs
  and no 429s in the sampled hour. GTA VI has used eight overlap pages since
  08:59 UTC that day. Known omissions remained after the cursor ended in 28 of
  31 overlap runs. [Follow-up](docs/PROJECT_HISTORY.md#2026-11-23-discovery-and-label-follow-up)
- **GTA VI discovery** has been structural since release `4ab8d05f1ca1` on
  November 21. Exhaustive coverage is not guaranteed and recent coverage was
  DEGRADED. Boot enablement is configured; a real reboot is unverified.
  [Structural release](docs/PROJECT_HISTORY.md#2026-11-21-gta-vi-structural-discovery-release) ·
  [Boot enablement](docs/PROJECT_HISTORY.md#2026-11-21-gta-vi-persistent-boot-enablement)

## Next actions

The [action plan](docs/ACTION_PLAN.md) sets the order of work and the split
between agents. Open direction questions are argued by reviewer and reviewer in the
[direction review](docs/DIRECTION_REVIEW.md) before the owner decides. The end goal is a model that helps clippers choose clips whose
TikTok, Shorts and Reels posts get the most views; Twitch ranking is the
first signal and the candidate shortlist.

1. Benchmark protocol v1 is implemented offline for both cohorts. The first
   real 2/2/2 mechanism run awaits admissible cohorts; the formal 7/3/7
   benchmark and model adoption remain separate gates.
   [Protocol v1](docs/CHRONOLOGICAL_EVALUATION.md#benchmark-protocol-v1)
2. Feature and generalization plan approved on November 25
   ([ACTION_PLAN §5bis](docs/ACTION_PLAN.md#5bis-feature-nuove-e-giochi-mai-visti)):
   simplified the same day for a portfolio project (beat the baseline,
   several games at launch, a few hundred to about 1k users). Freeze
   challenger c1 by November 27; after the reboot rehearsal, one new non-GTA
   collector on the legacy path if authorized; public static deploy late
   December or early January. Metadata capture, Get Streams and chat are
   deferred; VPS-3 only when needed; Twitch authorization assumed until the
   legal reply. **c1 frozen on November 25** (`c1-v1`,
   [protocol](docs/CHRONOLOGICAL_EVALUATION.md#challenger-protocol-c1)):
   `viralclip evaluate --protocol c1-v1 --game-id ID`; benchmark-v1
   artifacts unchanged. Catalog games use a 2/2/7 calendar; for a game
   going live on November 28 the earliest c1 result is December 15 00:05 UTC.
   VPS-3 is offered in the OVH panel (owner, November 25); upgrade after
   December 16 when the disk forecast requires it. Offline tooling ready on
   synthetic data: c2 model comparison (`c2-metadata`, `c2-train`,
   `evaluate --protocol c2-v1`; ridge, XGBoost, LightGBM and a small
   scikit-learn neural network (MLP) on safe and
   exploratory features; owner: if the exploratory variant beats the
   baseline or c1 it becomes the definitive version) and the static deploy
   (`viralclip publish`, `VITE_STATIC_DATA=1` build, `web/README.md`).
   reviewer's re-review of the c2 fixes is pending (reviewer usage limit).
   Catalog collectors prepared offline (pending reviewer review, nothing
   installed): `viralclip-game@<ID>.service`, `game.env.example`, catalog
   preflight (`viralclip.deployment preflight DB --game-id ID`), reliability
   profile `vcg-<ID>`, `viralclip probe-volume` and the
   [catalog runbook](docs/CATALOG_COLLECTORS.md).
   Twitch applications (owner, November 25): GTA V and GTA VI credentials
   live in their `/etc/viralclip/*.env` files on the VPS and in the owner's
   password manager; one new application (catalog 1) is created and kept in
   the owner's password manager, not yet installed anywhere. Further
   applications are created one per additional game.
3. Run the authorized November 27 09:00 UTC reboot rehearsal after a fresh
   preflight, following the
   [reboot procedure](docs/M1_RELIABILITY_HARDENING.md#collector-correction-reboot-and-rollback).
4. Audit each new UTC day with `--readiness`, record outages in UTC and keep
   the split boundaries predeclared before reading scores.
5. The offline ranking register and fixture-based editor page are implemented.
   The local entry point is `viralclip demo`. The page distinguishes
   simulated model scores, baseline scores and missing scores. The UI is
   in English and shows a relative 1–100 score for each ranked clip.
   The collector-backed registry records `latest_views` baseline runs as
   `not_trained_yet` and links 24h outcomes without modifying predictions.
   Its first use on a sealed private copy is a separate step.
   `viralclip synthetic-dry-run` runs export, benchmark v1, registry and
   outcome linking end to end on synthetic data; it returned
   `MECHANISM ONLY` on the 2/2/2 calendar as expected.
   [Ranking contract](docs/PROJECT_MANUAL.md#7-contratto-del-ranking-dal-vivo)
6. Version 1: the owner tests a cleared clip's Twitch link in an external
   editor (external editor on the owner's account) and publishes manually. The
   integrated download and reviewer + external editor path is out of scope for now,
   as are automated posting, multiple platforms and level C before a
   validated Twitch result; the Discord bot is deferred and later steps are
   evaluated after M2. Until Twitch answers a written authorization request
   (sent by the owner to `legal@twitch.tv` on November 24; no reply yet), historical data, derivatives
   and models stay private and are never redistributed; without
   authorization, collected data is to be deleted before a public deploy.
   Training and public scoring on historical Twitch data remain subject to
   terms verification. The owner runs the Shorts trial after delivery. Creator
   recruitment for training remains deferred until after the demo.
   [Operating plan](docs/ACTION_PLAN.md#5-piano-operativo) ·
   [reviewer–reviewer exchange](docs/DEMO_REVIEW.md)

## Work in progress

Agents declare multi-file work here before starting and remove it when done,
per the [collaboration rules](docs/REVIEW_INTEGRATION.md#collaborazione-fra-reviewer-e-reviewer).

**Pending reviewer reviews (prepared by reviewer on 2026-11-25 while reviewer was at
its usage limit; the owner asked that reviewer find everything ready):**

1. Re-review of the c2 fixes and the MLP (`f710b21`, `d84de71`): verify the
   eight earlier findings are fixed (`src/viralclip/models.py`).
2. Review of the catalog collector preparation (`c5074d3`):
   `deploy/viralclip-game@.service`, `deploy/game.env.example`,
   `deployment.preflight --game-id`, `reliability.resolve_profile`,
   `probe.py`, [catalog runbook](docs/CATALOG_COLLECTORS.md). Required before
   the first catalog deployment after the November 27 rehearsal.
3. Design review of [live publishing](docs/LIVE_PUBLISHING.md) (top 200
   recorded, rolling 24-hour pool, 15-minute refresh, Cloudflare R2).
4. Owner-approved catalog order (November 25): Fortnite (`33214`) first,
   then VALORANT (`516575`), then League of Legends (`21779`), one at a
   time after the November 27 rehearsal, each with its own Twitch
   application ([volume probe](docs/PROJECT_HISTORY.md#2026-11-25-candidate-category-volume-probe)).

- None.

## Repository and workflow

Since November 24, reviewer and reviewer collaborate: both edit and commit on the
owner's request and review each other's changes in sensitive areas.
The direct reviewer-to-reviewer round trip passed the synthetic cutoff probe on
November 24 using the existing a subscription login and network access.
See the [review workflow](docs/REVIEW_INTEGRATION.md)
for the current sharing scope and synthetic acceptance probe.

The code is MIT-licensed (owner decision, November 24); Twitch data,
derivatives and models stay private. Development continues on local `main`; the
`docs/benchmark-protocol-and-plan` branch was fast-forwarded into it on
November 24. The private GitHub repository was
deleted on November 24 after the initial import passed CI on Windows and
Ubuntu; future publication will use a reviewed release copy.
[Import evidence](docs/PROJECT_HISTORY.md#2026-11-24-private-github-import-and-verification)
On November 24, strict offline verification passed 9/9 checks on Windows:
pytest, Ruff lint and format, Git, Bash, PowerShell, Web (ESLint, TypeScript,
Vitest, Vite build), Web e2e (Playwright) and packaging. Workflow phases P0–P2
are GO locally.
[P0–P2 evidence](docs/PROJECT_HISTORY.md#2026-11-19-p2-context-and-token-efficiency)

## Read as needed

- [Specification](docs/PROJECT_SPECIFICATION.md) for invariants, contracts and milestone acceptance criteria.
- [Project manual](docs/PROJECT_MANUAL.md) for architecture, data model, research pipeline and open decisions.
- [Milestone 1 operations runbook](docs/MILESTONE_1_ROLLOUT.md), [M1 reliability hardening](docs/M1_RELIABILITY_HARDENING.md) and [dual-collector operations](docs/DUAL_COLLECTOR_OPERATIONS.md) for operator procedures.
- [Point-in-time dataset](docs/POINT_IN_TIME_DATASET.md), [chronological evaluation](docs/CHRONOLOGICAL_EVALUATION.md) and [M2 cohort audit](docs/M2_COHORT_AUDIT.md) for research.
- [Offline verification](README.md#offline-verification) for local checks.
