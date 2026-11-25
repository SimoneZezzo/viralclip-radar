"""Publish sealed prediction runs as static JSON, replacing each file atomically."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from viralclip.challenger import SCORE_VERSION as C1_VERSION
from viralclip.predictions import BASELINE_VERSION, NOT_TRAINED, _read_registry
from viralclip.storage.database import to_utc_iso, utc_now


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
                (stage / f"{game_id}.json").write_text(
                    json.dumps(ranking, ensure_ascii=False), encoding="utf-8"
                )
                entries.append(
                    {"id": game_id, "name": ranking["game_name"], "scored_at": ranking["scored_at"]}
                )
        index = {"published_at": stamp, "games": entries}
        manifest = directory / "index.json"
        old_ids = set()
        if manifest.exists():
            for game in json.loads(manifest.read_text(encoding="utf-8"))["games"]:
                if re.fullmatch(r"[0-9]+", game["id"]):
                    old_ids.add(game["id"])
        (stage / manifest.name).write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
        # The index becomes visible after every file it references is in place.
        for game_id in games:
            filename = f"{game_id}.json"
            os.replace(stage / filename, directory / filename)
        os.replace(stage / manifest.name, manifest)
        # Retire only game files named by our previous index.
        for old_id in old_ids.difference(games):
            (directory / f"{old_id}.json").unlink(missing_ok=True)
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
