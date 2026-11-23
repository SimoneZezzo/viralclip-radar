from datetime import UTC, datetime, timedelta

import pytest

from viralclip.twitch.clip_pages import ClipPageError, ClipPages

START = datetime(2026, 11, 23, 7, tzinfo=UTC)
END = START + timedelta(minutes=10)
GAME = "1867279146"


def item(clip_id, views, created=START, game=GAME):
    return {
        "id": clip_id,
        "created_at": created.isoformat(),
        "view_count": views,
        "game_id": game,
    }


def page(*clips, cursor=None):
    return {"data": list(clips), "pagination": {"cursor": cursor} if cursor else {}}


def test_inversions_warn_and_keep_wire_order_with_duplicate_ids():
    scan = ClipPages(GAME, START, END)
    first = scan.accept(page(item("a", 8), item("b", 10), cursor="first"), END)
    second = scan.accept(page(item("c", 11), item("a", 7), item("d", 7)), END)
    assert [clip_id for clip_id, _ in first.in_window] == ["a", "b"]
    assert first.cursor == "first"
    assert first.warnings == {"view_order_in_page": 1}
    assert second.warnings == {"view_order_between_pages": 1, "duplicate_ids": 1}
    assert second.cursor is None
    assert set(scan.ids) == {"a", "b", "c", "d"}


@pytest.mark.parametrize("views", ["10", True, -1])
def test_only_nonnegative_integer_view_counts_are_accepted(views):
    scan = ClipPages(GAME, START, END)
    with pytest.raises(ClipPageError, match="invalid_clip_identity_category_timestamp_or_views"):
        scan.accept(page(item("a", views)), END)
    assert not scan.ids


def test_conflicting_identity_and_cursor_without_progress_are_fatal():
    scan = ClipPages(GAME, START, END)
    scan.accept(page(item("a", 7), cursor="first"), END)
    with pytest.raises(ClipPageError, match="conflicting_clip_creation_time"):
        scan.accept(page(item("a", 8, START + timedelta(seconds=1))), END)
    with pytest.raises(ClipPageError, match="cursor_without_id_progress"):
        scan.accept(page(item("a", 8), cursor="other"), END)
    with pytest.raises(ClipPageError, match="page_size_or_repeated_cursor"):
        scan.accept(page(item("b", 8), cursor="first"), END)
    assert scan.ids == {"a": START}


def test_half_open_bounds_and_exact_game_protect_comparison():
    scan = ClipPages(GAME, START, END)
    result = scan.accept(page(item("inside", 5), item("next-window", 4, END)), END)
    assert result.in_window == (("inside", START),)
    assert result.warnings == {"out_of_window": 1}
    with pytest.raises(ClipPageError, match="page_entirely_outside_window"):
        scan.accept(page(item("outside", 5, END)), END)
    with pytest.raises(ClipPageError, match="invalid_clip_identity_category_timestamp_or_views"):
        scan.accept(page(item("wrong", 5, game="32982")), END)
