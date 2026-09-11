"""The Bjorn application: three panes over one bearcli snapshot."""

from __future__ import annotations

import asyncio
import contextlib
import functools
import os
import shlex
import subprocess
import sys
import tempfile
from collections import OrderedDict
from pathlib import Path

from textual import on
from textual.app import App, ComposeResult, SuspendNotSupported
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.timer import Timer
from textual.widgets import Footer, Input, ListView, Tree

from .bear import BearClient, BearError, Note, NoteContent, Probe, Snapshot, display_tag, normalize_tag, recently_modified, resolve_bearcli
from .config import Config, editor_available, resolve_editor
from .export import FORMATS, ExportError, default_export_path, export_note, extension_for, format_by_id, safe_filename
from .icons import IconSet
from .model import Selection, View, duplicate_titles, select_notes
from .reminders import RemctlClient, RemctlError, join as join_reminders, remctl_found, resolve_remctl
from .render import AUTO_COMPLETE_LINES, BROWSE_LINES
from .screen import BjornScreen
from .search import query_pattern
from .todos import scan_rows
from .widgets.modals import ConfirmScreen, FormatPrompt, HelpScreen, NewNotePrompt, TextPrompt
from .widgets.note_list import NoteList
from .widgets.note_view import ColumnsToggle, NoteView
from .widgets.sidebar import Sidebar
from .widgets.triage import TriageRow, TriageScreen

#: Delay between the list cursor moving and the note being fetched and rendered.
PREVIEW_DEBOUNCE = 0.12
#: After a truncated render, how long the cursor must rest before the rest is
#: rendered automatically (only for notes up to AUTO_COMPLETE_LINES).
PREVIEW_SETTLE = 0.35
#: Note bodies kept in memory, most recently read last. Each is keyed by the
#: note's modification stamp, so a changed note is fetched again on its own.
CONTENT_CACHE_SIZE = 64


