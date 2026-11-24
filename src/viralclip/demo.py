"""Local portfolio demo backed by an append-only synthetic prediction registry."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from viralclip.collector.service import GTA_VI_GAME_ID
from viralclip.storage.database import to_utc_iso, utc_now

REGISTRY = Path("data/demo/predictions.sqlite3")
ASSETS = Path(__file__).with_name("demo_web")
APPLICATION_ID = 0x56435244
FIXTURE_REVISION = "fixture-v2"
CUTOFF = 60
DAY = datetime(2026, 11, 22, tzinfo=UTC)
GAMES = {GTA_VI_GAME_ID: "GTA VI", "32982": "GTA V"}

# title, synthetic channel, duration, age-52 view count, estimated views feature,
# media scenario, preview scene
CLIPS = {
    GTA_VI_GAME_ID: (
        ("Overpass getaway", "neon_driver", 28, 128, 1840, "open", 0),
        ("Parking with inches to spare", "city_loop", 19, 96, 1420, "open", 1),
        ("One shortcut too many", "last_corner", 34, 118, 1190, "file", 2),
        ("Coastal drift", "ocean_shift", 22, 71, 860, "render_error", 3),
        ("Back in the rain", "after_rain", 41, 56, 620, "blocked", 4),
        ("One last lap", "neon_driver", 26, None, None, "open", 5),
    ),
    "32982": (
        ("Rooftop landing", "roof_runner", 21, 98, None, "open", 2),
        ("The impossible turn", "west_coast", 35, 79, None, "file", 0),
        ("Out of the tunnel", "late_shift", 32, 45, None, "render_error", 4),
        ("Sunset lap", "roof_runner", 24, 22, None, "blocked", 3),
    ),
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS demo_ranking_runs (
    run_id TEXT PRIMARY KEY,
    game_id TEXT NOT NULL,
    pool_day TEXT NOT NULL,
    cutoff_minutes INTEGER NOT NULL,
    scored_at TEXT NOT NULL,
    source_watermark TEXT NOT NULL,
    score_version TEXT NOT NULL,
    method TEXT NOT NULL CHECK (method IN ('simulated_model', 'baseline')),
    model_status TEXT NOT NULL,
    pool_size INTEGER NOT NULL CHECK (pool_size > 0)
);
CREATE TABLE IF NOT EXISTS demo_predictions (
    prediction_id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES demo_ranking_runs(run_id) DEFERRABLE INITIALLY DEFERRED,
    clip_id TEXT NOT NULL,
    title TEXT NOT NULL,
    channel TEXT NOT NULL,
    duration INTEGER NOT NULL,
    scenario TEXT NOT NULL,
    scene INTEGER NOT NULL,
    prediction_at TEXT NOT NULL,
    score INTEGER,
    rank INTEGER,
    latest_views INTEGER,
    latest_observed_at TEXT,
    observation_ids TEXT NOT NULL,
    CHECK ((score IS NULL) = (rank IS NULL)),
    UNIQUE (run_id, clip_id),
    UNIQUE (run_id, rank)
);
CREATE TRIGGER IF NOT EXISTS demo_run_no_update
BEFORE UPDATE ON demo_ranking_runs BEGIN SELECT RAISE(ABORT, 'Append-only registry'); END;
CREATE TRIGGER IF NOT EXISTS demo_run_no_delete
BEFORE DELETE ON demo_ranking_runs BEGIN SELECT RAISE(ABORT, 'Append-only registry'); END;
CREATE TRIGGER IF NOT EXISTS demo_prediction_no_update
BEFORE UPDATE ON demo_predictions BEGIN SELECT RAISE(ABORT, 'Append-only registry'); END;
CREATE TRIGGER IF NOT EXISTS demo_prediction_no_delete
BEFORE DELETE ON demo_predictions BEGIN SELECT RAISE(ABORT, 'Append-only registry'); END;
CREATE TRIGGER IF NOT EXISTS demo_run_insert_guard
BEFORE INSERT ON demo_ranking_runs
WHEN EXISTS (SELECT 1 FROM demo_ranking_runs WHERE run_id = NEW.run_id)
  OR NEW.pool_size != (SELECT count(*) FROM demo_predictions WHERE run_id = NEW.run_id)
BEGIN SELECT RAISE(ABORT, 'Run already sealed or incomplete'); END;
CREATE TRIGGER IF NOT EXISTS demo_prediction_insert_guard
BEFORE INSERT ON demo_predictions
WHEN EXISTS (SELECT 1 FROM demo_ranking_runs WHERE run_id = NEW.run_id)
  OR EXISTS (SELECT 1 FROM demo_predictions WHERE prediction_id = NEW.prediction_id)
  OR NEW.latest_observed_at > NEW.prediction_at
BEGIN SELECT RAISE(ABORT, 'Sealed run, existing prediction, or observation after cutoff'); END;
"""


