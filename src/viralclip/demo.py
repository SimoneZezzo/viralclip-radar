"""Local portfolio demo backed by the live ranking registry over synthetic collector data."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from viralclip.collector.service import GTA_VI_GAME_ID, Collector
from viralclip.predictions import _connect_registry, rank_pool, read_run
from viralclip.storage.database import Database, to_utc_iso

REGISTRY = Path("data/demo/registry-v3.sqlite3")
ASSETS = Path(__file__).with_name("demo_web")
FIXTURE_REVISION = "fixture-v3"
CUTOFF = 60
DAY = datetime(2026, 11, 22, tzinfo=UTC)
GAMES = {GTA_VI_GAME_ID: "GTA VI", "32982": "GTA V"}
SIMULATED_VERSION = "fixture:potential:v3"

# title, synthetic channel, duration, age-52 view count, estimated views feature,
# media scenario, preview scene
CLIPS = {
    GTA_VI_GAME_ID: (
        ("Overpass getaway", "neon_driver", 28, 128, 1840, "open", 0),
        ("Parking with inches to spare", "city_loop", 19, 96, 1420, "open", 1),
        ("One shortcut too many", "last_corner", 34, 118, 1190, "file", 2),
        ("Coastal drift", "ocean_shift", 22, 71, 860, "render_error", 3),
        ("Back in the rain", "after_rain", 41, 56, 620, "blocked", 4),
        ("One last lap", "neon_driver", 26, 34, None, "open", 5),
    ),
    "32982": (
        ("Rooftop landing", "roof_runner", 21, 98, None, "open", 2),
        ("The impossible turn", "west_coast", 35, 79, None, "file", 0),
        ("Out of the tunnel", "late_shift", 32, 45, None, "render_error", 4),
        ("Sunset lap", "roof_runner", 24, 22, None, "blocked", 3),
    ),
}


def clip_id(game_id: str, index: int) -> str:
    return f"demo-{game_id}-{index:02d}"


def fixture_clips() -> dict[str, dict]:
    """Synthetic clip metadata keyed by clip ID, including the simulated estimate feature."""
    return {
        clip_id(game_id, index): {
            "game_id": game_id,
            "title": title,
            "channel": channel,
            "duration": duration,
            "views": views,
            "estimate": estimate,
            "scenario": scenario,
            "scene": scene,
            "created": DAY + timedelta(hours=18, minutes=4 * index),
        }
        for game_id, clips in CLIPS.items()
        for index, (title, channel, duration, views, estimate, scenario, scene) in enumerate(
            clips, 1
        )
    }


def synthetic_collector(path: Path) -> Path:
    """Build, once, a collector database holding only labeled synthetic observations."""
    if path.exists():
        return path
    writer = Database(path)
    try:
        for game_id, name in GAMES.items():
            writer.upsert_game(game_id, f"{name} (SYNTHETIC / NOT REAL TWITCH DATA)", DAY)
        for key, clip in fixture_clips().items():
            # The 64-minute observation is deliberately after the 60-minute cutoff.
            for minutes, views in ((52, clip["views"]), (64, clip["views"] + 100)):
                raw = {
                    "id": key,
                    "broadcaster_name": clip["channel"],
                    "title": clip["title"],
                    "created_at": to_utc_iso(clip["created"]),
                    "view_count": views,
                    "duration": clip["duration"],
                }
                writer.record_clip(
                    Collector._parse_clip(raw),
                    clip["game_id"],
                    clip["created"] + timedelta(minutes=minutes),
                    None,
                )
    finally:
        writer.close()
    return path


def _simulated_output(row: dict) -> float | None:
    # This fixture stand-in combines the estimate feature with the cutoff views.
    estimate = fixture_clips()[row["clip_id"]]["estimate"]
    if estimate is None or row["latest_views"] is None:
        return None
    return estimate + 2 * row["latest_views"]


def prepare_registry(path: Path) -> None:
    collector = synthetic_collector(path.with_name(f"{path.stem}-synthetic-collector.sqlite3"))
    _connect_registry(path, collector).close()
    for game_id in GAMES:
        run_id = f"{FIXTURE_REVISION}:{game_id}"
        if read_run(path, run_id) is not None:
            continue
        simulated = game_id == GTA_VI_GAME_ID
        rank_pool(
            collector,
            path,
            game_id,
            DAY,
            CUTOFF,
            run_id=run_id,
            **(
                {
                    "scorer": _simulated_output,
                    "score_version": SIMULATED_VERSION,
                    "model_status": "simulated",
                }
                if simulated
                else {}
            ),
        )


def read_ranking(path: Path, game_id: str) -> dict:
    result = read_run(path, f"{FIXTURE_REVISION}:{game_id}")
    if result is None:
        raise ValueError("The demo ranking has not been prepared")
    run = result["run"]
    run["method"] = "simulated_model" if run["model_status"] == "simulated" else "baseline"
    clips = fixture_clips()
    predictions = []
    for row in result["predictions"]:
        clip = clips[row["clip_id"]]
        demo_open = clip["scenario"] in ("open", "render_error")
        predictions.append(
            row
            | {key: clip[key] for key in ("title", "channel", "duration", "scenario", "scene")}
            | {
                "media": {
                    "download": demo_open,
                    "edit_original": demo_open,
                    "accept_file": clip["scenario"] != "blocked",
                }
            }
        )
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
