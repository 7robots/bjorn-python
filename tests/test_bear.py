"""BearClient against the fake bearcli, driven as a real subprocess."""

from __future__ import annotations

import json

import pytest

from bjorn.bear import BearError, Location, Note, display_tag, normalize_tag


def test_normalize_and_display_tag():
    assert normalize_tag("#work/CAD and Design#") == "work/CAD and Design"
    assert normalize_tag(" #tech ") == "tech"
    assert display_tag("work/CAD and Design") == "#work/CAD and Design#"
    assert display_tag("tech/dev") == "#tech/dev"


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


def test_resolve_bearcli_falls_back_to_the_app_bundle(monkeypatch, tmp_path):
    from bjorn import bear

    monkeypatch.delenv(bear.ENV_COMMAND, raising=False)
    monkeypatch.setattr(bear.shutil, "which", lambda _cmd: None)
    bundled = tmp_path / "Bear.app" / "Contents" / "MacOS" / "bearcli"
    bundled.parent.mkdir(parents=True)
    bundled.write_text("#!/bin/sh\n")
    bundled.chmod(0o755)
    monkeypatch.setattr(bear, "APP_BUNDLE_COMMANDS", (str(tmp_path / "missing"), str(bundled)))

    assert bear.resolve_bearcli() == str(bundled)
    assert bear.resolve_bearcli("/opt/bearcli") == "/opt/bearcli"  # config still wins
    monkeypatch.setenv(bear.ENV_COMMAND, "/env/bearcli")
    assert bear.resolve_bearcli("/opt/bearcli") == "/env/bearcli"  # env wins over config

    monkeypatch.delenv(bear.ENV_COMMAND)
    monkeypatch.setattr(bear, "APP_BUNDLE_COMMANDS", ())
    assert bear.resolve_bearcli() == "bearcli"  # nothing found: PATH name, so the not_found error still names it


class RecordingClient:
    """A BearClient whose bearcli is a dict of canned rows; every call is logged."""

    def __init__(self, rows):
        from bjorn.bear import BearClient

        self.rows = rows
        self.calls: list[tuple[str, ...]] = []
        self.client = BearClient("unused")
        self.client._run = self._run  # type: ignore[method-assign]

    async def _run(self, *args, parse=True, stdin=None):
        self.calls.append(args)
        if args[0] == "cat":
            row = next(r for r in self.rows if r["id"] == args[1])
            return {"content": row["content"], "hash": "h"}
        fields = args[args.index("--fields") + 1].split(",")
        return [{k: v for k, v in r.items() if k in fields} for r in self.rows]

    def kinds(self) -> list[str]:
        out = []
        for call in self.calls:
            if call[0] == "cat":
                out.append("cat")
            else:
                out.append("list+content" if "content" in call[call.index("--fields") + 1] else "list")
        return out


def _row(i: int, stamp: str = "2026-09-01T00:00:00Z") -> dict:
    return {"id": f"N{i}", "title": f"Note {i}", "modified": stamp, "location": "notes", "content": f"# Note {i}\n\nbody {i} at {stamp}\n"}


async def test_snapshot_reads_bodies_only_for_notes_whose_stamp_moved():
    rows = [_row(i) for i in range(5)]
    rec = RecordingClient(rows)
    first = await rec.client.snapshot()
    assert rec.kinds() == ["list+content"], "a cold snapshot lists content in one call"
    assert first.by_id("N3").preview == "body 3 at 2026-09-01T00:00:00Z"

    rec.calls.clear()
    second = await rec.client.snapshot()
    assert rec.kinds() == ["list"], "nothing changed: metadata only"
    assert second.by_id("N3").preview == first.by_id("N3").preview

    rows[3] = _row(3, "2026-09-02T00:00:00Z")
    rec.calls.clear()
    third = await rec.client.snapshot()
    assert sorted(rec.kinds()) == ["cat", "list"], "one stamp moved: one cat"
    assert rec.calls[-1][1] == "N3"
    assert third.by_id("N3").preview == "body 3 at 2026-09-02T00:00:00Z"
    assert third.by_id("N1").preview == first.by_id("N1").preview


