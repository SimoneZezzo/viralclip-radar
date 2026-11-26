"""Local portfolio demo backed by the live ranking registry over synthetic collector data."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from viralclip.collector.service import GTA_VI_GAME_ID, Collector
from viralclip.predictions import _connect_registry, rank_pool, read_run
from viralclip.storage.database import Database, to_utc_iso

REGISTRY = Path("data/demo/registry-v3.sqlite3")
# Built by `npm --prefix web run build`; the demo runs from a source checkout.
ASSETS = Path(__file__).resolve().parents[2] / "web" / "dist"
FIXTURE_REVISION = "fixture-v4"
CUTOFF = 60
DAY = datetime(2026, 11, 22, tzinfo=UTC)
GAMES = {GTA_VI_GAME_ID: "GTA VI", "32982": "GTA V"}
SIMULATED_VERSION = "fixture:potential:v3"

# Suggested external editors. The site only links to them: it has no integration,
# sends them nothing, and the user picks and pays for the editor.
EDITORS = (
    {"name": "CapCut", "url": "https://www.capcut.com/"},
    {"name": "Clipchamp", "url": "https://clipchamp.com/"},
    {"name": "DaVinci Resolve", "url": "https://www.blackmagicdesign.com/products/davinciresolve"},
    {"name": "Shotcut", "url": "https://shotcut.org/"},
)
SYNTHETIC_LINK = "https://example.invalid/synthetic-clips/"

# title, synthetic channel, duration, age-52 view count, estimated views feature,
# preview scene
CLIPS = {
    GTA_VI_GAME_ID: (
        ("Clip 1", "neon_driver", 28, 128, 1840, 0),
        ("Clip 2", "city_loop", 19, 96, 1420, 1),
        ("Clip 3", "last_corner", 34, 118, 1190, 2),
        ("Clip 4", "ocean_shift", 22, 71, 860, 3),
        ("Clip 5", "after_rain", 41, 56, 620, 4),
        ("Clip 6", "neon_driver", 26, 34, None, 5),
    ),
    "32982": (
        ("Clip 1", "roof_runner", 21, 98, None, 2),
        ("Clip 2", "west_coast", 35, 79, None, 0),
        ("Clip 3", "late_shift", 32, 45, None, 4),
        ("Clip 4", "roof_runner", 24, 22, None, 3),
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
            "scene": scene,
            "created": DAY + timedelta(hours=18, minutes=4 * index),
        }
        for game_id, clips in CLIPS.items()
        for index, (title, channel, duration, views, estimate, scene) in enumerate(clips, 1)
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
        predictions.append(
            row
            | {key: clip[key] for key in ("title", "channel", "duration", "scene")}
            # Synthetic clips have no Twitch page; real rankings carry the clip's Twitch URL.
            | {"url": SYNTHETIC_LINK + row["clip_id"], "twitch_url": None}
        )
    return {
        "synthetic": True,
        "games": [{"id": key, "name": name} for key, name in GAMES.items()],
        "editors": list(EDITORS),
        "run": run,
        "predictions": predictions,
    }


SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self'; object-src 'none'; base-uri 'none'; "
        "frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}


def create_app(registry: Path, assets: Path = ASSETS) -> FastAPI:
    """FastAPI app: the ranking API plus the built React front end from `web/dist`."""
    app = FastAPI(
        title="ViralClip Radar demo",
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.update(SECURITY_HEADERS)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/ranking")
    def ranking(game_id: str = GTA_VI_GAME_ID) -> dict:
        if game_id not in GAMES:
            raise HTTPException(status_code=404, detail="Unknown game")
        return read_ranking(registry, game_id)

    if (assets / "index.html").is_file():
        app.mount("/", StaticFiles(directory=assets, html=True), name="web")
    else:

        @app.get("/", response_class=PlainTextResponse, status_code=503)
        def missing_front_end() -> str:
            return (
                "The front end is not built. Run: npm --prefix web ci; npm --prefix web run build"
            )

    return app


def run_demo(port: int, registry: Path = REGISTRY) -> None:
    import uvicorn

    prepare_registry(registry)
    if not (ASSETS / "index.html").is_file():
        print("Front end not built: run `npm --prefix web ci` and `npm --prefix web run build`.")
    print(f"Local demo: http://127.0.0.1:{port}", flush=True)
    uvicorn.run(create_app(registry), host="127.0.0.1", port=port, log_level="warning")
