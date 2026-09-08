"""Phase 2: a tag subtree as the whole app's scope."""

from __future__ import annotations

from helpers import loaded, titles, wait_until


async def test_w_scopes_and_W_clears(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        app.sidebar.tree.focus()
        await pilot.pause()
        await pilot.press("down")
        await wait_until(lambda: app.selection.tag == "home")
        await pilot.press("w")
        await wait_until(lambda: app.selection.workspace == "home")
        assert titles(app) == ["Garden Plan", "Reading Queue"]
        assert str(app.sidebar.query_one("#sidebar-header").render()) == "WORKSPACE #home"
        roots = [str(n.data) for n in app.sidebar.tree.root.children]
        assert roots == ["home"]
        counts = {item.view.value: item.count for item in app.sidebar.views.query("ViewItem")}
        assert counts["all"] == 2 and counts["untagged"] == 0 and counts["todo"] == 1
        await pilot.press("3")
        await wait_until(lambda: titles(app) == ["Garden Plan"])
        await pilot.press("W")
        await wait_until(lambda: app.selection.workspace == "")
        assert len(titles(app)) == 5
        assert str(app.sidebar.query_one("#sidebar-header").render()) == "BJORN"


async def test_workspace_from_cli_flag_and_default_tags(make_app):
    app = make_app(workspace="#work")
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        assert app.selection.workspace == "work"
        assert titles(app) == ["Sprint Planning", "CAD and Design"]
        await pilot.press("n")
        await pilot.pause()
        assert type(app.screen).__name__ == "NewNotePrompt"
        assert app.screen.query_one("#tags").value == "work"
        await pilot.press("escape")


async def test_workspace_from_config(client, config):
    from bjorn.app import BjornApp

    config.workspace = "home"
    app = BjornApp(config, client=client, environ={})
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        assert app.selection.workspace == "home"
        assert titles(app) == ["Garden Plan", "Reading Queue"]


async def test_w_without_a_tag_explains_itself(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await pilot.press("w")
        await pilot.pause()
        assert app.selection.workspace == ""
