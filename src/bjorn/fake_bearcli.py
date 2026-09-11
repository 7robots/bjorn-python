#!/usr/bin/env python3
"""A local stand-in for bearcli, used by the test suite and `bjorn --demo`.

Implements the subset Bjorn drives with the real tool's contract: `--format
json` puts one JSON document on stdout for reads and `{"error": {...}}` for
their failures; writes print nothing on success and plain text on stderr
(exit 1) when they fail. State lives in a JSON file at $BJORN_FAKE_BEAR_STATE
(default ~/.cache/bjorn/demo-bear.json), seeded with sample notes on first run.
Every `app open` call is appended to `<state>.opened` so tests can assert on it.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

META_FIELDS = ("id", "title", "locked", "tags", "length", "created", "modified", "pins", "location", "todos", "done", "attachments")
DEFAULT_LIST_FIELDS = ("id", "title", "tags", "length")


#: A 1x1 transparent PNG, base64: the seeded attachment.
ONE_PIXEL_PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="


def state_path() -> Path:
    override = os.environ.get("BJORN_FAKE_BEAR_STATE")
    if override:
        return Path(override)
    return Path.home() / ".cache" / "bjorn" / "demo-bear.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def seed_state() -> dict:
    today = now_iso()
    notes = [
        {
            "id": "NOTE-PLANNING", "title": "Sprint Planning", "tags": ["work", "work/sprint"],
            "locked": False, "pins": ["global"], "location": "notes",
            "created": "2026-08-01T09:00:00Z", "modified": today,
            "content": (
                "# Sprint Planning\n#work/sprint\n\n"
                "## Tasks\n- [x] book the retro room\n- [ ] write the release notes\n"
                "- [ ] ask Priya about the API deprecation\n  - [ ] confirm the sunset date\n\n"
                "## Notes\nVelocity is ==holding== steady.\n"
            ),
        },
        {
            "id": "NOTE-GARDEN", "title": "Garden Plan", "tags": ["home", "home/garden"],
            "locked": False, "pins": ["#home"], "location": "notes",
            "created": "2026-07-12T09:00:00Z", "modified": "2026-08-28T10:00:00Z",
            "content": (
                "# Garden Plan\n#home/garden\n\n- [ ] order bulbs for the front bed\n- [x] mulch the roses\n\n"
                "## Next spring\n- [ ] move the hydrangea\n```\n- [ ] this is inside a code block\n```\n"
                "\n![](Front%20bed.png)\n"
            ),
            "attachments": ["Front bed.png"],
            "attachment_data": {"Front bed.png": ONE_PIXEL_PNG},
        },
        {
            "id": "NOTE-READING", "title": "Reading Queue", "tags": ["home"],
            "locked": False, "pins": [], "location": "notes",
            "created": "2026-06-01T09:00:00Z", "modified": "2026-08-15T12:00:00Z",
            "content": "# Reading Queue\n#home\n\nNo tasks here, just titles.\n\n" + "\n".join(f"- Book {i}" for i in range(1, 121)) + "\n",
        },
        {
            "id": "NOTE-DESIGN", "title": "CAD and Design", "tags": ["work", "work/CAD and Design"],
            "locked": False, "pins": [], "location": "notes",
            "created": "2026-05-01T09:00:00Z", "modified": "2026-08-01T12:00:00Z",
            "content": "# CAD and Design\n#work/CAD and Design#\n\nMulti-word tag note.\n",
        },
        {
            "id": "NOTE-UNTAGGED", "title": "Loose Thought", "tags": [],
            "locked": False, "pins": [], "location": "notes",
            "created": "2026-04-01T09:00:00Z", "modified": "2026-07-01T12:00:00Z",
            "content": "# Loose Thought\n\nNo tags on this one.\n",
        },
        {
            "id": "NOTE-TRASHED", "title": "Old Draft", "tags": ["work"],
            "locked": False, "pins": [], "location": "trash",
            "created": "2026-03-01T09:00:00Z", "modified": "2026-06-01T12:00:00Z",
            "content": "# Old Draft\n#work\n\nThrown away.\n",
        },
        {
            "id": "NOTE-ARCHIVED", "title": "Finished Project", "tags": ["work"],
            "locked": False, "pins": [], "location": "archive",
            "created": "2026-02-01T09:00:00Z", "modified": "2026-05-01T12:00:00Z",
            "content": "# Finished Project\n#work\n\nDone and dusted.\n",
        },
    ]
    return {"notes": notes, "next_id": 1}


def load_state() -> dict:
    path = state_path()
    if path.exists():
        return json.loads(path.read_text())
    state = seed_state()
    save_state(state)
    return state


def save_state(state: dict) -> None:
    """Atomic: `probe` runs two of us at once, and on first use both seed the
    file; a reader must never see a half-written one."""
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False))
    os.replace(tmp, path)


# -- output ----------------------------------------------------------------


def emit_json(payload) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def fail(fmt: str, code: str, message: str, exit_code: int = 1) -> None:
    if fmt == "json":
        emit_json({"error": {"code": code, "message": message}})
    else:
        print(f"Error: {message}", file=sys.stderr)
    sys.exit(exit_code)


def fail_text(message: str, exit_code: int = 1) -> None:
    print(f"Error: {message}", file=sys.stderr)
    sys.exit(exit_code)


def tsv_row(values) -> str:
    def cell(v):
        if isinstance(v, list):
            v = ",".join(str(x) for x in v)
        return str(v).replace("\\", "\\\\").replace("\n", "\\n").replace("\t", "\\t")

    return "\t".join(cell(v) for v in values)


# -- helpers ---------------------------------------------------------------


def content_hash(content: str) -> str:
    return hashlib.sha1(content.encode()).hexdigest()[:7]


def display_tags(note: dict) -> list[str]:
    out = []
    for tag in note.get("tags") or []:
        out.append(f"#{tag}#" if " " in tag else f"#{tag}")
    return out


def todo_counts(content: str) -> tuple[int, int]:
    open_, done = 0, 0
    for line in content.splitlines():
        if re.match(r"^\s*[-*+] \[ \]", line):
            open_ += 1
        elif re.match(r"^\s*[-*+] \[[xX]\]", line):
            done += 1
    return open_, done


def row_for(note: dict, fields) -> dict:
    todos, done = todo_counts(note.get("content", ""))
    full = {
        "id": note["id"], "title": note["title"], "locked": "yes" if note.get("locked") else "no",
        "tags": display_tags(note), "length": len(note.get("content", "")),
        "created": note.get("created"), "modified": note.get("modified"), "pins": note.get("pins") or [],
        "location": note.get("location", "notes"), "todos": todos, "done": done,
        "attachments": note.get("attachments") or [], "content": note.get("content", ""), "matches": 0,
    }
    return {f: full[f] for f in fields if f in full}


def parse_fields(spec: str | None, default, extra=()) -> list[str]:
    if not spec:
        return list(default)
    out: list[str] = []
    for f in spec.split(","):
        f = f.strip()
        if f == "all":
            out.extend(META_FIELDS)
            out.extend(extra)
        elif f:
            out.append(f)
    return out


def find_note(state: dict, note_id: str | None, title: str | None) -> dict | None:
    for note in state["notes"]:
        if note_id and note["id"] == note_id:
            return note
        if title and note["title"].casefold() == title.casefold():
            return note
    return None


def note_has_tag(note: dict, tag: str) -> bool:
    tag = tag.strip().strip("#").strip()
    return any(t == tag or t.startswith(tag + "/") for t in note.get("tags") or [])


def sort_notes(notes: list[dict], spec: str) -> list[dict]:
    for term in reversed([t.strip() for t in spec.split(",") if t.strip()]):
        field, _, direction = term.partition(":")
        reverse = direction == "desc" or (not direction and field in ("pinned", "modified"))
        if field == "pinned":
            notes.sort(key=lambda n: bool(n.get("pins")), reverse=reverse)
        elif field == "title":
            notes.sort(key=lambda n: n["title"].casefold(), reverse=reverse)
        else:
            notes.sort(key=lambda n: n.get(field) or "", reverse=reverse)
    return notes


def emit_rows(rows: list[dict], fields, fmt: str) -> None:
    if fmt == "json":
        emit_json(rows)
    elif fmt == "csv":
        print(",".join(fields))
        for r in rows:
            print(",".join(json.dumps(r.get(f)) for f in fields))
    else:
        if not rows:
            print("No notes found.", file=sys.stderr)
        for r in rows:
            print(tsv_row(r.get(f) for f in fields))


def in_location(note: dict, location: str) -> bool:
    return location == "all" or note.get("location", "notes") == location


# -- commands ----------------------------------------------------------------


def cmd_list(args, state):
    notes = [n for n in state["notes"] if in_location(n, args.location)]
    if args.tag:
        notes = [n for n in notes if note_has_tag(n, args.tag)]
    notes = sort_notes(notes, args.sort)
    total = len(notes)
    if args.count or args.limit == 0:
        if args.format == "json":
            emit_json({"count": total})
        else:
            print(total)
        return
    notes = notes[args.offset:]
    if args.limit is not None:
        notes = notes[: args.limit]
    fields = parse_fields(args.fields, DEFAULT_LIST_FIELDS)
    emit_rows([row_for(n, fields) for n in notes], fields, args.format)


def matches_query(note: dict, query: str) -> bool:
    todos, done = todo_counts(note.get("content", ""))
    today = datetime.now(timezone.utc).date().isoformat()
    for term in query.split():
        negate = term.startswith("-")
        term = term[1:] if negate else term
        if term.startswith("#"):
            ok = note_has_tag(note, term)
        elif term == "@todo":
            ok = todos > 0
        elif term == "@untagged":
            ok = not note.get("tags")
        elif term == "@tagged":
            ok = bool(note.get("tags"))
        elif term == "@today":
            ok = str(note.get("modified", "")).startswith(today)
        elif term == "@pinned":
            ok = "global" in (note.get("pins") or [])
        elif term.startswith("@"):
            ok = True
        else:
            ok = term.strip('"').casefold() in note.get("content", "").casefold()
        if ok == negate:
            return False
    return True


def cmd_search(args, state):
    query = args.query or args.query_arg or ""
    notes = [n for n in state["notes"] if in_location(n, args.location) and matches_query(n, query)]
    notes = sort_notes(notes, args.sort)
    if args.count:
        emit_json({"count": len(notes)}) if args.format == "json" else print(len(notes))
        return
    fields = parse_fields(args.fields, ("id", "title", "tags", "length", "matches"), extra=("matches",))
    emit_rows([row_for(n, fields) for n in notes[args.offset:][: args.limit]], fields, args.format)


def cmd_cat(args, state):
    note = find_note(state, args.note_id, args.title)
    if note is None:
        fail(args.format, "not_found", "Note not found")
    if note.get("locked"):
        fail(args.format, "locked", "Note is locked; content unavailable")
    content = note.get("content", "")
    if args.format == "json":
        emit_json({"content": content, "hash": content_hash(content)})
    else:
        sys.stdout.write(content)


def cmd_show(args, state):
    note = find_note(state, args.note_id, args.title)
    if note is None:
        fail(args.format, "not_found", "Note not found")
    fields = parse_fields(args.fields, ("id", "title", "tags"))
    row = row_for(note, fields)
    emit_json(row) if args.format == "json" else print(tsv_row(row.get(f) for f in fields))


def cmd_tags(args, state):
    if args.tags_cmd in (None, "list"):
        if args.note_id:
            note = find_note(state, args.note_id, None)
            if note is None:
                fail(args.format, "not_found", "Note not found")
            tags = display_tags(note)
        else:
            tags = sorted({t for n in state["notes"] if n.get("location", "notes") == "notes" for t in display_tags(n)}, key=str.casefold)
        rows = [{"tag": t} for t in tags]
        emit_json(rows) if args.format == "json" else print("\n".join(t for t in tags))
        return
    note = find_note(state, args.note_id, None)
    if note is None:
        fail_text("Note not found")
    wanted = [t.strip().strip("#").strip() for t in args.tag_names]
    if args.tags_cmd == "add":
        for t in wanted:
            parts = t.split("/")
            for i in range(len(parts)):
                anc = "/".join(parts[: i + 1])
                if anc not in note["tags"]:
                    note["tags"].append(anc)
        line = " ".join(f"#{t}#" if " " in t else f"#{t}" for t in wanted)
        lines = note["content"].splitlines()
        lines.insert(1 if lines and lines[0].startswith("# ") else 0, line)
        note["content"] = "\n".join(lines) + "\n"
    elif args.tags_cmd == "remove":
        note["tags"] = [t for t in note["tags"] if not any(t == w or t.startswith(w + "/") for w in wanted)]
    note["modified"] = now_iso()
    save_state(state)


def cmd_create(args, state):
    content = args.content if args.content is not None else sys.stdin.read()
    content = content.replace("\\n", "\n") if args.content is not None else content
    title = args.title
    if not title:
        first = next((l for l in content.splitlines() if l.strip()), "Untitled")
        title = first.lstrip("# ").strip()
    if args.if_not_exists:
        existing = find_note(state, None, title)
        if existing:
            fields = parse_fields(args.fields, ("id", "title", "tags"))
            emit_rows([row_for(existing, fields)], fields, args.format)
            return
    tags: list[str] = []
    for t in (args.tags or "").split(","):
        t = t.strip().strip("#").strip()
        if not t:
            continue
        parts = t.split("/")
        for i in range(len(parts)):
            anc = "/".join(parts[: i + 1])
            if anc not in tags:
                tags.append(anc)
    body = content
    if body.startswith(f"# {title}"):
        body = body[len(f"# {title}"):].lstrip("\n")
    leaf_tags = [t for t in tags if not any(o != t and o.startswith(t + "/") for o in tags)]
    tag_line = " ".join(f"#{t}#" if " " in t else f"#{t}" for t in leaf_tags)
    full = f"# {title}\n" + (tag_line + "\n\n" if tag_line else "\n") + body
    if not full.endswith("\n"):
        full += "\n"
    nid = f"NEW-{state.get('next_id', 1):04d}"
    state["next_id"] = state.get("next_id", 1) + 1
    note = {
        "id": nid, "title": title, "tags": tags, "locked": False, "pins": [], "location": "notes",
        "created": now_iso(), "modified": now_iso(), "content": full,
    }
    state["notes"].insert(0, note)
    save_state(state)
    fields = parse_fields(args.fields, ("id", "title", "tags"))
    if args.format == "json":
        emit_json(row_for(note, fields))
    else:
        print(tsv_row(row_for(note, fields).get(f) for f in fields))


def cmd_overwrite(args, state):
    note = find_note(state, args.note_id, args.title)
    if note is None:
        fail_text("Note not found")
    content = args.content.replace("\\n", "\n") if args.content is not None else sys.stdin.read()
    if args.base and args.base != content_hash(note.get("content", "")):
        fail_text("Note has changed since last read. Read it again before writing.")
    note["content"] = content
    first = next((l for l in content.splitlines() if l.startswith("# ")), None)
    if first:
        note["title"] = first[2:].strip()
    tags: list[str] = []
    for m in re.finditer(r"(?m)^#(?![# ])([^\n#]*?)#(?=\s|$)|(?<!\S)#(?![# ])([^\s#]+)", content):
        t = (m.group(1) or m.group(2) or "").strip()
        if not t or re.match(r"^#{1,6} ", content.splitlines()[0] if content else ""):
            pass
        if t:
            parts = t.split("/")
            for i in range(len(parts)):
                anc = "/".join(parts[: i + 1])
                if anc not in tags:
                    tags.append(anc)
    note["tags"] = tags
    if not args.no_update_modified:
        note["modified"] = now_iso()
    save_state(state)


def cmd_edit(args, state):
    note = find_note(state, args.note_id, args.title)
    if note is None:
        fail_text("Note not found")
    find = args.find.replace("\\n", "\n")
    content = note["content"]
    start, end = 0, len(content)
    if args.section:
        heading = args.section.replace("\\n", "\n").strip()
        lines = content.split("\n")
        level = len(heading) - len(heading.lstrip("#"))
        starts = [i for i, l in enumerate(lines) if l.strip() == heading]
        if len(starts) != 1:
            fail_text("Section not found" if not starts else "Section address is ambiguous")
        first = starts[0]
        last = len(lines)
        for j in range(first + 1, len(lines)):
            m = re.match(r"^(#{1,6}) ", lines[j])
            if m and len(m.group(1)) <= level:
                last = j
                break
        start = len("\n".join(lines[:first])) + (1 if first else 0)
        end = len("\n".join(lines[:last]))
    region = content[start:end]
    if region.count(find) == 0:
        fail_text("Find text not found")
    if region.count(find) > 1 and not args.all:
        fail_text("Find text matches more than once")
    if args.replace is not None:
        repl = args.replace.replace("\\n", "\n")
    elif args.delete:
        repl = ""
    else:
        fail_text("edit needs --replace or --delete")
    region = region.replace(find, repl) if args.all else region.replace(find, repl, 1)
    note["content"] = content[:start] + region + content[end:]
    note["modified"] = now_iso()
    save_state(state)


def move(args, state, location: str):
    note = find_note(state, args.note_id, args.title)
    if note is None:
        fail_text("Note not found")
    note["location"] = location
    save_state(state)


def cmd_pin(args, state):
    if args.pin_cmd in (None, "list"):
        if args.note_id:
            note = find_note(state, args.note_id, None)
            if note is None:
                fail(args.format, "not_found", "Note not found")
            rows = [{"pin": p} for p in note.get("pins") or []]
        else:
            rows = [{"pin": p} for p in sorted({p for n in state["notes"] for p in n.get("pins") or []})]
        emit_json(rows) if args.format == "json" else print("\n".join(r["pin"] for r in rows))
        return
    note = find_note(state, args.note_id, None)
    if note is None:
        fail_text("Note not found")
    pins = list(note.get("pins") or [])
    for target in args.targets:
        label = "global" if target == "global" else f"#{target.strip('#')}"
        if args.pin_cmd == "add" and label not in pins:
            pins.append(label)
        if args.pin_cmd == "remove" and label in pins:
            pins.remove(label)
    note["pins"] = pins
    save_state(state)


def cmd_attachments(args, state):
    note = find_note(state, args.note_id, args.title)
    if note is None:
        fail(getattr(args, "format", "tsv"), "not_found", "Note not found")
    if args.att_cmd in (None, "list"):
        rows = [{"filename": name, "size": len(base64.b64decode((note.get("attachment_data") or {}).get(name, "")))} for name in note.get("attachments") or []]
        fields = parse_fields(args.fields, ("filename", "size"))
        emit_rows([{f: r[f] for f in fields if f in r} for r in rows], fields, args.format)
        return
    if args.att_cmd == "save":
        if sys.stdout.isatty():
            fail_text("Refusing to write binary data to a terminal; redirect stdout.")
        data = (note.get("attachment_data") or {}).get(args.filename)
        if data is None or args.filename not in (note.get("attachments") or []):
            fail_text("Attachment not found")
        sys.stdout.buffer.write(base64.b64decode(data))
        sys.stdout.flush()
        return
    fail_text("unsupported attachments subcommand", 64)


def cmd_app(args, state):
    if args.app_cmd == "open":
        note = find_note(state, args.note_id, args.title)
        if note is None:
            fail_text("Note not found")
        log = Path(str(state_path()) + ".opened")
        with log.open("a") as fh:
            fh.write(json.dumps({"id": note["id"], "header": args.header}) + "\n")
        return
    fail_text("unsupported app subcommand", 64)


# -- argv ----------------------------------------------------------------------


def add_format(p, default_fields_help=""):
    p.add_argument("--format", choices=("tsv", "csv", "json"), default="tsv")
    p.add_argument("--fields", default=None)


def add_listing(p):
    p.add_argument("-s", "--sort", default="pinned,modified")
    p.add_argument("-n", "--limit", type=int, default=None)
    p.add_argument("-o", "--offset", type=int, default=0)
    p.add_argument("-l", "--location", choices=("notes", "trash", "archive", "all"), default="notes")
    p.add_argument("--count", action="store_true")
    add_format(p)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bearcli")
    parser.add_argument("-v", "--version", action="version", version="fake")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("list"); add_listing(p); p.add_argument("--tag", default=None); p.set_defaults(func=cmd_list)
    p = sub.add_parser("search"); p.add_argument("query_arg", nargs="?"); p.add_argument("-q", "--query", default=None); add_listing(p); p.set_defaults(func=cmd_search)
    p = sub.add_parser("cat"); p.add_argument("note_id", nargs="?"); p.add_argument("-t", "--title"); p.add_argument("--section"); add_format(p); p.set_defaults(func=cmd_cat)
    p = sub.add_parser("show"); p.add_argument("note_id", nargs="?"); p.add_argument("-t", "--title"); add_format(p); p.set_defaults(func=cmd_show)
    p = sub.add_parser("tags"); ts = p.add_subparsers(dest="tags_cmd")
    for name in ("list", "add", "remove"):
        q = ts.add_parser(name); q.add_argument("note_id", nargs="?"); q.add_argument("tag_names", nargs="*"); add_format(q)
    add_format(p); p.set_defaults(func=cmd_tags, note_id=None, tag_names=[])
    p = sub.add_parser("create"); p.add_argument("title", nargs="?"); p.add_argument("-c", "--content", default=None); p.add_argument("--tags", default=None); p.add_argument("--if-not-exists", action="store_true"); add_format(p); p.set_defaults(func=cmd_create)
    p = sub.add_parser("overwrite"); p.add_argument("note_id", nargs="?"); p.add_argument("-t", "--title"); p.add_argument("-c", "--content", default=None); p.add_argument("--base", default=None); p.add_argument("--section"); p.add_argument("--no-update-modified", action="store_true"); p.add_argument("--force", action="store_true"); p.set_defaults(func=cmd_overwrite)
    p = sub.add_parser("edit"); p.add_argument("note_id", nargs="?"); p.add_argument("-t", "--title"); p.add_argument("--section"); p.add_argument("--find", required=True); p.add_argument("--replace", default=None); p.add_argument("--delete", action="store_true"); p.add_argument("--all", action="store_true"); p.add_argument("--no-update-modified", action="store_true"); p.set_defaults(func=cmd_edit)
    for name, loc in (("trash", "trash"), ("archive", "archive"), ("restore", "notes")):
        p = sub.add_parser(name); p.add_argument("note_id", nargs="?"); p.add_argument("-t", "--title"); p.set_defaults(func=lambda a, s, loc=loc: move(a, s, loc))
    p = sub.add_parser("pin"); ps = p.add_subparsers(dest="pin_cmd")
    for name in ("list", "add", "remove"):
        q = ps.add_parser(name); q.add_argument("note_id", nargs="?"); q.add_argument("targets", nargs="*"); add_format(q)
    add_format(p); p.set_defaults(func=cmd_pin, note_id=None, targets=[])
    p = sub.add_parser("attachments"); ats = p.add_subparsers(dest="att_cmd")
    q = ats.add_parser("list"); q.add_argument("note_id", nargs="?"); q.add_argument("-t", "--title"); add_format(q)
    q = ats.add_parser("save"); q.add_argument("note_id", nargs="?"); q.add_argument("-t", "--title"); q.add_argument("-f", "--filename", required=True)
    add_format(p); p.set_defaults(func=cmd_attachments, note_id=None, title=None, filename=None)
    p = sub.add_parser("app"); aps = p.add_subparsers(dest="app_cmd")
    q = aps.add_parser("open"); q.add_argument("note_id", nargs="?"); q.add_argument("-t", "--title"); q.add_argument("--header"); q.add_argument("--edit", action="store_true"); q.add_argument("--new-window", action="store_true")
    p.set_defaults(func=cmd_app)
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 64 if exc.code not in (0, None) else 0
    if not getattr(args, "cmd", None):
        parser.print_help()
        return 64
    if not hasattr(args, "format"):
        args.format = "tsv"
    state = load_state()
    args.func(args, state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
