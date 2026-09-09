"""Phase 2: smart views by hotkey and sidebar cursor."""

from __future__ import annotations

from bjorn.model import View
from helpers import loaded, titles, wait_until


async def test_number_keys_switch_views(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        expectations = {
            "2": ["Loose Thought"],
            "3": ["Sprint Planning", "Garden Plan"],
            "4": ["Sprint Planning"],
            "5": ["Sprint Planning", "Garden Plan"],
            "6": ["Finished Project"],
            "7": ["Old Draft"],
            "1": ["Sprint Planning", "Garden Plan", "Reading Queue", "CAD and Design", "Loose Thought"],
        }
        for key, expected in expectations.items():
            await pilot.press(key)
            await wait_until(lambda: titles(app) == expected)
            assert app.selection.view is View(list(View)[int(key) - 1].value)
        header = str(app.note_list.query_one("#notes-header").render())
        assert header == "Notes · 5"
        assert app.sidebar.views.index == 0


async def test_sidebar_cursor_selects_views_and_tags(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        app.sidebar.views.focus()
        await pilot.press("j")
        await wait_until(lambda: titles(app) == ["Loose Thought"])
        assert str(app.note_list.query_one("#notes-header").render()) == "Untagged · 1"
        app.sidebar.tree.focus()
        await pilot.pause()
        await pilot.press("down")
        await wait_until(lambda: app.selection.tag == "home")
        assert titles(app) == ["Garden Plan", "Reading Queue"]
        await pilot.press("f")  # tags start folded
        await pilot.pause()
        await pilot.press("down")
        await wait_until(lambda: app.selection.tag == "home/garden")
        assert titles(app) == ["Garden Plan"]
        assert str(app.note_list.query_one("#notes-header").render()) == "#home/garden · 1"


async def test_multi_word_tag_selects_its_note(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        app.sidebar.tree.focus()
        await pilot.pause()
        assert app.sidebar.move_to_tag("work/CAD and Design")
        await wait_until(lambda: app.selection.tag == "work/CAD and Design")
        assert titles(app) == ["CAD and Design"]


async def test_refresh_picks_up_external_changes(make_app, client):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await client.create("Made Elsewhere", ["home"])
        await pilot.press("r")
        await wait_until(lambda: "Made Elsewhere" in titles(app))


async def test_poll_reloads_when_the_probe_changes(client, config):
    from bjorn.app import BjornApp

    config.poll_seconds = 1
    app = BjornApp(config, client=client, environ={})
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await client.create("Polled In", ["home"])
        await wait_until(lambda: "Polled In" in titles(app), timeout=6)
