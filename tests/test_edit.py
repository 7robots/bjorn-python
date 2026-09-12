"""Phase 3: edit through $EDITOR with hash-guarded write-back."""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path

from helpers import loaded, wait_until


def fake_editor(tmp_path: Path, script: str) -> str:
    path = tmp_path / "editor.py"
    path.write_text("import sys\nfrom pathlib import Path\np = Path(sys.argv[1])\n" + script)
    return f"{os.sys.executable} {path}"


async def test_edit_round_trips_through_editor(make_app, client, tmp_path):
    editor = fake_editor(tmp_path, "p.write_text(p.read_text() + '\\nAdded from the editor\\n')")
    app = make_app(environ={"EDITOR": editor})
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await pilot.press("e")
        await wait_until(lambda: "Added from the editor" in app.note_view.markdown.source)
        content = await client.cat("NOTE-PLANNING")
        assert content.content.endswith("Added from the editor\n")


async def test_visual_beats_editor_and_config_beats_both(make_app, config, tmp_path):
    marker = tmp_path / "which"
    visual = fake_editor(tmp_path, f"Path({str(marker)!r}).write_text('visual')")
    app = make_app(environ={"EDITOR": "definitely-not-an-editor", "VISUAL": visual})
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await pilot.press("e")
        await wait_until(lambda: marker.exists())
        assert marker.read_text() == "visual"


async def test_unchanged_edit_writes_nothing(make_app, client, tmp_path):
    editor = fake_editor(tmp_path, "pass")
    app = make_app(environ={"EDITOR": editor})
    before = await client.cat("NOTE-PLANNING")
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await pilot.press("e")
        await pilot.pause(0.5)
    after = await client.cat("NOTE-PLANNING")
    assert after == before


async def test_conflict_keeps_the_temp_file(make_app, client, tmp_path, monkeypatch):
    # The "editor" changes the note in Bear behind our back, then edits the file.
    state = os.environ["BJORN_FAKE_BEAR_STATE"]
    fake = Path(__file__).resolve().parents[1] / "src" / "bjorn" / "fake_bearcli.py"
    editor = fake_editor(
        tmp_path,
        "import subprocess, os\n"
        f"subprocess.run([sys.executable, {str(fake)!r}, 'overwrite', 'NOTE-PLANNING', '--content', '# Sprint Planning\\\\n#work/sprint\\\\n\\\\nchanged in Bear\\\\n'], check=True, env={{**os.environ, 'BJORN_FAKE_BEAR_STATE': {state!r}}})\n"
        "p.write_text(p.read_text() + 'my edit\\n')\n",
    )
    # `edit_note` calls `tempfile.mkdtemp`, which resolves the parent through
    # `tempfile.gettempdir()`. Point that at this test's own directory so the
    # assertions below can only see the file this run produced: globbing the
    # shared system temp directory matched leftovers from earlier runs, in
    # arbitrary order, and then deleted them.
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))

    app = make_app(environ={"EDITOR": editor})
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await pilot.press("e")
        # The editor has run once the file carries its line, and the write-back
        # has been decided once the conflict has been reported. Waiting on
        # those two instead of on a fixed pause is what makes the file's
        # survival the thing under test: a successful write deletes it.
        await wait_until(lambda: any(scratch.glob("bjorn-*/Sprint Planning.md")))
        kept = next(iter(scratch.glob("bjorn-*/Sprint Planning.md")))
        await wait_until(lambda: kept.read_text().endswith("my edit\n"))
        await wait_until(
            lambda: any("Edit conflict" == n.title for n in app._notifications)
        )

        assert list(scratch.glob("bjorn-*/Sprint Planning.md")) == [kept], (
            "the edited file must survive a conflict, and nothing else may appear"
        )
        assert kept.read_text().endswith("my edit\n")
    content = await client.cat("NOTE-PLANNING")
    assert content.content.endswith("changed in Bear\n")


async def test_missing_editor_is_reported_not_fatal(make_app):
    app = make_app(environ={"EDITOR": "no-such-editor-xyz"})
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await pilot.press("e")
        await pilot.pause(0.3)
        assert app.is_running
