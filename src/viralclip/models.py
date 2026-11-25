"""Model comparison c2: learned rankers on cutoff features, frozen before a fresh test.

Training reads only labeled rows whose 24-hour outcome matured before the validation and
test boundaries. The fitted models are sealed with a hash, then `evaluate --protocol c2-v1`
scores every candidate of a later export through the benchmark-v1 machinery.

The `exploratory` feature set adds clip duration, language and a broadcaster prior read
from the current collector row. Rediscovery can overwrite those fields, so their value at
the cutoff is assumed, not proven (owner decision, 2026-11-25); reports name the variant.
ML libraries are imported lazily because collector installs do not ship them.
"""

from __future__ import annotations

import csv
import json
import pickle
import sqlite3
import subprocess
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import datetime, timedelta
from hashlib import sha256
from math import copysign, log1p, nan
from pathlib import Path
from statistics import mean

from viralclip.benchmark import KS, Frozen, run_benchmark
from viralclip.challenger import METHOD as C1
from viralclip.challenger import add_c1, c1_score, paired_test_difference
from viralclip.dataset import ignored_output, write_json
from viralclip.evaluation import (
    DAY,
    MATURITY,
    MIN_POOL,
    rank_candidates,
    read_candidate_exports,
    read_export_outcomes,
)
from viralclip.storage.database import parse_utc

VERSION = "c2-v1"
METHOD = "c2"
CUTOFF = 60
SEED = 20261125
ACTIVITY_WINDOW = timedelta(hours=1)
PRIOR_WEIGHT = 5.0
SAFE = (
    "log1p_latest_views",
    "log1p_first_views",
    "log1p_c1",
    "signed_log_growth_rate",
    "latest_observation_age_seconds",
    "staleness_seconds",
    "observation_count",
    "discovery_delay_seconds",
    "hour_utc",
    "weekday_utc",
    "log1p_category_activity",
)
EXPLORATORY = (*SAFE, "duration_seconds", "is_english", "broadcaster_prior", "broadcaster_clips")
FEATURE_SETS = {"safe": SAFE, "exploratory": EXPLORATORY}
MODELS = ("ridge", "xgboost", "lightgbm")


def export_metadata(database: Path, output: Path) -> int:
    """Copy duration, language and a pseudonymous broadcaster token from a sealed copy."""
    output = output.resolve()
    ignored = subprocess.run(
        ["git", "check-ignore", "--quiet", "--", output.as_posix()],
        check=False,
        capture_output=True,
    )
    if output.exists() or ignored.returncode != 0:
        raise ValueError("Metadata output must be a new file in a Git-ignored directory")
    connection = sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only = ON")
        rows = connection.execute(
            "SELECT clip_id, broadcaster_id, duration_seconds, language FROM clips"
        ).fetchall()
    finally:
        connection.close()
    with output.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(("clip_id", "broadcaster", "duration_seconds", "language"))
        for clip_id, broadcaster, duration, language in rows:
            token = sha256(broadcaster.encode()).hexdigest()[:16] if broadcaster else ""
            writer.writerow((clip_id, token, "" if duration is None else duration, language or ""))
    return len(rows)


def read_metadata(path: Path | None) -> dict[str, dict]:
    if path is None:
        return {}
    with path.open(encoding="utf-8", newline="") as stream:
        return {row["clip_id"]: row for row in csv.DictReader(stream)}


def _number(value: str | None) -> float | None:
    return float(value) if value not in (None, "") else None


def load_rows(directories: list[Path]) -> dict[tuple[str, int], dict]:
    """Candidate feature rows by (clip, cutoff); outcomes are never read here."""
    rows: dict[tuple[str, int], dict] = {}
    for directory in directories:
        with (directory / "candidates.csv").open(encoding="utf-8", newline="") as stream:
            for raw in csv.DictReader(stream):
                if raw["feature_status"] not in ("eligible", "missing_observations"):
                    continue
                key = (raw["clip_id"], int(raw["cutoff_minutes"]))
                if key in rows:
                    continue
                created = parse_utc(raw["created_at"])
                delay = _number(raw["discovery_delay_seconds"])
                rows[key] = {
                    "clip_id": raw["clip_id"],
                    "game_id": raw["game_id"],
                    "cutoff": key[1],
                    "eligible": raw["feature_status"] == "eligible",
                    "created": created,
                    "day": created.replace(hour=0, minute=0, second=0, microsecond=0),
                    "prediction": parse_utc(raw["prediction_at"]),
                    "first_seen": created + timedelta(seconds=delay) if delay is not None else None,
                    "views_24h": None,
                    **{
                        name: _number(raw[name])
                        for name in (
                            "latest_views",
                            "first_views",
                            "growth_views_per_minute",
                            "latest_observation_age_seconds",
                            "staleness_seconds",
                            "observation_count",
                            "discovery_delay_seconds",
                        )
                    },
                }
    add_activity(rows.values())
    return rows