class BjornApp(App[None]):
    TITLE = "Bjorn"
    CSS = """
    Screen {
        layout: vertical;
    }
    #columns {
        height: 1fr;
    }
    """
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("question_mark", "help", "Help"),
        Binding("r", "refresh", "Refresh"),
        Binding("slash", "search", "Search"),
        Binding("escape", "clear_search", "Clear search", show=False),
        Binding("n", "new_note", "New"),
        Binding("e", "edit_note", "Edit"),
        Binding("d", "trash_note", "Trash"),
        Binding("u", "restore_note", "Restore", show=False),
        Binding("p", "toggle_pin", "Pin"),
        Binding("x", "export_note", "Export"),
        Binding("b", "open_in_bear", "Bear"),
        Binding("w", "toggle_workspace", "Workspace"),
        Binding("W", "clear_workspace", "Clear workspace", show=False),
        Binding("f", "fold_tag", "Fold"),
        Binding("t", "triage", "Triage"),
        Binding("c", "cycle_columns", "Columns"),
        Binding("F", "fold_all", "Fold all", show=False),
        Binding("j", "cursor(1)", "Down", show=False),
        Binding("k", "cursor(-1)", "Up", show=False),
        Binding("right_square_bracket", "jump_match(1)", "Next match", show=False, key_display="]"),
        Binding("left_square_bracket", "jump_match(-1)", "Previous match", show=False, key_display="["),
    ] + [Binding(v.hotkey, f"view('{v.value}')", v.label, show=False) for v in View]

    def __init__(
        self,
        config: Config | None = None,
        *,
        client: BearClient | None = None,
        remctl: RemctlClient | None = None,
        workspace: str | None = None,
        environ: dict[str, str] | None = None,
    ) -> None:
        super().__init__()
        self.config = config or Config()
        self.client = client or BearClient(resolve_bearcli(self.config.bearcli))
        self.remctl: RemctlClient | None = remctl
        if self.remctl is None and self.config.reminders.enabled and remctl_found(self.config.reminders.remctl):
            self.remctl = RemctlClient(resolve_remctl(self.config.reminders.remctl))
        self._reminders_notice_shown = False
        self.environ = dict(os.environ if environ is None else environ)
        self.icons = IconSet(self.config.icon_style, self.config.icons, self.environ)
        self.snapshot = Snapshot()
        ws = self.config.workspace if workspace is None else workspace
        self.selection = Selection(workspace=normalize_tag(ws or ""))
        self.search_query = ""
        self._content_cache: OrderedDict[str, tuple[str, NoteContent]] = OrderedDict()
        # Bumped whenever an entry is dropped, so a read that was in flight
        # when its note was rewritten does not put the old body back.
        self._cache_epoch = 0
        self._preview_timer: Timer | None = None
        self._settle_timer: Timer | None = None
        self._poll_timer: Timer | None = None
        self._last_probe: Probe | None = None
        self._busy = False
        self._written_titles: set[str] = set()
        self.loaded = False
        # Renders are never cancelled mid-flight (a half-mounted Markdown wedges
        # its message queue); a stale render is skipped by generation instead.
        self._load_gen = 0
        self._render_lock = asyncio.Lock()
        self._reload_lock = asyncio.Lock()

    # -- layout ------------------------------------------------------------------

    def get_default_screen(self) -> BjornScreen:
        return BjornScreen()

    def compose(self) -> ComposeResult:
        with Horizontal(id="columns"):
            yield Sidebar(icons=self.icons, id="sidebar")
            yield NoteList(id="note-list")
            yield NoteView(id="note-view")
        yield Footer()

    @property
    def sidebar(self) -> Sidebar:
        return self.query_one("#sidebar", Sidebar)

    @property
    def note_list(self) -> NoteList:
        return self.query_one("#note-list", NoteList)

    @property
    def note_view(self) -> NoteView:
        return self.query_one("#note-view", NoteView)

    # -- columns -----------------------------------------------------------------

    #: How many columns are showing: 3 = tags · notes · note, 2 = notes · note, 1 = note.
    columns: int = 3

    def action_cycle_columns(self) -> None:
        """`c`: hide the tag column, then the note column too, then show all three."""
        self.set_columns(3 if self.columns == 1 else self.columns - 1)

    @on(ColumnsToggle.Pressed)
    def _on_columns_toggle(self) -> None:
        self.action_cycle_columns()

    def set_columns(self, count: int) -> None:
        if count not in (1, 2, 3):
            raise ValueError(f"columns must be 1, 2 or 3, not {count}")
        self.columns = count
        self.sidebar.display = count == 3
        self.note_list.display = count >= 2
        self.query_one(ColumnsToggle).show_columns(count)
        focused = self.focused
        if focused is not None and not (focused.display and all(a.display for a in focused.ancestors)):
            (self.note_list.list_view if count >= 2 else self.note_view.scroll_view).focus()

    def on_mount(self) -> None:
        self.note_list.tag_source = self.query_tags
        self.sidebar.set_workspace(self.selection.workspace)
        self.note_list.list_view.focus()
        self.run_worker(self.reload, name="reload", group="reload")
        if self.config.poll_seconds > 0:
            self._poll_timer = self.set_interval(self.config.poll_seconds, self._poll)

    # -- data --------------------------------------------------------------------

    async def reload(self, *, keep_id: str | None = None, focus_id: str | None = None) -> None:
        """Take a fresh snapshot and redraw every pane around it."""
        async with self._reload_lock:
            if not self.is_running:
                return
            # The probe runs alongside the snapshot: both are bearcli calls, and
            # the probe taken here is what the next poll compares against.
            snapshot, probe = await asyncio.gather(self.client.snapshot(), self.client.probe(), return_exceptions=True)
            if isinstance(snapshot, BaseException):
                if not isinstance(snapshot, BearError):
                    raise snapshot
                self.notify(str(snapshot), title="bearcli", severity="error", timeout=10)
                if not self.loaded:
                    await self._clear_view(f"Could not read Bear: {snapshot}")
                return
            self.snapshot = snapshot
            self.loaded = True
            if isinstance(probe, Probe):
                self._last_probe = probe
            if not self.is_running:
                return
            current = self.note_list.current()
            await self.sidebar.populate(self.snapshot, self.selection.workspace, keep_tag=self.selection.tag, keep_view=self.selection.view)
            await self.apply_selection(keep_id=focus_id or keep_id or (current.id if current else None))
            if focus_id:
                await self.note_list.select_id(focus_id)
            self._warn_duplicates()

    async def apply_selection(self, *, keep_id: str | None = None) -> None:
        async with self._render_lock:
            sel = self.selection
            notes = select_notes(self.snapshot, sel)
            header = sel.describe()
            if self.search_query:
                header = f"“{self.search_query}”"
            self.note_list.set_header(f"{header} · {len(notes)}")
            pattern = query_pattern(self.search_query) if self.search_query else None
            self.note_view.set_pattern(pattern)
            self.note_list.set_pattern(pattern)
            await self.note_list.show_notes(notes, keep_id=keep_id)

    def _warn_duplicates(self) -> None:
        if not self._written_titles:
            return
        dups = duplicate_titles(self.snapshot, self._written_titles)
        for title, ids in dups.items():
            self.notify(
                f"“{title}” now exists {len(ids)} times — iCloud may have resurrected the old version. "
                "Check in Bear before trashing either copy.",
                title="Duplicate note", severity="warning", timeout=15,
            )
        self._written_titles.clear()

    async def _poll(self) -> None:
        if self._busy or not self.loaded:
            return
        if not any(w.name == "poll" and w.is_running for w in self.workers):
            self.run_worker(self._poll_worker, name="poll", group="poll")

    async def _poll_worker(self) -> None:
        try:
            probe = await self.client.probe()
        except BearError:
            return
        if self._last_probe is not None and probe != self._last_probe:
            self._last_probe = probe
            await self.reload()
            current = self.note_list.current()
            if current is not None:
                self._schedule_preview(current, immediate=True)
        else:
            self._last_probe = probe

    # -- selection messages ----------------------------------------------------------

    @on(Sidebar.ViewSelected)
    async def _on_view_selected(self, event: Sidebar.ViewSelected) -> None:
        self.search_query = ""
        self.selection = Selection(view=event.view, workspace=self.selection.workspace)
        await self.apply_selection()

    @on(Sidebar.TagSelected)
    async def _on_tag_selected(self, event: Sidebar.TagSelected) -> None:
        self.search_query = ""
        self.selection = Selection(view=View.ALL, tag=event.tag, workspace=self.selection.workspace)
        await self.apply_selection()

    @on(NoteList.Highlighted)
    def _on_note_highlighted(self, event: NoteList.Highlighted) -> None:
        if event.note is None:
            if self._preview_timer is not None:
                self._preview_timer.stop()
            self._load_gen += 1
            self.run_worker(functools.partial(self._clear_view, "No note selected"), group="note-load")
            return
        self._schedule_preview(event.note)

    async def _clear_view(self, message: str) -> None:
        gen = self._load_gen
        async with self._render_lock:
            if gen == self._load_gen and self.is_running:
                await self.note_view.clear(message)

    @on(NoteView.WantsFull)
    def _on_wants_full(self) -> None:
        self.run_worker(functools.partial(self._render_full, self._load_gen), group="note-full")

    @on(NoteList.Opened)
    def _on_note_opened(self, event: NoteList.Opened) -> None:
        """`enter` on a row: into the reader, at the first match when searching."""
        if self.note_view.pattern is not None:
            self.run_worker(functools.partial(self._jump_match, 1, first=True), group="note-jump")
            return
        self.note_view.scroll_view.focus()

    async def action_jump_match(self, delta: int) -> None:
        await self._jump_match(delta)

    async def _jump_match(self, delta: int, *, first: bool = False) -> None:
        """Render the rest of a truncated note first: the match may be past the head."""
        view = self.note_view
        if view.pattern is None:
            return
        if view.truncated:
            await self._render_full(self._load_gen)

        def go() -> None:
            # After the refresh: freshly mounted blocks have no region to scroll to until then.
            if first:
                view.reset_match_cursor()
            if not view.jump(delta):
                view.scroll_view.focus()

        self.call_after_refresh(go)

    @on(NoteList.SearchSubmitted)
    async def _on_search(self, event: NoteList.SearchSubmitted) -> None:
        self.search_query = event.query
        query = event.query
        self.run_worker(functools.partial(self._search_worker, query), name="search", group="search")

    async def _search_worker(self, query: str) -> None:
        try:
            ids = await self.client.search_ids(query, location=self.selection.view.location)
        except BearError as exc:
            self.notify(str(exc), title="Search", severity="error")
            return
        if self.search_query != query:
            return
        self.selection = Selection(
            view=self.selection.view, tag=self.selection.tag,
            workspace=self.selection.workspace, search_ids=tuple(ids),
        )
        await self.apply_selection()

    @on(NoteList.SearchCleared)
    async def _on_search_cleared(self) -> None:
        await self.action_clear_search()

    # -- preview ---------------------------------------------------------------------

    def _schedule_preview(self, note: Note, *, immediate: bool = False, force: bool = False) -> None:
        """Render `note` after the debounce, unless the reader already shows this
        version of it: a list rebuild re-highlights the same note, and redrawing
        it would blank and remount the whole page for nothing."""
        if not force and not recently_modified(note.modified) and self.note_view.shows(note):
            return
        if self._preview_timer is not None:
            self._preview_timer.stop()
        if self._settle_timer is not None:
            self._settle_timer.stop()
        self._load_gen += 1
        gen = self._load_gen

        def start() -> None:
            if self.is_running and gen == self._load_gen:
                self.run_worker(functools.partial(self._load_note, note, gen), name="note-load", group="note-load")

        if immediate:
            start()
        else:
            self._preview_timer = self.set_timer(PREVIEW_DEBOUNCE, start)

    async def _fetch_content(self, note: Note) -> NoteContent:
        stamp = note.modified.isoformat() if note.modified else ""
        fresh = recently_modified(note.modified)
        cached = self._content_cache.get(note.id)
        if cached and cached[0] == stamp and not fresh:
            self._content_cache.move_to_end(note.id)
            return cached[1]
        epoch = self._cache_epoch
        content = await self.client.cat(note.id)
        if epoch == self._cache_epoch and not fresh:
            self._content_cache[note.id] = (stamp, content)
            while len(self._content_cache) > CONTENT_CACHE_SIZE:
                self._content_cache.popitem(last=False)
        return content

    def _forget_content(self, note_id: str | None = None) -> None:
        """Drop one note's body (or all of them) and outdate any read in flight."""
        if note_id is None:
            self._content_cache.clear()
        else:
            self._content_cache.pop(note_id, None)
        self._cache_epoch += 1

    async def _load_note(self, note: Note, gen: int) -> None:
        view = self.note_view
        if note.locked:
            async with self._render_lock:
                if gen == self._load_gen:
                    await view.show_error(note, "This note is locked; Bear does not expose its content.")
            return
        try:
            content = await self._fetch_content(note)
        except BearError as exc:
            async with self._render_lock:
                if gen == self._load_gen:
                    await view.show_error(note, f"Could not read note: {exc}")
            return
        async with self._render_lock:
            if gen != self._load_gen or not self.is_running:
                return
            truncated = await view.show(note, content.content, max_lines=BROWSE_LINES)
        if truncated and len(content.content.splitlines()) <= AUTO_COMPLETE_LINES:

            def finish() -> None:
                if self.is_running and gen == self._load_gen:
                    self.run_worker(functools.partial(self._render_full, gen), group="note-full")

            self._settle_timer = self.set_timer(PREVIEW_SETTLE, finish)

    async def _render_full(self, gen: int) -> None:
        async with self._render_lock:
            if gen == self._load_gen and self.is_running:
                await self.note_view.render_full()

    def current_note(self) -> Note | None:
        return self.note_list.current()

    def query_tags(self) -> list[str]:
        """Tags for search-box completion: the workspace's subtree first, then
        the rest, each group sorted."""
        tags = sorted({tag for note in self.snapshot.notes for tag in note.tags})
        ws = self.selection.workspace
        if not ws:
            return tags
        inside = [t for t in tags if t == ws or t.startswith(ws + "/")]
        return inside + [t for t in tags if t not in inside]

    # -- actions: navigation -----------------------------------------------------------

    def action_cursor(self, delta: int) -> None:
        focused = self.focused
        if isinstance(focused, (ListView, Tree)):
            focused.action_cursor_down() if delta > 0 else focused.action_cursor_up()
        elif isinstance(focused, VerticalScroll):
            focused.scroll_down() if delta > 0 else focused.scroll_up()

    async def action_view(self, value: str) -> None:
        view = View(value)
        self.sidebar.select_view(view)
        self.search_query = ""
        self.selection = Selection(view=view, workspace=self.selection.workspace)
        await self.apply_selection()

    def action_search(self) -> None:
        self.note_list.open_search(self.search_query)

    async def action_clear_search(self) -> None:
        if self.note_list.search_open:
            self.note_list.close_search()
        if self.search_query or self.selection.search_ids is not None:
            self.search_query = ""
            self.selection = Selection(view=self.selection.view, tag=self.selection.tag, workspace=self.selection.workspace)
            await self.apply_selection()

    def action_quit(self) -> None:
        """`q` asks first: it sits next to the navigation keys and is easy to hit."""
        self.run_worker(self._confirm_quit(), name="quit", exclusive=True)

    async def _confirm_quit(self) -> None:
        if await self.push_screen_wait(ConfirmScreen("Quit Bjorn?", confirm_label="Quit")):
            self.exit()

    def action_refresh(self) -> None:
        self._forget_content()
        self.run_worker(self._refresh_worker, name="reload", group="reload")

    async def _refresh_worker(self) -> None:
        await self.reload()
        current = self.current_note()
        if current is not None:
            self._schedule_preview(current, immediate=True, force=True)

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    # -- actions: workspace --------------------------------------------------------------

    async def action_toggle_workspace(self) -> None:
        """`w` scopes to the highlighted tag; pressed again on the workspace
        itself (or with no other tag in hand) it clears the scope."""
        tag = ""
        if self.focused is self.sidebar.tree:
            tag = self.sidebar.highlighted_tag()
        tag = tag or self.selection.tag
        current = self.selection.workspace
        if current and (not tag or tag == current):
            await self.set_workspace("")
            return
        if not tag:
            self.notify("Highlight a tag first (the workspace is a tag subtree).", title="Workspace")
            return
        await self.set_workspace(tag)

    def action_fold_all(self) -> None:
        """Collapse every tag, or expand every tag when all are collapsed."""
        expanded = self.sidebar.toggle_all_folds()
        self.notify("All tags expanded" if expanded else "All tags folded", timeout=1.5)

    def action_fold_tag(self) -> None:
        """Collapse or expand the highlighted tag's subtree."""
        tree = self.sidebar.tree
        node = tree.cursor_node
        if node is None and self.selection.tag and self.sidebar.move_to_tag(self.selection.tag):
            node = tree.cursor_node
        if node is None:
            return
        if node.allow_expand:
            node.toggle()
        elif node.parent is not None and node.parent is not tree.root and self.sidebar.highlighted_tag():
            tree.move_cursor(node.parent)
            node.parent.collapse()

    async def set_workspace(self, tag: str) -> None:
        tag = normalize_tag(tag)
        self.search_query = ""
        self.selection = Selection(view=View.ALL, workspace=tag)
        await self.sidebar.populate(self.snapshot, tag)
        await self.apply_selection()
        self.notify(f"Workspace: {display_tag(tag)}" if tag else "Workspace cleared", timeout=3)

    async def action_clear_workspace(self) -> None:
        if not self.selection.workspace:
            return
        await self.set_workspace("")

    # -- triage -----------------------------------------------------------------------------

    #: App-level actions that stay available while the triage screen is up.
    _TRIAGE_SAFE_ACTIONS = frozenset({"quit", "help"})

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Main-screen keys (edit, trash, new…) would act on the note behind the
        triage screen; hide and disable them while it is up."""
        if self.triage is not None and action not in self._TRIAGE_SAFE_ACTIONS:
            return False
        return True

    @property
    def triage(self) -> TriageScreen | None:
        screen = self.screen
        return screen if isinstance(screen, TriageScreen) else None

    def action_triage(self) -> None:
        if self.triage is not None:
            return
        scope = display_tag(self.selection.workspace) if self.selection.workspace else "all notes"
        if self.config.reminders.enabled and self.remctl is None and not self._reminders_notice_shown:
            self._reminders_notice_shown = True
            self.notify("Reminders mode is configured but remctl was not found; triage runs Bear-only.", title="Reminders", severity="warning", timeout=6)
        self.push_screen(TriageScreen(scope_label=scope, reminders_enabled=self.reminders_enabled))

    @property
    def reminders_enabled(self) -> bool:
        return self.config.reminders.enabled and self.remctl is not None


    @on(TriageScreen.Reload)
    def _on_triage_reload(self) -> None:
        self.run_worker(self._triage_load, name="triage-load", group="triage-load", exclusive=True)

    async def _triage_load(self) -> None:
        screen = self.triage
        if screen is None:
            return
        try:
            rows = await self.client.todo_rows(self.selection.workspace)
        except BearError as exc:
            self.notify(str(exc), title="Triage", severity="error", timeout=10)
            return
        scan = scan_rows(rows)
        statuses: dict[str, tuple[str, int]] = {}
        error = ""
        if self.reminders_enabled and self.remctl is not None:
            try:
                statuses = join_reminders(scan.todos, await self.remctl.linked_reminders())
            except RemctlError as exc:
                error = f"Reminders unavailable: {exc}"
        if self.triage is screen:
            await screen.show(scan, statuses=statuses, error=error)

    @on(TriageScreen.Tick)
    def _on_triage_tick(self, event: TriageScreen.Tick) -> None:
        self.run_worker(functools.partial(self._triage_tick, event.rows), name="triage-tick", exclusive=False)

    async def _triage_tick(self, rows: list[TriageRow]) -> None:
        if len(rows) > 1:
            ok = await self.push_screen_wait(ConfirmScreen(f"Tick {len(rows)} todos in Bear?", confirm_label="Tick"))
            if not ok:
                return
        ticked: list[TriageRow] = []
        failures: list[str] = []
        for row in rows:
            todo = row.todo
            try:
                await self.client.tick_todo(todo.note_id, todo.line, todo.done_line, section=todo.section)
                ticked.append(row)
            except BearError as exc:
                failures.append(f"{todo.text[:40]}: {exc}")
        screen = self.triage
        if screen is not None and ticked:
            await screen.note_removed(ticked)
        if failures:
            self.notify("\n".join(failures), title="Some todos were not ticked (the line changed in Bear?)", severity="warning", timeout=10)
        elif ticked:
            self.notify(f"Ticked {len(ticked)} in Bear.", timeout=2)
        await self.reload()
        if self.triage is not None:
            await self._triage_load()

    @on(TriageScreen.GoTo)
    def _on_triage_goto(self, event: TriageScreen.GoTo) -> None:
        self.run_worker(functools.partial(self._triage_goto, event.todo.note_id), name="triage-goto", exclusive=False)

    async def _triage_goto(self, note_id: str) -> None:
        if self.triage is not None:
            self.pop_screen()
        if not await self.note_list.select_id(note_id):
            self.search_query = ""
            self.selection = Selection(view=View.ALL, workspace=self.selection.workspace)
            self.sidebar.select_view(View.ALL)
            await self.apply_selection(keep_id=note_id)
            await self.note_list.select_id(note_id)
        self.note_list.list_view.focus()
        current = self.current_note()
        if current is not None:
            self._schedule_preview(current, immediate=True)

    @on(TriageScreen.OpenInBear)
    def _on_triage_open(self, event: TriageScreen.OpenInBear) -> None:
        todo = event.todo
        header = "" if todo.section.startswith("# ") else todo.header
        self.run_worker(functools.partial(self._open_note_in_bear, todo.note_id, header), name="open", exclusive=False)

    async def _open_note_in_bear(self, note_id: str, header: str = "") -> None:
        try:
            await self.client.open_in_app(note_id, header=header)
        except BearError as exc:
            self.notify(str(exc), title="Open in Bear failed", severity="error", timeout=10)

    @on(TriageScreen.AddReminders)
    def _on_triage_add(self, event: TriageScreen.AddReminders) -> None:
        if not self.reminders_enabled or self.remctl is None:
            self.notify("Reminders mode is off ([reminders] enabled = true in config).", timeout=4)
            return
        self.run_worker(functools.partial(self._triage_add, event.rows), name="triage-add", exclusive=False)

    async def _triage_add(self, rows: list[TriageRow]) -> None:
        assert self.remctl is not None
        cfg = self.config.reminders
        added = 0
        failures: list[str] = []
        for row in rows:
            try:
                await self.remctl.add(row.todo, list_title=cfg.list, due=cfg.due)
                added += 1
            except RemctlError as exc:
                failures.append(f"{row.todo.text[:40]}: {exc}")
        if failures:
            self.notify("\n".join(failures), title="Some reminders were not created", severity="warning", timeout=10)
        if added:
            where = f" to “{cfg.list}”" if cfg.list else ""
            self.notify(f"Added {added} reminder{'s' if added != 1 else ''}{where}.", timeout=3)
        for row in rows:
            row.marked = False
        if self.triage is not None:
            await self._triage_load()

    # -- actions: writes ------------------------------------------------------------------

    def action_new_note(self) -> None:
        self.run_worker(self._new_note(), name="new-note", exclusive=False)

    async def _new_note(self) -> None:
        default_tags = self.selection.tag or self.selection.workspace
        result = await self.push_screen_wait(NewNotePrompt(default_tags=default_tags))
        if not result:
            return
        title, tags = result
        tag_list = [t for t in (normalize_tag(t) for t in tags.split(",")) if t]
        try:
            note_id = await self.client.create(title, tag_list)
        except BearError as exc:
            self.notify(str(exc), title="Create failed", severity="error", timeout=10)
            return
        await self.reload(focus_id=note_id)
        note = self.snapshot.by_id(note_id)
        if note is not None:
            await self.edit_note(note)

    def action_edit_note(self) -> None:
        note = self.current_note()
        if note is None:
            self.notify("No note selected.")
            return
        self.run_worker(self.edit_note(note), name="edit", exclusive=False)

    async def edit_note(self, note: Note) -> None:
        """Round-trip the note through the editor, writing back hash-guarded."""
        if note.locked:
            self.notify("Locked notes cannot be edited here.", severity="warning")
            return
        editor = resolve_editor(self.config, self.environ)
        if not editor_available(editor):
            self.notify(f"Editor “{editor}” not found. Set $EDITOR or `editor` in config.", severity="error", timeout=10)
            return
        try:
            before = await self.client.cat(note.id)
        except BearError as exc:
            self.notify(str(exc), title="Read failed", severity="error")
            return
        tmp_dir = Path(tempfile.mkdtemp(prefix="bjorn-"))
        tmp = tmp_dir / f"{safe_filename(note.title)}.md"
        tmp.write_text(before.content, encoding="utf-8")
        self._busy = True
        try:
            self._run_editor(shlex.split(editor) + [str(tmp)])
        finally:
            self._busy = False
        try:
            after = tmp.read_text(encoding="utf-8")
        except OSError as exc:
            self.notify(f"Could not read the edited file: {exc}", severity="error")
            return
        if after == before.content:
            self._cleanup(tmp)
            self.notify("No changes.", timeout=2)
            return
        try:
            await self.client.overwrite(note.id, after, base=before.hash)
        except BearError as exc:
            if exc.is_conflict:
                self.notify(
                    f"The note changed in Bear while you were editing. Nothing was written; "
                    f"your version is at {tmp}",
                    title="Edit conflict", severity="error", timeout=30,
                )
            else:
                self.notify(f"{exc} — your version is at {tmp}", title="Write failed", severity="error", timeout=30)
            return
        self._cleanup(tmp)
        self._forget_content(note.id)
        self._written_titles.add(note.title)
        await self.reload(keep_id=note.id)
        current = self.current_note()
        if current is not None and current.id == note.id:
            self._schedule_preview(current, immediate=True, force=True)
        self.notify("Saved to Bear.", timeout=2)

    def _run_editor(self, command: list[str]) -> None:
        """Hand the terminal to the editor. Headless (tests) runs it inline."""
        try:
            with self.suspend():
                subprocess.run(command, check=False)
        except SuspendNotSupported:
            subprocess.run(command, check=False, stdin=subprocess.DEVNULL)

    @staticmethod
    def _cleanup(tmp: Path) -> None:
        with contextlib.suppress(OSError):
            tmp.unlink()
        with contextlib.suppress(OSError):
            tmp.parent.rmdir()

    def action_trash_note(self) -> None:
        note = self.current_note()
        if note is None:
            self.notify("No note selected.")
            return
        if self.selection.view is View.TRASH:
            self.notify("Already in the trash. Bear empties the trash itself.", timeout=4)
            return
        self.run_worker(self._trash(note), name="trash", exclusive=False)

    async def _trash(self, note: Note) -> None:
        ok = await self.push_screen_wait(ConfirmScreen(f"Move “{note.title}” to the trash?", confirm_label="Trash"))
        if not ok:
            return
        try:
            await self.client.trash(note.id)
        except BearError as exc:
            self.notify(str(exc), title="Trash failed", severity="error", timeout=10)
            return
        self._forget_content(note.id)
        await self.reload()
        self.notify(f"Trashed “{note.title}” — restore it from the Trash view with u.", timeout=4)

    def action_restore_note(self) -> None:
        note = self.current_note()
        if note is None:
            return
        if self.selection.view not in (View.TRASH, View.ARCHIVE):
            self.notify("Restore works in the Trash and Archive views.", timeout=3)
            return
        self.run_worker(self._restore(note), name="restore", exclusive=False)

    async def _restore(self, note: Note) -> None:
        try:
            await self.client.restore(note.id)
        except BearError as exc:
            self.notify(str(exc), title="Restore failed", severity="error", timeout=10)
            return
        await self.reload()
        self.notify(f"Restored “{note.title}”.", timeout=3)

    def action_toggle_pin(self) -> None:
        note = self.current_note()
        if note is None:
            return
        self.run_worker(self._toggle_pin(note), name="pin", exclusive=False)

    async def _toggle_pin(self, note: Note) -> None:
        # The list item may predate the last reload; decide from the snapshot.
        note = self.snapshot.by_id(note.id) or note
        try:
            if note.pinned_globally:
                await self.client.unpin(note.id)
            else:
                await self.client.pin(note.id)
        except BearError as exc:
            self.notify(str(exc), title="Pin failed", severity="error", timeout=10)
            return
        await self.reload(keep_id=note.id)

    def action_open_in_bear(self) -> None:
        note = self.current_note()
        if note is None:
            return
        self.run_worker(self._open_in_bear(note), name="open", exclusive=False)

    async def _open_in_bear(self, note: Note) -> None:
        try:
            await self.client.open_in_app(note.id)
        except BearError as exc:
            self.notify(str(exc), title="Open in Bear failed", severity="error", timeout=10)

    def action_export_note(self) -> None:
        note = self.current_note()
        if note is None:
            self.notify("No note selected.")
            return
        self.run_worker(self._export(note), name="export", exclusive=False)

    async def _export(self, note: Note) -> None:
        if note.locked:
            self.notify("Locked notes cannot be exported here.", severity="warning")
            return
        chosen = await self.push_screen_wait(FormatPrompt(FORMATS, self.config.export_format))
        if not chosen:
            return
        fmt = format_by_id(chosen)
        default = default_export_path(self.config.export_dir, note.title, extension_for(fmt, bool(note.attachments)))
        target = await self.push_screen_wait(
            TextPrompt(f"Export as {fmt.label} to", prefill=str(default), hint="enter to write · esc to cancel")
        )
        if not target:
            return
        try:
            content = await self._fetch_content(note)
            images = await self._attachment_bytes(note) if fmt.needs_attachments else {}
            written = await asyncio.to_thread(export_note, fmt, content.content, note.title, Path(target), images)
        except (BearError, ExportError, OSError, ValueError) as exc:
            self.notify(str(exc), title="Export failed", severity="error", timeout=10)
            return
        self.notify(f"Exported to {written}", timeout=5)

    async def _attachment_bytes(self, note: Note) -> dict[str, bytes]:
        """Every attachment of `note`, by filename; nothing to fetch when the
        snapshot says it has none."""
        if not note.attachments:
            return {}
        names = await self.client.attachments(note.id)
        return {name: await self.client.attachment(note.id, name) for name in names}


def cell_mouse_driver_class():
    """Textual's Linux driver with in-band resize (mode 2048) never queried.

    Textual switches the mouse to SGR-pixel reporting (mode 1016) as soon as a
    terminal answers the 2048 query, and its parser then converts pixels to
    cells with the pixel size from the 2048 report. SwiftTerm-based terminals
    (Tecolot) report that size in device pixels but send mouse positions in
    points, so every hover lands on the wrong row. Not asking about 2048 keeps
    the mouse in cell mode; resizes still arrive through SIGWINCH.
    """
    from textual.drivers.linux_driver import LinuxDriver

    class CellMouseLinuxDriver(LinuxDriver):
        def _query_in_band_window_resize(self) -> None:  # noqa: D401
            return None

    return CellMouseLinuxDriver


def run(*, tag: str | None = None, config_path: str | None = None, demo: bool = False, mouse_pixels: bool | None = None) -> int:
    config = Config.load(config_path)
    if mouse_pixels is not None:
        config.mouse_pixels = mouse_pixels
    client: BearClient | None = None
    remctl: RemctlClient | None = None
    if demo:
        client = BearClient([sys.executable, str(Path(__file__).with_name("fake_bearcli.py"))])
        config.reminders.enabled = True
        remctl = RemctlClient([sys.executable, str(Path(__file__).with_name("fake_remctl.py"))])
    app = BjornApp(config, client=client, remctl=remctl, workspace=tag)
    if not config.mouse_pixels and sys.platform != "win32":
        app.driver_class = cell_mouse_driver_class()
    app.run()
    return 0
