"""Phase 3: global pin toggle and open in Bear."""

from __future__ import annotations

import json

from helpers import loaded, titles, wait_until


async def test_p_toggles_global_pin_and_resorts(make_app, client):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        assert titles(app)[0] == "Sprint Planning"
        await pilot.press("p")
        await wait_until(lambda: titles(app)[0] == "Garden Plan")
        assert not (await client.snapshot()).by_id("NOTE-PLANNING").pins
        assert app.note_list.current().id == "NOTE-PLANNING"
        await pilot.press("p")
        await wait_until(lambda: titles(app)[0] == "Sprint Planning")
        assert (await client.snapshot()).by_id("NOTE-PLANNING").pinned_globally


async def test_b_opens_the_note_in_bear(make_app, fake_state):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await pilot.press("b")
        log = fake_state.parent / "bear.json.opened"
        await wait_until(lambda: log.exists())
        assert json.loads(log.read_text().splitlines()[-1])["id"] == "NOTE-PLANNING"
