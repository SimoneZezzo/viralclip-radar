# Project status and session handoff

Last updated: 2026-11-19 (Europe/Rome).

## Current priority

Resume **Milestone 1** once the local workflow work is complete. The latest
recorded operator samples showed GTA V and GTA VI advancing on OVH with distinct
PIDs and successful SQLite integrity and category checks. GTA V was enabled at
boot and GTA VI was reported disabled. The installed revision and current VPS,
backup, monitoring and recovery state are **UNKNOWN**.
[Operator samples](docs/PROJECT_HISTORY.md#2026-11-19-operator-production-evidence-and-milestone-1-release-review)

The next production step, with explicit authorization, is the
[read-only rollout inventory](docs/MILESTONE_1_ROLLOUT.md#0-linux-vps--read-only-inventory-and-baseline).
Preserve both active collectors. The operations-only rollout remains conditional
on verified off-VPS recovery anchors for both games, independent backup profiles
and isolated restores, monitoring and alert evidence, and a separate decision
and verification for GTA VI reboot recovery.

## Product milestones

| Milestone | Status and remaining gate |
| --- | --- |
| 0. Collector MVP | **GO**, 2026-11-18. The post-resumption cohort had 1,323 clips with a first-hour observation and linked 24h outcome. |
| 1. Reliable 24/7 service | 1A and 1B complete. Dual-collector operations fixes are verified offline. Unattended production acceptance remains open. |
| 2. Features, baselines and labels | 2A and 2B implemented. Evaluate the four baselines after independent full UTC creation days mature. Keep the 24h+5m label-maturity embargo and report coverage and censoring. |
| 3. Machine learning | Pending validated features and enough mature labels. |
| 4. Open-source demo | Pending synthetic offline demo and presentation. |

## Workflow verification

P0 and P1 passed locally. The P1 reference is
`1c8c16d3d26660f35b6a54be7584ab7762b58307` with 159 tests and 7/7 offline checks
on Windows. GitHub Actions and Ubuntu execution are **UNKNOWN**. P2 is a local
context change and does not close a product or production gate.

## Read as needed

- [Product and engineering specification](docs/PROJECT_SPECIFICATION.md) for invariants, contracts and original milestone acceptance criteria.
- [Milestone 0 audit](docs/MILESTONE_0_AUDIT.md) and [final acceptance](docs/PROJECT_HISTORY.md#2026-11-18-final-milestone-0-acceptance-go) for collector evidence.
- [Milestone 1 rollout](docs/MILESTONE_1_ROLLOUT.md), [backup and monitoring](docs/BACKUP_AND_MONITORING.md) and [historical production health audit](docs/PRODUCTION_HEALTH_AUDIT.md) for operator procedures and limits.
- [Point-in-time dataset](docs/POINT_IN_TIME_DATASET.md) and [chronological evaluation](docs/CHRONOLOGICAL_EVALUATION.md) for research.
- [Offline verification](README.md#offline-verification) for local checks and [dated project history](docs/PROJECT_HISTORY.md#evidence-log) for past results and handoffs.
