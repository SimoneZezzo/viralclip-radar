from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

GTA_VI_OVERLAP_PAGES = 7


@dataclass(frozen=True)
class GtaViOverlap:
    pages: int = GTA_VI_OVERLAP_PAGES
    extra_seconds: int = 15

    def __post_init__(self) -> None:
        if not GTA_VI_OVERLAP_PAGES <= self.pages <= 10 or not 1 <= self.extra_seconds <= 30:
            raise ValueError("GTA VI overlap needs 7–10 pages and a 1–30 second extra-page budget")


@dataclass(frozen=True)
class Settings:
    client_id: str | None
    client_secret: str | None
    db_path: Path
    discovery_interval_seconds: int
    discovery_lookback_minutes: int
    games: tuple[str, ...]
    game_ids: tuple[str, ...]
    http_log_directory: str | None = None
    gta_vi_overlap: GtaViOverlap = GtaViOverlap()

    @property
    def has_twitch_credentials(self) -> bool:
        return bool(self.client_id and self.client_secret)


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _csv_values(name: str) -> tuple[str, ...]:
    return tuple(value.strip() for value in os.getenv(name, "").split(",") if value.strip())


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        client_id=os.getenv("TWITCH_CLIENT_ID") or None,
        client_secret=os.getenv("TWITCH_CLIENT_SECRET") or None,
        db_path=Path(os.getenv("VIRALCLIP_DB_PATH", "data/viralclip.sqlite3")).expanduser(),
        discovery_interval_seconds=_positive_int("DISCOVERY_INTERVAL_SECONDS", 300),
        discovery_lookback_minutes=_positive_int("DISCOVERY_LOOKBACK_MINUTES", 30),
        games=_csv_values("VIRALCLIP_GAMES"),
        game_ids=_csv_values("VIRALCLIP_GAME_IDS"),
        http_log_directory=os.getenv("VIRALCLIP_HTTP_LOG_DIR") or None,
        gta_vi_overlap=GtaViOverlap(
            _positive_int("VIRALCLIP_GTA_VI_OVERLAP_PAGES", GTA_VI_OVERLAP_PAGES),
            _positive_int("VIRALCLIP_GTA_VI_EXTRA_PAGE_SECONDS", GtaViOverlap().extra_seconds),
        ),
    )
