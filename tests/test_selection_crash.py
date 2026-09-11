"""A click must not crash when the compositor is a frame behind the DOM.

`Markdown.update()` detaches every block before mounting the new ones, so a
mouse down arriving in that window used to reach Textual's click-to-select with
a widget whose parent is already gone — `AttributeError: 'NoneType' object has
no attribute 'region'`. See `bjorn.screen.SafeSelectMixin`.
"""

from __future__ import annotations

from textual.events import MouseDown
from textual.widgets._markdown import MarkdownBlock

from helpers import loaded, wait_until


async def test_mouse_down_on_a_detached_markdown_block_does_not_crash(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await wait_until(lambda: bool(app.note_view.markdown.query(MarkdownBlock)))
        block = app.note_view.markdown.query(MarkdownBlock).first()
        region = block.region
        parent = block.parent
        x, y = region.x + 1, region.y
        block._detach()
        try:
            app.screen._forward_event(
                MouseDown(None, x=x, y=y, delta_x=0, delta_y=0, button=1, shift=False, meta=False, ctrl=False)
            )
        finally:
            block._attach(parent)
        await pilot.pause()
        assert app.screen._select_state is None
