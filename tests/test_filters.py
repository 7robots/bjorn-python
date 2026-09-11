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
        assert app.sidebar.highlighted_view() is View.ALL


async def test_sidebar_cursor_selects_views_and_tags(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        app.sidebar.tree.focus()
        await pilot.press("j")
        await wait_until(lambda: titles(app) == ["Loose Thought"])
        assert str(app.note_list.query_one("#notes-header").render()) == "Untagged · 1"
        # Down through the remaining views and over the gap lands on the first tag.
        for _ in range(6):
            await pilot.press("down")
        await wait_until(lambda: app.selection.tag == "home")
        assert app.sidebar.highlighted_tag() == "home"
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


async def test_reload_leaves_an_unchanged_note_on_the_page(make_app):
    """A poll that changes nothing the reader shows must not blank and redraw it."""
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        # The first note is stamped this very second, which the caches rightly
        # distrust; step onto an older one.
        await pilot.press("j")
        await wait_until(lambda: app.note_view.note is not None and app.note_view.note.title == "Garden Plan")
        shown = app.note_view.note
        calls = {"show": 0, "clear": 0}
        real_show, real_clear = app.note_view.show, app.note_view.clear

        async def counting_show(*args, **kwargs):
            calls["show"] += 1
            return await real_show(*args, **kwargs)

        async def counting_clear(*args, **kwargs):
            calls["clear"] += 1
            return await real_clear(*args, **kwargs)

        app.note_view.show = counting_show  # type: ignore[method-assign]
        app.note_view.clear = counting_clear  # type: ignore[method-assign]
        await app.reload()
        await pilot.pause()
        await pilot.pause(0.3)
        assert app.note_view.note == shown
        assert calls == {"show": 0, "clear": 0}


async def test_sidebar_is_one_column_arrows_cross_the_gap_and_tab_reaches_the_notes(make_app):
    """The seven views and the tags share one tree: `down` from Trash lands on
    the first tag, `up` from it returns to Trash, and `tab` from a view goes to
    the notes list without touching the selection."""
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        tree = app.sidebar.tree
        tree.focus()
        await pilot.pause()
        app.sidebar.select_view(View.TRASH)
        await pilot.pause()
        await pilot.press("down")
        await wait_until(lambda: app.sidebar.highlighted_tag() == "home")
        assert app.selection.tag == "home"
        await pilot.press("up")
        await wait_until(lambda: app.sidebar.highlighted_view() is View.TRASH)
        assert app.selection.view is View.TRASH and not app.selection.tag
        # The gap: two blank rows and the TAGS heading, none of them a stop.
        gap = app.sidebar.tag_roots()[0].line - app.sidebar.view_node(View.TRASH).line - 1
        assert gap == 3
        await pilot.press("3")
        await wait_until(lambda: app.selection.view is View.TODO)
        await pilot.press("tab")
        await pilot.pause()
        assert app.focused is app.note_list.list_view
        assert app.selection.view is View.TODO and titles(app) == ["Sprint Planning", "Garden Plan"]
