"""Screen bases that survive a click landing on a widget the DOM has let go of."""

from __future__ import annotations

from textual.geometry import Offset
from textual.screen import Screen
from textual.widget import Widget


class SafeSelectMixin:
    """Guard Textual's click-to-select against a stale compositor.

    On mouse down Textual starts a text selection from the widget under the
    pointer and uses that widget's *parent* as the selection container. The
    compositor's map can lag the DOM by a frame: `Markdown.update()` detaches
    every block before mounting the new ones, so a click arriving in that window
    finds a widget whose `parent` is already `None` and Textual raises
    `AttributeError: 'NoneType' object has no attribute 'region'`
    (textual 8.2.8, `Screen._forward_event`). Reporting "no widget here" costs
    at most one missed selection drag and keeps the app up.
    """

    def get_widget_and_offset_at(self, x: int, y: int) -> tuple[Widget | None, Offset | None]:
        widget, offset = super().get_widget_and_offset_at(x, y)
        if widget is not None and widget is not self and widget.parent is None:
            return None, None
        return widget, offset


class BjornScreen(SafeSelectMixin, Screen[None]):
    """The app's default screen."""
