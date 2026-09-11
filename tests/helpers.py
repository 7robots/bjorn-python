"""Test helpers: a wait loop and small accessors shared by the UI tests."""

from __future__ import annotations

import asyncio

from bjorn.app import BjornApp


async def wait_until(predicate, *, timeout: float = 5.0, interval: float = 0.05) -> None:
    """Poll a predicate; worker.wait_for_complete hangs on exclusive groups."""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return
        await asyncio.sleep(interval)
    raise AssertionError("condition not met within timeout")


async def loaded(app: BjornApp, pilot) -> None:
    await wait_until(lambda: app.loaded and app.note_list.notes)
    await pilot.pause()


def titles(app: BjornApp) -> list[str]:
    return [n.title for n in app.note_list.notes]
