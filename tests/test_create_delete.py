"""Phase 3: create, trash, restore."""

from __future__ import annotations

from helpers import first_note, loaded, titles, wait_until
from test_edit import fake_editor


async def test_new_note_prompt_creates_and_opens_editor(make_app, client, tmp_path):
    editor = fake_editor(tmp_path, "p.write_text(p.read_text() + 'first line\\n')")
    app = make_app(environ={"EDITOR": editor})
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await pilot.press("n")
        await pilot.pause()
        for ch in "Fresh":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause()
        for ch in ",garden":
            await pilot.press(ch)
        await pilot.press("enter")
        await wait_until(lambda: "Fresh" in titles(app))
        await wait_until(lambda: app.note_view.note is not None and app.note_view.note.title == "Fresh")
        await wait_until(lambda: "first line" in app.note_view.markdown.source)
    snap = await client.snapshot()
    note = next(n for n in snap.notes if n.title == "Fresh")
    assert note.tags == ("garden",)
    assert (await client.cat(note.id)).content.endswith("first line\n")


async def test_new_note_defaults_tags_to_selected_tag(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        app.sidebar.tree.focus()
        await pilot.pause()
        await pilot.press("down")
        await wait_until(lambda: app.selection.tag == "home")
        await pilot.press("n")
        await pilot.pause()
        assert app.screen.query_one("#tags").value == "home"
        await pilot.press("escape")
        await pilot.pause()
        assert type(app.screen).__name__ == "BjornScreen"


async def test_trash_needs_confirmation_then_restore(make_app, client):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await first_note(app, pilot)
        await pilot.press("d")
        await pilot.pause()
        assert type(app.screen).__name__ == "ConfirmScreen"
        await pilot.press("escape")
        await pilot.pause()
        assert titles(app)[0] == "Sprint Planning"
        await pilot.press("d")
        await pilot.pause()
        await pilot.press("y")
        await wait_until(lambda: "Sprint Planning" not in titles(app))
        await pilot.press("7")
        await wait_until(lambda: titles(app) == ["Sprint Planning", "Old Draft"])
        await first_note(app, pilot)
        await pilot.press("d")
        await pilot.pause()
        assert type(app.screen).__name__ == "BjornScreen"
        await pilot.press("u")
        await wait_until(lambda: titles(app) == ["Old Draft"])
        await pilot.press("1")
        await wait_until(lambda: "Sprint Planning" in titles(app))
    snap = await client.snapshot()
    assert snap.by_id("NOTE-PLANNING").location.value == "notes"


async def test_restore_from_archive(make_app, client):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await pilot.press("6")
        await wait_until(lambda: titles(app) == ["Finished Project"])
        await first_note(app, pilot)
        await pilot.press("u")
        await wait_until(lambda: titles(app) == [])
    assert (await client.snapshot()).by_id("NOTE-ARCHIVED").location.value == "notes"
