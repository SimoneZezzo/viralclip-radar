# Questo è il punto d'ingresso da terminale. La CLI (interfaccia a riga di comando) legge parole
# come `collect --once`, sceglie l'operazione e stampa il risultato.

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

from viralclip.benchmark import VERSION as BENCHMARK_PROTOCOL
from viralclip.benchmark import run_benchmark
from viralclip.collector.service import Collector
from viralclip.config import load_settings
from viralclip.dataset import CUTOFFS, Selection, extract
from viralclip.evaluation import run_evaluation
from viralclip.observed_evaluation import MODE as OBSERVED_COHORT
from viralclip.observed_evaluation import run_observed_evaluation
from viralclip.predictions import ignored_registry, link_outcomes, rank_pool, shortlist
from viralclip.storage.database import Database, parse_utc, utc_now
from viralclip.storage.health import LEVELS, read_health
from viralclip.synthetic import dry_run, summary_lines
from viralclip.twitch.client import TwitchAPIError, TwitchClient
from viralclip.twitch.telemetry import HttpEventLog


# Qui prepariamo le regole con cui argparse leggerà il comando.
# I comandi sono: `init-db`, `collect`, `status`, `health`, `dataset` e `evaluate`. Le opzioni iniziano con due trattini.
def _parser() -> argparse.ArgumentParser:  # Command-line argument parser for the viralclip CLI
    # Il parser è l'oggetto che controlla il comando inserito.
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
    demo = commands.add_parser("demo", help="serve the synthetic portfolio demo on this computer")
    demo.add_argument("--port", type=int, default=8765, help="local HTTP port (default: 8765)")
    demo.add_argument(
        "--registry",
        type=Path,
        default=Path("data/demo/registry-v3.sqlite3"),
        help="synthetic ranking registry path (default: data/demo/registry-v3.sqlite3)",
    )
    # L'estrazione sceglie le clip create dall'inizio incluso alla fine esclusa, in UTC.
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
    # Definisce il comando per valutare le prestazioni dei modelli di ranking cronologico. Richiede i percorsi dei dataset e un percorso di output per il report.
    evaluation = commands.add_parser("evaluate", help="evaluate chronological ranking baselines")
    evaluation.add_argument("datasets", nargs="+", type=Path, help="dataset artifact directories")
    evaluation.add_argument(
        "--cohort",
        choices=("primary", OBSERVED_COHORT),
        help="evaluation cohort (default: primary, or observed-at-cutoff for benchmark-v1)",
    )
    evaluation.add_argument("--validation-start", help="validation start at UTC midnight")
    evaluation.add_argument("--test-start", help="test start at UTC midnight")
    evaluation.add_argument(
        "--protocol", choices=(BENCHMARK_PROTOCOL,), help="select the versioned benchmark"
    )
    evaluation.add_argument("--game-id", help="exact category ID for benchmark-v1")
    evaluation.add_argument("--k", type=int, default=10, help="maximum size of the top ranks")
    evaluation.add_argument(
        "--output", required=True, type=Path, help="new Git-ignored report directory"
    )
    rank = commands.add_parser("rank", help="record a baseline ranking for one pool at its cutoff")
    rank.add_argument("--registry", required=True, type=Path, help="Git-ignored registry path")
    rank.add_argument("--game-id", required=True, help="exact Twitch category ID")
    rank.add_argument("--day", required=True, help="UTC creation day, YYYY-MM-DD")
    rank.add_argument("--cutoff", required=True, type=int, choices=CUTOFFS, help="minutes")
    rank.add_argument("--watermark", help="UTC source watermark; defaults to latest observation")
    link = commands.add_parser("link-outcomes", help="attach settled 24h outcomes to predictions")
    link.add_argument("--registry", required=True, type=Path, help="Git-ignored registry path")
    link.add_argument("--watermark", help="UTC source watermark; defaults to latest observation")
    top = commands.add_parser("shortlist", help="print the latest top-K ranking for one pool")
    top.add_argument("--registry", required=True, type=Path, help="prediction registry path")
    top.add_argument("--game-id", required=True, help="exact Twitch category ID")
    top.add_argument("--day", required=True, help="UTC creation day, YYYY-MM-DD")
    top.add_argument("--cutoff", required=True, type=int, choices=CUTOFFS, help="minutes")
    top.add_argument("--k", type=int, default=10, help="number of ranks (default: 10)")
    synthetic = commands.add_parser(
        "synthetic-dry-run", help="run the offline pipeline end to end on synthetic data"
    )
    synthetic.add_argument(
        "--output", required=True, type=Path, help="new Git-ignored output directory"
    )
    synthetic.add_argument("--clips-per-day", type=int, default=240, help="default: 240")
    synthetic.add_argument("--seed", type=int, default=20261124, help="default: 20261124")
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