def add_activity(rows) -> None:
    """Other clips of the same game discovered in the hour up to each prediction time."""
    rows = list(rows)
    first: dict[str, tuple[str, datetime]] = {}
    for row in rows:
        if row["first_seen"] is not None:
            first[row["clip_id"]] = (row["game_id"], row["first_seen"])
    seen: dict[str, list[datetime]] = defaultdict(list)
    for game_id, instant in first.values():
        seen[game_id].append(instant)
    for times in seen.values():
        times.sort()
    for row in rows:
        times = seen[row["game_id"]]
        t = row["prediction"]
        count = bisect_right(times, t) - bisect_left(times, t - ACTIVITY_WINDOW)
        own = row["first_seen"] is not None and t - ACTIVITY_WINDOW <= row["first_seen"] <= t
        row["category_activity"] = count - own


def broadcaster_priors(rows: list[dict], metadata: dict[str, dict]) -> dict:
    """Shrunk mean log 24-hour views per broadcaster from labeled training rows."""
    totals: dict[str, list[float]] = defaultdict(lambda: [0.0, 0])
    for row in rows:
        token = metadata.get(row["clip_id"], {}).get("broadcaster")
        if token:
            totals[token][0] += log1p(row["views_24h"])
            totals[token][1] += 1
    labels = [log1p(row["views_24h"]) for row in rows]
    return {"overall": (sum(labels), len(labels)), "totals": dict(totals)}


def feature_vector(
    row: dict, names: tuple[str, ...], metadata: dict[str, dict], priors: dict, *, own=False
) -> list[float]:
    """Features known at the row's cutoff; `own` removes the row's label from its prior."""
    views, rate, staleness = (
        row["latest_views"],
        row["growth_views_per_minute"],
        row["staleness_seconds"],
    )
    projected = c1_score(views, rate, staleness)
    meta = metadata.get(row["clip_id"], {})
    total, count = priors.get("totals", {}).get(meta.get("broadcaster") or "", (0.0, 0))
    grand, size = priors.get("overall", (0.0, 0))
    if own and row["views_24h"] is not None:
        # Leave-one-out: the row's own label leaves both its broadcaster and the global mean.
        label = log1p(row["views_24h"])
        grand, size = grand - label, size - 1
        if count:
            total, count = total - label, count - 1
    overall = grand / size if size else 0.0
    values = {
        "log1p_latest_views": log1p(views) if views is not None else nan,
        "log1p_first_views": log1p(row["first_views"]) if row["first_views"] is not None else nan,
        "log1p_c1": log1p(projected) if projected is not None else nan,
        "signed_log_growth_rate": copysign(log1p(abs(rate)), rate) if rate is not None else nan,
        "latest_observation_age_seconds": row["latest_observation_age_seconds"],
        "staleness_seconds": staleness,
        "observation_count": row["observation_count"],
        "discovery_delay_seconds": row["discovery_delay_seconds"],
        "hour_utc": row["created"].hour,
        "weekday_utc": row["created"].weekday(),
        "log1p_category_activity": log1p(row["category_activity"]),
        "duration_seconds": _number(meta.get("duration_seconds")),
        "is_english": float(meta.get("language") == "en") if meta.get("language") else None,
        "broadcaster_prior": (total + PRIOR_WEIGHT * overall) / (count + PRIOR_WEIGHT),
        "broadcaster_clips": log1p(count),
    }
    return [nan if values[name] is None else float(values[name]) for name in names]


def _model(name: str):
    if name == "ridge":
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import Ridge
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler

        return make_pipeline(
            SimpleImputer(strategy="median", keep_empty_features=True), StandardScaler(), Ridge()
        )
    if name == "xgboost":
        from xgboost import XGBRegressor

        return XGBRegressor(
            n_estimators=300,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=SEED,
            n_jobs=2,
        )
    from lightgbm import LGBMRegressor

    return LGBMRegressor(
        n_estimators=300,
        learning_rate=0.05,
        num_leaves=15,
        subsample=0.8,
        subsample_freq=1,
        colsample_bytree=0.8,
        random_state=SEED,
        n_jobs=2,
        verbose=-1,
    )


def _fit(name: str, rows: list[dict], names, metadata, priors):
    model = _model(name)
    model.fit(
        [feature_vector(row, names, metadata, priors, own=True) for row in rows],
        [log1p(row["views_24h"]) for row in rows],
    )
    return model


def _predict(model, rows: list[dict], names, metadata, priors) -> list[float]:
    if not rows:
        return []
    return [
        float(value)
        for value in model.predict([feature_vector(row, names, metadata, priors) for row in rows])
    ]


