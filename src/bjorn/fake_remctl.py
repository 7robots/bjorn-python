#!/usr/bin/env python3
"""A local stand-in for remctl, for the test suite.

Implements the subset Bjorn drives with the real tool's contract: `search
--json` prints a JSON array of reminders on stdout, `add --json` prints a
compact status object, `done <id>` completes one, errors are plain text on
stderr with exit 1. State lives at $BJORN_FAKE_REMCTL_STATE (default
~/.cache/bjorn/demo-reminders.json).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path


def state_path() -> Path:
    override = os.environ.get("BJORN_FAKE_REMCTL_STATE")
    return Path(override) if override else Path.home() / ".cache" / "bjorn" / "demo-reminders.json"


def load_state() -> dict:
    path = state_path()
    if path.exists():
        return json.loads(path.read_text())
    state = {"lists": ["Reminders", "Work"], "reminders": [], "next_id": 1}
    save_state(state)
    return state


def save_state(state: dict) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def serialize(row: dict) -> dict:
    out = {
        "id": row["id"], "title": row["title"], "list": row["list"], "completed": bool(row.get("completed")),
        "flagged": False, "urgent": False, "priority": "none", "subtaskCount": 0, "isSubtask": False,
    }
    if row.get("notes"):
        out["notes"] = row["notes"]
    if row.get("dueDate"):
        out["dueDate"] = row["dueDate"]
    return out


def fail(message: str, code: int = 1) -> None:
    print(f"Error: {message}", file=sys.stderr)
    sys.exit(code)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="remctl")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("search"); p.add_argument("query"); p.add_argument("--completed", action="store_true"); p.add_argument("--json", action="store_true")
    p = sub.add_parser("add"); p.add_argument("title"); p.add_argument("-l", "--list", dest="list_name"); p.add_argument("-n", "--notes", default=""); p.add_argument("-d", "--due"); p.add_argument("--json", action="store_true")
    p = sub.add_parser("done"); p.add_argument("id", type=int)
    p = sub.add_parser("lists"); p.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    state = load_state()
    reminders = state["reminders"]

    if args.command == "search":
        pool = reminders if args.completed else [r for r in reminders if not r.get("completed")]
        needle = args.query.casefold()
        hits = [serialize(r) for r in pool if needle in r["title"].casefold() or needle in (r.get("notes") or "").casefold()]
        print(json.dumps(hits, ensure_ascii=False))
    elif args.command == "add":
        list_name = args.list_name or state["lists"][0]
        if list_name not in state["lists"]:
            fail(f"list '{list_name}' not found")
        if args.due and args.due not in ("today", "tomorrow") and not args.due[:4].isdigit():
            print(json.dumps({"status": "error", "message": f"invalid due date '{args.due}'"}))
            return 2
        row = {"id": state["next_id"], "title": args.title, "list": list_name, "completed": False, "notes": args.notes,
               "dueDate": datetime.now().strftime("%Y-%m-%dT09:00:00") if args.due else ""}
        state["next_id"] += 1
        reminders.append(row)
        save_state(state)
        print(json.dumps({"status": "created", "id": f"FAKE-CK-{row['id']}", "title": row["title"], "numericId": row["id"]}))
    elif args.command == "done":
        for r in reminders:
            if r["id"] == args.id:
                r["completed"] = True
                save_state(state)
                print(json.dumps({"status": "completed", "numericId": args.id}))
                return 0
        fail(f"#{args.id} not found")
    elif args.command == "lists":
        print(json.dumps([{"id": i + 1, "title": t} for i, t in enumerate(state["lists"])]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
