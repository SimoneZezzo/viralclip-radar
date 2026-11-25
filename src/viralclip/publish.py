"""Publish sealed prediction runs as static JSON with immutable names and the index last.

Each game file is named by its content hash, so an update never rewrites a file a live
index points to. Replacing `index.json` alone switches readers to the new set; an
interrupted run leaves the previous index and its files intact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import time
from contextlib import closing
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from viralclip.challenger import SCORE_VERSION as C1_VERSION
from viralclip.predictions import BASELINE_VERSION, NOT_TRAINED, _read_registry
from viralclip.storage.database import to_utc_iso, utc_now

GAME_FILE = re.compile(r"[0-9]+-[0-9a-f]{16}\.json")
# Unreferenced game files survive this long for readers and caches holding an older index.
GRACE_SECONDS = 6 * 3600


def _method(run: sqlite3.Row) -> str:
    version, status = run["score_version"], run["model_status"]
    if status == "simulated":
        return f"Simulated model · {version}"
    if version == BASELINE_VERSION and status == NOT_TRAINED:
        return "latest_views baseline · no validated model for this game"
    if version == C1_VERSION:
        # The registry records the scorer, but contains no validation results.
        return "c1 · staleness projection"
    return f"{version} · {status}"


def _ranking(db: sqlite3.Connection, game_id: str, name: str, stamp: str) -> dict:
    run = db.execute(
        """SELECT run_id, pool_day, cutoff_minutes, scored_at, score_version, model_status, pool_size
           FROM ranking_runs WHERE game_id=?
           ORDER BY scored_at DESC, run_id DESC LIMIT 1""",
        (game_id,),
    ).fetchone()
    if run is None:
        raise ValueError(f"No sealed run for game {game_id}")
    if stamp < run["scored_at"]:
        raise ValueError(f"Publication precedes scoring for game {game_id}")
    clips = []
    synthetic = run["model_status"] == "simulated" or bool(
        re.match(r"^(?:fixture|synthetic)(?:[-:_]|$)", run["run_id"])
    )
    for row in db.execute(
        "SELECT * FROM predictions WHERE run_id=? AND rank IS NOT NULL ORDER BY rank",
        (run["run_id"],),
    ):
        prediction = dict(row)
        clips.append(
            {key: prediction[key] for key in ("rank", "clip_id", "score", "prediction_at")}
            | {
                "url": prediction.get("url") or prediction.get("clip_url"),
                "title": prediction.get("title"),
            }
        )
    if clips and all(
        re.fullmatch(r"synthetic-[0-9]{8}-[0-9]+|demo-[0-9]+-[0-9]+", clip["clip_id"])
        for clip in clips
    ):
        synthetic = True
    for clip in clips:
        if synthetic:
            clip["url"] = None
        elif not clip["url"]:
            clip["url"] = "https://clips.twitch.tv/" + quote(clip["clip_id"], safe="")
    return {
        "game_id": game_id,
        "game_name": name,
        "pool_day": run["pool_day"],
        "cutoff_minutes": run["cutoff_minutes"],
        "scored_at": run["scored_at"],
        "score_version": run["score_version"],
        "model_status": run["model_status"],
        "pool_size": run["pool_size"],
        "published_at": stamp,
        "method_label": _method(run),
        "synthetic": synthetic,
        "clips": clips,
    }


def publish(
    registry: Path, output: Path, games: dict[str, str], *, published_at: datetime | None = None
) -> dict:
    """Write selected games from one read-only registry snapshot and return the index."""
    if not games:
        raise ValueError("Select at least one game")
    for game_id, name in games.items():
        if not re.fullmatch(r"[0-9]+", game_id) or not name.strip():
            raise ValueError("Each game needs a numeric ID and nonempty name")
    if registry.resolve().is_relative_to(output.resolve()):
        raise ValueError("Keep the private registry outside the public output directory")
    stamp = to_utc_iso(published_at if published_at is not None else utc_now())
    directory = output / "rankings"
    directory.mkdir(parents=True, exist_ok=True)
    # A 0700 TemporaryDirectory on Windows gives its files a private ACL that
    # survives os.replace. Inherit the public directory's normal permissions.
    stage = directory / ".publishing"
    try:
        stage.mkdir()
    except FileExistsError:
        raise ValueError(f"Publish in progress or interrupted. Check {stage}") from None
    try:
        entries = []
        with closing(_read_registry(registry)) as db:
            db.execute("BEGIN")
            for game_id, name in games.items():
                ranking = _ranking(db, game_id, name.strip(), stamp)
                content = json.dumps(ranking, ensure_ascii=False).encode("utf-8")
                filename = f"{game_id}-{hashlib.sha256(content).hexdigest()[:16]}.json"
                (stage / filename).write_bytes(content)
                entries.append(
                    {
                        "id": game_id,
                        "name": ranking["game_name"],
                        "scored_at": ranking["scored_at"],
                        "file": filename,
                    }
                )
        index = {"published_at": stamp, "games": entries}
        manifest = directory / "index.json"
        previous = set()
        if manifest.exists():
            for game in json.loads(manifest.read_text(encoding="utf-8"))["games"]:
                if GAME_FILE.fullmatch(game.get("file", "")):
                    previous.add(game["file"])
        (stage / manifest.name).write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
        # New names never overwrite a file the live index references; the index goes last.
        for entry in entries:
            os.replace(stage / entry["file"], directory / entry["file"])
        os.replace(stage / manifest.name, manifest)
        # Keep the previous generation and anything newer than the grace period for readers
        # still holding an older index; remove older game files, including interrupted runs.
        keep = previous | {entry["file"] for entry in entries}
        horizon = time.time() - GRACE_SECONDS  # file times are wall-clock times
        for path in directory.iterdir():
            if GAME_FILE.fullmatch(path.name) and path.name not in keep:
                try:
                    if path.stat().st_mtime < horizon:
                        path.unlink()
                except OSError:
                    pass  # e.g. open on Windows; the publication succeeded, retried next run
    finally:
        shutil.rmtree(stage)
    return index


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="viralclip publish", description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--game", action="append", metavar="ID=NAME", required=True)
    args = parser.parse_args(argv)
    games = {}
    for item in args.game:
        game_id, separator, name = item.partition("=")
        if not separator or game_id in games:
            parser.error("Supply each game once as --game ID=NAME")
        games[game_id] = name
    try:
        index = publish(args.registry, args.output, games)
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.exit(1, f"Publish failed: {exc}\n")
    print(json.dumps(index, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