def top_overlap(scored: list[tuple[float, int, str]], k: int = 50) -> float | None:
    """Benchmark T1 tie rule: share of the true top-k (ties included) in the predicted top-k."""
    if len(scored) < MIN_POOL:
        return None
    values = sorted((views for _, views, _ in scored), reverse=True)
    size = min(k, len(values))
    relevant = {clip for _, views, clip in scored if views >= values[size - 1]}
    top = [clip for _, _, clip in sorted(scored, key=lambda item: (-item[0], item[2]))[:k]]
    return len(relevant.intersection(top)) / size


def informative_k(rows: list[dict]) -> int | None:
    """Top-50 when some daily pool exceeds 50 labels, else top-10; None without evidence."""
    sizes = Counter((row["game_id"], row["day"]) for row in rows).values()
    return next((k for k in (50, 10) if any(size > k for size in sizes)), None)


def _daily_overlap(rows: list[dict], scores: list[float], k: int) -> float | None:
    """Mean daily top-k overlap over pools larger than k, where overlap can discriminate."""
    pools: dict[tuple[str, datetime], list] = defaultdict(list)
    for row, score in zip(rows, scores, strict=True):
        pools[row["game_id"], row["day"]].append((score, row["views_24h"], row["clip_id"]))
    values = [top_overlap(pool, k) for pool in pools.values() if len(pool) > k]
    return mean(values) if values else None


def train_c2(
    directories: list[Path],
    output: Path,
    validation_start: datetime,
    test_start: datetime,
    *,
    game_ids: tuple[str, ...],
    metadata: Path | None = None,
) -> dict:
    """Fit the model zoo on train, select on validation and seal it before any test export.

    Models are not refitted on validation, so a later report's validation split stays
    out of sample. Training exports must end by the test start: test labels stay unread.
    """
    output = ignored_output(output)
    if not validation_start < test_start:
        raise ValueError("Validation must start before the test")
    inputs, exports = read_candidate_exports(directories, benchmark=True)
    if any(export.window.end > test_start for export in exports):
        raise ValueError("Training exports must end by the test start")
    read_export_outcomes(inputs, exports)
    meta = read_metadata(metadata)
    labeled = []
    for row in load_rows(directories).values():
        outcome = inputs.outcomes.get(row["clip_id"])
        if (
            row["cutoff"] == CUTOFF
            and row["eligible"]
            and row["game_id"] in game_ids
            and outcome is not None
            and outcome.status == "valid"
        ):
            labeled.append(row | {"views_24h": outcome.views})
    labeled.sort(key=lambda row: (row["created"], row["clip_id"]))
    train = [row for row in labeled if row["day"] + DAY + MATURITY <= validation_start]
    validation = [
        row
        for row in labeled
        if validation_start <= row["day"] and row["day"] + DAY + MATURITY <= test_start
    ]
    k = informative_k(validation)
    if not train or k is None:
        raise ValueError("Training needs matured train rows and a validation pool above 10 labels")
    sets = {name: FEATURE_SETS[name] for name in ("safe", "exploratory") if name == "safe" or meta}
    priors = broadcaster_priors(train, meta)
    selection, fitted = [], {}
    for set_name, names in sets.items():
        for model_name in MODELS:
            model = _fit(model_name, train, names, meta, priors)
            fitted[f"{set_name}:{model_name}"] = model
            overlap = _daily_overlap(
                validation, _predict(model, validation, names, meta, priors), k
            )
            selection.append(
                {"features": set_name, "model": model_name, "validation_overlap": overlap}
            )
    best = max(item["validation_overlap"] for item in selection)
    winners = [
        f"{item['features']}:{item['model']}"
        for item in selection
        if item["validation_overlap"] == best
    ]
    decision = {
        "evaluation_version": VERSION,
        "game_ids": list(game_ids),
        "cutoff_minutes": CUTOFF,
        "validation_start": validation_start.isoformat(),
        "test_start": test_start.isoformat(),
        "selection_k": k,
        "selected": winners[0],
        "metadata_sha256": sha256(metadata.read_bytes()).hexdigest() if metadata else None,
    }
    output.mkdir(parents=True)
    payload = pickle.dumps({"models": fitted, "priors": priors, "sets": sets, "decision": decision})
    (output / "models.pkl").write_bytes(payload)
    manifest = decision | {
        "train_rows": len(train),
        "validation_rows": len(validation),
        "validation_latest_views_overlap": _daily_overlap(
            validation, [row["latest_views"] for row in validation], k
        ),
        "selection": selection,
        "selection_ties": winners,
        "exploratory_assumption": (
            "duration, language and broadcaster come from the current collector row"
            if meta
            else None
        ),
        "models_sha256": sha256(payload).hexdigest(),
    }
    write_json(output / "manifest.json", manifest)
    return manifest


