"""BearClient against the fake bearcli, driven as a real subprocess."""

from __future__ import annotations

import json

import pytest

from bjorn.bear import BearError, Location, Note, display_tag, normalize_tag


def test_normalize_and_display_tag():
    assert normalize_tag("#kybernetes/CAD and Design#") == "kybernetes/CAD and Design"
    assert normalize_tag(" #techne ") == "techne"
    assert display_tag("kybernetes/CAD and Design") == "#kybernetes/CAD and Design#"
    assert display_tag("techne/dev") == "#techne/dev"


def test_note_from_row_parses_bearcli_shapes():
    row = {
        "id": "X", "title": "T", "locked": "no", "tags": ["#a", "#a/b c#"], "length": 12,
        "created": "2026-09-01T13:10:12Z", "modified": "2026-09-08T13:33:55Z", "pins": ["#meetings"],
        "location": "notes", "todos": 1, "done": 0, "attachments": [],
    }
    note = Note.from_row(row)
    assert note.tags == ("a", "a/b c")
    assert note.pinned and not note.pinned_globally
    assert note.modified.year == 2026 and note.modified.tzinfo is not None
    assert note.has_tag("a") and note.has_tag("#a/b c#") and not note.has_tag("z")
    assert note.location is Location.NOTES and not note.locked


async def test_snapshot_covers_every_location(client):
    snap = await client.snapshot()
    locations = {n.location for n in snap.notes}
    assert locations == {Location.NOTES, Location.TRASH, Location.ARCHIVE}
    planning = snap.by_id("NOTE-PLANNING")
    assert planning.todos == 3 and planning.done == 1 and planning.pinned_globally


async def test_probe_changes_after_a_write(client):
    before = await client.probe()
    assert before.count == 7
    await client.pin("NOTE-READING")
    await client.create("Fresh", ["home"])
    after = await client.probe()
    assert after != before and after.count == 8


async def test_cat_returns_hash_and_conflict_is_typed(client):
    content = await client.cat("NOTE-GARDEN")
    assert content.content.startswith("# Garden Plan")
    assert content.hash
    with pytest.raises(BearError) as info:
        await client.overwrite("NOTE-GARDEN", "# Garden Plan\n#home/garden\n\nx\n", base="0000000")
    assert info.value.is_conflict
    await client.overwrite("NOTE-GARDEN", "# Garden Plan\n#home/garden\n\nx\n", base=content.hash)
    assert (await client.cat("NOTE-GARDEN")).content.endswith("x\n")


async def test_search_ids_and_tags(client):
    assert await client.search_ids("@todo") == ["NOTE-PLANNING", "NOTE-GARDEN"]
    assert await client.search_ids("@untagged") == ["NOTE-UNTAGGED"]
    assert await client.search_ids("   ") == []
    assert "work/CAD and Design" in await client.tags()


async def test_create_trash_restore_pin(client):
    nid = await client.create("Brand New", ["work/new"], content="body\n")
    snap = await client.snapshot()
    note = snap.by_id(nid)
    assert note.title == "Brand New" and note.tags == ("work", "work/new")
    await client.trash(nid)
    assert (await client.snapshot()).by_id(nid).location is Location.TRASH
    await client.restore(nid)
    assert (await client.snapshot()).by_id(nid).location is Location.NOTES
    await client.pin(nid)
    assert (await client.snapshot()).by_id(nid).pinned_globally
    await client.unpin(nid)
    assert not (await client.snapshot()).by_id(nid).pins


async def test_edit_and_open_in_app(client, fake_state):
    await client.edit("NOTE-GARDEN", "- [ ] move the hydrangea", "- [x] move the hydrangea", section="## Next spring")
    assert "- [x] move the hydrangea" in (await client.cat("NOTE-GARDEN")).content
    await client.open_in_app("NOTE-GARDEN", header="Next spring")
    log = json.loads((fake_state.parent / "bear.json.opened").read_text().splitlines()[-1])
    assert log == {"id": "NOTE-GARDEN", "header": "Next spring"}


async def test_missing_binary_is_a_bear_error():
    from bjorn.bear import BearClient

    with pytest.raises(BearError) as info:
        await BearClient("/nonexistent/bearcli").snapshot()
    assert info.value.code == "not_found"
