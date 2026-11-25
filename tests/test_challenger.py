from __future__ import annotations

from datetime import UTC, datetime

import pytest

from viralclip.benchmark import KS
from viralclip.challenger import add_c1, c1_row_score, c1_score, compare_with_strongest
from viralclip.evaluation import BASELINES, Candidate, rank_candidates

CREATED = datetime(2026, 11, 1, tzinfo=UTC)


def test_c1_projects_latest_views_to_the_cutoff():
    assert c1_score(None, None, None) is None
    assert c1_score(40, None, 600) == 40
    assert c1_score(40, 6.0, 600) == pytest.approx(100)
    assert c1_score(40, -6.0, 600) == 0
    row = {"latest_views": 40, "growth_views_per_minute": 6.0, "staleness_seconds": 600.0}
    assert c1_row_score(row) == pytest.approx(100)
    assert c1_row_score({"latest_views": None}) is None


def candidate(clip_id, views, rate, age):
    scores = (None,) * len(BASELINES)
    if views is not None:
        scores = (views, None, rate, views)
    return Candidate(clip_id, "42", CREATED, 60, "eligible", "1", scores, age)


def test_c1_reorders_stale_fast_clips_and_keeps_baseline_orders():
    pool = [
        candidate("fresh", 90, 1.0, 3540.0),  # 90 + 1 * 1 min = 91
        candidate("stale", 60, 3.0, 2400.0),  # 60 + 3 * 20 min = 120
        candidate("single", 95, None, 3000.0),  # one observation keeps latest views
        candidate("missing", None, None, None),
    ]
    frozen = {(CREATED, 60): {name: rank_candidates(pool, i) for i, name in enumerate(BASELINES)}}
    orders = add_c1(frozen)[(CREATED, 60)]
    assert list(orders) == [*BASELINES, "c1"]
    assert [row.clip_id for row in orders["c1"]] == ["stale", "single", "fresh", "missing"]
    assert [row.clip_id for row in orders["latest_views"]] == [
        row.clip_id for row in frozen[(CREATED, 60)]["latest_views"]
    ]
    assert orders["c1"][0].scores[-1] == pytest.approx(120)
    assert orders["c1"][-1].scores[-1] is None


def test_secondary_comparison_uses_the_validation_winner_on_test_days():
    def methods(**overlaps):
        values = dict.fromkeys(BASELINES, 0.5) | overlaps
        return {name: {"overlap": value} for name, value in values.items()}

    validation = {name: {"macro_mean": 0.4} for name in BASELINES}
    validation["growth_rate"]["macro_mean"] = 0.6  # validation winner
    report = {
        "by_cutoff_minutes": {
            60: {
                "metrics": {
                    "validation": {
                        "views_24h": {k: {"overlap": {"methods": validation}} for k in KS}
                    }
                },
                "days": [
                    {"split": "validation", "metrics": {}},
                    *(
                        {
                            "split": "test",
                            "metrics": {
                                "views_24h": {
                                    k: {"methods": methods(growth_rate=g, c1=c)} for k in KS
                                }
                            },
                        }
                        for g, c in ((0.5, 0.7), (0.4, 0.5), (0.9, 0.6))
                    ),
                    {"split": "test"},  # excluded day without metrics
                ],
            },
            30: {"metrics": {}, "days": []},
        }
    }
    compare_with_strongest(report)
    result = report["by_cutoff_minutes"][60]["c1_vs_strongest_validation_baseline"][50]
    assert result["baseline"] == "growth_rate"
    assert result["days"] == 3
    assert result["paired_difference"] == pytest.approx((0.2 + 0.1 - 0.3) / 3)
    low, high = result["paired_ci95"]
    assert -0.3 - 1e-9 <= low < 0 < high <= 0.2 + 1e-9
    assert "c1_vs_strongest_validation_baseline" not in report["by_cutoff_minutes"][30]
