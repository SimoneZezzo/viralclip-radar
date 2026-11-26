# Project status

Last updated 2026-11-26 (Europe/Rome). How the system works is in the
[project manual](docs/PROJECT_MANUAL.md) and the
[specification](docs/PROJECT_SPECIFICATION.md).

## Final state: closed, data deleted

ViralClip Radar is closed as an operational service and kept as a code-only
portfolio project. The public GitHub repository carries this history since
2026-11-26.

On November 26, 2026 Twitch replied to a written request for research use
that it is unable to allow the use of its user data for research purposes.
The owner stopped collection and deleted all collected data the same day.
Collection ran from November 17 to November 26, 2026.

| Area | State |
| --- | --- |
| Production collectors | Both services and both reliability timers stopped and disabled on the VPS (19:22 UTC); production markers removed; no process running. |
| Collected data | Every VPS database, copy, recovery anchor, staging file and HTTP log deleted (19:22:45 UTC). All local databases, exports, evaluation outputs and audits deleted (local `data/` removed entirely). |
| Credentials | Twitch credential files removed from the VPS (`/etc/viralclip`, shredded) and blanked in the local `.env`. The three Twitch applications were revoked by the owner on 2026-11-26. |
| System journal | Kept: it holds only aggregate operational lines (service state, queue and error counts, timestamps), with no clip IDs, titles, channel names or URLs. journald cannot delete one unit's entries without other services' logs; they expire under normal retention. |
| VPS | Still provisioned with code under `/opt`, unit files and service accounts; no data. Deleting it needs owner authorization. |
| Real-data research | Not allowed. No training, evaluation or calibration on Twitch data was or will be performed. |

## Milestones (final)

| Milestone | Final status |
| --- | --- |
| 0. Collector MVP | **GO**, 2026-11-18. |
| 1. Reliable 24/7 service | **Closed, partial.** Paired 48-hour journal check passed on 2026-11-24. Reboot rehearsal and cold-start recovery never run (cancelled). |
| 2. Features, baselines and labels | **Closed.** Point-in-time dataset, cohort audit, benchmark protocol and baselines implemented and tested on synthetic data. No real-data scoring. |
| 3. Machine learning | **Closed.** Challenger c1 frozen and c2 comparison (ridge, XGBoost, LightGBM, MLP) implemented and tested on synthetic data only. No real-data results. |
| 4. Portfolio demo | **Done on synthetic data.** FastAPI and React dashboard, ranking registry and static publishing; runs without Twitch credentials. |

Cancelled: the November 27 reboot rehearsal, the December scoring calendar,
the Fortnite and other catalog collectors, the text metadata ledger
deployment, live publishing and any public scoring.

## Next actions (owner)

1. Decide whether to delete the VPS.

## Verification

Run `uv run --offline --no-sync python -B scripts/verify_offline.py --strict`.
It uses synthetic fixtures and mocked HTTP only; see the
[README](README.md#quick-start).
