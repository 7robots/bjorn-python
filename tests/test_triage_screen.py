"""Phase 7: the triage screen against the fake bearcli."""

from __future__ import annotations

import json

from bjorn.widgets.triage import TriageScreen
from helpers import loaded, titles, wait_until


async def open_triage(app, pilot):
    await pilot.press("t")
    await wait_until(lambda: isinstance(app.screen, TriageScreen) and app.screen.state.rows)
    await pilot.pause()
    return app.screen


def texts(screen):
    return [r.todo.text for r in screen.state.rows]


async def test_t_lists_open_todos_grouped_and_scoped(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        screen = await open_triage(app, pilot)
        assert texts(screen) == [
            "write the release notes", "ask Priya about the API deprecation", "confirm the sunset date",
            "order bulbs for the front bed", "move the hydrangea",
        ]
        assert screen.state.notes == 2
        status = str(screen.query_one("#triage-status").render())
        assert status.startswith("5 open · 2 notes")
        assert "TRIAGE · all notes" in str(screen.query_one("#triage-header").render())
        assert screen.current_row().todo.text == "write the release notes"
        # main-screen keys are disabled while triage is up: e must not open an editor
        await pilot.press("e")
        await pilot.pause()
        assert isinstance(app.screen, TriageScreen)
        footer_keys = {b.key for (_, b, enabled, _) in app.screen.active_bindings.values() if enabled}
        assert "x" in footer_keys and "n" not in footer_keys and "d" not in footer_keys
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, TriageScreen)


async def test_workspace_scopes_the_triage(make_app):
    app = make_app(workspace="home")
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        screen = await open_triage(app, pilot)
        assert texts(screen) == ["order bulbs for the front bed", "move the hydrangea"]
        assert "#home" in str(screen.query_one("#triage-header").render())


async def test_cursor_mark_and_filter(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        screen = await open_triage(app, pilot)
        await pilot.press("j")
        await pilot.pause()
        assert screen.current_row().todo.text == "ask Priya about the API deprecation"
        await pilot.press("space")
        await pilot.press("j")
        await pilot.press("space")
        await pilot.pause()
        assert [r.todo.text for r in screen.state.marked] == ["ask Priya about the API deprecation", "confirm the sunset date"]
        assert "2 marked" in str(screen.query_one("#triage-status").render())
        await pilot.press("slash")
        for ch in "hydra":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause()
        assert [i.row.todo.text for i in screen._items] == ["move the hydrangea"]
        await pilot.press("escape")  # clears the filter first
        await pilot.pause()
        assert len(screen._items) == 5
        assert isinstance(app.screen, TriageScreen)
        assert len(screen.state.marked) == 2  # marks survive a rebuild


async def test_x_ticks_in_bear_and_reloads_counts(make_app, client):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        planning = next(n for n in app.snapshot.notes if n.id == "NOTE-PLANNING")
        assert planning.todos == 3
        screen = await open_triage(app, pilot)
        await pilot.press("x")  # highlighted row only, no confirm
        await wait_until(lambda: "write the release notes" not in texts(screen))
        content = (await client.cat("NOTE-PLANNING")).content
        assert "- [x] write the release notes" in content
        await wait_until(lambda: app.snapshot.by_id("NOTE-PLANNING").todos == 2)
        # two marked rows ask first; escape declines
        await pilot.press("space")
        await pilot.press("j")
        await pilot.press("space")
        await pilot.pause()
        await pilot.press("x")
        await pilot.pause()
        assert type(app.screen).__name__ == "ConfirmScreen"
        await pilot.press("escape")
        await pilot.pause()
        assert len(texts(screen)) == 4
        await pilot.press("x")
        await pilot.pause()
        await pilot.press("y")
        await wait_until(lambda: len(texts(screen)) == 2)
        content = (await client.cat("NOTE-PLANNING")).content
        assert "- [x] ask Priya" in content and "  - [x] confirm the sunset date" in content


async def test_stale_line_is_reported_not_fatal(make_app, client):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        screen = await open_triage(app, pilot)
        # change the line behind the screen's back
        await client.edit("NOTE-PLANNING", "- [ ] write the release notes", "- [ ] write the release notes tomorrow")
        await pilot.press("x")
        await wait_until(lambda: "write the release notes tomorrow" in texts(screen))
        assert app.is_running
        content = (await client.cat("NOTE-PLANNING")).content
        assert "- [ ] write the release notes tomorrow" in content  # nothing was ticked


async def test_enter_goes_to_the_note_and_b_opens_bear_at_the_section(make_app, fake_state):
    app = make_app(workspace="home")
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        screen = await open_triage(app, pilot)
        await pilot.press("j")
        await pilot.pause()
        assert screen.current_row().todo.text == "move the hydrangea"
        await pilot.press("b")
        log = fake_state.parent / "bear.json.opened"
        await wait_until(lambda: log.exists())
        assert json.loads(log.read_text().splitlines()[-1]) == {"id": "NOTE-GARDEN", "header": "Next spring"}
        await pilot.press("enter")
        await wait_until(lambda: not isinstance(app.screen, TriageScreen))
        await wait_until(lambda: app.note_view.note is not None and app.note_view.note.id == "NOTE-GARDEN")
        assert app.focused is app.note_list.list_view


async def test_goto_a_note_outside_the_current_list(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await pilot.press("2")  # Untagged view: neither todo note is listed
        await wait_until(lambda: titles(app) == ["Loose Thought"])
        screen = await open_triage(app, pilot)
        await pilot.press("enter")
        await wait_until(lambda: not isinstance(app.screen, TriageScreen))
        await wait_until(lambda: app.note_list.current() is not None and app.note_list.current().id == "NOTE-PLANNING")
        assert app.selection.view.value == "all"