def fixture_rows(game_id: str) -> list[dict]:
    rows = []
    for index, (title, channel, duration, views, estimate, scenario, scene) in enumerate(
        CLIPS[game_id], 1
    ):
        clip_id = f"demo-{game_id}-{index:02d}"
        created = DAY + timedelta(hours=18, minutes=4 * index)
        prediction = created + timedelta(minutes=CUTOFF)
        # The later synthetic observation is deliberately unavailable to the ranker.
        observations = (
            []
            if views is None
            else [
                (f"{clip_id}:52", created + timedelta(minutes=52), views),
                (f"{clip_id}:64", created + timedelta(minutes=64), views + 100),
            ]
        )
        eligible = [item for item in observations if item[1] <= prediction]
        latest = eligible[-1] if eligible else None
        latest_views = latest[2] if latest else None
        # This fixture stand-in combines the estimate with a separate cutoff feature.
        output = latest_views
        if game_id == GTA_VI_GAME_ID:
            output = (
                estimate + 2 * latest_views
                if estimate is not None and latest_views is not None
                else None
            )
        rows.append(
            {
                "clip_id": clip_id,
                "title": title,
                "channel": channel,
                "duration": duration,
                "scenario": scenario,
                "scene": scene,
                "prediction_at": to_utc_iso(prediction),
                "output": output,
                "latest_views": latest_views,
                "latest_observed_at": to_utc_iso(latest[1]) if latest else None,
                "fixture_watermark": to_utc_iso(observations[-1][1]) if observations else None,
                "observation_ids": json.dumps([item[0] for item in eligible]),
            }
        )
    rows.sort(key=lambda row: (row["output"] is None, -(row["output"] or 0), row["clip_id"]))
    scored = [row["output"] for row in rows if row["output"] is not None]
    for row in rows:
        output = row["output"]
        if output is None:
            row["score"] = None
            continue
        highest, lowest = scored[0], scored[-1]
        # Equal outputs share the top score when there is no spread.
        row["score"] = (
            100 if highest == lowest else 1 + round(99 * (output - lowest) / (highest - lowest))
        )
    return rows