def load_models(directory: Path) -> tuple[dict, dict]:
    """Load a sealed model directory. Only load artifacts this project produced locally."""
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    payload = (directory / "models.pkl").read_bytes()
    if sha256(payload).hexdigest() != manifest["models_sha256"]:
        raise ValueError("The sealed models do not match their manifest")
    sealed = pickle.loads(payload)  # local artifact whose hash was just verified
    if any(manifest.get(key) != value for key, value in sealed["decision"].items()):
        raise ValueError("The manifest decision fields differ from the sealed models")
    return manifest, sealed


def add_models(directories: list[Path], model_dir: Path, metadata: Path | None):
    """Benchmark hooks that append c1, the selected c2 and every zoo model, then annotate.

    Only candidate features are read here; outcomes stay closed until the orders freeze.
    """
    manifest, sealed = load_models(model_dir)
    meta = read_metadata(metadata)
    expected = sealed["decision"]["metadata_sha256"]
    if expected and (metadata is None or sha256(metadata.read_bytes()).hexdigest() != expected):
        raise ValueError("The exploratory models need the exact --metadata file they used")
    rows = load_rows(directories)
    focal = [row for row in rows.values() if row["cutoff"] == CUTOFF]
    coverage = sum(row["clip_id"] in meta for row in focal) / len(focal) if focal else 0.0
    if expected and not coverage:
        raise ValueError("The metadata file covers no candidate clip")
    names = [manifest["selected"], *sealed["models"]]
    methods = [METHOD, *(f"{METHOD}:{name}" for name in sealed["models"])]

    def extend(frozen: Frozen) -> Frozen:
        extended = add_c1(frozen)
        for key, orders in extended.items():
            pool = orders[C1]
            width = len(pool[0].scores)
            ready = [row for row in pool if rows[row.clip_id, row.cutoff]["eligible"]]
            features = [rows[row.clip_id, row.cutoff] for row in ready]
            scores: dict[str, list[float | None]] = {}
            for name in dict.fromkeys(names):
                set_name = name.split(":")[0]
                predicted = _predict(
                    sealed["models"][name],
                    features,
                    sealed["sets"][set_name],
                    meta,
                    sealed["priors"],
                )
                by_clip = dict(zip((row.clip_id for row in ready), predicted, strict=True))
                scores[name] = [by_clip.get(row.clip_id) for row in pool]
            rescored = [
                replace(row, scores=(*row.scores, *(scores[name][i] for name in names)))
                for i, row in enumerate(pool)
            ]
            by_id = {row.clip_id: row for row in rescored}
            result = {
                method: [by_id[row.clip_id] for row in order] for method, order in orders.items()
            }
            for offset, method in enumerate(methods):
                result[method] = rank_candidates(rescored, width + offset)
            extended[key] = result
        return extended

    def annotate(report: dict) -> None:
        report["c2_model"] = {
            "selected": manifest["selected"],
            "selection_ties": manifest["selection_ties"],
            "models_sha256": manifest["models_sha256"],
            "metadata_sha256": expected,
            "metadata_coverage_at_cutoff": coverage,
            "exploratory_assumption": manifest["exploratory_assumption"],
            "trained_cutoff_minutes": CUTOFF,
            "note": "Only the trained cutoff carries c2 comparisons.",
        }
        block = report["by_cutoff_minutes"][CUTOFF]
        if not block["metrics"]:
            return
        for k in KS:
            for reference in ("latest_views", C1):
                paired = paired_test_difference(block, k, METHOD, reference)
                if paired is not None:
                    block.setdefault(f"c2_vs_{reference}", {})[k] = paired

    return extend, annotate


def run_c2(
    directories: list[Path],
    output: Path,
    validation_start: datetime | None,
    test_start: datetime | None,
    *,
    game_id: str,
    cohort: str,
    model_dir: Path,
    metadata: Path | None = None,
) -> dict:
    """Score a later export with the sealed models on the exact boundaries they were sealed for."""
    manifest = json.loads((model_dir / "manifest.json").read_text(encoding="utf-8"))
    boundaries = (
        validation_start.isoformat() if validation_start else None,
        test_start.isoformat() if test_start else None,
    )
    if boundaries != (manifest["validation_start"], manifest["test_start"]):
        raise ValueError("The c2 evaluation must use the boundaries the models were sealed for")
    extend, annotate = add_models(directories, model_dir, metadata)
    return run_benchmark(
        directories,
        output,
        validation_start,
        test_start,
        game_id=game_id,
        cohort=cohort,
        version=VERSION,
        extend=extend,
        annotate=annotate,
    )
