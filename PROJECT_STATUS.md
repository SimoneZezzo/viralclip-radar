# Project status and session handoff

Last updated 2026-11-21 (Europe/Rome).

## Current priority

**GTA VI observed-at-cutoff benchmark available offline.** The opt-in
mode freezes recommendations before reading 24h labels and gates each
cutoff independently. A synthetic rehearsal reached the 2/2/2 scoring
floor at 60m and 65m. Real GTA VI 2a.3 exports were unavailable locally.
The discovery-attested primary remains the default, with M1 and M2
PARTIAL and M3 pending.
[CLI and protocol](docs/M2_COHORT_AUDIT.md#benchmark-gta-vi-sulle-clip-note-al-cutoff)

**M1-02 cancelled. M1-01 remains PARTIAL.** The operator waived the unmet
original off-VPS requirement and accepted permanent loss of the experimental
dataset if the VPS and its copies are lost. Automated backups and off-VPS
storage are outside the current plan. Existing VPS copies are retained.

**GTA VI discovery recovery candidate.** The offline Helix replay reproduced
the stalled checkpoint and partial-run pattern. The local candidate commits
completed UTC windows in order and carries the first unresolved interval
into the next cycle within the existing request budget. Live recovery is
**UNKNOWN**. The local release is identified by the commit subject
`fix(collector): prevent GTA VI discovery checkpoint starvation`. The
strict offline suite passes with 175 tests. Deployment awaits separate
approval and a fresh preflight. Keep GTA V running through its required
training, validation and testing. Return to M2 and M3 after discovery
stabilizes. Collector availability, disk monitoring and GTA VI boot
recovery remain open.
[Candidate and rollout gates](docs/GTA_VI_PILOT.md#offline-discovery-recovery-candidate)

## Product milestones

| Milestone | Status and remaining gate |
| --- | --- |
| 0. Collector MVP | **GO**, 2026-11-18. The post-resumption cohort had 1,323 clips with a first-hour observation and linked 24h outcome. |
| 1. Reliable 24/7 service | 1A and 1B complete. Availability, lightweight monitoring and GTA VI recovery remain open. M1-01 PARTIAL. M1-02 cancelled. |
| 2. Features, baselines and labels | 2A and 2B implemented. The current mature-day cohort falls short of scoring. Keep the 24h+5m label-maturity embargo and report coverage and censoring. |
| 3. Machine learning | Pending validated features and enough mature labels. |
| 4. Open-source demo | Pending synthetic offline demo and presentation. |

## Workflow verification

**Git snapshot before this status refresh.** `chore/context-efficiency` at
`c01480c6d401d84ae0cb4d169c333e409231395f`, six commits ahead of `master`
(`8fefbf957c3c81712d6c0cbdb26b4118fd3bd75f`) and none behind. No remote was
configured. The working tree and index were clean before this refresh.
Recheck Git state at the start of the next session.

- **P0 GO locally.** Git exclusions, Linux line endings and release checks
  verified. [P0 evidence](docs/PROJECT_HISTORY.md#2026-11-19-p0-git-baseline-hardening)
- **P1 GO locally.** Windows clean-checkout verification passed with 159 tests
  and 7/7 offline checks. Packaging matched the selected Git blobs.
  GitHub Actions and Ubuntu execution are **UNKNOWN**.
  [P1 evidence](docs/PROJECT_HISTORY.md#2026-11-19-p1-offline-verification-and-reproducible-packaging)
- **P2 GO locally.** The shorter handoff preserves the original specification
  and history. Windows strict verification again passed with 159 tests and
  7/7 checks. The token pilot was inconclusive for successful tasks and for
  choosing High versus Medium. No production gate was closed.
  [P2 evidence](docs/PROJECT_HISTORY.md#2026-11-19-p2-context-and-token-efficiency)

## Read as needed

- [Product and engineering specification](docs/PROJECT_SPECIFICATION.md) for invariants, contracts and original milestone acceptance criteria.
- [Milestone 0 audit](docs/MILESTONE_0_AUDIT.md) and [final acceptance](docs/PROJECT_HISTORY.md#2026-11-18-final-milestone-0-acceptance-go) for collector evidence.
- [Milestone 1 rollout](docs/MILESTONE_1_ROLLOUT.md), [backup and monitoring](docs/BACKUP_AND_MONITORING.md) and [historical production health audit](docs/PRODUCTION_HEALTH_AUDIT.md) for operator procedures and limits.
- [Point-in-time dataset](docs/POINT_IN_TIME_DATASET.md) and [chronological evaluation](docs/CHRONOLOGICAL_EVALUATION.md) for research.
- [Offline verification](README.md#offline-verification) for local checks and [dated project history](docs/PROJECT_HISTORY.md#evidence-log) for past results and handoffs.
