"""Right column: the rendered note."""

from __future__ import annotations

from textual.app import ComposeResult
from textual import events
from textual.content import Content
from pathlib import Path

from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Markdown, Static

from ..bear import Note
from ..render import head_of, preprocess

#: The empty page: a two-colour bear under a few stars, as Bear shows before a
#: note is chosen. Every line is the same width so centring keeps the shape.
EMPTY_ART_LINES = [
    " ✦          ·               ✦ ",
    "        .--.      .--.        ",
    "   ·   (    `----'    )    ✦  ",
    "       /  o        o  \\       ",
    " ✦     \\     (__)     /   ·   ",
    "        `-.________.-'        ",
    "    ·          ✦           ·  ",
]
STAR_CHARS = "✦·"


def count_text(count: int) -> str:
    return f"{count} notes" if count != 1 else "1 note"


def empty_page(count: int) -> Content:
    """The art with the stars in the accent colour, the bear in the widget's
    own (muted) colour, and the count underneath."""
    lines = []
    for line in EMPTY_ART_LINES:
        lines.append("".join(f"[$accent]{ch}[/$accent]" if ch in STAR_CHARS else ch for ch in line))
    lines += ["", count_text(count)]
    return Content.from_markup("\n".join(lines))


#: Glyph per column count: a hollow block for each hidden column.
COLUMN_GLYPHS = {3: "▮▮▮", 2: "▯▮▮", 1: "▯▯▮"}


class ColumnsToggle(Static):
    """The mouse's way to cycle the columns; the app owns the state."""

    class Pressed(Message):
        pass

    def __init__(self, **kwargs) -> None:
        super().__init__(COLUMN_GLYPHS[3], **kwargs)
        self.tooltip = "Hide / show the tag and note columns (c)"

    def show_columns(self, count: int) -> None:
        self.update(COLUMN_GLYPHS[count])

    def on_click(self, event: events.Click) -> None:
        event.stop()
        self.post_message(self.Pressed())


