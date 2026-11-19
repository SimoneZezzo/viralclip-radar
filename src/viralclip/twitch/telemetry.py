"""Persistent, bounded JSON Lines output for the collector's HTTP events."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path


class _QuietRotatingHandler(RotatingFileHandler):
    def handleError(self, record: logging.LogRecord) -> None:
        # Logging's default error handler prints the record and a traceback.
        pass


class HttpEventLog:
    def __init__(self, db_path: Path, directory: str | None):
        self._db_path = db_path
        self._directory = directory
        self._handler: RotatingFileHandler | None = None

    def __call__(self, event: dict[str, object]) -> None:
        if self._directory == "off":
            return
        if self._handler is None:
            directory = (
                Path(self._directory).expanduser()
                if self._directory is not None
                else self._db_path.parent
            )
            directory.mkdir(parents=True, exist_ok=True)
            self._handler = _QuietRotatingHandler(
                directory / (self._db_path.name + ".http.jsonl"),
                maxBytes=5 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
                delay=True,
            )
        payload = {
            "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds"),
            **event,
        }
        line = json.dumps(payload, separators=(",", ":"), allow_nan=False)
        self._handler.handle(
            logging.LogRecord("viralclip.http", logging.INFO, "", 0, line, (), None)
        )

    def close(self) -> None:
        if self._handler is not None:
            try:
                self._handler.close()
            except Exception:  # noqa: BLE001
                # A flush failure during shutdown must also stay isolated.
                return
