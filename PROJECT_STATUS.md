# Project status and session handoff

Last updated 2026-11-24 (Europe/Rome).

## Product objectives in priority order

1. **Live ranking.** Generate and record clip rankings at the prediction cutoff.
2. **Absolute popularity.** Rank clips by predicted 24-hour views or top-decile
   membership within a comparable cohort.
3. **Relative breakout.** Identify clips that outperform their creator's usual
   results using only history available before prediction.

[Priority decision](docs/PROJECT_HISTORY.md#2026-11-24-product-objective-priorities)

## Preparatory work before M3

- **Next benchmark.** Record outages in UTC, audit new days with `--readiness`,
  and predeclare validation and test boundaries before reading scores. Check
  whether an independent, verifiable ID reference is available for GTA VI
  primary discovery. [M2 audit](docs/M2_COHORT_AUDIT.md)
- **Live ranking contract.** Specify which predictions to record, including
  prediction time, cutoff and score version. Exercise the contract offline
  with a baseline and synthetic inputs. [Inference design](docs/project-manual/09-MACHINE-LEARNING.md#23-dalla-misura-alleventuale-inferenza)

## GitHub source repository

The reviewed source import targets `main` in the
[private development repository](https://github.com/SimoneZezzo/viralclip-radar).
The import removes the VPS
address from historical runbooks. Original local revisions referenced in
deployment evidence identify the artifacts used at the time.
[Import decision](docs/PROJECT_HISTORY.md#2026-11-24-private-github-import-preparation)

## Current priority

**GTA VI canary labels MEASURED, November 24.** At the 09:39:48 UTC
watermark, all 20 first discoveries from the eighth overlap page had both
valid 60m features and valid 24h labels. The sealed copies passed integrity
and foreign-key checks. Replaying the exact frozen roster reproduced the
counts. M2 scoring still requires eligible calendar days and primary coverage
evidence for the primary benchmark.
[Canary label evidence](docs/PROJECT_HISTORY.md#2026-11-24-gta-vi-canary-labels-measured)

**Bounded GTA VI label retry probe, November 23 at 12:26 UTC.**
One authenticated by-ID batch recovered 0 of 3 verified omissions
inside their original label windows. The probe consumed three HTTP
requests including authentication and kept the collector progressing.
Retry effectiveness remains inconclusive. The current pipeline and
M1/M2 gate criteria are unchanged.
[Probe evidence](docs/PROJECT_HISTORY.md#2026-11-23-bounded-gta-vi-label-retry-probe)

**Production follow-up, November 23 at 11:30 UTC.** Both collectors
advanced with zero failed jobs and no 429s in the sampled hour.
GTA VI remains at eight overlap pages. Since the handoff, page eight
added 59 previously unseen IDs within 60m. In 28 of 31 overlap runs,
known omissions remained after the cursor ended. All real export and
recommendation hashes reproduced. At that sample both the canary label
and 48h checks were pending.
[Follow-up evidence and gate commands](docs/PROJECT_HISTORY.md#2026-11-23-discovery-and-label-follow-up)

**GTA VI observed-at-cutoff validated on real exports.** Three private
2a.3 exports cover the mature November 19–21 cohorts. At 60m they contain
253,820 clips with valid features and 24h labels out of 258,244 known
by the cutoff. All four cutoffs return INSUFFICIENT DATA for scoring.
The three days have declared collection interruptions in their
creation or label horizons. Both SQLite snapshots passed integrity
and foreign-key checks. The discovery-attested primary remains the
default, with M1 and M2 PARTIAL and M3 pending.
[CLI and protocol](docs/M2_COHORT_AUDIT.md#benchmark-gta-vi-sulle-clip-note-al-cutoff)
[Real validation and pending gates](docs/PROJECT_HISTORY.md#2026-11-23-real-gta-vi-export-and-operational-validation)

**GTA VI eight-page canary PASS.** GTA VI has used eight overlap pages
since 08:59:09 UTC on November 23. Three matched-phase cycles added
36, 1 and 8 IDs within 60 minutes from page 8. Of these, 18, 1 and 1
were new to the DB. The production configuration remains at eight.
GTA V and the timers retained their service identities. The previous
runtime and seven-page configuration remain verified for rollback.
[Canary and first readiness check](docs/PROJECT_HISTORY.md#2026-11-23-gta-vi-eight-page-canary)

**M2 primary coverage and M1 closure remain PARTIAL.** A read-only trace
confirmed zero eligible GTA VI search seconds on November 22 and 23
before the maturity gate. A legacy GTA V run exposed false coverage:
two already-known clips were missing from a run labeled completed.
The local audit now checks the run-linked observations. The four GTA V
days accepted under v1 failed the v2 coverage-only replay. Their prior
hashed evidence remains historical. Both games are short of the primary
chronological split. The two 48-hour monitoring windows can first be
verified together on November 24 at 15:25 UTC, subject to continued
journal evidence. Separately authorized reboot rehearsal remains pending.
[Coverage trace and replay](docs/PROJECT_HISTORY.md#2026-11-23-m2-primary-coverage-trace-after-the-canary)
[Recovery replay](docs/GTA_VI_DISCOVERY_REPLAY.md) · [Isolated audit](docs/PROJECT_HISTORY.md#2026-11-23-gta-vi-recovery-replay-and-isolated-m2-validation)
[Resumed comparison](docs/PROJECT_HISTORY.md#2026-11-23-resumed-gta-vi-helix-comparison-and-readiness)

**GTA VI live collection remained operational during the resumed comparison.**
At 07:47 UTC on November 23 both collectors retained their process and
database identities, advanced discovery and recorded new scheduled
observations. GTA VI had no failed jobs and its oldest overdue job was
3.53 seconds old.
[Resumed comparison and follow-up](docs/PROJECT_HISTORY.md#2026-11-23-resumed-gta-vi-helix-comparison-and-readiness)

**November 22 live collection sample.**
From 23:42:36 to 23:48:38 UTC on November 22, GTA VI added 889 clips and
3,697 scheduled observations. Recent scan progress advanced by one cycle.
The oldest overdue job was below five seconds in both samples, with no
failed jobs or operational errors in the preceding hour. Discovery
coverage was **DEGRADED**: 17 of 24 recent attempts in the final rolling
hour were incomplete. At 00:11 UTC on November 23, an isolated SQLite
snapshot of GTA VI passed full integrity and foreign-key checks.
[Live verification](docs/PROJECT_HISTORY.md#2026-11-23-gta-vi-live-ab-verification)

**M1/M2 audit.** Recent discovery was limited by the overlap page budget
and known-ID omissions. The latest HTTP sample recorded zero 429s and
zero retries in that sample. Both monitor timers are active. Through
November 23 07:45 UTC, contiguous evidence was 16.50h for GTA V
and 16.33h for GTA VI.
In the paired November 21 UTC cohort,
97.53% of GTA V clips and 44.63% of GTA VI clips had both a 60m feature
and a valid 24h outcome. None of the four sampled GTA VI days meets the
primary discovery gate.
Four GTA V days were verified across two audits, below the minimum before
embargo. Local fixes are in `9ddfa81` and `37ed39c`. The runtime-hash
procedure is in `2f985c9`.
[Current audit and remaining gates](docs/PROJECT_HISTORY.md#2026-11-23-m1m2-discovery-and-data-quality-audit)

**Milestone 1 phase 0 is PASS within the observed local scope.** Both collectors
passed the operational checks in the operator's 2026-11-20 samples at
13:56:46 and 16:51:33 UTC.
Their distinct PIDs and database identities were stable across A/B. Both
passed SQLite integrity and category checks and advanced discovery and
scheduled refresh. GTA V was enabled at boot and GTA VI disabled. Current
production state beyond the sampled window is **UNKNOWN**.
[Operator samples](docs/PROJECT_HISTORY.md#2026-11-20-operator-phase-0-inventory-and-ab-samples)

The eight expected operations units and three operations paths were absent.
The targeted local scheduler inventory found no job attributable to either
database. Over authorized read-only SSH, the three observed cron configuration
files matched the checksums recorded by their installed packages. External
schedules remain **UNKNOWN**.
[Inventory follow-up](docs/PROJECT_HISTORY.md#2026-11-20-phase-0-alternate-automation-inventory)

**M1-02 cancelled. M1-01 remains PARTIAL.** The operator waived the unmet
original off-VPS requirement and accepted permanent loss of the experimental
dataset if the VPS and its copies are lost. Automated backups and off-VPS
storage are outside the current plan. Existing VPS copies are retained.
[Decision and evidence](docs/PROJECT_HISTORY.md#2026-11-21-research-first-strategy-and-read-only-audit)

**November 21 pre-release collection evidence.** At 13:34 UTC on 2026-11-21 both collectors
were active. GTA V had a recent discovery checkpoint. GTA VI still recorded views,
but its discovery checkpoint was stuck at 23:11 UTC on 2026-11-20, with 36
flagged runs in the preceding hour. The eight expected project operations
units were absent. The shared filesystem had 30.68 GiB free.
[Monitoring plan](docs/MILESTONE_1_ROLLOUT.md#current-collection-and-monitoring-plan)

**Current research priority.** M2A and M2B are implemented. Chronological
scoring awaits enough eligible days after embargo and matching export
provenance. M3 training remains pending. GTA V is a
temporary research source and stays active until its approved experiment
and reproducibility gates are met.
[Research and GTA V gates](docs/CHRONOLOGICAL_EVALUATION.md#research-readiness-and-gta-v-retirement)

**M2 cohort audit is implemented locally.** The read-only tool reports per-game
UTC-day eligibility, discovery evidence and chronological splits after embargo.
The isolated follow-up completed the larger November 20 cohort and the
remaining dates with no primary-admissible GTA VI days.
[Audit and authorization boundary](docs/M2_COHORT_AUDIT.md)

**M1 reliability timers are active and enabled.** The journal through
November 23 07:45 UTC contained 200 HEALTHY samples for GTA V and
198 DEGRADED samples for GTA VI. Both continuous samples fall short of
48 hours. The GTA VI frontier correction is local and the reboot
rehearsal remains open.
[Diagnosis and validation](docs/M1_RELIABILITY_HARDENING.md)

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

**GTA VI controlled activation, 2026-11-21 14:14 UTC.** Phase 2 passed
its immediate smoke test. GTA VI is running the reviewed discovery
patch and the prior runtime remains at `/opt/viralclip-gta-vi.next`.
GTA V retained its PID and runtime. The first smoke sample with new
observations found the GTA VI checkpoint at 23:18 UTC on November 20,
up from 23:11.
[Activation evidence](docs/PROJECT_HISTORY.md#2026-11-21-gta-vi-controlled-activation)

**GTA VI Phase 3 live acceptance is NO-GO.** From 15:47 to 16:01 UTC
on November 21, three consecutive cycles left the same November 20
23:19–23:20 UTC window partial. The checkpoint stayed at 23:19 and
lag increased by 13m58s. Jobs and observations continued and GTA V
stayed stable. The minute repeatedly returned mostly out-of-window
rows and hit the truncation guard. Coverage remains incomplete.
[Live acceptance evidence](docs/PROJECT_HISTORY.md#2026-11-21-gta-vi-live-acceptance)

**GTA VI Phase 3B identified the local truncation mechanism.** Each
historical blocked run had 104–117 in-window rows out of 982–991
total. Raw rows reached the 900-row guard before deduplication or
window membership checks. The live A/B/C diagnostic used zero HTTP
requests because no reusable bearer token was found in the inspected
configuration or environments. The upstream cause remains unverified.
[Phase 3B evidence](docs/PROJECT_HISTORY.md#2026-11-21-gta-vi-helix-diagnostic)

**GTA VI end-to-end recovery is NO-GO.** The subsequent authorized live
diagnostic reproduced out-of-window and repeated rows. An aligned query
exhausted its cursor but omitted at least 60 clips in the blocked
minute that Helix immediately returned by ID. Neither alignment,
deduplication, nor an exhausted cursor establishes coverage. The
checkpoint remains at November 20 23:19 UTC. No replacement runtime
was staged or deployed.
[Live Helix evidence](docs/PROJECT_HISTORY.md#2026-11-21-gta-vi-helix-coverage-blocker)

**GTA VI structural discovery is operational.** The November 21 release
`4ab8d05f1ca1` passed three live cycles. It discovered 2,862 new clips
in the recent lane and 171 in the historical lane. At 20:39 UTC the
recent scan watermark was 20:39:17 UTC and the historical scan watermark
was November 20 23:40 UTC. The legacy checkpoint remains 23:19 UTC and
its minute remains explicitly partial. Exhaustive coverage is
**not guaranteed**. GTA V was unchanged during the observed window.
[Release and live acceptance evidence](docs/PROJECT_HISTORY.md#2026-11-21-gta-vi-structural-discovery-release)

**GTA VI boot enablement is configured.** On November 21 at 20:45 UTC
the existing unit was enabled persistently under `multi-user.target`.
Both collectors kept their existing PIDs and recorded discovery and
observations after enablement. A real reboot and cold-start recovery
remain unverified.
[Boot enablement evidence](docs/PROJECT_HISTORY.md#2026-11-21-gta-vi-persistent-boot-enablement)

**Milestone 1 operational closure is PARTIAL.** Both collectors and both
reliability timers are enabled at boot. The uninterrupted 48-hour
monitoring window, cold-start recovery and GTA VI scan coverage remain
open. The accepted backup waiver remains in effect. A separately
approved M2 cohort audit is possible while scoring and training gates
remain open.
[M1 closure gate](docs/M1_RELIABILITY_HARDENING.md#proposed-m1-closure-gate)

## Product milestones

| Milestone | Status and remaining gate |
| --- | --- |
| 0. Collector MVP | **GO**, 2026-11-18. The post-resumption cohort had 1,323 clips with a first-hour observation and linked 24h outcome. |
| 1. Reliable 24/7 service | **PARTIAL**. Both collectors and recurring monitors are active and enabled. The 48-hour monitoring gate and reboot rehearsal remain open. M1-01 PARTIAL with waiver. M1-02 cancelled. |
| 2. Features, baselines and labels | **PARTIAL**. 2A and 2B implemented. The historical audit and November 22–23 readiness check fell short of scoring. Keep the 24h+5m embargo and report coverage and censoring. |
| 3. Machine learning | Pending validated features and enough mature labels. |
| 4. Open-source demo | Pending synthetic offline demo and presentation. |

## Workflow verification

**Git snapshot before the phase 0 evidence updates.** Branch
`chore/context-efficiency` at `3fe10358c6e785351132737e1d4bec2dcd1c071e`,
seven commits ahead of `master`
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
