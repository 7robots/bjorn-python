"""The Bjorn application: three panes over one bearcli snapshot."""

from __future__ import annotations

import contextlib
import functools
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

from textual import on
from textual.app import App, ComposeResult, SuspendNotSupported
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.timer import Timer
from textual.widgets import Footer, Input, ListView, Tree

from .bear import BearClient, BearError, Note, NoteContent, Probe, Snapshot, display_tag, normalize_tag, resolve_bearcli
from .config import Config, editor_available, resolve_editor
from .export import default_export_path, export_markdown, safe_filename
from .model import Selection, View, duplicate_titles, select_notes
from .render import AUTO_COMPLETE_LINES, BROWSE_LINES
from .widgets.modals import ConfirmScreen, HelpScreen, NewNotePrompt, TextPrompt
from .widgets.note_list import NoteList
from .widgets.note_view import NoteView
from .widgets.sidebar import Sidebar

#: Delay between the list cursor moving and the note being fetched and rendered.
PREVIEW_DEBOUNCE = 0.12
#: After a truncated render, how long the cursor must rest before the rest is
#: rendered automatically (only for notes up to AUTO_COMPLETE_LINES).
PREVIEW_SETTLE = 0.35


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
        Binding("o", "open_in_bear", "Bear"),
        Binding("w", "set_workspace", "Workspace"),
        Binding("W", "clear_workspace", "Clear workspace", show=False),
        Binding("j", "cursor(1)", "Down", show=False),
        Binding("k", "cursor(-1)", "Up", show=False),
    ] + [Binding(v.hotkey, f"view('{v.value}')", v.label, show=False) for v in View]

    def __init__(
        self,
        config: Config | None = None,
        *,
        client: BearClient | None = None,
        workspace: str | None = None,
        environ: dict[str, str] | None = None,
    ) -> None:
        super().__init__()
        self.config = config or Config()
        self.client = client or BearClient(resolve_bearcli(self.config.bearcli))
        self.environ = dict(os.environ if environ is None else environ)
        self.snapshot = Snapshot()
        ws = self.config.workspace if workspace is None else workspace
        self.selection = Selection(workspace=normalize_tag(ws or ""))
        self.search_query = ""
        self._content_cache: dict[str, tuple[str, NoteContent]] = {}
        self._preview_timer: Timer | None = None
        self._settle_timer: Timer | None = None
        self._poll_timer: Timer | None = None
        self._last_probe: Probe | None = None
        self._busy = False
        self._written_titles: set[str] = set()
        self.loaded = False

    # -- layout ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Horizontal(id="columns"):
            yield Sidebar(id="sidebar")
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

    def on_mount(self) -> None:
        self.sidebar.set_workspace(self.selection.workspace)
        self.note_list.list_view.focus()
        self.run_worker(self.reload, name="reload", group="reload", exclusive=True)
        if self.config.poll_seconds > 0:
            self._poll_timer = self.set_interval(self.config.poll_seconds, self._poll)

    # -- data --------------------------------------------------------------------

    async def reload(self, *, keep_id: str | None = None, focus_id: str | None = None) -> None:
        """Take a fresh snapshot and redraw every pane around it."""
        try:
            snapshot = await self.client.snapshot()
        except BearError as exc:
            self.notify(str(exc), title="bearcli", severity="error", timeout=10)
            if not self.loaded:
                await self.note_view.clear(f"Could not read Bear: {exc}")
            return
        self.snapshot = snapshot
        self.loaded = True
        with contextlib.suppress(BearError):
            self._last_probe = await self.client.probe()
        current = self.note_list.current()
        await self.apply_selection(keep_id=focus_id or keep_id or (current.id if current else None))
        if focus_id:
            self.note_list.select_id(focus_id)
        self._warn_duplicates()

    async def apply_selection(self, *, keep_id: str | None = None) -> None:
        sel = self.selection
        await self.sidebar.populate(self.snapshot, sel.workspace, keep_tag=sel.tag)
        notes = select_notes(self.snapshot, sel)
        header = sel.describe()
        if self.search_query:
            header = f"“{self.search_query}”"
        self.note_list.set_header(f"{header} · {len(notes)}")
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
        self.run_worker(self._poll_worker, name="poll", group="poll", exclusive=True)

    async def _poll_worker(self) -> None:
        try:
            probe = await self.client.probe()
        except BearError:
            return
        if self._last_probe is not None and probe != self._last_probe:
            self._last_probe = probe
            self._content_cache.clear()
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
            self.run_worker(functools.partial(self.note_view.clear, "No note selected"), group="note-load", exclusive=True)
            return
        self._schedule_preview(event.note)

    @on(NoteList.Opened)
    def _on_note_opened(self, event: NoteList.Opened) -> None:
        self.note_view.scroll_view.focus()

    @on(NoteList.SearchSubmitted)
    async def _on_search(self, event: NoteList.SearchSubmitted) -> None:
        self.search_query = event.query
        query = event.query
        self.run_worker(functools.partial(self._search_worker, query), name="search", group="search", exclusive=True)

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

    def _schedule_preview(self, note: Note, *, immediate: bool = False) -> None:
        if self._preview_timer is not None:
            self._preview_timer.stop()
        if self._settle_timer is not None:
            self._settle_timer.stop()
        def start() -> None:
            if self.is_running:
                self.run_worker(functools.partial(self._load_note, note), name="note-load", group="note-load", exclusive=True)

        if immediate:
            start()
        else:
            self._preview_timer = self.set_timer(PREVIEW_DEBOUNCE, start)

    async def _fetch_content(self, note: Note) -> NoteContent:
        stamp = note.modified.isoformat() if note.modified else ""
        cached = self._content_cache.get(note.id)
        if cached and cached[0] == stamp:
            return cached[1]
        content = await self.client.cat(note.id)
        self._content_cache[note.id] = (stamp, content)
        return content

    async def _load_note(self, note: Note) -> None:
        if note.locked:
            await self.note_view.show_error(note, "This note is locked; Bear does not expose its content.")
            return
        try:
            content = await self._fetch_content(note)
        except BearError as exc:
            await self.note_view.show_error(note, f"Could not read note: {exc}")
            return
        current = self.note_list.current()
        if current is None or current.id != note.id:
            return
        view = self.note_view
        truncated = await view.show(note, content.content, max_lines=BROWSE_LINES)
        if truncated and len(content.content.splitlines()) <= AUTO_COMPLETE_LINES:

            def finish() -> None:
                if self.is_running and view.is_attached:
                    self.run_worker(view.render_full, group="note-full", exclusive=True)

            self._settle_timer = self.set_timer(PREVIEW_SETTLE, finish)

    def current_note(self) -> Note | None:
        return self.note_list.current()

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

    def action_refresh(self) -> None:
        self._content_cache.clear()
        self.run_worker(self.reload, name="reload", group="reload", exclusive=True)
        current = self.current_note()
        if current is not None:
            self._schedule_preview(current, immediate=True)

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    # -- actions: workspace --------------------------------------------------------------

    async def action_set_workspace(self) -> None:
        tag = ""
        if self.focused is self.sidebar.tree:
            tag = self.sidebar.highlighted_tag()
        tag = tag or self.selection.tag
        if not tag:
            self.notify("Highlight a tag first (the workspace is a tag subtree).", title="Workspace")
            return
        await self.set_workspace(tag)

    async def set_workspace(self, tag: str) -> None:
        tag = normalize_tag(tag)
        self.search_query = ""
        self.selection = Selection(view=View.ALL, workspace=tag)
        await self.apply_selection()
        self.sidebar.select_view(View.ALL)
        self.notify(f"Workspace: {display_tag(tag)}" if tag else "Workspace cleared", timeout=3)

    async def action_clear_workspace(self) -> None:
        if not self.selection.workspace:
            return
        await self.set_workspace("")

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
        self._content_cache.clear()
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
        self._content_cache.pop(note.id, None)
        self._written_titles.add(note.title)
        await self.reload(keep_id=note.id)
        current = self.current_note()
        if current is not None and current.id == note.id:
            self._schedule_preview(current, immediate=True)
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
        self._content_cache.pop(note.id, None)
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
        default = default_export_path(self.config.export_dir, note.title, "md")
        target = await self.push_screen_wait(
            TextPrompt("Export as Markdown to", prefill=str(default), hint="enter to write · esc to cancel")
        )
        if not target:
            return
        try:
            content = await self._fetch_content(note)
            written = export_markdown(content.content, Path(target))
        except (BearError, OSError) as exc:
            self.notify(str(exc), title="Export failed", severity="error", timeout=10)
            return
        self.notify(f"Exported to {written}", timeout=5)


def run(*, tag: str | None = None, config_path: str | None = None, demo: bool = False) -> int:
    config = Config.load(config_path)
    client: BearClient | None = None
    if demo:
        client = BearClient([sys.executable, str(Path(__file__).with_name("fake_bearcli.py"))])
    app = BjornApp(config, client=client, workspace=tag)
    app.run()
    return 0
