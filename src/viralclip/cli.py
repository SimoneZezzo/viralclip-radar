from __future__ import annotations

import argparse
import sys
import time

from viralclip.collector.service import Collector
from viralclip.config import load_settings
from viralclip.storage.database import Database, utc_now
from viralclip.twitch.client import TwitchAPIError, TwitchClient


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="viralclip")
    parser.add_argument("--db", help="SQLite database path (overrides VIRALCLIP_DB_PATH)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-db", help="create or migrate the local SQLite database")
    collect = commands.add_parser("collect", help="discover clips and collect view snapshots")
    collect.add_argument("--game", action="append", help="game category name; may be repeated")
    collect.add_argument("--game-id", action="append", help="explicit Twitch category ID")
    mode = collect.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true", help="perform one collection cycle")
    mode.add_argument("--loop", action="store_true", help="collect continuously until interrupted")
    commands.add_parser("status", help="show local collection status (no credentials required)")
    return parser


def _print_status(database: Database) -> None:
    status = database.status(utc_now())
    print(f"Database: {database.path}")
    print(f"Games: {status['games']}")
    print(f"Clips: {status['clips']}")
    print(f"Snapshots: {status['snapshots']}")
    print(f"Latest successful collection: {status['latest_success'] or 'never'}")
    print(f"Due/missed jobs: {status['due_jobs']} due / {status['jobs'].get('missed', 0)} missed")
    print(f"Jobs: {status['jobs'] or 'none'}")
    print(f"Last error: {status['last_error'] or 'none'}")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        settings = load_settings()
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    if args.db:
        settings = settings.__class__(
            **{**settings.__dict__, "db_path": settings.db_path.__class__(args.db).expanduser()}
        )
    database = Database(settings.db_path)
    try:
        if args.command == "init-db":
            print(f"Database ready: {database.path}")
            return 0
        if args.command == "status":
            _print_status(database)
            return 0
        if not settings.has_twitch_credentials:
            print(
                "Twitch credentials are missing. Set TWITCH_CLIENT_ID and "
                "TWITCH_CLIENT_SECRET in .env; see README.md.",
                file=sys.stderr,
            )
            return 2
        games = tuple(args.game) if args.game else settings.games
        game_ids = tuple(args.game_id) if args.game_id else settings.game_ids
        if not games and not game_ids:
            print(
                "No games configured. Pass --game NAME/--game-id ID or set "
                "VIRALCLIP_GAMES/VIRALCLIP_GAME_IDS.",
                file=sys.stderr,
            )
            return 2

        twitch = TwitchClient(settings.client_id or "", settings.client_secret or "")
        try:
            collector = Collector(
                database, twitch, lookback_minutes=settings.discovery_lookback_minutes
            )
            if args.once:
                collector.collect_cycle(games, game_ids)
                print("Collection cycle completed.")
                return 0
            print("Continuous collection started. Press Ctrl+C to stop.")
            next_discovery = 0.0
            while True:
                try:
                    if time.monotonic() >= next_discovery:
                        next_discovery = time.monotonic() + settings.discovery_interval_seconds
                        collector.collect_cycle(games, game_ids)
                    else:
                        collector.collect_due_snapshots()
                except TwitchAPIError as exc:
                    database.record_error(utc_now(), str(exc))
                    print(f"Collection cycle failed: {exc}", file=sys.stderr)
                time.sleep(min(5, settings.discovery_interval_seconds))
        except KeyboardInterrupt:
            print("\nCollection stopped.")
            return 0
        finally:
            twitch.close()
    except (TwitchAPIError, ValueError) as exc:
        if isinstance(exc, TwitchAPIError):
            database.record_error(utc_now(), str(exc))
        print(f"Collection failed: {exc}", file=sys.stderr)
        return 1
    finally:
        database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
