"""Quitting while the note list is being rebuilt must not crash.

`App.exit()` sets `app._exit` at once, and from then on Textual reports every
widget as detached, so `mount()` raises `MountError` — while `app.is_running`
stays true until teardown. A rebuild already in flight when `q` is pressed
(a view or tag change, a reload) used to die with
`MountError: Can't mount widget(s) before NotesListView(id='notes') is mounted`.
"""

from __future__ import annotations

from textual.app import App

from bjorn.widgets.note_list import NoteList

from helpers import loaded
from test_note_list_window import notes


class ListApp(App[None]):
    def compose(self):
        yield NoteList(id="note-list")


async def test_show_notes_after_exit_does_not_mount():
    app = ListApp()
    async with app.run_test(size=(120, 40)):
        nl = app.query_one(NoteList)
        app.exit()
        await nl.show_notes(notes(NoteList.WINDOW * 2))
        assert nl.mounted == 0


async def test_extend_window_and_select_id_after_exit_do_not_mount():
    app = ListApp()
    async with app.run_test(size=(120, 40)):
        nl = app.query_one(NoteList)
        many = notes(NoteList.WINDOW * 3)
        await nl.show_notes(many)
        app.exit()
        await nl.extend_window()
        await nl.select_id(many[-1].id)
        assert nl.mounted == NoteList.WINDOW


async def test_apply_selection_after_quit_does_not_crash(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        app.exit()
        await app.apply_selection()
