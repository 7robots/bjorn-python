"""Apple Reminders through `remctl`, and the link between a todo and its reminder.

The link lives entirely on the Reminders side, exactly as remtui writes it: a
reminder created from a todo carries, in its notes, the note's `bear://` link
and a `bear-todo: <key>` line. Nothing is written into Bear on add. On every
triage load the reminders carrying a key are read back and joined to the
current todos on that key.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from .todos import Todo

ENV_COMMAND = "BJORN_REMCTL"
DEFAULT_COMMAND = "remctl"
KEY_PREFIX = "bear-todo:"
_KEY_RE = re.compile(rf"^{re.escape(KEY_PREFIX)}\s*([0-9a-f]{{6,40}})\s*$", re.MULTILINE)


class RemctlError(Exception):
    def __init__(self, message: str, *, exit_code: int = 1) -> None:
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code


def resolve_remctl(configured: str = "") -> str:
    return os.environ.get(ENV_COMMAND, "").strip() or configured.strip() or DEFAULT_COMMAND


def remctl_found(configured: str = "") -> bool:
    command = resolve_remctl(configured)
    return shutil.which(command) is not None or os.path.isfile(command)


def note_url(note_id: str) -> str:
    return f"bear://x-callback-url/open-note?id={note_id}"


def link_notes(todo: Todo) -> str:
    """The notes block written into a reminder created from `todo`: a line for
    a human, a clickable link, and the machine key `link_key` reads back."""
    return "\n".join(
        (
            f"From Bear: {todo.note_title}" if todo.note_title else "From Bear",
            note_url(todo.note_id),
            f"{KEY_PREFIX} {todo.key}",
        )
    )


def link_key(notes: str) -> str:
    match = _KEY_RE.search(notes or "")
    return match.group(1) if match else ""


@dataclass(frozen=True, slots=True)
class LinkedReminder:
    """The little we need of a reminder remctl serialised."""

    id: int
    title: str
    completed: bool
    key: str
    list_name: str = ""

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "LinkedReminder | None":
        key = link_key(str(data.get("notes") or ""))
        if not key:
            return None
        try:
            rid = int(data.get("id"))
        except (TypeError, ValueError):
            return None
        return cls(id=rid, title=str(data.get("title") or ""), completed=bool(data.get("completed")), key=key, list_name=str(data.get("list") or ""))


def join(todos: Iterable[Todo], reminders: Iterable[LinkedReminder]) -> dict[str, tuple[str, int]]:
    """todo key -> (status, reminder id) for todos that have a reminder.

    When several reminders share a key (the same todo added twice, say), an
    active one wins over a completed one so the row does not read as finished
    while work is still open.
    """
    by_key: dict[str, LinkedReminder] = {}
    for reminder in reminders:
        current = by_key.get(reminder.key)
        if current is None or (current.completed and not reminder.completed):
            by_key[reminder.key] = reminder
    out: dict[str, tuple[str, int]] = {}
    for todo in todos:
        reminder = by_key.get(todo.key)
        if reminder is not None:
            out[todo.key] = ("done" if reminder.completed else "added", reminder.id)
    return out


class RemctlClient:
    """Shells out to remctl. Reads parse `--json`; adds return the created id."""

    def __init__(self, command: str | Sequence[str] = DEFAULT_COMMAND) -> None:
        self.command: tuple[str, ...] = (command,) if isinstance(command, str) else tuple(command)
        self._write_lock = asyncio.Lock()

    async def _run(self, *args: str) -> str:
        try:
            proc = await asyncio.create_subprocess_exec(
                *self.command, *args,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, stdin=asyncio.subprocess.DEVNULL,
            )
        except FileNotFoundError as exc:
            raise RemctlError(f"remctl not found ({self.command[0]})") from exc
        try:
            stdout_b, stderr_b = await proc.communicate()
        except asyncio.CancelledError:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            with contextlib.suppress(Exception):
                await proc.wait()
            raise
        stdout, stderr = stdout_b.decode(), stderr_b.decode()
        if proc.returncode != 0:
            message = next((line.strip() for line in stderr.splitlines() if line.strip()), "") or stdout.strip()
            with contextlib.suppress(ValueError):
                payload = json.loads(stdout)
                if isinstance(payload, dict) and payload.get("message"):
                    message = str(payload["message"])
            raise RemctlError(message or "remctl failed", exit_code=proc.returncode or 1)
        return stdout

    async def linked_reminders(self) -> list[LinkedReminder]:
        """Every reminder, active or completed, created from a Bear todo."""
        out = await self._run("search", KEY_PREFIX, "--completed", "--json")
        try:
            rows = json.loads(out) if out.strip() else []
        except ValueError as exc:
            raise RemctlError(f"remctl returned invalid JSON: {exc}") from exc
        if isinstance(rows, dict):
            rows = rows.get("reminders") or rows.get("results") or []
        found = [LinkedReminder.from_json(r) for r in rows if isinstance(r, dict)]
        return [r for r in found if r is not None]

    async def add(self, todo: Todo, *, list_title: str = "", due: str = "") -> int | None:
        """Create the reminder for a todo; returns remctl's numeric id when given."""
        args = ["add", "--json"]
        if list_title:
            args += ["--list", list_title]
        if due:
            args += ["--due", due]
        args += ["--notes", link_notes(todo), "--", todo.text]
        async with self._write_lock:
            out = await self._run(*args)
        with contextlib.suppress(ValueError, TypeError):
            payload = json.loads(out)
            if isinstance(payload, dict):
                if payload.get("status") == "error":
                    raise RemctlError(str(payload.get("message") or "remctl add failed"))
                rid = payload.get("numericId", payload.get("id"))
                if isinstance(rid, int):
                    return rid
        return None
