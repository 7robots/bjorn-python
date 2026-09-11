"""Phase 16: the reader highlights the query's terms and ] [ jump between them."""

from __future__ import annotations

from helpers import loaded, titles, wait_until

from bjorn.search import MATCH_STYLE


async def search(app, pilot, query: str) -> None:
    await pilot.press("slash")
    await pilot.pause()
    for ch in query:
        await pilot.press("space" if ch == " " else ch)
    await pilot.press("enter")


def highlighted_blocks(app):
    return [b for b in app.note_view.matches if any(str(s.style) == MATCH_STYLE for s in b._content.spans)]


def header(app) -> str:
    return str(app.note_view.query_one("#note-header").render())


async def test_body_match_is_highlighted_in_the_reader(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await search(app, pilot, "bulbs")
        await wait_until(lambda: titles(app) == ["Garden Plan"])
        await wait_until(lambda: app.note_view.note is not None and app.note_view.note.id == "NOTE-GARDEN")
        await wait_until(lambda: len(app.note_view.matches) == 1)
        block = app.note_view.matches[0]
        assert "order bulbs" in block._content.plain
        assert highlighted_blocks(app) == [block]
        assert "1 match" in header(app)


async def test_brackets_jump_between_matching_blocks(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await search(app, pilot, "the")
        await wait_until(lambda: "Garden Plan" in titles(app))
        await app.note_list.select_id("NOTE-GARDEN")
        await wait_until(lambda: len(app.note_view.matches) == 3)
        plains = [b._content.plain for b in app.note_view.matches]
        assert "code block" not in " ".join(plains)  # fences are skipped
        assert "3 matches" in header(app)
        await pilot.press("right_square_bracket")
        await wait_until(lambda: app.note_view.match_index == 0)
        assert app.focused is app.note_view.scroll_view
        assert "match 1/3" in header(app)
        await pilot.press("right_square_bracket")
        await wait_until(lambda: app.note_view.match_index == 1)
        assert "match 2/3" in header(app)
        await pilot.press("left_square_bracket")
        await wait_until(lambda: app.note_view.match_index == 0)
        await pilot.press("left_square_bracket")
        await wait_until(lambda: app.note_view.match_index == 2)  # wraps


async def test_enter_from_the_list_lands_on_the_first_match(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await search(app, pilot, "roses")
        await wait_until(lambda: titles(app) == ["Garden Plan"])
        await wait_until(lambda: len(app.note_view.matches) == 1)
        assert app.focused is app.note_list.list_view
        await pilot.press("enter")
        await wait_until(lambda: app.note_view.match_index == 0)
        assert app.focused is app.note_view.scroll_view
        assert "match 1/1" in header(app)


async def test_escape_clears_the_highlights(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await search(app, pilot, "bulbs")
        await wait_until(lambda: len(app.note_view.matches) == 1)
        block = app.note_view.matches[0]
        await pilot.press("escape")
        await wait_until(lambda: app.note_view.pattern is None)
        assert app.note_view.matches == []
        assert not any(str(s.style) == MATCH_STYLE for s in block._content.spans)
        assert "match" not in header(app)


async def test_jump_completes_a_truncated_note_first(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await search(app, pilot, "119")
        await wait_until(lambda: titles(app) == ["Reading Queue"])
        await wait_until(lambda: app.note_view.note is not None and app.note_view.note.id == "NOTE-READING")
        assert app.note_view.truncated
        assert app.note_view.matches == []  # the match is past the rendered head
        await pilot.press("right_square_bracket")
        await wait_until(lambda: not app.note_view.truncated and app.note_view.match_index == 0)
        assert "Book 119" in app.note_view.matches[0]._content.plain
        assert app.note_view.scroll_view.scroll_y > 0


# -- Phase 17: list rows --------------------------------------------------------------


def row(app, note_id):
    from bjorn.widgets.note_list import NoteItem

    return next(i for i in app.note_list.list_view.query(NoteItem) if i.note.id == note_id)


def row_highlights(item) -> list[str]:
    text = item.render()
    return [text.plain[s.start:s.end] for s in text.spans if str(s.style) == MATCH_STYLE]


async def test_row_highlights_a_term_in_the_preview(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await search(app, pilot, "bulbs")
        await wait_until(lambda: titles(app) == ["Garden Plan"])
        await pilot.pause()
        assert row_highlights(row(app, "NOTE-GARDEN")) == ["bulbs"]


async def test_row_highlights_a_term_in_the_title_case_insensitively(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await search(app, pilot, "garden")
        await wait_until(lambda: "Garden Plan" in titles(app))
        await pilot.pause()
        assert "Garden" in row_highlights(row(app, "NOTE-GARDEN"))


async def test_row_with_a_body_only_match_shows_no_highlight(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await search(app, pilot, "119")
        await wait_until(lambda: titles(app) == ["Reading Queue"])
        await pilot.pause()
        assert row_highlights(row(app, "NOTE-READING")) == []


async def test_rows_are_plain_after_escape(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await search(app, pilot, "bulbs")
        await wait_until(lambda: titles(app) == ["Garden Plan"])
        await pilot.press("escape")
        await wait_until(lambda: len(titles(app)) == 5)
        await pilot.pause()
        assert app.note_list._pattern is None
        assert row_highlights(row(app, "NOTE-GARDEN")) == []
