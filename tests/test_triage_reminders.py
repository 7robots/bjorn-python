"""Phase 8: the triage screen in Reminders mode against fake bearcli + fake remctl."""

from __future__ import annotations

from bjorn.app import BjornApp
from bjorn.config import Config, RemindersConfig
from bjorn.widgets.triage import TriageScreen
from helpers import loaded, wait_until


def make(client, remctl, tmp_path, **kw) -> BjornApp:
    cfg = Config(poll_seconds=0, export_dir=tmp_path / "exports", reminders=RemindersConfig(enabled=True, list="Work", due="today"))
    return BjornApp(cfg, client=client, remctl=remctl, environ={}, **kw)


async def open_triage(app, pilot):
    await pilot.press("t")
    await wait_until(lambda: isinstance(app.screen, TriageScreen) and app.screen.state.rows)
    await pilot.pause()
    return app.screen


async def test_a_adds_marked_rows_and_status_glyphs_follow(client, remctl, tmp_path):
    app = make(client, remctl, tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        screen = await open_triage(app, pilot)
        assert screen.state.reminders_enabled
        await pilot.press("space")
        await pilot.press("j")
        await pilot.press("space")
        await pilot.press("a")
        await wait_until(lambda: sum(1 for r in screen.state.rows if r.status == "added") == 2)
        linked = await remctl.linked_reminders()
        assert sorted(r.title for r in linked) == ["ask Priya about the API deprecation", "write the release notes"]
        assert all(r.list_name == "Work" for r in linked)
        assert not screen.state.marked
        assert "reminders: 2 added, 0 completed" in str(screen.query_one("#triage-status").render())
        # complete one in "Reminders", reload, see it done, tick it in Bear
        await remctl._run("done", str(linked[0].id))
        await pilot.press("r")
        await wait_until(lambda: any(r.status == "done" for r in screen.state.rows))
        done_row = next(r for r in screen.state.rows if r.status == "done")
        screen.list_view.index = screen.list_view.children.index(next(i for i in screen._items if i.row is done_row))
        await pilot.pause()
        await pilot.press("x")
        await wait_until(lambda: done_row.todo.key not in {r.todo.key for r in screen.state.rows})
        content = (await client.cat("NOTE-PLANNING")).content
        assert f"- [x] {done_row.todo.text}" in content or f"  - [x] {done_row.todo.text}" in content


async def test_a_only_adds_rows_without_a_reminder(client, remctl, tmp_path):
    app = make(client, remctl, tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        screen = await open_triage(app, pilot)
        await pilot.press("a")  # highlighted row, unmarked
        await wait_until(lambda: screen.state.rows[0].status == "added")
        await pilot.press("a")  # same row again: nothing new
        await pilot.pause(0.5)
        assert len(await remctl.linked_reminders()) == 1


async def test_reminders_off_by_default_and_missing_remctl_degrades(client, tmp_path, monkeypatch):
    app = BjornApp(Config(poll_seconds=0, export_dir=tmp_path), client=client, environ={})
    assert not app.reminders_enabled
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        screen = await open_triage(app, pilot)
        assert not screen.state.reminders_enabled
        await pilot.press("a")
        await pilot.pause()
        assert isinstance(app.screen, TriageScreen)
    cfg = Config(poll_seconds=0, export_dir=tmp_path, reminders=RemindersConfig(enabled=True, remctl="/nonexistent/remctl"))
    app = BjornApp(cfg, client=client, environ={})
    assert app.remctl is None and not app.reminders_enabled


def test_reminders_config_section(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[reminders]\nenabled = true\nlist = "Bear"\ndue = ""\nremctl = "/opt/remctl"\n')
    cfg = Config.load(path)
    assert cfg.reminders == RemindersConfig(enabled=True, list="Bear", due="", remctl="/opt/remctl")
    assert Config.load(tmp_path / "none.toml").reminders == RemindersConfig()
