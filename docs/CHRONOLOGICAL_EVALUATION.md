# Chronological ranking evaluation

`viralclip evaluate` reads version 2A CSV and JSON artifacts. It verifies the
artifact SHA-256 hashes and the feature and outcome time bounds. It requires
no SQLite connection, Twitch connection or credentials. It writes only to a
new Git-ignored directory.

```powershell
uv run viralclip evaluate data/datasets/m2a-exploratory data/datasets/m2b-input-exploratory data/datasets/m2b-input-blackout data/datasets/m2b-input-post-restart --k 10 --output data/evaluations/m2b-nov18-replay
```

The three `m2b-input-*` directories were extracted using the same creation bounds,
watermarks and blackout declaration as the historical replays in the
[dataset guide](POINT_IN_TIME_DATASET.md). The overlapping legacy exploratory
input exercises deduplication. Replays contribute one candidate per clip and
cutoff and one outcome per clip. A newer watermark can fill an immature
prediction or label. Conflicting stable features or valid labels are rejected.

`evaluation.json` records coverage, embargoed labels, matched and cutoff-specific
populations, missing scores, declared-outage exposure, broadcaster concentration,
deduplication counts and any metrics. `manifest.json` records evaluator settings,
input hashes, metric definitions and sample counts. A version 2a.2 dataset
has the audit grouping tokens needed to compute broadcaster concentration on
new periods and matched cohorts. Legacy rows without tokens are counted as
unknown. Tokens are pseudonyms for local analysis and provide no anonymity
guarantee. They are excluded from baseline inputs.

## When scoring is permitted

Supply both `--validation-start YYYY-MM-DDT00:00:00Z` and
`--test-start YYYY-MM-DDT00:00:00Z` to predeclare increasing UTC boundaries.
Creation time assigns every cutoff for a clip to the same period. Train
labels must have fully matured by validation start, and validation labels
must have fully matured by test start. Test labels must have fully matured by
their source watermarks. Maturity is creation plus 24 hours and five minutes,
even if the scheduled label was measured earlier.

A scored game/day pool requires the extraction windows to cover the entire
UTC creation day with elapsed outcome windows by the relevant boundary.
This is coverage of the extracted cohort and gives no guarantee of complete
Twitch discovery. A pool also needs at least 10 matched labeled clips with
at least two distinct outcomes. Each of train, validation and test must have
at least two distinct rankable UTC days per game after embargo. Declared
outages exclude a game/day when they overlap its creation day or full
label-maturity horizon. Game scope comes from the source manifest or the
games present in an unfiltered export. This is a minimum
scoring floor. Two days alone provide weak evidence about generalization.
Without adequate coverage the harness reports `INSUFFICIENT DATA` and emits no
ranking metrics. Without boundaries it reports overall coverage and requests
boundaries only when the necessary pre-embargo day count is present.

The evaluator checks observation IDs, timestamp bounds, and the derivation
of observed growth and growth rate from the stored endpoints. Primary
scoring requires export 2a.3 discovery evidence for the game's UTC day
in the hashed `coverage.json`. The exporter reads that evidence with the
same SQLite snapshot and watermark as the actual rows. Only rows sourced
from an attested export can join a primary pool. The evaluator still
reports diagnostic coverage from older exports. Hold split boundaries
and the eligible game/day roster fixed before a primary benchmark.
[M2 cohort audit](M2_COHORT_AUDIT.md).

For ready periods, validation and test are scored separately. There are no
training-set scores. Results use the same rankable game/day pools across
cutoffs. The cutoff-specific population uses all eligible labeled clips for
that cutoff within those pools. The matched population uses the intersection
of clip IDs eligible and labeled at all four cutoffs. Coverage includes rows
from unscored days so exclusions remain visible.

## Baselines and metrics

| Baseline | Score |
| --- | --- |
| Latest views | Latest eligible observed views |
| Observed growth | Latest minus first eligible views |
| Growth rate | Observed growth per actual elapsed minute |
| Age-normalized views | Latest views divided by the actual age in minutes, with a one-minute denominator floor |

Higher scores rank first. Put missing scores last and break score ties by
ascending clip ID. Keep those clips in the pool for every method. Use actual
24-hour outcomes as the relevance reference. Clips at or above the view count
at rank `ceil(0.10 × pool size)` are relevant, including all boundary ties.
This defines evaluation ground truth per pool and fits no popularity threshold.

The default is `K=10`, capped at the pool size. Precision@K divides relevant
hits by the number of predictions inspected. Recall@K divides those hits by
the total number of relevant clips. NDCG@K uses `log1p(24h views)` gains and
`log2(rank + 1)` discounts with one-based ranks, normalized by the ideal
ordering. Reports include per-game/day values and an unweighted macro average.
No model is trained and no metric is computed for the audited one-day replay.

## Research readiness and GTA V retirement

The 2026-11-21 read-only audit counted valid labels on four UTC dates for
GTA V and two for GTA VI. With whole maturity windows and continuous
successful search-window coverage, GTA V had two rankable dates and GTA VI
had zero. Search-window coverage records queries and cannot measure clips
the API never returned. Treat the launch day, the stalled GTA VI period
and any outage as explicit coverage strata. The independent scoring and
training gates remain open.
[Dated audit](PROJECT_HISTORY.md#2026-11-21-research-first-strategy-and-read-only-audit).

For the first reproducible experiment, predeclare a strict 60-minute
primary cutoff and keep 30/35/65 minutes as distinct analyses. Target at
least 7 train, 3 validation and 7 independent test UTC days per evaluated
game, with at least 500 matched test labels across those days. These are
proposed experiment targets. The documented 2/2/2-day minimum remains the
software scoring floor. Use the 24h+5m embargo and skip the two UTC cohort
days before each next split boundary for a simple whole-day design. Report
both matched and cutoff-specific coverage, censoring, staleness and
broadcaster concentration. Keep features within the manifest allowlist.
Score the four fixed baselines first. A subsequent first model can use
regularized logistic regression to rank clips by probability of a
per-game/day top-decile outcome. Fit preprocessing on train and confine
tuning to validation. Open the
test metrics only after those choices are frozen. Report per-day results
and paired gain with uncertainty against the strongest validation baseline.

GTA V is a temporary source for training, validation and test comparisons.
Before proposing shutdown, finish its planned evaluations and compare a
GTA VI-only model with the same protocol trained on both games, scored on
the identical held-out GTA VI days. For the proposed first comparison, use
+0.01 NDCG@10 as a material gain. Require the upper bound of a paired 95%
interval clustered by test day to be at most +0.01 before concluding that
pooled training adds no material improvement. Verify that excluding fresh
GTA V data preserves the planned comparisons and that a rerun works from
the remaining private artifacts, code revision and recorded hashes. If GTA V still adds a
material gain, a needed comparison is open or that result is inconclusive,
continue collection. A separately approved pause must preserve the DB, WAL
handling, configuration and normal single-writer restart path. Database
deletion requires a separate decision.