async def test_snapshot_falls_back_to_one_content_list_when_many_notes_changed():
    from bjorn.bear import PREVIEW_CAT_LIMIT

    rows = [_row(i) for i in range(PREVIEW_CAT_LIMIT + 5)]
    rec = RecordingClient(rows)
    await rec.client.snapshot()
    for i in range(PREVIEW_CAT_LIMIT + 1):
        rows[i] = _row(i, "2026-09-03T00:00:00Z")
    rec.calls.clear()
    snap = await rec.client.snapshot()
    assert rec.kinds() == ["list", "list+content"]
    assert snap.by_id("N0").preview.endswith("2026-09-03T00:00:00Z")


async def test_snapshot_forgets_previews_of_notes_that_are_gone():
    rows = [_row(i) for i in range(3)]
    rec = RecordingClient(rows)
    await rec.client.snapshot()
    del rows[0]
    await rec.client.snapshot()
    assert set(rec.client._previews) == {"N1", "N2"}


async def test_probe_runs_its_two_commands_together():
    rec = RecordingClient([_row(0)])

    async def run(*args, parse=True, stdin=None):
        rec.calls.append(args)
        if "--count" in args:
            return {"count": 1}
        return [{"id": "N0", "modified": "2026-09-01T00:00:00Z"}]

    rec.client._run = run  # type: ignore[method-assign]
    probe = await rec.client.probe()
    assert probe.count == 1 and probe.latest_id == "N0"
    assert len(rec.calls) == 2


async def test_a_note_stamped_this_second_is_read_again_every_snapshot():
    """Stamps have one-second resolution, so a very recent stamp proves nothing."""
    from datetime import datetime, timezone

    from bjorn.bear import recently_modified

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert recently_modified(now) and not recently_modified("2026-09-01T00:00:00Z") and not recently_modified(None)
    rows = [_row(0, "2026-09-01T00:00:00Z"), _row(1, now)]
    rec = RecordingClient(rows)
    await rec.client.snapshot()
    rec.calls.clear()
    await rec.client.snapshot()
    assert sorted(rec.kinds()) == ["cat", "list"]
    assert rec.calls[-1][1] == "N1"


async def test_attachments_list_and_save(client):
    assert await client.attachments("NOTE-GARDEN") == ["Front bed.png"]
    assert await client.attachments("NOTE-PLANNING") == []
    data = await client.attachment("NOTE-GARDEN", "Front bed.png")
    assert data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) == 70
    with pytest.raises(BearError):
        await client.attachment("NOTE-GARDEN", "missing.png")


async def test_previews_survive_a_restart_through_the_cache_file(client, tmp_path):
    import sys

    from bjorn.bear import PREVIEW_CACHE_VERSION, BearClient
    from conftest import FAKE

    path = tmp_path / "cache" / "previews.json"
    first = client.use_preview_cache(path)
    assert first.preview_cache_dirty, "nothing written yet"
    await first.snapshot()
    first.save_preview_cache()
    assert path.exists() and not first.preview_cache_dirty
    doc = json.loads(path.read_text())
    assert doc["version"] == PREVIEW_CACHE_VERSION and doc["bearcli"] == " ".join(client.command)
    assert not list(path.parent.glob("*.tmp")), "the temp file is renamed into place"

    # A second run, same library: the previews are there before any bearcli call.
    restarted = BearClient([sys.executable, str(FAKE)]).use_preview_cache(path)
    assert restarted._previews == first._previews and restarted._previews
    assert not restarted.preview_cache_dirty

    # Another bearcli's cache is not this one's; nor is a corrupt or
    # wrong-shaped file. None of them may stop the app from starting.
    for junk in (
        json.dumps({"version": PREVIEW_CACHE_VERSION, "bearcli": "elsewhere", "previews": {"N": ["s", "p"]}}),
        "{not json",
        "[]",
        "null",
        '"a string"',
    ):
        path.write_text(junk)
        cold = BearClient([sys.executable, str(FAKE)]).use_preview_cache(path)
        assert cold._previews == {}, junk
        assert cold.preview_cache_dirty
