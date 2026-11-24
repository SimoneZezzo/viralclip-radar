# Project status and session handoff

Last updated 2026-11-24 (Europe/Rome). This file holds only the current state,
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
| 1. Reliable 24/7 service | **PARTIAL**. Both collectors and reliability timers are active and enabled at boot. Open: paired 48-hour journal check, reboot rehearsal and cold-start recovery. M1-01 PARTIAL under the off-VPS backup waiver; M1-02 cancelled. |
| 2. Features, baselines and labels | **PARTIAL**. 2A and 2B implemented. No game has enough admissible mature days for chronological scoring. |
| 3. Machine learning | Pending validated baselines and enough mature labels. |
| 4. Open-source demo | Pending synthetic offline demo, presentation and license. |

## Open gates

**M1 closeout PENDING.** The paired 48-hour journal check has been ready since
November 24 at 15:25:11 UTC and needs an authorized read-only SSH session. The
candidate reboot window is November 27 at 09:00 UTC, chosen to protect the
November 24–25 cohorts. It requires the journal result, a fresh preflight and
separate reboot authorization.
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
2. With authorization, run the read-only 48-hour journal check, then decide on
   the November 27 reboot rehearsal.
3. Audit each new UTC day with `--readiness`, record outages in UTC and keep
   the split boundaries predeclared before reading scores.
4. Implement the live ranking record approved on November 24 offline with a
   baseline and synthetic inputs.
   [Record draft](docs/PROJECT_MANUAL.md#7-contratto-del-ranking-dal-vivo)
5. Social track: YouTube Shorts only, observational (owner decision of
   November 24). Feasibility is a **conditional GO** pending a 3–4 week pilot
   decided mainly by matching precision and weekly volume. The design complies
   without an audit: Twitch features, and YouTube total views refreshed at least
   every 30 days as the label. The Google Cloud project and restricted key exist
   (owner report); live collection still needs authorization. Automated posting
   is deferred to future model validation.
   [Feasibility](docs/YOUTUBE_SHORTS_FEASIBILITY.md) ·
   [Social track](docs/ACTION_PLAN.md#3-due-binari-paralleli)

## Repository and workflow

Development continues on local `main`. The private GitHub repository was
deleted on November 24 after the initial import passed CI on Windows and
Ubuntu; future publication will use a reviewed release copy.
[Import evidence](docs/PROJECT_HISTORY.md#2026-11-24-private-github-import-and-verification)
On November 24, strict offline verification passed 7/7 checks and 238 tests on
Windows. Workflow phases P0–P2 are GO locally.
[P0–P2 evidence](docs/PROJECT_HISTORY.md#2026-11-19-p2-context-and-token-efficiency)

## Read as needed

- [Specification](docs/PROJECT_SPECIFICATION.md) for invariants, contracts and milestone acceptance criteria.
- [Project manual](docs/PROJECT_MANUAL.md) for architecture, data model, research pipeline and open decisions.
- [Milestone 1 operations runbook](docs/MILESTONE_1_ROLLOUT.md), [M1 reliability hardening](docs/M1_RELIABILITY_HARDENING.md) and [dual-collector operations](docs/DUAL_COLLECTOR_OPERATIONS.md) for operator procedures.
- [Point-in-time dataset](docs/POINT_IN_TIME_DATASET.md), [chronological evaluation](docs/CHRONOLOGICAL_EVALUATION.md) and [M2 cohort audit](docs/M2_COHORT_AUDIT.md) for research.
- [Offline verification](README.md#offline-verification) for local checks.
