"""Verify the GTA VI category and guard an isolated collector instance."""

from __future__ import annotations

import argparse
import os
import sqlite3
from contextlib import closing
from pathlib import Path

from viralclip.cli import main as collector
from viralclip.config import load_settings
from viralclip.deployment import _check_schema, _open_read_only
from viralclip.twitch.client import TwitchAPIError, TwitchClient

NAME = "Grand Theft Auto VI"
# Verified by authenticated Helix Get Games name and ID lookups on 2026-11-19.
APPROVED_GAME_ID = "1867279146"
DB_NAME = "gta-vi.sqlite3"
INTERVAL, LOOKBACK = 300, 10


def _exact_match(records: list[dict]) -> str:
    if len(records) != 1:
        raise ValueError("Helix did not return one GTA VI category")
    record = records[0]
    game_id = record.get("id")
    if (
        record.get("name") != NAME
        or not isinstance(game_id, str)
        or not game_id.strip()
        or game_id == "32982"
    ):
        raise ValueError("Helix result did not identify the exact GTA VI category")
    return game_id


def resolve(client: TwitchClient) -> str:
    game_id = _exact_match(client.get_games(name=NAME))
    if _exact_match(client.get_games(game_id=game_id)) != game_id:
        raise ValueError("Twitch category lookup by ID disagreed with lookup by name")
    return game_id


def _preflight(state: Path, game_id: str) -> Path:
    # This validation only accepts operator-pinned IDs and the new dedicated paths.
    if game_id != APPROVED_GAME_ID:
        raise ValueError("GTA VI game ID does not match the approved Helix result")
    settings = load_settings()
    if not settings.has_twitch_credentials:
        raise ValueError("Missing GTA VI credentials")
    database = state / DB_NAME
    if (
        state.absolute() != state.resolve()
        or database != settings.db_path
        or settings.http_log_directory != str(state)
        or settings.games
        or settings.game_ids
        or (settings.discovery_interval_seconds, settings.discovery_lookback_minutes)
        != (INTERVAL, LOOKBACK)
    ):
        raise ValueError("GTA VI isolation paths or pilot settings do not match")
    if database.is_symlink() or not database.is_file() or database.stat().st_nlink != 1:
        raise ValueError("Initialize a separate GTA VI database before activation")
    # Reject aliases on all writable siblings, including the file lock and rotated logs.
    base = database.name
    for name in (
        f"{base}-wal",
        f"{base}-shm",
        f"{base}-journal",
        f"{base}.collector.lock",
        f"{base}.http.jsonl",
        *(f"{base}.http.jsonl.{i}" for i in (1, 2, 3)),
    ):
        sibling = state / name
        if sibling.is_symlink() or (
            sibling.exists() and (not sibling.is_file() or sibling.stat().st_nlink != 1)
        ):
            raise ValueError("GTA VI state contains an aliased or invalid writable file")
    with closing(_open_read_only(database)) as reader:
        reader.execute("PRAGMA query_only = ON")
        _check_schema(reader)
        if reader.execute("PRAGMA journal_mode").fetchone()[0] != "wal":
            raise ValueError("GTA VI collector database must use WAL")
        if reader.execute("SELECT 1 FROM games WHERE game_id <> ?", (game_id,)).fetchone():
            raise ValueError("GTA VI database contains another category")
    return database


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("resolve", help="Check the exact name and ID with official Twitch Helix")
    for name in ("preflight", "run"):
        command = commands.add_parser(name)
        command.add_argument("--state", type=Path, default=Path("/var/lib/viralclip-gta-vi"))
    args = parser.parse_args(argv)
    try:
        if args.command == "resolve":
            settings = load_settings()
            if not settings.has_twitch_credentials:
                raise ValueError("Twitch credentials are required for Helix verification")
            client = TwitchClient(
                settings.client_id or "", settings.client_secret or "", max_retries=0
            )
            try:
                print(resolve(client))
            finally:
                client.close()
        else:
            game_id = os.environ.get("VIRALCLIP_GTA_VI_GAME_ID", "")
            database = _preflight(args.state, game_id)
            if args.command == "run":
                return collector(["--db", str(database), "collect", "--game-id", game_id, "--loop"])
            print("GTA VI pilot preflight passed.")
    except TwitchAPIError:
        parser.exit(1, "GTA VI category verification via Twitch Helix failed.\n")
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.exit(1, f"GTA VI check failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
