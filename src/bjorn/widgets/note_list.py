"""Middle column: the notes matching the current selection, plus the search box."""

from __future__ import annotations

import re

from datetime import datetime, timezone

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Input, ListItem, ListView, Static

from ..search import MATCH_STYLE
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


class NoteItem(ListItem):
    """One note: the title, then two rows of date, counters and body preview.

    The item draws itself instead of composing child widgets: mounting is what
    a list rebuild costs, and one widget per note mounts about four times as
    fast as a ListItem holding a Label and a Static.
    """

    PREVIEW_ROWS = 2

    def __init__(self, note: Note, pattern: re.Pattern[str] | None = None) -> None:
        super().__init__()
        self.note = note
        #: The active search's terms, highlighted in the title and preview.
        self.pattern = pattern

    def render(self) -> Text:
        width = self.content_size.width or self.size.width
        if width <= 0:
            return Text("")
        note = self.note
        title = Text()
        if note.pinned:
            title.append("📌 ", "yellow")
        title.append(note.title, "bold")
        title.truncate(width, overflow="ellipsis")
        lead = Text(relative_date(note.modified), "dim")
        if note.todos:
            lead.append(f"  ☐ {note.todos}", "dim")
        if note.locked:
            lead.append("  🔒", "dim")
        rows = [title, *self.preview_lines(lead, note.preview, width)]
        if self.pattern is not None:
            for row in rows:
                row.highlight_regex(self.pattern, MATCH_STYLE)
        return Text("\n").join(rows)

    def preview_lines(self, lead: Text, body: str, width: int) -> list[Text]:
        """`lead` then `body` flowing on, wrapped to `width` and cut to
        PREVIEW_ROWS rows with an ellipsis."""
        text = lead.copy()
        if body:
            if text.plain:
                text.append("  ")
            text.append(body, "dim")
        lines = text.wrap(self.app.console, width, overflow="ellipsis", no_wrap=False)
        clipped = list(lines[: self.PREVIEW_ROWS])
        if len(lines) > self.PREVIEW_ROWS and clipped:
            last = clipped[-1]
            last.rstrip()
            last.truncate(width - 1)
            last.append("…", "dim")
        return clipped

    def preview_text(self) -> str:
        """The two preview rows as plain text, for tests."""
        width = self.content_size.width or self.size.width or 80
        note = self.note
        return "\n".join(line.plain for line in self.preview_lines(Text(relative_date(note.modified)), note.preview, width))


class NotesListView(ListView):
    """A ListView whose Enter opens the note in the reader while a mouse click
    only moves the highlight. Textual's ListView reports both as `Selected`, so
    the keyboard path is intercepted here before that message exists."""

    class Opened(Message):
        def __init__(self, index: int) -> None:
            super().__init__()
            self.index = index

    class NearEnd(Message):
        """The cursor or the scroll position is close to the last mounted item."""

    def action_select_cursor(self) -> None:
        if self.index is not None:
            self.post_message(self.Opened(self.index))

    def watch_scroll_y(self, old_value: float, new_value: float) -> None:
        super().watch_scroll_y(old_value, new_value)
        if new_value >= self.max_scroll_y - self.size.height:
            self.post_message(self.NearEnd())


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

    #: How many rows are mounted up front, and how many more each time the
    #: cursor or the scrollbar nears the last one. Mounting is the cost of a
    #: rebuild, so a long list mounts only its head and grows as it is read.
    WINDOW = 120

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._notes: list[Note] = []
        self._mounted = 0
        self._pattern: re.Pattern[str] | None = None

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

    def __len__(self) -> int:
        return len(self._notes)

    @property
    def mounted(self) -> int:
        """How many of the notes have a row in the list so far."""
        return self._mounted

    def set_header(self, text: str) -> None:
        self.query_one("#notes-header", Static).update(text)

    def set_pattern(self, pattern: re.Pattern[str] | None) -> None:
        """Highlight `pattern` in every row, now and as rows are mounted."""
        self._pattern = pattern
        for item in self.list_view.query(NoteItem):
            item.pattern = pattern
            item.refresh()

    async def show_notes(self, notes: list[Note], *, keep_id: str | None = None) -> None:
        """Replace the list; keep the cursor on `keep_id` when it is still present."""
        self._notes = list(notes)
        lv = self.list_view
        previous = lv.index
        target = 0
        if keep_id is not None:
            for i, n in enumerate(self._notes):
                if n.id == keep_id:
                    target = i
                    break
            else:
                target = min(previous or 0, len(self._notes) - 1) if self._notes else 0
        await lv.clear()
        self._mounted = 0
        self.query_one("#empty", Static).set_class(not self._notes, "visible")
        if not self._notes:
            self.post_message(self.Highlighted(None))
            return
        await self._mount_through(target)
        lv.index = target
        # Setting the same index does not re-emit Highlighted; the caller needs
        # the current note either way.
        self.post_message(self.Highlighted(self._notes[target]))

    async def _mount_through(self, index: int) -> None:
        """Mount rows so that `index` has one, in whole windows."""
        wanted = min(len(self._notes), max(self.WINDOW, index + 1 + self.WINDOW // 2))
        wanted = min(len(self._notes), max(wanted, self._mounted))
        lv = self.list_view
        if not lv.is_attached:
            # App is exiting (`q` during a rebuild): Textual refuses mounts from here on.
            return
        if wanted > self._mounted:
            await lv.extend([NoteItem(n, self._pattern) for n in self._notes[self._mounted:wanted]])
            self._mounted = wanted

    async def extend_window(self) -> None:
        """Mount the next window of rows, if any are left."""
        if self._mounted < len(self._notes):
            await self._mount_through(self._mounted + self.WINDOW - 1)

    def current(self) -> Note | None:
        lv = self.list_view
        if lv.index is None or not self._notes or lv.index >= len(self._notes):
            return None
        return self._notes[lv.index]

    async def select_id(self, note_id: str) -> bool:
        for i, n in enumerate(self._notes):
            if n.id == note_id:
                await self._mount_through(i)
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

    async def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.list_view is not self.list_view:
            return
        item = event.item
        if item is None and self._notes:
            # A rebuild empties the ListView before refilling it; the note that
            # ends up highlighted follows in its own message, so the reader is
            # not blanked in between.
            return
        self.post_message(self.Highlighted(item.note if isinstance(item, NoteItem) else None))
        index = self.list_view.index
        if index is not None and index >= self._mounted - self.WINDOW // 4:
            await self.extend_window()

    async def on_notes_list_view_near_end(self, event: NotesListView.NearEnd) -> None:
        await self.extend_window()

    def on_notes_list_view_opened(self, event: NotesListView.Opened) -> None:
        if 0 <= event.index < len(self._notes):
            self.post_message(self.Opened(self._notes[event.index]))
