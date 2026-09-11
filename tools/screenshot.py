#!/usr/bin/env python3
"""Render docs/screenshot.svg from an invented library through the fake bearcli.

    uv run python tools/screenshot.py [output.svg]

Nothing here touches Bear: the notes are made up and live in a temp state file.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bjorn.app import BjornApp  # noqa: E402
from bjorn.bear import BearClient  # noqa: E402
from bjorn.config import Config, RemindersConfig  # noqa: E402
from bjorn.reminders import RemctlClient  # noqa: E402
from bjorn.widgets.triage import TriageScreen  # noqa: E402

FAKE = ROOT / "src" / "bjorn" / "fake_bearcli.py"
FAKE_REMCTL = ROOT / "src" / "bjorn" / "fake_remctl.py"


def stamp(days: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def note(id_: str, title: str, tags: list[str], body: str, *, days: float, pins: list[str] | None = None, location: str = "notes") -> dict:
    leaf = [t for t in tags if not any(o != t and o.startswith(t + "/") for o in tags)]
    tag_line = " ".join(f"#{t}#" if " " in t else f"#{t}" for t in leaf)
    return {
        "id": id_, "title": title, "tags": tags, "locked": False, "pins": pins or [], "location": location,
        "created": stamp(days + 30), "modified": stamp(days),
        "content": f"# {title}\n{tag_line}\n\n{body}",
    }


NOTES = [
    note("N1", "Greenhouse Build Log", ["garden", "garden/greenhouse"], (
        "## Frame\n"
        "The 2×4 frame went up over the weekend. Corners are braced with 45° gussets; the ridge beam is a single 12' piece.\n\n"
        "- [x] level the footings\n- [x] raise the end walls\n- [ ] hang the door\n- [ ] run the drip line from the rain barrel\n\n"
        "## Glazing\n"
        "Twin-wall polycarbonate, 8 mm. Order from the supplier in ==Portland==, not the big-box store: the UV coating is on one side only and theirs is labelled.\n\n"
        "| Panel | Size | Qty |\n|---|---|---|\n| Roof | 4' × 8' | 6 |\n| Side | 4' × 6' | 8 |\n| Gable | custom | 2 |\n\n"
        "## Notes\n"
        "> A greenhouse is a promise you make to February.\n\n"
        "Ventilation math: one square foot of vent per ten square feet of floor. That's 24 ft², so two 12 ft² louvres, one high on each gable.\n"
    ), days=0.1, pins=["global"]),
    note("N2", "Reading Queue", ["books"], "- *The Overstory*, Richard Powers\n- *Braiding Sweetgrass*, Robin Wall Kimmerer\n- *The Dawn of Everything*, Graeber & Wengrow\n", days=1.2),
    note("N3", "Sourdough Schedule", ["kitchen", "kitchen/bread"], "Feed at 8, mix at 9, fold every 30 min until noon, shape at 1, fridge overnight, bake at 7.\n\n- [ ] buy rye flour\n", days=2.5, pins=["#kitchen"]),
    note("N4", "Robot Drivetrain Ideas", ["robotics", "robotics/drivetrain"], "Mecanum vs. swerve for this season. Swerve needs four more motors.\n\n- [ ] price the swerve modules\n- [ ] ask the team about the mecanum wear\n", days=3),
    note("N5", "Meeting with Dana", ["work", "work/1on1"], "Talked through the Q4 roadmap. Dana wants the migration done before the freeze.\n\n- [ ] send the draft plan\n- [x] book the follow-up\n", days=4),
    note("N6", "Trail Notes: Ridge Loop", ["outdoors", "outdoors/hikes"], "11.2 miles, 2,400 ft. Water at mile 4 and mile 8. The upper switchbacks were icy.\n", days=6),
    note("N7", "Home Network Map", ["tech", "tech/homelab"], "```\nrouter ── switch ── nas\n            └── pi (dns)\n```\n", days=9),
    note("N8", "Compost Ratios", ["garden"], "Browns to greens about 3:1 by volume. Turn weekly.\n", days=12),
    note("N9", "Ideas for Winter Soups", ["kitchen"], "Parsnip and apple. Black bean with lime. Leek and potato.\n", days=15),
    note("N10", "Camera Settings Cheat Sheet", ["tech", "tech/photo"], "Golden hour: f/4, 1/250, ISO 200.\n", days=20),
    note("N11", "Loose Thought", [], "Untagged, for now.\n", days=25),
    note("N12", "Old Garden Plan", ["garden"], "Superseded by the greenhouse log.\n", days=60, location="trash"),
]


async def main(out: Path, triage_out: Path | None) -> None:
    tmp = Path(tempfile.mkdtemp(prefix="bjorn-shot-"))
    state = tmp / "bear.json"
    state.write_text(json.dumps({"notes": NOTES, "next_id": 1}))
    os.environ["BJORN_FAKE_BEAR_STATE"] = str(state)
    os.environ["BJORN_FAKE_REMCTL_STATE"] = str(tmp / "reminders.json")
    client = BearClient([sys.executable, str(FAKE)])
    remctl = RemctlClient([sys.executable, str(FAKE_REMCTL)])
    config = Config(poll_seconds=0, icon_style="emoji", reminders=RemindersConfig(enabled=True, list="Work"))
    app = BjornApp(config, client=client, remctl=remctl, environ={})
    async with app.run_test(size=(132, 38)) as pilot:
        for _ in range(100):
            await pilot.pause(0.05)
            if app.loaded and app.note_list.notes:
                break
        app.note_list.list_view.focus()
        await pilot.pause(0.8)
        await pilot.press("enter")
        await pilot.pause(0.8)
        app.note_list.list_view.focus()
        await pilot.pause(0.3)
        app.save_screenshot(filename=out.name, path=str(out.parent))
        print(out)
        if triage_out is not None:
            await pilot.press("t")
            for _ in range(100):
                await pilot.pause(0.05)
                if isinstance(app.screen, TriageScreen) and app.screen.state.rows:
                    break
            await pilot.pause(0.5)
            # one reminder already made, one marked, to show the glyphs
            await pilot.press("a")
            for _ in range(60):
                await pilot.pause(0.05)
                if any(r.status == "added" for r in app.screen.state.rows):
                    break
            await pilot.press("j")
            await pilot.press("j")
            await pilot.press("space")
            await pilot.pause(0.5)
            app.save_screenshot(filename=triage_out.name, path=str(triage_out.parent))
            print(triage_out)


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "screenshot.svg"
    triage = ROOT / "docs" / "screenshot-triage.svg" if len(sys.argv) <= 1 else None
    asyncio.run(main(target, triage))
