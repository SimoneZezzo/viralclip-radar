# Project status and session handoff

Last updated: 2026-11-19 (Europe/Rome).

## Current priority

Resume **Milestone 1** at phase 0. In the operator's two 2026-11-19 samples,
about four minutes apart, GTA V and GTA VI advanced on OVH with distinct PIDs
and passed SQLite integrity and category checks. GTA V was enabled at boot
and GTA VI was reported disabled. The expected operations units and timers
were absent in those samples. Current production state is **UNKNOWN**.
[Operator samples](docs/PROJECT_HISTORY.md#2026-11-19-operator-production-evidence-and-milestone-1-release-review)

**Next task.** Obtain explicit authorization for phase 0 VPS access and run the
[read-only rollout inventory](docs/MILESTONE_1_ROLLOUT.md#0-linux-vps--read-only-inventory-and-baseline).
Inventory the expected and alternate backup and monitor schedules. Take two
timestamped UTC samples at least six minutes apart. For each collector,
record the health verdict, service PID, DB device/inode, category and integrity
checks, discovery watermarks and job progress. Record disk and RAM headroom.
Phase 0 is complete when both samples and the inventory are recorded, with
any failures or gaps identified. Hold the rollout on unexplained automation,
an unhealthy collector or missing evidence. Keep both collectors running.
Subsequent rollout phases and GTA VI boot changes require separate approval.

**Milestone 1 blockers.** The installed revision, live collector health and
database isolation, and any alternate automation are **UNKNOWN**. Both games
still need verified off-VPS recovery anchors, independently scoped backup
profiles and isolated restores. Timer-driven backups and monitor runs, alert
failure/recovery delivery and GTA VI reboot recovery remain unverified.
[Production acceptance gates](docs/MILESTONE_1_ROLLOUT.md#acceptance-and-risk)

## Product milestones

| Milestone | Status and remaining gate |
| --- | --- |
| 0. Collector MVP | **GO**, 2026-11-18. The post-resumption cohort had 1,323 clips with a first-hour observation and linked 24h outcome. |
| 1. Reliable 24/7 service | 1A and 1B complete. Dual-collector operations fixes are verified offline. Unattended production acceptance remains open. |
| 2. Features, baselines and labels | 2A and 2B implemented. Evaluate the four baselines after independent full UTC creation days mature. Keep the 24h+5m label-maturity embargo and report coverage and censoring. |
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
