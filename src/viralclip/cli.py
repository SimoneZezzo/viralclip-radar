from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

from viralclip.collector.service import Collector
from viralclip.config import load_settings
from viralclip.dataset import CUTOFFS, Selection, extract
from viralclip.evaluation import run_evaluation
from viralclip.storage.database import Database, parse_utc, utc_now
from viralclip.storage.health import LEVELS, read_health
from viralclip.twitch.client import TwitchAPIError, TwitchClient
from viralclip.twitch.telemetry import HttpEventLog


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
    commands.add_parser("health", help="inspect collector health using read-only SQLite access")
    dataset = commands.add_parser("dataset", help="extract point-in-time features and 24h labels")
    dataset.add_argument("--start", required=True, help="inclusive UTC clip creation timestamp")
    dataset.add_argument("--end", required=True, help="exclusive UTC clip creation timestamp")
    dataset.add_argument("--game-id", action="append", help="filter by game ID; may be repeated")
    dataset.add_argument("--watermark", help="UTC source watermark; defaults to latest observation")
    dataset.add_argument(
        "--outage",
        action="append",
        nargs=2,
        metavar=("START", "END"),
        help="known outage interval in UTC; may be repeated",
    )
    dataset.add_argument(
        "--output", required=True, type=Path, help="new Git-ignored output directory"
    )
    evaluation = commands.add_parser("evaluate", help="evaluate chronological ranking baselines")
    evaluation.add_argument("datasets", nargs="+", type=Path, help="dataset artifact directories")
    evaluation.add_argument("--validation-start", help="validation start at UTC midnight")
    evaluation.add_argument("--test-start", help="test start at UTC midnight")
    evaluation.add_argument("--k", type=int, default=10, help="maximum size of the top ranks")
    evaluation.add_argument(
        "--output", required=True, type=Path, help="new Git-ignored report directory"
    )
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
    if args.command == "evaluate":
        try:
            report = run_evaluation(
                args.datasets,
                args.output,
                parse_utc(args.validation_start) if args.validation_start is not None else None,
                parse_utc(args.test_start) if args.test_start is not None else None,
                args.k,
            )
        except (KeyError, TypeError, ValueError, OSError) as exc:
            print(f"Evaluation failed: {exc}", file=sys.stderr)
            return 1
        print(report["status"])
        for reason in report["reasons"]:
            print(reason)
        return 0
    try:
        settings = load_settings()
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    if args.db:
        settings = settings.__class__(
            **{**settings.__dict__, "db_path": settings.db_path.__class__(args.db).expanduser()}
        )
    if args.command == "health":
        severity, lines = read_health(settings.db_path, settings.discovery_interval_seconds)
        print(f"Collector health: {LEVELS[severity]}")
        print("\n".join(lines))
        return severity
    if args.command == "dataset":
        try:
            selection = Selection(
                parse_utc(args.start),
                parse_utc(args.end),
                tuple(args.game_id or ()),
                parse_utc(args.watermark) if args.watermark is not None else None,
                tuple((parse_utc(start), parse_utc(end)) for start, end in args.outage or ()),
            )
            coverage = extract(settings.db_path, selection, args.output)
        except (OSError, ValueError, sqlite3.Error) as exc:
            print(f"Dataset extraction failed: {exc}", file=sys.stderr)
            return 1
        for cutoff in CUTOFFS:
            counts = coverage["by_cutoff_minutes"][cutoff]
            print(
                f"{cutoff}m: {counts['candidates']} candidates, "
                f"{counts['eligible']} eligible, {counts['labeled']} labeled"
            )
        return 0
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

        http_log = HttpEventLog(settings.db_path, settings.http_log_directory)
        twitch = TwitchClient(
            settings.client_id or "", settings.client_secret or "", events=http_log
        )
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
            try:
                twitch.close()
            finally:
                http_log.close()
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
