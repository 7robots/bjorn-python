"""Middle column: the notes matching the current selection, plus the search box."""

from __future__ import annotations

from datetime import datetime, timezone

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Input, Label, ListItem, ListView, Static

from ..bear import Note


def relative_date(when: datetime | None, now: datetime | None = None) -> str:
    """`14:02` today, `Yesterday`, `Mon`, `Sep 3`, or `2025-11-06` for older."""
    if when is None:
        return ""
    now = now or datetime.now(timezone.utc)
    local = when.astimezone()
    today = now.astimezone().date()
    delta = (today - local.date()).days
    if delta <= 0:
        return local.strftime("%H:%M")
    if delta == 1:
        return "Yesterday"
    if delta < 7:
        return local.strftime("%a")
    if local.year == today.year:
        return local.strftime("%b %-d")
    return local.strftime("%Y-%m-%d")


class PreviewText(Static):
    """Two rows under the title: the date and counters, then the body preview
    flowing on, wrapped to the row width and cut with an ellipsis."""

    ROWS = 2

    def __init__(self, lead: Text, body: str) -> None:
        super().__init__()
        self.lead = lead
        self.body = body

    def render(self) -> Text:
        width = self.size.width
        if width <= 0:
            return Text("")
        text = self.lead.copy()
        if self.body:
            if text.plain:
                text.append("  ")
            text.append(self.body, "dim")
        lines = text.wrap(self.app.console, width, overflow="ellipsis", no_wrap=False)
        clipped = list(lines[: self.ROWS])
        if len(lines) > self.ROWS and clipped:
            last = clipped[-1]
            last.rstrip()
            last.truncate(width - 1)
            last.append("…", "dim")
        return Text("\n").join(clipped)


class NoteItem(ListItem):
    def __init__(self, note: Note) -> None:
        super().__init__()
        self.note = note

    def compose(self) -> ComposeResult:
        note = self.note
        title = Text()
        if note.pinned:
            title.append("📌 ", "yellow")
        title.append(note.title, "bold")
        lead = Text(relative_date(note.modified), "dim")
        if note.todos:
            lead.append(f"  ☐ {note.todos}", "dim")
        if note.locked:
            lead.append("  🔒", "dim")
        yield Label(title, classes="note-title")
        yield PreviewText(lead, note.preview)


class NotesListView(ListView):
    """A ListView whose Enter opens the note in the reader while a mouse click
    only moves the highlight. Textual's ListView reports both as `Selected`, so
    the keyboard path is intercepted here before that message exists."""

    class Opened(Message):
        def __init__(self, index: int) -> None:
            super().__init__()
            self.index = index

    def action_select_cursor(self) -> None:
        if self.index is not None:
            self.post_message(self.Opened(self.index))


class NoteList(Vertical):
    DEFAULT_CSS = """
    NoteList {
        width: 36;
        min-width: 24;
        height: 1fr;
        border-right: solid $panel-lighten-2;
    }
    NoteList > #notes-header {
        height: 1;
        padding: 0 1;
        background: $primary-background;
        color: $success;
        text-style: bold;
    }
    NoteList:focus-within > #notes-header {
        color: $accent;
    }
    NoteList > #search {
        display: none;
        height: 3;
        border: tall $accent;
    }
    NoteList > #search.visible {
        display: block;
    }
    NoteList > #notes {
        height: 1fr;
        border: none;
        padding: 0;
    }
    NoteList > #notes > ListItem {
        padding: 0 1;
        height: 4;
        border-bottom: solid $panel-lighten-2;
    }
    NoteList > #notes > ListItem .note-title {
        width: 1fr;
    }
    NoteList > #notes > ListItem PreviewText {
        width: 1fr;
        height: 2;
    }
    NoteList > #empty {
        display: none;
        padding: 1 2;
        color: $text-muted;
    }
    NoteList > #empty.visible {
        display: block;
    }
    """

    class Highlighted(Message):
        def __init__(self, note: Note | None) -> None:
            super().__init__()
            self.note = note

    class Opened(Message):
        """Enter on a note: hand focus to the note view."""

        def __init__(self, note: Note) -> None:
            super().__init__()
            self.note = note

    class SearchSubmitted(Message):
        def __init__(self, query: str) -> None:
            super().__init__()
            self.query = query

    class SearchCleared(Message):
        pass

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._notes: list[Note] = []

    def compose(self) -> ComposeResult:
        yield Static("NOTES", id="notes-header")
        yield Input(placeholder="Search (Bear syntax) — enter to run, esc to clear", id="search")
        yield NotesListView(id="notes")
        yield Static("No notes", id="empty")

    @property
    def list_view(self) -> NotesListView:
        return self.query_one("#notes", NotesListView)

    @property
    def search_input(self) -> Input:
        return self.query_one("#search", Input)

    @property
    def notes(self) -> list[Note]:
        return list(self._notes)

    def set_header(self, text: str) -> None:
        self.query_one("#notes-header", Static).update(text)

    async def show_notes(self, notes: list[Note], *, keep_id: str | None = None) -> None:
        """Replace the list; keep the cursor on `keep_id` when it is still present."""
        self._notes = list(notes)
        lv = self.list_view
        previous = lv.index
        await lv.clear()
        await lv.extend([NoteItem(n) for n in self._notes])
        self.query_one("#empty", Static).set_class(not self._notes, "visible")
        if not self._notes:
            self.post_message(self.Highlighted(None))
            return
        target = 0
        if keep_id is not None:
            for i, n in enumerate(self._notes):
                if n.id == keep_id:
                    target = i
                    break
            else:
                target = min(previous or 0, len(self._notes) - 1)
        lv.index = target
        # Setting the same index does not re-emit Highlighted; the caller needs
        # the current note either way.
        self.post_message(self.Highlighted(self._notes[target]))

    def current(self) -> Note | None:
        lv = self.list_view
        if lv.index is None or not self._notes or lv.index >= len(self._notes):
            return None
        return self._notes[lv.index]

    def select_id(self, note_id: str) -> bool:
        for i, n in enumerate(self._notes):
            if n.id == note_id:
                self.list_view.index = i
                return True
        return False

    # -- search ------------------------------------------------------------------

    def open_search(self, prefill: str = "") -> None:
        box = self.search_input
        box.add_class("visible")
        box.value = prefill
        box.focus()

    def close_search(self) -> None:
        box = self.search_input
        box.remove_class("visible")
        box.value = ""
        self.list_view.focus()

    @property
    def search_open(self) -> bool:
        return self.search_input.has_class("visible")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input is not self.search_input:
            return
        query = event.value.strip()
        if query:
            self.post_message(self.SearchSubmitted(query))
            self.list_view.focus()
        else:
            self.close_search()
            self.post_message(self.SearchCleared())

    # -- list events -------------------------------------------------------------

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.list_view is not self.list_view:
            return
        item = event.item
        self.post_message(self.Highlighted(item.note if isinstance(item, NoteItem) else None))

    def on_notes_list_view_opened(self, event: NotesListView.Opened) -> None:
        if 0 <= event.index < len(self._notes):
            self.post_message(self.Opened(self._notes[event.index]))