# La funzione principale legge le parole del comando, esegue l'operazione e restituisce un numero intero come codice di uscita.
def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(
        argv
    )  # Legge le parole del comando e le converte in un oggetto con attributi.

    if args.command == "demo":
        try:
            # Imported here: FastAPI is a development dependency, absent from collector installs.
            from viralclip.demo import run_demo
        except ImportError as exc:
            print(
                f"Demo unavailable: {exc}. Run uv sync to install the dev group.", file=sys.stderr
            )
            return 1
        try:
            run_demo(args.port, args.registry)
        except (ValueError, OSError, sqlite3.Error) as exc:
            print(f"Demo failed: {exc}", file=sys.stderr)
            return 1
        return 0

    if args.command == "evaluate":
        try:
            validation_start = (
                parse_utc(args.validation_start) if args.validation_start is not None else None
            )
            test_start = parse_utc(args.test_start) if args.test_start is not None else None
            if args.protocol == BENCHMARK_PROTOCOL:
                if not args.game_id:
                    raise ValueError("Benchmark v1 requires --game-id")
                if args.k != 10:
                    raise ValueError("Benchmark v1 uses fixed K values of 10 and 50")
                report = run_benchmark(
                    args.datasets,
                    args.output,
                    validation_start,
                    test_start,
                    game_id=args.game_id,
                    cohort=args.cohort or OBSERVED_COHORT,
                )
            else:
                if args.game_id is not None:
                    raise ValueError("--game-id requires --protocol benchmark-v1")
                evaluate_cohort = (
                    run_observed_evaluation if args.cohort == OBSERVED_COHORT else run_evaluation
                )
                report = evaluate_cohort(
                    args.datasets, args.output, validation_start, test_start, args.k
                )
        except (KeyError, TypeError, ValueError, OSError) as exc:
            print(f"Evaluation failed: {exc}", file=sys.stderr)
            return 1
        print(report["status"])
        for reason in report["reasons"]:
            print(reason)
        return 0

    if args.command == "synthetic-dry-run":
        try:
            if args.clips_per_day <= 0:
                raise ValueError("--clips-per-day must be positive")
            summary = dry_run(args.output, clips_per_day=args.clips_per_day, seed=args.seed)
        except (KeyError, TypeError, ValueError, OSError, sqlite3.Error) as exc:
            print(f"Synthetic dry run failed: {exc}", file=sys.stderr)
            return 1
        print("\n".join(summary_lines(summary)))
        return 0

    if args.command == "shortlist":
        try:
            result = shortlist(args.registry, args.game_id, args.day, args.cutoff, args.k)
        except (ValueError, OSError, sqlite3.Error) as exc:
            print(f"Shortlist failed: {exc}", file=sys.stderr)
            return 1
        run = result["run"]
        print(f"{run['run_id']} {run['score_version']} ({run['model_status']})")
        for row in result["predictions"]:
            print(f"{row['rank']:>3} {row['score']:>3} {row['clip_id']}")
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

    if args.command in ("rank", "link-outcomes"):
        try:
            registry = ignored_registry(args.registry)
            watermark = parse_utc(args.watermark) if args.watermark is not None else None
            if args.command == "rank":
                result = rank_pool(
                    settings.db_path,
                    registry,
                    args.game_id,
                    parse_utc(f"{args.day}T00:00:00Z"),
                    args.cutoff,
                    watermark=watermark,
                )
                print(
                    f"{result['run_id']}: {result['scored']}/{result['pool_size']} scored "
                    f"with {result['score_version']} ({result['model_status']})"
                )
            else:
                result = link_outcomes(settings.db_path, registry, watermark=watermark)
                print(f"Linked {result['linked']} outcomes: {result['by_status']}")
        except (OSError, ValueError, sqlite3.Error) as exc:
            print(f"{args.command} failed: {exc}", file=sys.stderr)
            return 1
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
                database,
                twitch,
                lookback_minutes=settings.discovery_lookback_minutes,
                gta_vi_overlap=settings.gta_vi_overlap,
                overlap_events=http_log,
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
