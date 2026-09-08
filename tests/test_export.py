"""Phase 4: Markdown export."""

from __future__ import annotations

from pathlib import Path

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
