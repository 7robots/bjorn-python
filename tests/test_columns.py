"""`c` and the header glyph cycle the columns: 3 -> 2 (no tags) -> 1 (note only) -> 3."""

from __future__ import annotations

from bjorn.widgets.note_view import COLUMN_GLYPHS, ColumnsToggle

from helpers import loaded, wait_until


def shown(app) -> tuple[bool, bool, bool]:
    return (app.sidebar.display, app.note_list.display, app.note_view.display)


def glyph(app) -> str:
    return str(app.query_one(ColumnsToggle).render())


async def test_c_cycles_three_two_one_and_back(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        assert shown(app) == (True, True, True) and glyph(app) == COLUMN_GLYPHS[3]
        await pilot.press("c")
        assert app.columns == 2 and shown(app) == (False, True, True) and glyph(app) == COLUMN_GLYPHS[2]
        await pilot.press("c")
        assert app.columns == 1 and shown(app) == (False, False, True) and glyph(app) == COLUMN_GLYPHS[1]
        await pilot.press("c")
        assert app.columns == 3 and shown(app) == (True, True, True) and glyph(app) == COLUMN_GLYPHS[3]


async def test_hiding_the_focused_pane_moves_focus_and_keeps_keys_working(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        app.sidebar.tree.focus()
        await pilot.pause()
        await pilot.press("c")
        assert app.focused is app.note_list.list_view
        await pilot.press("j")
        await wait_until(lambda: app.note_view.note is not None and app.note_view.note.id == "NOTE-GARDEN")
        await pilot.press("c")
        assert app.focused is app.note_view.scroll_view
        # tab never lands on a hidden pane
        for _ in range(4):
            await pilot.press("tab")
            assert app.focused is not None and app.focused.display
            assert app.focused not in (app.sidebar.tree, app.note_list.list_view)
        await pilot.press("c")
        assert app.focused is app.note_view.scroll_view  # nothing was hidden under it, so nothing moves


async def test_clicking_the_glyph_cycles_too(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await pilot.click(ColumnsToggle)
        await pilot.pause()
        assert app.columns == 2 and not app.sidebar.display
        await pilot.click(ColumnsToggle)
        await pilot.pause()
        assert app.columns == 1 and not app.note_list.display
        await pilot.click(ColumnsToggle)
        await pilot.pause()
        assert app.columns == 3 and shown(app) == (True, True, True)
