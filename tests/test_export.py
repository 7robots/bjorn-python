"""Phase 4: Markdown export. Phase 11: the format picker, HTML and text."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from bjorn.export import default_export_path, safe_filename, unique_path
from helpers import loaded, wait_until


def test_safe_filename_and_unique_path(tmp_path):
    assert safe_filename("Dave Conversation: 6/Nov/2025?") == "Dave Conversation 6 Nov 2025"
    assert safe_filename("...") == "note"
    target = tmp_path / "Note.md"
    assert unique_path(target) == target
    target.write_text("x")
    assert unique_path(target) == tmp_path / "Note (2).md"
    (tmp_path / "Note (2).md").write_text("x")
    assert default_export_path(tmp_path, "Note") == tmp_path / "Note (3).md"


async def test_x_exports_to_the_prefilled_path(make_app, config):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await pilot.press("x")
        await pilot.pause()
        assert type(app.screen).__name__ == "FormatPrompt", "the picker comes first, Markdown preselected"
        await pilot.press("enter")
        await pilot.pause()
        assert type(app.screen).__name__ == "TextPrompt"
        prefill = app.screen.query_one("#value").value
        assert prefill == str(config.export_dir / "Sprint Planning.md")
        await pilot.press("enter")
        await wait_until(lambda: Path(prefill).exists())
        text = Path(prefill).read_text()
        assert text.startswith("# Sprint Planning\n#work/sprint\n")
        assert "- [ ] write the release notes" in text


async def test_export_can_be_cancelled(make_app, config):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await pilot.press("x")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert not config.export_dir.exists()


async def _export_via_picker(app, pilot, key: str) -> Path:
    await pilot.press("x")
    await pilot.pause()
    assert type(app.screen).__name__ == "FormatPrompt"
    await pilot.press(key)
    await pilot.pause()
    assert type(app.screen).__name__ == "TextPrompt"
    prefill = Path(app.screen.query_one("#value").value)
    await pilot.press("enter")
    await wait_until(lambda: prefill.exists())
    return prefill


async def test_h_exports_self_contained_html_with_the_attachment_embedded(make_app, config):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await pilot.press("j")  # Garden Plan carries the seeded image
        await wait_until(lambda: app.note_view.note is not None and app.note_view.note.id == "NOTE-GARDEN")
        written = await _export_via_picker(app, pilot, "h")
        assert written == config.export_dir / "Garden Plan.html"
        doc = written.read_text()
        assert doc.startswith("<!DOCTYPE html>") and "<title>Garden Plan</title>" in doc
        assert '<li class="task"><input type="checkbox" disabled> order bulbs' in doc
        assert 'src="data:image/png;base64,iVBORw0KGgo' in doc, "the attachment travels inside the file"
        assert "Front%20bed.png" not in doc


async def test_t_exports_plain_text(make_app, config):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        written = await _export_via_picker(app, pilot, "t")
        assert written == config.export_dir / "Sprint Planning.txt"
        text = written.read_text()
        assert text.startswith("Sprint Planning\n#work/sprint\n\nTasks\n- ☑ book the retro room\n- ☐ write the release notes\n")
        assert "Velocity is holding steady." in text and "==" not in text


async def test_export_format_config_preselects_and_arrows_move(make_app, config):
    config.export_format = "txt"
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await pilot.press("x")
        await pilot.pause()
        picker = app.screen
        assert picker.formats[picker.index].id == "txt"
        await pilot.press("left")
        assert picker.formats[picker.index].id == "html"
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.query_one("#value").value.endswith("Sprint Planning.html")
        await pilot.press("escape")
        await pilot.pause()
        assert not config.export_dir.exists()


def test_unknown_export_format_falls_back_to_markdown():
    from bjorn.export import format_by_id

    assert format_by_id("docx").id == "md" and format_by_id("html").ext == "html"


textutil_present = pytest.mark.skipif(shutil.which("textutil") is None, reason="textutil ships with macOS")


@textutil_present
async def test_r_exports_rtf_and_rtfd_when_the_note_has_images(make_app, config):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        written = await _export_via_picker(app, pilot, "r")
        assert written == config.export_dir / "Sprint Planning.rtf"
        rtf = written.read_text(errors="replace")
        assert rtf.startswith("{\\rtf1") and "release notes" in rtf and "Sprint Planning" in rtf
        await pilot.press("j")  # Garden Plan carries the seeded image
        await wait_until(lambda: app.note_view.note is not None and app.note_view.note.id == "NOTE-GARDEN")
        package = await _export_via_picker(app, pilot, "r")
        assert package == config.export_dir / "Garden Plan.rtfd" and package.is_dir()
        names = sorted(p.name for p in package.iterdir())
        assert "TXT.rtf" in names and any(n.endswith(".png") for n in names), names


def test_rtf_export_reports_a_missing_textutil(monkeypatch, tmp_path):
    from bjorn.export import ExportError, export_note, format_by_id

    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(ExportError, match="textutil"):
        export_note(format_by_id("rtf"), "# T\n", "T", tmp_path / "t.rtf")


def test_extension_for_switches_rtf_to_a_package_only_with_attachments():
    from bjorn.export import extension_for, format_by_id

    assert extension_for(format_by_id("rtf"), False) == "rtf"
    assert extension_for(format_by_id("rtf"), True) == "rtfd"
    assert extension_for(format_by_id("html"), True) == "html"
