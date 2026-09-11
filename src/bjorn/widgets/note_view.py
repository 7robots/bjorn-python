"""Right column: the rendered note."""

from __future__ import annotations

import re

from textual.app import ComposeResult
from textual import events
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.content import Content
from textual.widgets import Markdown, Static
from textual.widgets._markdown import MarkdownBlock, MarkdownFence, MarkdownTable

from ..bear import Note
from ..render import head_of, preprocess
from ..search import MATCH_STYLE

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
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._note: Note | None = None
        self._full_text: str | None = None
        self._rendered_full = True
        self._pattern: re.Pattern[str] | None = None
        #: Blocks holding a match, in document order, and the block last jumped to.
        self._matches: list[MarkdownBlock] = []
        self._match_index = -1
        #: Each highlighted block's content before highlighting, to restore on clear.
        self._originals: dict[MarkdownBlock, Content] = {}

    def compose(self) -> ComposeResult:
        with Horizontal(id="note-bar"):
            yield ColumnsToggle(id="columns-toggle")
            yield Static("", id="note-header")
        with VerticalScroll(id="note-scroll"):
            yield Markdown("", id="note-markdown", open_links=False)
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

    # -- search highlighting -----------------------------------------------------------

    @property
    def pattern(self) -> re.Pattern[str] | None:
        return self._pattern

    @property
    def matches(self) -> list[MarkdownBlock]:
        return list(self._matches)

    @property
    def match_index(self) -> int:
        return self._match_index

    def set_pattern(self, pattern: re.Pattern[str] | None) -> None:
        """Highlight `pattern` in the rendered note now and in every note
        shown until it changes; None clears."""
        if pattern is not None and self._pattern is not None and pattern.pattern == self._pattern.pattern:
            return
        self._pattern = pattern
        self._apply_highlight()

    def _apply_highlight(self) -> None:
        for block, original in self._originals.items():
            if block.is_attached:
                block.set_content(original)
        self._originals = {}
        self._matches = []
        self._match_index = -1
        pattern = self._pattern
        if pattern is not None and self._full_text is not None:
            for block in self.markdown.query(MarkdownBlock):
                if isinstance(block, (MarkdownFence, MarkdownTable)) or any(
                    isinstance(a, (MarkdownFence, MarkdownTable)) for a in block.ancestors
                ):
                    continue
                content = block._content
                if not content.plain or pattern.search(content.plain) is None:
                    continue
                self._originals[block] = content
                block.set_content(content.highlight_regex(pattern, style=MATCH_STYLE))
                self._matches.append(block)
        if self._note is not None and self._full_text is not None:
            self._set_header(self._note, not self._rendered_full, self.markdown.source, self._full_text)

    def reset_match_cursor(self) -> None:
        """The next `jump(1)` lands on the first match."""
        self._match_index = -1

    def jump(self, delta: int) -> bool:
        """Scroll to the next (`delta` 1) or previous (-1) matching block,
        wrapping, and focus the reader. False when there is nothing to jump to."""
        if not self._matches:
            return False
        self._match_index = (self._match_index + delta) % len(self._matches)
        block = self._matches[self._match_index]
        self.scroll_view.scroll_to_widget(block, top=True, animate=False)
        self.scroll_view.focus()
        if self._note is not None and self._full_text is not None:
            self._set_header(self._note, not self._rendered_full, self.markdown.source, self._full_text)
        return True

    def _match_label(self) -> str:
        if self._pattern is None or not self._matches:
            return ""
        if self._match_index < 0:
            n = len(self._matches)
            return f"{n} match" if n == 1 else f"{n} matches"
        return f"match {self._match_index + 1}/{len(self._matches)}"

    def shows(self, note: Note) -> bool:
        """Is this version of `note` (same id, same modification) already on the
        page? An error page counts as not shown."""
        shown = self._note
        return shown is not None and self._full_text is not None and shown.id == note.id and shown.modified == note.modified

    async def clear(self, message: str = "") -> None:
        self._note = None
        self._full_text = None
        self._rendered_full = True
        self._originals, self._matches, self._match_index = {}, [], -1
        self.query_one("#note-header", Static).update("")
        self.query_one("#note-meta", Static).update("")
        await self.markdown.update(f"*{message}*" if message else "")

    async def show(self, note: Note, content: str, *, max_lines: int | None = None) -> bool:
        """Render a note. Returns True when only the head was rendered."""
        self._note = note
        text = preprocess(content)
        self._full_text = text
        shown = text
        truncated = False
        if max_lines is not None and not self.scroll_view.has_focus:
            shown, truncated = head_of(text, max_lines)
        self._rendered_full = not truncated
        self._originals, self._matches, self._match_index = {}, [], -1
        self._set_header(note, truncated, shown, text)
        await self.markdown.update(shown)
        self.scroll_view.scroll_home(animate=False)
        self._apply_highlight()
        return truncated

    async def render_full(self) -> None:
        if self._rendered_full or self._note is None or self._full_text is None:
            return
        self._rendered_full = True
        self._originals, self._matches, self._match_index = {}, [], -1
        self._set_header(self._note, False, self._full_text, self._full_text)
        await self.markdown.update(self._full_text)
        self._apply_highlight()

    async def show_error(self, note: Note, message: str) -> None:
        self._note = note
        self._full_text = None
        self._rendered_full = True
        self._originals, self._matches, self._match_index = {}, [], -1
        self.query_one("#note-header", Static).update(note.title)
        self.query_one("#note-meta", Static).update("")
        await self.markdown.update(f"*{message}*")

    def _set_header(self, note: Note, truncated: bool, shown: str, full: str) -> None:
        header = note.title
        if label := self._match_label():
            header += f"  · {label}"
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