def prepare_registry(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("PRAGMA foreign_keys=ON")
        application_id = db.execute("PRAGMA application_id").fetchone()[0]
        occupied = db.execute("SELECT 1 FROM sqlite_schema LIMIT 1").fetchone()
        if application_id != APPLICATION_ID and (application_id != 0 or occupied):
            raise ValueError("The demo registry path is already used by another database")
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript(f"BEGIN IMMEDIATE;\nPRAGMA application_id={APPLICATION_ID};\n{SCHEMA}")
        db.execute("PRAGMA defer_foreign_keys=ON")
        now = utc_now()
        for game_id in GAMES:
            run_id = f"{FIXTURE_REVISION}:{game_id}"
            if db.execute("SELECT 1 FROM demo_ranking_runs WHERE run_id=?", (run_id,)).fetchone():
                continue
            rows = fixture_rows(game_id)
            scored_at = to_utc_iso(now)
            watermark = max(row["fixture_watermark"] for row in rows if row["fixture_watermark"])
            if scored_at < max(watermark, *(row["prediction_at"] for row in rows)):
                raise ValueError("System clock precedes the synthetic prediction times")
            simulated = game_id == GTA_VI_GAME_ID
            db.executemany(
                """
                INSERT INTO demo_predictions (
                    run_id, clip_id, title, channel, duration, scenario, scene, prediction_at,
                    score, rank, latest_views, latest_observed_at, observation_ids
                ) VALUES (
                    :run_id, :clip_id, :title, :channel, :duration, :scenario, :scene,
                    :prediction_at, :score, :rank, :latest_views, :latest_observed_at,
                    :observation_ids
                )
                """,
                (
                    row | {"run_id": run_id, "rank": rank if row["score"] is not None else None}
                    for rank, row in enumerate(rows, 1)
                ),
            )
            db.execute(
                """
                INSERT INTO demo_ranking_runs (
                    run_id, game_id, pool_day, cutoff_minutes, scored_at, source_watermark,
                    score_version, method, model_status, pool_size
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    game_id,
                    DAY.date().isoformat(),
                    CUTOFF,
                    scored_at,
                    watermark,
                    "fixture:potential:v2" if simulated else "baseline:latest_views:v2",
                    "simulated_model" if simulated else "baseline",
                    "simulated" if simulated else "not_trained_yet",
                    len(rows),
                ),
            )


def read_ranking(path: Path, game_id: str) -> dict:
    with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        run = dict(
            db.execute(
                "SELECT * FROM demo_ranking_runs WHERE run_id=?",
                (f"{FIXTURE_REVISION}:{game_id}",),
            ).fetchone()
        )
        predictions = [
            dict(row)
            for row in db.execute(
                """SELECT prediction_id, clip_id, title, channel, duration, scenario, scene,
                          prediction_at, score, rank, latest_observed_at, observation_ids
                   FROM demo_predictions WHERE run_id=?
                   ORDER BY rank IS NULL, rank, clip_id""",
                (run["run_id"],),
            )
        ]
    for row in predictions:
        row["observation_ids"] = json.loads(row["observation_ids"])
        demo_open = row["scenario"] in ("open", "render_error")
        row["media"] = {
            "download": demo_open,
            "edit_original": demo_open,
            "accept_file": row["scenario"] != "blocked",
        }
    return {
        "synthetic": True,
        "games": [{"id": key, "name": name} for key, name in GAMES.items()],
        "run": run,
        "predictions": predictions,
    }


def handler(registry: Path) -> type[BaseHTTPRequestHandler]:
    assets = {
        "/": ("index.html", "text/html; charset=utf-8"),
        "/styles.css": ("styles.css", "text/css; charset=utf-8"),
        "/app.js": ("app.js", "text/javascript; charset=utf-8"),
        "/media.js": ("media.js", "text/javascript; charset=utf-8"),
        "/gameplay.jpg": ("gameplay.jpg", "image/jpeg"),
    }

    class DemoHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            request = urlsplit(self.path)
            if request.path == "/api/ranking":
                values = parse_qs(request.query, keep_blank_values=True)
                game_id = values.get("game_id", [GTA_VI_GAME_ID])[0]
                if game_id not in GAMES:
                    self.send_error(HTTPStatus.NOT_FOUND, "Unknown game")
                    return
                body = json.dumps(read_ranking(registry, game_id), ensure_ascii=False).encode()
                content_type = "application/json; charset=utf-8"
            elif request.path in assets:
                name, content_type = assets[request.path]
                body = (ASSETS / name).read_bytes()
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; media-src 'self' blob:; "
                "object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
            )
            self.end_headers()
            self.wfile.write(body)

    return DemoHandler


def run_demo(port: int) -> None:
    prepare_registry(REGISTRY)
    with ThreadingHTTPServer(("127.0.0.1", port), handler(REGISTRY)) as server:
        print(f"Local demo: http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
