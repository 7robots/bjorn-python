"""Phase 21 acceptance gate: search-box completion against live Bear.

Headless run through the real bearcli. Exits non-zero on the first failed
check.

    uv run python tools/gate_search_box.py [tag-prefix]
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bjorn.app import BjornApp  # noqa: E402
from bjorn.bear import BearClient, resolve_bearcli  # noqa: E402
from bjorn.config import Config  # noqa: E402

TAG_PREFIX = sys.argv[1] if len(sys.argv) > 1 else "tec"
KEYS = {"@": "at", "#": "number_sign", " ": "space"}


def check(cond: bool, label: str) -> None:
    print(("ok   " if cond else "FAIL ") + label)
    if not cond:
        sys.exit(1)


async def wait_until(pred, timeout: float = 20.0) -> None:
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if pred():
            return
        await asyncio.sleep(0.05)
    raise SystemExit("timeout waiting for a condition")


async def type_text(pilot, text: str) -> None:
    for ch in text:
        await pilot.press(KEYS.get(ch, ch))


async def main() -> None:
    client = BearClient(resolve_bearcli(""))
    app = BjornApp(Config(poll_seconds=0), client=client, environ={})
    async with app.run_test(size=(140, 44)) as pilot:
        await wait_until(lambda: app.loaded and app.note_list.notes)
        await pilot.pause()
        box = app.note_list.search_input

        # 1. @to completes to @todo, → accepts, enter runs, every result has an open todo.
        await pilot.press("slash")
        await pilot.pause()
        check(app.note_list.hint_visible, "hint row shows with the box")
        await type_text(pilot, "@to")
        await wait_until(lambda: box._suggestion == "@todo")
        check(True, "@to suggests @todo")
        await pilot.press("right")
        await pilot.pause()
        check(box.value == "@todo", "→ accepts the completion")
        await pilot.press("enter")
        await wait_until(lambda: app.search_query == "@todo" and app.note_list.notes)
        notes = app.note_list.notes
        check(all(n.todos > 0 for n in notes), f"@todo lists {len(notes)} notes, all with open todos")

        # 2. A live tag completes.
        await pilot.press("slash")
        await pilot.pause()
        await type_text(pilot, "#" + TAG_PREFIX)
        await wait_until(lambda: box._suggestion.startswith("#" + TAG_PREFIX) and len(box._suggestion) > len(TAG_PREFIX) + 1)
        check(True, f"#{TAG_PREFIX} suggests {box._suggestion!r}")
        tags = app.query_tags()
        check(box._suggestion.lstrip("#").rstrip("#") in tags, "suggestion is a tag from the snapshot")

        # 3. esc hides the box and the hint.
        await pilot.press("escape")
        await wait_until(lambda: not app.note_list.search_open)
        check(not app.note_list.hint_visible, "esc hides the hint row")
    print("GATE PASSED")


if __name__ == "__main__":
    asyncio.run(main())
