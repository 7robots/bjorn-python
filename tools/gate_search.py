"""Phase 18 acceptance gate: search highlighting and jump-to-match against live Bear.

Runs the app headlessly through the real bearcli. Exits non-zero on the first
failed check; prints one line per check otherwise.

    uv run python tools/gate_search.py [body-only-term] [title-term]
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bjorn.app import BjornApp  # noqa: E402
from bjorn.bear import BearClient, resolve_bearcli  # noqa: E402
from bjorn.config import Config  # noqa: E402
from bjorn.search import MATCH_STYLE  # noqa: E402
from bjorn.widgets.note_list import NoteItem  # noqa: E402

BODY_TERM = sys.argv[1] if len(sys.argv) > 1 else "hash-guarded"
TITLE_TERM = sys.argv[2] if len(sys.argv) > 2 else "Bjorn"


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
    raise SystemExit("timeout waiting for: " + getattr(pred, "__name__", "condition"))


async def run_search(app, pilot, query: str) -> None:
    app.note_list.open_search()
    await pilot.pause()
    app.note_list.search_input.value = query
    await pilot.press("enter")


def header(app) -> str:
    return str(app.note_view.query_one("#note-header").render())


def row_highlights(app, note_id: str) -> list[str]:
    item = next(i for i in app.note_list.list_view.query(NoteItem) if i.note.id == note_id)
    text = item.render()
    return [text.plain[s.start:s.end] for s in text.spans if str(s.style) == MATCH_STYLE]


async def main() -> None:
    client = BearClient(resolve_bearcli(""))
    app = BjornApp(Config(poll_seconds=0), client=client, environ={})
    async with app.run_test(size=(140, 44)) as pilot:
        await wait_until(lambda: app.loaded and app.note_list.notes)
        await pilot.pause()
        total = len(app.note_list.notes)

        # 1. A body-only term lists the note and the reader highlights it.
        await run_search(app, pilot, BODY_TERM)
        await wait_until(lambda: app.search_query == BODY_TERM and app.note_list.notes and len(app.note_list.notes) < total)
        listed = app.note_list.notes
        check(all(BODY_TERM.lower() not in n.title.lower() for n in listed), f"“{BODY_TERM}” lists {len(listed)} note(s), none by title")
        await wait_until(lambda: app.note_view.note is not None and app.note_view.note.id == listed[0].id and app.note_view.matches)
        blocks = app.note_view.matches
        check(all(any(str(s.style) == MATCH_STYLE for s in b._content.spans) for b in blocks), f"reader highlights {len(blocks)} block(s)")
        check(BODY_TERM.lower() in blocks[0]._content.plain.lower(), "first matching block holds the term")
        n = len(blocks)
        check(("1 match" if n == 1 else f"{n} matches") in header(app), f"header counts: {header(app)!r}")
        check(row_highlights(app, listed[0].id) == [], "list row shows no highlight for a body-only match")

        # 2. ] and [ move the reader. A truncated note renders its tail on the
        # first jump, so the count can grow here.
        await pilot.press("right_square_bracket")
        await wait_until(lambda: app.note_view.match_index == 0 and app.focused is app.note_view.scroll_view)
        n = len(app.note_view.matches)
        check(f"match 1/{n}" in header(app), f"] → {header(app)!r}, reader focused")
        y_first = app.note_view.scroll_view.scroll_y
        if n > 1:
            await pilot.press("right_square_bracket")
            await wait_until(lambda: app.note_view.match_index == 1)
            check(f"match 2/{n}" in header(app), "] again → match 2")
            await pilot.press("left_square_bracket")
            await wait_until(lambda: app.note_view.match_index == 0)
            check(app.note_view.scroll_view.scroll_y == y_first, "[ returns to the first match's position")
        else:
            await pilot.press("left_square_bracket")
            await pilot.pause()
            check(app.note_view.match_index == 0, "[ with a single match stays on it")

        # 3. A title term highlights the list row.
        await run_search(app, pilot, TITLE_TERM)
        await wait_until(lambda: app.search_query == TITLE_TERM and app.note_list.notes)
        await pilot.pause()
        titled = [x for x in app.note_list.notes if TITLE_TERM.lower() in x.title.lower()]
        check(bool(titled), f"“{TITLE_TERM}” lists a note with it in the title")
        hits = row_highlights(app, titled[0].id)
        check(any(h.lower() == TITLE_TERM.lower() for h in hits), f"row highlights {hits!r}")

        # 4. esc clears everything.
        app.note_list.list_view.focus()
        await pilot.press("escape")
        await wait_until(lambda: app.search_query == "" and app.note_view.pattern is None and len(app.note_list.notes) == total)
        await pilot.pause()
        check(app.note_view.matches == [] and app.note_list._pattern is None, "esc: no pattern, no matches")
        check(all(row_highlights(app, x.id) == [] for x in app.note_list.notes[:20]), "esc: first rows are plain")
        check("match" not in header(app), "esc: header has no match count")
    print("GATE PASSED")


if __name__ == "__main__":
    asyncio.run(main())
