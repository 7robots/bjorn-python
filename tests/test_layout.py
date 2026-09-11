"""Phase 1: three panes browse the fake notes read-only."""

from __future__ import annotations

from rich.cells import cell_len

from bjorn.render import OPEN_BOX
from bjorn.widgets.note_list import NoteList
from bjorn.widgets.note_view import NoteView
from bjorn.widgets.sidebar import Sidebar

from helpers import loaded, titles, wait_until


async def test_three_columns_load_and_render_first_note(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        assert app.query_one(Sidebar) and app.query_one(NoteList) and app.query_one(NoteView)
        assert titles(app) == ["Sprint Planning", "Garden Plan", "Reading Queue", "CAD and Design", "Loose Thought"]
        await wait_until(lambda: app.note_view.note is not None and app.note_view.note.id == "NOTE-PLANNING")
        assert str(app.note_view.query_one("#note-header").render()) == "Sprint Planning"
        await pilot.pause(0.2)
        assert OPEN_BOX in app.note_view.markdown.source
        assert "**holding**" in app.note_view.markdown.source
        assert "`#work/sprint`" in app.note_view.markdown.source


async def test_moving_the_cursor_changes_the_note(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        app.note_list.list_view.focus()
        await pilot.press("j")
        await wait_until(lambda: app.note_view.note is not None and app.note_view.note.id == "NOTE-GARDEN")
        await pilot.press("k")
        await wait_until(lambda: app.note_view.note is not None and app.note_view.note.id == "NOTE-PLANNING")


async def test_long_note_is_truncated_until_focused(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        app.note_list.list_view.focus()
        await app.note_list.select_id("NOTE-READING")
        await wait_until(lambda: app.note_view.note is not None and app.note_view.note.id == "NOTE-READING")
        assert app.note_view.truncated
        assert "lines" in str(app.note_view.query_one("#note-header").render())
        await pilot.press("enter")
        await wait_until(lambda: not app.note_view.truncated)
        assert app.focused is app.note_view.scroll_view
        assert "Book 120" in app.note_view.markdown.source


async def test_sidebar_counts_match_the_snapshot(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        counts = {item.view.value: item.count for item in app.sidebar.views.query("ViewItem")}
        assert counts == {"all": 5, "untagged": 1, "todo": 2, "today": 1, "pinned": 2, "archive": 1, "trash": 1}
        tags = [str(node.data) for node in app.sidebar.tree.root.children]
        assert tags == ["home", "work"]


async def test_help_screen_opens_and_closes(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await pilot.press("question_mark")
        await pilot.pause()
        assert type(app.screen).__name__ == "HelpScreen"
        await pilot.press("escape")
        await pilot.pause()
        assert type(app.screen).__name__ == "BjornScreen"


async def test_mouse_click_selects_without_stealing_focus(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        items = list(app.note_list.list_view.query("NoteItem"))
        await pilot.click(items[2])
        await wait_until(lambda: app.note_view.note is not None and app.note_view.note.id == items[2].note.id)
        assert app.focused is app.note_list.list_view
        await pilot.press("enter")
        await pilot.pause()
        assert app.focused is app.note_view.scroll_view
        tree = app.sidebar.tree
        home = tree.root.children[0]
        assert not home.is_expanded, "tags start folded"
        await pilot.click(tree, offset=(4, 0))
        await wait_until(lambda: app.selection.tag == "home")
        assert not home.is_expanded, "clicking a tag must select it, not toggle it"
        assert app.focused is tree
        await pilot.click("#view-untagged")
        await wait_until(lambda: titles(app) == ["Loose Thought"])
        assert app.focused is app.sidebar.views


async def test_note_rows_show_a_preview_and_no_tags(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await pilot.pause()
        first = app.note_list.list_view.query("NoteItem").first()
        assert first.note.preview
        rendered = first.preview_text()
        assert first.note.preview.split()[0] in rendered
        assert "#" not in rendered
        assert rendered.count("\n") <= 1
        whole = first.render().plain
        assert whole.startswith(first.note.title) or first.note.title in whole.split("\n")[0]
        assert whole.count("\n") <= 2


async def test_tag_counts_sit_flush_right_at_every_depth(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        tree = app.sidebar.tree
        await pilot.press("F")  # unfold every tag so nested rows render too
        await pilot.pause()
        width = tree.size.width
        rows = 0
        for line in range(len(tree._tree_lines)):
            strip = tree._render_line(line, 0, width, tree.rich_style)
            text = strip.text.rstrip()
            if not text:
                continue
            rows += 1
            assert cell_len(text) == width, text  # the count is the last cell of the row
            assert text.split()[-1].isdigit(), text
        assert rows >= 3 and any(len(l.path) > 1 for l in tree._tree_lines)  # at least one nested tag (paths omit the hidden root)
