"""The notes list mounts a window of rows and grows it as the cursor nears the end."""

from __future__ import annotations

from datetime import datetime, timezone

from bjorn.bear import Note
from bjorn.theme import ThemedApp
from bjorn.widgets.note_list import NoteItem, NoteList


def notes(count: int) -> list[Note]:
    when = datetime(2026, 9, 1, tzinfo=timezone.utc)
    return [Note(id=f"N{i}", title=f"Note {i}", modified=when, preview=f"body {i}") for i in range(count)]


class ListApp(ThemedApp):
    def compose(self):
        yield NoteList(id="note-list")


async def test_a_long_list_mounts_one_window_and_grows_from_the_cursor():
    app = ListApp()
    async with app.run_test(size=(120, 40)) as pilot:
        nl = app.query_one(NoteList)
        many = notes(NoteList.WINDOW * 3)
        await nl.show_notes(many)
        await pilot.pause()
        assert len(nl) == len(many)
        assert nl.mounted == NoteList.WINDOW
        assert len(nl.list_view.query(NoteItem)) == NoteList.WINDOW
        assert nl.current() is many[0]

        # The cursor stepping toward the last mounted row pulls in the next window.
        nl.list_view.index = NoteList.WINDOW - 1
        await pilot.pause()
        assert nl.mounted > NoteList.WINDOW
        assert nl.current() is many[NoteList.WINDOW - 1]


async def test_select_id_beyond_the_window_mounts_up_to_it():
    app = ListApp()
    async with app.run_test(size=(120, 40)) as pilot:
        nl = app.query_one(NoteList)
        many = notes(NoteList.WINDOW * 4)
        await nl.show_notes(many)
        target = many[NoteList.WINDOW * 3]
        assert await nl.select_id(target.id)
        await pilot.pause()
        assert nl.current() is target
        assert nl.mounted > NoteList.WINDOW * 3
        assert nl.mounted < len(many), "the tail past the cursor stays unmounted"


async def test_keep_id_deep_in_the_list_is_mounted_on_rebuild():
    app = ListApp()
    async with app.run_test(size=(120, 40)) as pilot:
        nl = app.query_one(NoteList)
        many = notes(NoteList.WINDOW * 2 + 10)
        await nl.show_notes(many, keep_id=many[-1].id)
        await pilot.pause()
        assert nl.current() is many[-1]
        assert nl.mounted == len(many)


async def test_short_list_mounts_everything_once():
    app = ListApp()
    async with app.run_test(size=(120, 40)) as pilot:
        nl = app.query_one(NoteList)
        few = notes(5)
        await nl.show_notes(few)
        await pilot.pause()
        assert nl.mounted == 5
        await nl.extend_window()
        assert nl.mounted == 5
