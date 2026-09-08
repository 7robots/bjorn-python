"""The triage screen: every open todo in scope, grouped by note."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Footer, Input, Label, ListItem, ListView, Static

from .note_list import NotesListView

from ..bear import display_tag
from ..todos import Todo, TodoScan

Status = Literal["new", "added", "done"]

STATUS_GLYPH = {"new": " ", "added": "⏰", "done": "✓"}


@dataclass(slots=True)
class TriageRow:
    """One todo on the screen, with what became of it in Reminders (if any)."""

    todo: Todo
    status: Status = "new"
    reminder_id: int | None = None
    marked: bool = False


@dataclass(slots=True)
class TriageState:
    rows: list[TriageRow] = field(default_factory=list)
    locked: int = 0
    notes: int = 0
    reminders_enabled: bool = False
    reminders_error: str = ""

    def visible(self, needle: str) -> list[TriageRow]:
        needle = needle.strip().casefold()
        if not needle:
            return list(self.rows)
        return [r for r in self.rows if needle in r.todo.text.casefold() or needle in r.todo.note_title.casefold()]

    @property
    def marked(self) -> list[TriageRow]:
        return [r for r in self.rows if r.marked]


def note_header(todo: Todo, count: int) -> Text:
    text = Text.assemble((todo.note_title, "bold"), (f"  {count}", "dim"))
    tags = [t for t in todo.note_tags if not any(o != t and o.startswith(t + "/") for o in todo.note_tags)]
    if tags:
        text.append("  " + " ".join(display_tag(t) for t in tags[:2]), "dim italic")
    return text


class TodoItem(ListItem):
    """One todo. The first todo of each note carries the note's header line
    above it, so the list has no unselectable rows to step over."""

    def __init__(self, row: TriageRow, *, show_status: bool, header: Text | None = None) -> None:
        super().__init__(classes="triage-todo first" if header is not None else "triage-todo")
        self.row = row
        self.show_status = show_status
        self.header = header

    def compose(self) -> ComposeResult:
        if self.header is not None:
            yield Label(self.header, classes="triage-note")
        yield Label(self.render_text(), id="todo-label")

    def render_text(self) -> Text:
        row = self.row
        text = Text()
        text.append("● " if row.marked else "  ", "yellow" if row.marked else "")
        if self.show_status:
            glyph = STATUS_GLYPH[row.status]
            text.append(f"{glyph} ", "green" if row.status == "done" else "cyan" if row.status == "added" else "")
        text.append("☐ ", "dim")
        text.append(row.todo.text, "strike dim" if row.status == "done" else "")
        if row.todo.header:
            text.append(f"  {row.todo.header}", "dim")
        return text

    def refresh_text(self) -> None:
        self.query_one("#todo-label", Label).update(self.render_text())


class TriageScreen(Screen[None]):
    """Grouped todos with mark / tick / go-to / open-in-Bear / add-to-Reminders.

    The screen owns nothing but display state; every action is a message the
    app answers, because the app owns the clients and the main snapshot.
    """

    DEFAULT_CSS = """
    TriageScreen {
        layout: vertical;
    }
    TriageScreen > #triage-header {
        height: 1;
        padding: 0 1;
        background: $primary-background;
        color: $accent;
        text-style: bold;
    }
    TriageScreen > #triage-filter {
        display: none;
        height: 3;
        border: tall $accent;
    }
    TriageScreen > #triage-filter.visible {
        display: block;
    }
    TriageScreen > #triage-list {
        height: 1fr;
        padding: 0 1;
    }
    TriageScreen .triage-todo {
        padding: 0 1;
    }
    TriageScreen .triage-todo.first {
        margin-top: 1;
    }
    TriageScreen .triage-note {
        width: 1fr;
    }
    TriageScreen > #triage-status {
        height: 1;
        padding: 0 1;
        color: $text-muted;
    }
    TriageScreen > #triage-empty {
        display: none;
        padding: 2 3;
        color: $text-muted;
    }
    TriageScreen > #triage-empty.visible {
        display: block;
    }
    """

    BINDINGS = [
        Binding("escape,q", "close", "Close"),
        Binding("j", "cursor(1)", "Down", show=False),
        Binding("k", "cursor(-1)", "Up", show=False),
        Binding("space", "mark", "Mark"),
        Binding("x", "tick", "Tick in Bear"),
        Binding("b", "open_in_bear", "Bear"),
        Binding("a", "add_reminders", "Add to Reminders"),
        Binding("slash", "filter", "Filter"),
        Binding("r", "reload", "Reload"),
    ]

    # -- messages the app answers -------------------------------------------------

    class Reload(Message):
        pass

    class Tick(Message):
        def __init__(self, rows: list[TriageRow]) -> None:
            super().__init__()
            self.rows = rows

    class GoTo(Message):
        def __init__(self, todo: Todo) -> None:
            super().__init__()
            self.todo = todo

    class OpenInBear(Message):
        def __init__(self, todo: Todo) -> None:
            super().__init__()
            self.todo = todo

    class AddReminders(Message):
        def __init__(self, rows: list[TriageRow]) -> None:
            super().__init__()
            self.rows = rows

    def __init__(self, *, scope_label: str, reminders_enabled: bool) -> None:
        super().__init__()
        self.scope_label = scope_label
        self.state = TriageState(reminders_enabled=reminders_enabled)
        self.filter_text = ""
        self._items: list[TodoItem] = []

    def compose(self) -> ComposeResult:
        yield Static(f"TRIAGE · {self.scope_label}", id="triage-header")
        yield Input(placeholder="Filter todos — enter to apply, esc to clear", id="triage-filter")
        yield NotesListView(id="triage-list")
        yield Static("No open todos in scope", id="triage-empty")
        yield Static("loading…", id="triage-status")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#triage-list", ListView).focus()
        self.post_message(self.Reload())

    @property
    def list_view(self) -> ListView:
        return self.query_one("#triage-list", ListView)

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "add_reminders" and not self.state.reminders_enabled:
            return None
        return True

    # -- populate ----------------------------------------------------------------------

    async def show(self, scan: TodoScan, *, statuses: dict[str, tuple[Status, int | None]] | None = None, error: str = "") -> None:
        """Replace the rows from a scan, keeping marks and cursor where the keys survive."""
        marks = {r.todo.key for r in self.state.rows if r.marked}
        current = self.current_row()
        current_key = current.todo.key if current else None
        rows: list[TriageRow] = []
        for todo in scan.todos:
            status, rid = (statuses or {}).get(todo.key, ("new", None))
            rows.append(TriageRow(todo, status=status, reminder_id=rid, marked=todo.key in marks))
        self.state.rows = rows
        self.state.locked = scan.locked
        self.state.notes = scan.notes
        self.state.reminders_error = error
        await self._rebuild(keep_key=current_key)

    async def _rebuild(self, *, keep_key: str | None = None) -> None:
        lv = self.list_view
        await lv.clear()
        self._items = []
        items: list[ListItem] = []
        visible = self.state.visible(self.filter_text)
        per_note: dict[str, int] = {}
        for row in visible:
            per_note[row.todo.note_id] = per_note.get(row.todo.note_id, 0) + 1
        last_note = None
        for row in visible:
            header = None
            if row.todo.note_id != last_note:
                header = note_header(row.todo, per_note[row.todo.note_id])
                last_note = row.todo.note_id
            item = TodoItem(row, show_status=self.state.reminders_enabled, header=header)
            self._items.append(item)
            items.append(item)
        await lv.extend(items)
        self.query_one("#triage-empty", Static).set_class(not visible, "visible")
        target = 0
        for i, item in enumerate(self._items):
            if item.row.todo.key == keep_key:
                target = i
                break
        if self._items:
            lv.index = lv.children.index(self._items[target])
        self._update_status()

    def _update_status(self) -> None:
        st = self.state
        parts = [f"{len(st.rows)} open", f"{st.notes} notes"]
        if st.marked:
            parts.append(f"{len(st.marked)} marked")
        if st.locked:
            parts.append(f"{st.locked} locked skipped")
        if self.filter_text:
            parts.append(f"filter “{self.filter_text}”")
        if st.reminders_enabled:
            added = sum(1 for r in st.rows if r.status == "added")
            done = sum(1 for r in st.rows if r.status == "done")
            parts.append(f"reminders: {added} added, {done} completed")
        if st.reminders_error:
            parts.append(st.reminders_error)
        self.query_one("#triage-status", Static).update(" · ".join(parts))

    # -- cursor -------------------------------------------------------------------------

    def current_row(self) -> TriageRow | None:
        lv = self.list_view
        if lv.index is None or lv.index >= len(lv.children):
            return None
        item = lv.children[lv.index]
        return item.row if isinstance(item, TodoItem) else None

    def action_cursor(self, delta: int) -> None:
        lv = self.list_view
        if self.focused is not lv:
            return
        lv.action_cursor_down() if delta > 0 else lv.action_cursor_up()


    # -- actions ------------------------------------------------------------------------

    def action_close(self) -> None:
        """esc: hide the filter box, else clear an applied filter, else close."""
        if self.query_one("#triage-filter", Input).has_class("visible"):
            self._close_filter()
            return
        if self.filter_text:
            self.filter_text = ""
            self.run_worker(self._rebuild(), exclusive=True, group="triage-rebuild")
            return
        self.dismiss(None)

    def action_mark(self) -> None:
        row = self.current_row()
        if row is None:
            return
        row.marked = not row.marked
        for item in self._items:
            if item.row is row:
                item.refresh_text()
        self._update_status()

    def _targets(self) -> list[TriageRow]:
        marked = self.state.marked
        if marked:
            return marked
        row = self.current_row()
        return [row] if row else []

    def action_tick(self) -> None:
        rows = self._targets()
        if rows:
            self.post_message(self.Tick(rows))

    def on_notes_list_view_opened(self, event: NotesListView.Opened) -> None:
        """Enter on a row (a click only highlights, as in the notes list)."""
        row = self.current_row()
        if row is not None:
            self.post_message(self.GoTo(row.todo))

    def action_open_in_bear(self) -> None:
        row = self.current_row()
        if row is not None:
            self.post_message(self.OpenInBear(row.todo))

    def action_add_reminders(self) -> None:
        rows = [r for r in self._targets() if r.status == "new"]
        if not rows:
            self.notify("Mark rows that are not in Reminders yet.", timeout=3)
            return
        self.post_message(self.AddReminders(rows))

    def action_reload(self) -> None:
        self.query_one("#triage-status", Static).update("reloading…")
        self.post_message(self.Reload())

    def action_filter(self) -> None:
        box = self.query_one("#triage-filter", Input)
        box.add_class("visible")
        box.value = self.filter_text
        box.focus()

    def _close_filter(self) -> None:
        box = self.query_one("#triage-filter", Input)
        box.remove_class("visible")
        self.list_view.focus()

    @on(Input.Submitted, "#triage-filter")
    def _apply_filter(self, event: Input.Submitted) -> None:
        self.filter_text = event.value.strip()
        self._close_filter()
        self.run_worker(self._rebuild(), exclusive=True, group="triage-rebuild")

    def note_removed(self, rows: list[TriageRow]) -> None:
        """Drop rows after a successful tick; the app reloads anyway, this keeps
        the screen honest in between."""
        keys = {r.todo.key for r in rows}
        self.state.rows = [r for r in self.state.rows if r.todo.key not in keys]
