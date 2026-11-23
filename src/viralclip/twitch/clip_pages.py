"""Validate clip cursor progress independently of volatile view-count ordering."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

from viralclip.storage.database import parse_utc
from viralclip.twitch.client import TwitchAPIError, TwitchClient


class ClipPageError(TwitchAPIError):
    """A page cannot support a valid ID comparison."""


def view_order_warnings(
    views: Iterable[int], previous_page_last: int | None
) -> tuple[Counter, int | None]:
    """Count observations, leaving wire order and cursor semantics untouched."""
    warnings = Counter()
    previous = previous_page_last
    for index, value in enumerate(views):
        if previous is not None and value > previous:
            kind = "view_order_between_pages" if index == 0 else "view_order_in_page"
            warnings[kind] += 1
        previous = value
    return warnings, previous


@dataclass(frozen=True)
class ClipPage:
    in_window: tuple[tuple[str, datetime], ...]
    cursor: str | None
    rows: int
    warnings: Counter


@dataclass
class ClipPages:
    game: str
    start: datetime
    end: datetime
    ids: dict[str, datetime] = field(default_factory=dict, init=False)
    cursors: set[str] = field(default_factory=set, init=False)
    last_views: int | None = field(default=None, init=False)

    def accept(self, payload: dict, observed: datetime) -> ClipPage:
        if not isinstance(payload, dict):
            raise ClipPageError("invalid_page_object")
        try:
            rows = TwitchClient.parse_data(payload)
            cursor = TwitchClient.parse_cursor(payload)
        except TwitchAPIError as exc:
            raise ClipPageError("invalid_page_or_cursor") from exc
        if len(rows) > 100 or (cursor is not None and cursor in self.cursors):
            raise ClipPageError("page_size_or_repeated_cursor")
        warnings = Counter()
        in_window = []
        page_views = []
        new_ids: dict[str, datetime] = {}
        for row in rows:
            try:
                clip_id, views = row["id"], row["view_count"]
                created = parse_utc(row["created_at"])
                if (
                    not isinstance(clip_id, str)
                    or not clip_id
                    or type(views) is not int
                    or views < 0
                    or row["game_id"] != self.game
                    or created > observed
                ):
                    raise ValueError
            except (KeyError, TypeError, ValueError, OverflowError) as exc:
                raise ClipPageError("invalid_clip_identity_category_timestamp_or_views") from exc
            page_views.append(views)
            existing = new_ids.get(clip_id, self.ids.get(clip_id))
            if existing is not None:
                if existing != created:
                    raise ClipPageError("conflicting_clip_creation_time")
                warnings["duplicate_ids"] += 1
            else:
                new_ids[clip_id] = created
            if self.start <= created < self.end:
                in_window.append((clip_id, created))
            else:
                warnings["out_of_window"] += 1
        if cursor is not None and not new_ids:
            raise ClipPageError("cursor_without_id_progress")
        if rows and not in_window:
            raise ClipPageError("page_entirely_outside_window")
        self.ids.update(new_ids)
        order, self.last_views = view_order_warnings(page_views, self.last_views)
        warnings.update(order)
        if cursor is not None:
            self.cursors.add(cursor)
        return ClipPage(tuple(in_window), cursor, len(rows), warnings)
