"""Open todo items in Bear notes: the model, the parser, and the keys.

Ported from remtui so that the key a reminder carries (`bear-todo: <key>`) is
identical between the two tools and existing reminders join up unchanged.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Iterable

_TODO_RE = re.compile(r"^(?P<indent>\s*)(?P<bullet>[-*+]) \[ \]\s+(?P<text>\S.*?)\s*$")
_HEADING_RE = re.compile(r"^#{1,6} \S")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")


@dataclass(frozen=True, slots=True)
class Todo:
    """One open `- [ ]` line in a Bear note."""

    note_id: str
    note_title: str
    note_tags: tuple[str, ...]
    text: str
    #: The full line as written, indentation included: what `edit --find` needs.
    line: str
    #: The nearest heading line above the todo, `#` markers and all, or "" when
    #: the todo sits above every heading. Doubles as a bearcli section address.
    section: str = ""

    @property
    def normalized(self) -> str:
        return " ".join(self.text.split()).casefold()

    @property
    def key(self) -> str:
        """Stable id shared with the reminder created from this todo. Rewording
        the item in Bear yields a new key (and orphans the old reminder)."""
        digest = hashlib.sha1(f"{self.note_id}\n{self.normalized}".encode()).hexdigest()
        return digest[:12]

    @property
    def done_line(self) -> str:
        return self.line.replace("[ ]", "[x]", 1)

    @property
    def header(self) -> str:
        """The section heading without its `#` markers, for `app open --header`."""
        return self.section.lstrip("#").strip()


def parse_todos(content: str, *, note_id: str, note_title: str, note_tags: Iterable[str] = ()) -> list[Todo]:
    """Extract open todos from a note body, in document order.

    Fenced code blocks are skipped. Nested todos count like top-level ones; a
    checked parent does not hide its open children.
    """
    tags = tuple(note_tags)
    todos: list[Todo] = []
    section = ""
    in_fence = False
    for raw in content.splitlines():
        if _FENCE_RE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if _HEADING_RE.match(raw):
            section = raw.strip()
            continue
        match = _TODO_RE.match(raw)
        if match is None:
            continue
        todos.append(
            Todo(
                note_id=note_id,
                note_title=note_title,
                note_tags=tags,
                text=match.group("text"),
                line=raw.rstrip(),
                section=section,
            )
        )
    return todos


@dataclass(frozen=True, slots=True)
class TodoScan:
    """What a triage read of Bear produced."""

    todos: tuple[Todo, ...]
    #: Notes whose content bearcli could not read (locked or encrypted).
    locked: int = 0
    #: Notes with open todos, in list order.
    notes: int = 0


def scan_rows(rows: Iterable[dict[str, Any]]) -> TodoScan:
    """Turn `bearcli search "@todo" --fields id,title,tags,locked,content` rows
    into todos, in the order bearcli returned the notes."""
    from .bear import _is_yes, normalize_tag

    todos: list[Todo] = []
    locked = 0
    notes = 0
    for row in rows:
        if _is_yes(row.get("locked")) or row.get("content") is None:
            locked += 1
            continue
        found = parse_todos(
            str(row.get("content") or ""),
            note_id=str(row.get("id") or ""),
            note_title=str(row.get("title") or "").strip() or "Untitled",
            note_tags=[normalize_tag(str(t)) for t in row.get("tags") or ()],
        )
        if found:
            notes += 1
        todos.extend(found)
    return TodoScan(tuple(todos), locked, notes)
