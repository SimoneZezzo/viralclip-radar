# GTA VI discovery recovery replay

Run the nine offline comparisons from the repository root:

```powershell
uv run --offline --no-sync python -B scripts/replay_gta_vi_discovery.py
uv run --offline --no-sync python -B scripts/replay_gta_vi_discovery.py --density 60 --request-ms 700
```

The reference is the full list of 3,600 synthetic clip IDs known to the
fixture generator. The data contains 120 clips per minute for 30 minutes.
Index availability is delayed by 0, 2, 12, or 38 minutes by construction.
The transport sorts by synthetic views, returns 100 results per page,
and terminates at 1,000. In the persistent-omission scenario it never
emits 180 reference IDs. In the rounded-bounds scenario it serves the
ten-minute envelope for a five-minute request. That scenario reflects
the direction of a dated counterexample, without assuming the behavior
is universal. The replay uses the collector and real SQLite writes in
temporary files with no network. It follows 24 five-minute cycles.
Refresh, auth, and retry time are outside the simulated 250ms per page.

A keeps current 10, overlap 7, and history/retry 3 page slots. B allows
three additional overlap slots and retains the current and historical
allocations. C divides the active and preceding ten-minute ranges into
five-minute windows, newest half first, with the same total slots as A.
All use half-open UTC targets, stable ID deduplication, and independent
historical search. Discovery times are first persisted observation times.

| Fixture | Policy | Unique of 3,600 | Within 10 / 30 / 35 / 60 / 65m | P50 / P95 latency s | Mean / peak pages per cycle | Peak estimated HTTP s |
| --- | --- | ---: | --- | --- | --- | ---: |
| Minute bounds | A | 2,370 | 2,100 / 2,259 / 2,259 / 2,370 / 2,370 | 225 / 921.5 | 5.04 / 12 | 3.00 |
| Minute bounds | B | 2,970 | 2,700 / 2,859 / 2,859 / 2,970 / 2,970 | 206 / 881.5 | 5.67 / 15 | 3.75 |
| Minute bounds | C | 2,739 | 2,502 / 2,628 / 2,628 / 2,739 / 2,739 | 195 / 898.75 | 6.29 / 13 | 3.25 |
| Rounded bounds | A | 2,370 | 2,100 / 2,259 / 2,259 / 2,370 / 2,370 | 225 / 921.5 | 5.04 / 12 | 3.00 |
| Rounded bounds | B | 2,970 | 2,700 / 2,859 / 2,859 / 2,970 / 2,970 | 206 / 881.5 | 5.67 / 15 | 3.75 |
| Rounded bounds | C | 1,461 | 1,224 / 1,350 / 1,350 / 1,461 / 1,461 | 203 / 3,232.5 | 5.54 / 10 | 2.50 |
| Persistent omissions | A | 2,376 | 2,100 / 2,259 / 2,259 / 2,376 / 2,376 | 217.5 / 929.5 | 5.04 / 12 | 3.00 |
| Persistent omissions | B | 2,796 | 2,520 / 2,679 / 2,679 / 2,796 / 2,796 | 205.75 / 901.5 | 5.54 / 14 | 3.50 |
| Persistent omissions | C | 2,649 | 2,397 / 2,532 / 2,532 / 2,649 / 2,649 | 197.75 / 910.5 | 6.17 / 12 | 3.00 |

B recovers 420–600 more reference IDs by 60m. It still misses 630–804
reference IDs. C produces 12 pagination anomalies when narrow bounds
are rounded and loses 909 references by 60m against A. Search overlap
leads to intentional repeat observations. The report includes repeat
counts across runs, wire duplicates, scan outcomes, and
legacy checkpoint continuity. The reference is simulated. Production
capture rate and unseen Twitch IDs remain unknown.

At 60 clips per minute and 700ms per page, B and A find the same IDs
at every cutoff in all three conditions. C adds requests in the
minute-bounds case and loses 600 recoveries by 60m when narrow bounds
are rounded. Every case preserves the legacy checkpoint.

## Local candidate and decision

`VIRALCLIP_GTA_VI_OVERLAP_PAGES` defaults to seven and accepts seven
through ten. `VIRALCLIP_GTA_VI_EXTRA_PAGE_SECONDS` defaults to 15 and
accepts one through 30. The added time allowance starts at the end of
the seventh logical page. Due refresh work retains priority. Extra
pages use cached validated auth, one HTTP attempt per page, and HTTPX
phase timeouts bounded by the remaining allowance. The next extra page
cannot start once the allowance elapses. HTTPX phase timeouts are not
an end-to-end cancellation timer for a response already in flight.
An extra-page 429 records a cooldown and fails the run. Rate-budget
deferral and an elapsed allowance leave a partial run. The current and
historical budgets, history policy, category, and database schema are
unchanged. Ten raw full pages remain partial at a cursorless end even
when no omission of a previously known ID is detected.

**GO for a separately approved non-writing Helix comparison.** Start
with at most three predeclared overlap windows. Reuse each seven-page
prefix for the paired comparison and add at most three pages on the
same cursor. A standalone probe can add up to 30 logical calls in all,
including the prefixes, of which at most nine are pages 8–10. Reserve
auth and transport headroom separately. Stop on 429, unexpected
category, invalid pagination, or the existing low remaining-budget
threshold. Report newly returned IDs as aggregates and use actual
observation times. A retrospective response cannot reconstruct an
earlier view count or establish prospective first-hour recall.

**NO-GO for changing the live collector before the paired evidence.**
Require incremental in-window first-hour capture, corroboration on
more than one sampled window, and progress without category or query
violations. Any later authorized GTA VI canary must preserve the three
history slots, stable DB identity and one writer, the current queue age
gate, and GTA V continuity. Compare several cycles and then compare
mature same-cutoff populations. Stop or use the authorized rollback if
there are new rate limits, persistent queue delays, mismatched database
identity, frontier regression, or loss of scheduled observations.
The default is seven overlap pages. For a runtime rollback use the
reviewed previous GTA VI runtime and existing isolation procedure.
[Controlled release and rollback](GTA_VI_PILOT.md#coverage-gate-after-the-live-helix-diagnostic)
