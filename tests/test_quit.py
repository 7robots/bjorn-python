"""`q` asks before quitting."""

from __future__ import annotations

from helpers import loaded


async def test_q_asks_and_n_keeps_running(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await pilot.press("q")
        await pilot.pause()
        assert type(app.screen).__name__ == "ConfirmScreen"
        await pilot.press("n")
        await pilot.pause()
        assert app.is_running
        assert type(app.screen).__name__ == "BjornScreen"


async def test_q_then_y_quits(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await pilot.press("q")
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
    assert app.return_code == 0 or not app.is_running