class NoteView(Vertical):
    DEFAULT_CSS = """
    NoteView {
        width: 1fr;
        height: 1fr;
    }
    NoteView > #note-bar {
        height: 1;
        background: $primary-background;
    }
    NoteView #columns-toggle {
        width: auto;
        padding: 0 1;
        color: $text-muted;
    }
    NoteView #columns-toggle:hover {
        color: $accent;
        text-style: bold;
    }
    NoteView #note-header {
        width: 1fr;
        padding: 0 1 0 0;
        color: $success;
        text-style: bold;
    }
    NoteView:focus-within #note-header {
        color: $accent;
    }
    NoteView > #note-scroll {
        height: 1fr;
        padding: 0 2;
    }
    NoteView Markdown {
        margin: 0;
    }
    NoteView > #note-meta {
        height: 1;
        padding: 0 1;
        color: $text-muted;
    }
    NoteView > #note-empty {
        display: none;
        height: 1fr;
        align: center middle;
    }
    NoteView.empty > #note-empty {
        display: block;
    }
    NoteView #note-art {
        width: 1fr;
        height: 1fr;
        content-align: center middle;
        text-align: center;
        color: $text-muted;
    }
    NoteView #note-picture {
        width: 100%;
        height: 1fr;
        margin: 1 2 0 2;
    }
    NoteView #note-count {
        display: none;
        height: 2;
        padding: 1 0 0 0;
        text-align: center;
        color: $text-muted;
    }
    NoteView.picture #note-art {
        display: none;
    }
    NoteView.picture #note-count {
        display: block;
    }
    NoteView.empty > #note-scroll, NoteView.empty > #note-meta {
        display: none;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._note: Note | None = None
        self._full_text: str | None = None
        self._rendered_full = True
        self._picture: Path | None = None
        self._picture_widget: type | None = None
        self._count = 0

    def compose(self) -> ComposeResult:
        with Horizontal(id="note-bar"):
            yield ColumnsToggle(id="columns-toggle")
            yield Static("", id="note-header")
        with VerticalScroll(id="note-scroll"):
            yield Markdown("", id="note-markdown", open_links=False)
        with Vertical(id="note-empty"):
            yield Static("", id="note-art")
            yield Static("", id="note-count")
        yield Static("", id="note-meta")

    @property
    def scroll_view(self) -> VerticalScroll:
        return self.query_one("#note-scroll", VerticalScroll)

    @property
    def markdown(self) -> Markdown:
        return self.query_one("#note-markdown", Markdown)

    @property
    def note(self) -> Note | None:
        return self._note

    @property
    def truncated(self) -> bool:
        return not self._rendered_full

    async def clear(self, message: str = "") -> None:
        self._note = None
        self._full_text = None
        self._rendered_full = True
        self.remove_class("empty", "picture")
        self.query_one("#note-header", Static).update("")
        self.query_one("#note-meta", Static).update("")
        await self.markdown.update(f"*{message}*" if message else "")

    async def show_empty(self, count: int) -> None:
        """No note is chosen: the bear and how many notes the selection holds."""
        self._note = None
        self._full_text = None
        self._rendered_full = True
        self.query_one("#note-header", Static).update("")
        self.query_one("#note-meta", Static).update("")
        self._count = count
        if self._picture is not None and self._picture_widget is not None:
            await self._ensure_picture()
            self.query_one("#note-count", Static).update(count_text(count))
            self.add_class("picture")
        else:
            self.remove_class("picture")
            self.query_one("#note-art", Static).update(empty_page(count))
        self.add_class("empty")
        await self.markdown.update("")

    async def set_picture(self, path: Path | None, widget_class: type | None) -> None:
        """Use a bitmap for the empty page (or None for the ASCII bear); redraws
        the page if it is showing."""
        self._picture = path
        self._picture_widget = widget_class
        for old in self.query("#note-picture"):
            await old.remove()
        if self.empty:
            await self.show_empty(self._count)

    async def _ensure_picture(self) -> None:
        if self.query("#note-picture"):
            return
        assert self._picture is not None and self._picture_widget is not None
        picture = self._picture_widget(str(self._picture), id="note-picture")
        await self.query_one("#note-empty", Vertical).mount(picture, before=self.query_one("#note-count", Static))

    @property
    def empty(self) -> bool:
        return self.has_class("empty")

    @property
    def has_picture(self) -> bool:
        return self.has_class("picture")

    async def show(self, note: Note, content: str, *, max_lines: int | None = None) -> bool:
        """Render a note. Returns True when only the head was rendered."""
        self.remove_class("empty", "picture")
        self._note = note
        text = preprocess(content)
        self._full_text = text
        shown = text
        truncated = False
        if max_lines is not None and not self.scroll_view.has_focus:
            shown, truncated = head_of(text, max_lines)
        self._rendered_full = not truncated
        self._set_header(note, truncated, shown, text)
        await self.markdown.update(shown)
        self.scroll_view.scroll_home(animate=False)
        return truncated

    async def render_full(self) -> None:
        if self._rendered_full or self._note is None or self._full_text is None:
            return
        self._rendered_full = True
        self._set_header(self._note, False, self._full_text, self._full_text)
        await self.markdown.update(self._full_text)

    async def show_error(self, note: Note, message: str) -> None:
        self.remove_class("empty", "picture")
        self._note = note
        self._full_text = None
        self._rendered_full = True
        self.query_one("#note-header", Static).update(note.title)
        self.query_one("#note-meta", Static).update("")
        await self.markdown.update(f"*{message}*")

    def _set_header(self, note: Note, truncated: bool, shown: str, full: str) -> None:
        header = note.title
        if truncated:
            header += f"  ({len(shown.splitlines())}/{len(full.splitlines())} lines — focus to read on)"
        self.query_one("#note-header", Static).update(header)
        meta: list[str] = []
        if note.modified:
            meta.append("modified " + note.modified.astimezone().strftime("%Y-%m-%d %H:%M"))
        if note.created:
            meta.append("created " + note.created.astimezone().strftime("%Y-%m-%d"))
        words = len(full.split())
        meta.append(f"{words} words")
        if note.todos or note.done:
            meta.append(f"tasks {note.done}/{note.todos + note.done}")
        if note.pins:
            meta.append("pinned " + ", ".join(note.pins))
        self.query_one("#note-meta", Static).update(" · ".join(meta))

    class WantsFull(Message):
        """The pane was focused while truncated: the app should render the rest."""

    def on_descendant_focus(self, event) -> None:
        if not self._rendered_full:
            self.post_message(self.WantsFull())
