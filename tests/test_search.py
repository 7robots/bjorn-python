"""Phase 2: free-text search through bearcli, scoped by the current selection."""

from __future__ import annotations

from helpers import loaded, titles, wait_until


async def test_slash_search_and_escape(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await pilot.press("slash")
        await pilot.pause()
        assert app.focused is app.note_list.search_input
        for ch in "bulbs":
            await pilot.press(ch)
        await pilot.press("enter")
        await wait_until(lambda: titles(app) == ["Garden Plan"])
        assert str(app.note_list.query_one("#notes-header").render()) == "“bulbs” · 1"
        assert app.focused is app.note_list.list_view
        await pilot.press("escape")
        await wait_until(lambda: len(titles(app)) == 5)
        assert not app.note_list.search_open


async def test_search_respects_workspace_and_view(make_app):
    app = make_app(workspace="work")
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await pilot.press("slash")
        for ch in "@todo":
            await pilot.press(ch)
        await pilot.press("enter")
        await wait_until(lambda: titles(app) == ["Sprint Planning"])
        await pilot.press("7")
        await wait_until(lambda: titles(app) == ["Old Draft"])
        assert app.search_query == ""


async def test_typing_in_search_does_not_trigger_bindings(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await pilot.press("slash")
        for ch in "dnq":
            await pilot.press(ch)
        await pilot.pause()
        assert app.is_running
        assert app.note_list.search_input.value == "dnq"
        assert type(app.screen).__name__ == "BjornScreen"
        await pilot.press("escape")
