"""Right column: the rendered note."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Markdown, Static

from ..bear import Note
from ..render import head_of, preprocess


class NoteView(Vertical):
    DEFAULT_CSS = """
    NoteView {
        width: 1fr;
        height: 1fr;
    }
    NoteView > #note-header {
        height: 1;
        padding: 0 1;
        background: $primary-background;
        color: $success;
        text-style: bold;
    }
    NoteView:focus-within > #note-header {
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

    def compose(self) -> ComposeResult:
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

    async def clear(self, message: str = "") -> None:
        self._note = None
        self._full_text = None
        self._rendered_full = True
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
