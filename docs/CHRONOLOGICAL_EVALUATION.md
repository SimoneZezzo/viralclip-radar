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
at least two distinct rankable UTC days after embargo. This is a minimum
scoring floor. Two days alone provide weak evidence about generalization.
Without adequate coverage the harness reports `INSUFFICIENT DATA` and emits no
ranking metrics. Without boundaries it reports overall coverage and requests
boundaries only when the necessary pre-embargo day count is present.

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
