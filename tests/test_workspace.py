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
        # the empty page counts within the workspace
        await pilot.press("1")
        await wait_until(lambda: str(app.note_view.query_one("#note-empty").render()).rstrip().endswith("2 notes"))
        await pilot.press("2")
        await wait_until(lambda: str(app.note_view.query_one("#note-empty").render()).rstrip().endswith("0 notes"))
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


async def test_w_again_leaves_the_workspace(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        app.sidebar.tree.focus()
        await pilot.pause()
        await pilot.press("down")
        await wait_until(lambda: app.selection.tag == "home")
        await pilot.press("w")
        await wait_until(lambda: app.selection.workspace == "home")
        # the tree now shows only the workspace subtree; its root is highlighted
        assert app.sidebar.highlighted_tag() in ("home", "")
        await pilot.press("w")
        await wait_until(lambda: app.selection.workspace == "")
        assert len(titles(app)) == 5
        # w from the notes list with a workspace set also leaves it
        app.sidebar.tree.focus()
        await pilot.pause()
        app.sidebar.move_to_tag("work")
        await wait_until(lambda: app.selection.tag == "work")
        await pilot.press("w")
        await wait_until(lambda: app.selection.workspace == "work")
        app.note_list.list_view.focus()
        await pilot.press("w")
        await wait_until(lambda: app.selection.workspace == "")


async def test_f_folds_and_unfolds_a_tag(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        tree = app.sidebar.tree
        home = tree.root.children[0]
        assert not home.is_expanded, "tags start folded"
        tree.focus()
        await pilot.pause()
        await pilot.press("down")
        await wait_until(lambda: tree.cursor_node is home)
        await pilot.press("f")
        await pilot.pause()
        assert home.is_expanded
        await pilot.press("f")
        await pilot.pause()
        assert not home.is_expanded
        await pilot.press("f")
        await pilot.pause()
        assert home.is_expanded
        # on a leaf, f folds the parent and moves the cursor to it
        await pilot.press("down")
        await wait_until(lambda: tree.cursor_node is not home)
        await pilot.press("f")
        await pilot.pause()
        assert not home.is_expanded and tree.cursor_node is home


async def test_folds_survive_entering_and_leaving_a_workspace(make_app, client):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        tree = app.sidebar.tree
        tree.focus()
        await pilot.pause()
        for node in tree.root.children:
            node.collapse()
        assert not any(n.is_expanded for n in tree.root.children)
        app.sidebar.move_to_tag("home")
        await wait_until(lambda: app.selection.tag == "home")
        await pilot.press("w")
        await wait_until(lambda: app.selection.workspace == "home")
        await pilot.press("w")
        await wait_until(lambda: app.selection.workspace == "")
        await pilot.pause()
        assert [n.is_expanded for n in tree.root.children] == [False, False]
        # a reload (poll / r) keeps them folded too, and a fold made now is kept
        tree.root.children[1].expand()
        await client.create("Another", ["home/new"])
        await pilot.press("r")
        await wait_until(lambda: any(n.title == "Another" for n in app.snapshot.notes))
        await pilot.pause()
        assert [n.is_expanded for n in tree.root.children] == [False, True]


async def test_F_toggles_every_fold_and_respects_the_workspace(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        tree = app.sidebar.tree
        tree.focus()
        await pilot.pause()
        branches = lambda: [n for n in app.sidebar._all_nodes(tree.root) if n.allow_expand]
        assert not any(n.is_expanded for n in branches()), "tags start folded"
        await pilot.press("F")
        await pilot.pause()
        assert all(n.is_expanded for n in branches())
        await pilot.press("F")
        await pilot.pause()
        assert not any(n.is_expanded for n in branches())
        await pilot.press("F")
        await pilot.pause()
        assert all(n.is_expanded for n in branches())
        # inside a workspace only that subtree exists, so F acts on it alone
        app.sidebar.move_to_tag("work")
        await wait_until(lambda: app.selection.tag == "work")
        await pilot.press("w")
        await wait_until(lambda: app.selection.workspace == "work")
        await pilot.press("F")
        await pilot.pause()
        assert [str(n.data) for n in tree.root.children] == ["work"]
        assert not tree.root.children[0].is_expanded
        await pilot.press("w")
        await wait_until(lambda: app.selection.workspace == "")
        await pilot.pause()
        states = {str(n.data): n.is_expanded for n in tree.root.children}
        assert states == {"home": True, "work": False}


async def test_w_without_a_tag_explains_itself(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await pilot.press("w")
        await pilot.pause()
        assert app.selection.workspace == ""
