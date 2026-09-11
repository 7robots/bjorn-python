"""Async wrapper around bearcli, and the note models it produces.

bearcli reads and writes Bear's SQLite database directly, so everything here
works with Bear closed except `open_in_app`. Reads use `--format json`, where
every command emits one JSON document on stdout, errors included as
`{"error": {...}}`. Writes print nothing on success and a plain-text line on
stderr when they fail. Both shapes become `BearError`.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Sequence

from .render import preview

ENV_COMMAND = "BJORN_BEARCLI"
DEFAULT_COMMAND = "bearcli"

#: Where Bear ships bearcli. Used when nothing on PATH is called `bearcli`.
APP_BUNDLE_COMMANDS = (
    "/Applications/Bear.app/Contents/MacOS/bearcli",
    os.path.expanduser("~/Applications/Bear.app/Contents/MacOS/bearcli"),
)

#: Every metadata field `list` can return. Content is fetched separately.
LIST_FIELDS = "id,title,locked,tags,length,created,modified,pins,location,todos,done,attachments"
#: When more notes than this need a fresh preview, one `list` with content is
#: cheaper than a `cat` apiece.
PREVIEW_CAT_LIMIT = 24
#: How many `cat` processes run at once while previews are refreshed.
PREVIEW_CAT_CONCURRENCY = 6
#: bearcli stamps `modified` to the second, so a note edited twice within one
#: second keeps its stamp. Anything modified this recently is never trusted
#: from a stamp-keyed cache.
RECENT_SECONDS = 2.0

#: The stderr line bearcli prints when `--base` no longer matches.
_STALE_TEXT = "has changed since last read"


class BearError(Exception):
    """A bearcli invocation failed."""

    def __init__(self, message: str, *, code: str = "", exit_code: int = 1) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.exit_code = exit_code

    @property
    def is_conflict(self) -> bool:
        return self.code == "conflict"


def resolve_bearcli(configured: str = "") -> str:
    """The bearcli to run: `$BJORN_BEARCLI`, else the config value, else PATH, else inside Bear.app."""
    explicit = os.environ.get(ENV_COMMAND, "").strip() or configured.strip()
    if explicit:
        return explicit
    if shutil.which(DEFAULT_COMMAND) is not None:
        return DEFAULT_COMMAND
    for candidate in APP_BUNDLE_COMMANDS:
        if os.access(candidate, os.X_OK):
            return candidate
    return DEFAULT_COMMAND


def bearcli_found(configured: str = "") -> bool:
    return shutil.which(resolve_bearcli(configured)) is not None


class Location(str, Enum):
    NOTES = "notes"
    ARCHIVE = "archive"
    TRASH = "trash"


def normalize_tag(tag: str) -> str:
    """`#work/CAD and Design#` -> `work/CAD and Design`.

    Bear writes multi-word tags with a closing `#`; bearcli accepts either form
    on input. Internally tags are stored bare.
    """
    tag = tag.strip()
    if tag.startswith("#"):
        tag = tag[1:]
    if tag.endswith("#"):
        tag = tag[:-1]
    return tag.strip()


def display_tag(tag: str) -> str:
    """Bare tag back to the form Bear shows, closing `#` for multi-word tags."""
    tag = normalize_tag(tag)
    return f"#{tag}#" if " " in tag else f"#{tag}"


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def recently_modified(when: datetime | str | None, now: datetime | None = None) -> bool:
    """Was `when` within RECENT_SECONDS of now? The stamp may still move."""
    if isinstance(when, str):
        when = _parse_time(when)
    if when is None:
        return False
    now = now or datetime.now(timezone.utc)
    return (now - when).total_seconds() < RECENT_SECONDS


def _is_yes(value: Any) -> bool:
    """bearcli's JSON writes `locked` as the strings "yes"/"no"."""
    if isinstance(value, str):
        return value.strip().lower() in {"yes", "true", "1"}
    return bool(value)


@dataclass(frozen=True, slots=True)
class Note:
    """One row of `bearcli list --fields all`."""

    id: str
    title: str
    tags: tuple[str, ...] = ()
    length: int = 0
    created: datetime | None = None
    modified: datetime | None = None
    pins: tuple[str, ...] = ()
    location: Location = Location.NOTES
    todos: int = 0
    done: int = 0
    attachments: int = 0
    locked: bool = False
    preview: str = ""

    @classmethod
    def from_row(cls, row: dict[str, Any], preview_text: str | None = None) -> "Note":
        """A note from a `list` row; the preview comes from the row's content
        unless `preview_text` supplies one computed earlier."""
        tags = tuple(normalize_tag(str(t)) for t in row.get("tags") or () if str(t).strip())
        pins = tuple(str(p) for p in row.get("pins") or ())
        attachments = row.get("attachments") or ()
        try:
            location = Location(str(row.get("location") or "notes"))
        except ValueError:
            location = Location.NOTES
        return cls(
            id=str(row.get("id") or ""),
            title=str(row.get("title") or "").strip() or "Untitled",
            tags=tags,
            length=int(row.get("length") or 0),
            created=_parse_time(row.get("created")),
            modified=_parse_time(row.get("modified")),
            pins=pins,
            location=location,
            todos=int(row.get("todos") or 0),
            done=int(row.get("done") or 0),
            attachments=len(attachments) if isinstance(attachments, (list, tuple)) else int(attachments or 0),
            locked=_is_yes(row.get("locked")),
            preview=preview(str(row.get("content") or "")) if preview_text is None else preview_text,
        )

    @property
    def pinned(self) -> bool:
        """Any pin context, global or within a tag (ruling 2026-09-08)."""
        return bool(self.pins)

    @property
    def pinned_globally(self) -> bool:
        return "global" in self.pins

    def has_tag(self, tag: str) -> bool:
        """True for the tag itself or any nested child; bearcli lists ancestors too."""
        tag = normalize_tag(tag)
        if not tag:
            return True
        return tag in self.tags

    def modified_local_date(self):
        if self.modified is None:
            return None
        return self.modified.astimezone().date()


@dataclass(frozen=True, slots=True)
class NoteContent:
    """`bearcli cat --format json`: the body and the receipt for `overwrite --base`."""

    id: str
    content: str
    hash: str


@dataclass(frozen=True, slots=True)
class Probe:
    """The cheap change signal: active-note count plus the newest modification."""

    count: int
    latest_id: str
    latest_modified: str


@dataclass(slots=True)
class Snapshot:
    """Everything `list --location all` returned, in one consistent read."""

    notes: list[Note] = field(default_factory=list)
    taken_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _index: dict[str, Note] | None = field(default=None, repr=False, compare=False)

    def by_id(self, note_id: str) -> Note | None:
        if self._index is None or len(self._index) != len(self.notes):
            self._index = {note.id: note for note in self.notes}
        return self._index.get(note_id)

    def in_location(self, location: Location) -> list[Note]:
        return [n for n in self.notes if n.location == location]


class BearClient:
    """Shells out to bearcli. One instance per app; writes are serialized."""

    def __init__(self, command: str | Sequence[str] = DEFAULT_COMMAND) -> None:
        self.command: tuple[str, ...] = (command,) if isinstance(command, str) else tuple(command)
        self._write_lock = asyncio.Lock()
        #: note id -> (modification stamp, preview). Bodies make up nine tenths
        #: of a `list` with content, so a snapshot lists metadata only and
        #: fetches bodies just for the notes whose stamp moved.
        self._previews: dict[str, tuple[str, str]] = {}

    async def _run(self, *args: str, parse: bool = True, stdin: str | None = None) -> Any:
        try:
            proc = await asyncio.create_subprocess_exec(
                *self.command,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
            )
        except FileNotFoundError as exc:
            raise BearError(
                f"bearcli not found ({self.command[0]}). It ships inside Bear.app; see the README.",
                code="not_found",
            ) from exc
        try:
            stdout_b, stderr_b = await proc.communicate(stdin.encode() if stdin is not None else None)
        except asyncio.CancelledError:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            with contextlib.suppress(Exception):
                await proc.wait()
            raise
        stdout, stderr = stdout_b.decode(), stderr_b.decode()
        payload: Any = None
        if parse and stdout.strip():
            try:
                payload = json.loads(stdout)
            except ValueError as exc:
                raise BearError(f"bearcli returned invalid JSON: {exc}") from exc
            if isinstance(payload, dict) and "error" in payload:
                err = payload["error"] or {}
                raise BearError(
                    str(err.get("message") or "bearcli error"),
                    code=str(err.get("code") or ""),
                    exit_code=proc.returncode or 1,
                )
        if proc.returncode != 0:
            message = next((line.strip() for line in stderr.splitlines() if line.strip()), "")
            code = "conflict" if _STALE_TEXT in message else ""
            raise BearError(message or "bearcli failed with no error output", code=code, exit_code=proc.returncode or 1)
        return payload

    # -- reads ---------------------------------------------------------------

    async def snapshot(self) -> Snapshot:
        """Every note's metadata, with a body preview each.

        The first call lists content too and remembers every preview. Later
        calls list metadata alone (a third of the time on two thousand notes)
        and read the body only of notes whose modification stamp changed: a
        `cat` each for a few, one content-bearing `list` for many.
        """
        rows: list[dict[str, Any]] = []
        stale: list[dict[str, Any]] = []
        previews: dict[str, str] = {}
        if self._previews:
            rows = await self._run("list", "--location", "all", "--format", "json", "--fields", LIST_FIELDS) or []
            for row in rows:
                known = self._preview_of(row)
                if known is None:
                    stale.append(row)
                else:
                    previews[str(row.get("id") or "")] = known
        if not self._previews or len(stale) > PREVIEW_CAT_LIMIT:
            rows = await self._run("list", "--location", "all", "--format", "json", "--fields", LIST_FIELDS + ",content") or []
            for row in rows:
                previews[str(row.get("id") or "")] = self._remember_preview(row, preview(str(row.get("content") or "")))
        elif stale:
            semaphore = asyncio.Semaphore(PREVIEW_CAT_CONCURRENCY)

            async def read(row: dict[str, Any]) -> None:
                async with semaphore:
                    try:
                        body = (await self.cat(str(row.get("id") or ""))).content
                    except BearError:
                        body = ""  # locked, or gone since the list
                previews[str(row.get("id") or "")] = self._remember_preview(row, preview(body))

            await asyncio.gather(*(read(r) for r in stale))
        notes = [Note.from_row(r, previews.get(str(r.get("id") or ""), "")) for r in rows]
        live = {n.id for n in notes}
        self._previews = {k: v for k, v in self._previews.items() if k in live}
        return Snapshot(notes=notes)

    @staticmethod
    def _stamp(row: dict[str, Any]) -> str:
        return str(row.get("modified") or "")

    def _preview_of(self, row: dict[str, Any]) -> str | None:
        stamp = self._stamp(row)
        if recently_modified(stamp):
            return None
        cached = self._previews.get(str(row.get("id") or ""))
        return cached[1] if cached is not None and cached[0] == stamp else None

    def _remember_preview(self, row: dict[str, Any], text: str) -> str:
        self._previews[str(row.get("id") or "")] = (self._stamp(row), text)
        return text

    async def probe(self) -> Probe:
        """Two ~20 ms bearcli calls, run together: enough to know whether a
        full `snapshot` is worth taking."""
        count_rows, latest = await asyncio.gather(
            self._run("list", "--location", "all", "--count", "--format", "json"),
            self._run(
                "list", "--location", "all", "--sort", "modified:desc", "-n", "1",
                "--format", "json", "--fields", "id,modified",
            ),
        )
        count = _count_from(count_rows)
        row = (latest or [{}])[0] if isinstance(latest, list) else {}
        return Probe(count=count, latest_id=str(row.get("id") or ""), latest_modified=str(row.get("modified") or ""))

    async def search_ids(self, query: str, location: Location | str = "all") -> list[str]:
        """Ids matching a Bear search query, in bearcli's order."""
        query = query.strip()
        if not query:
            return []
        loc = location.value if isinstance(location, Location) else str(location)
        rows = await self._run("search", "--query", query, "--location", loc, "--format", "json", "--fields", "id")
        return [str(r.get("id")) for r in rows or [] if r.get("id")]

    async def cat(self, note_id: str) -> NoteContent:
        payload = await self._run("cat", note_id, "--format", "json")
        if not isinstance(payload, dict):
            raise BearError("bearcli cat returned no content")
        return NoteContent(id=note_id, content=str(payload.get("content") or ""), hash=str(payload.get("hash") or ""))

    async def todo_rows(self, workspace: str = "") -> list[dict[str, Any]]:
        """Raw rows for every active note with an open todo, optionally only
        under a tag. Content included; `todos.scan_rows` turns them into items."""
        query = "@todo" + (f" #{normalize_tag(workspace)}" if normalize_tag(workspace) else "")
        rows = await self._run(
            "search", "--query", query, "--location", "notes",
            "--format", "json", "--fields", "id,title,tags,locked,content",
        )
        return list(rows or [])

    async def tags(self) -> list[str]:
        rows = await self._run("tags", "list", "--format", "json")
        return [normalize_tag(str(r.get("tag"))) for r in rows or [] if r.get("tag")]

    # -- writes --------------------------------------------------------------

    async def create(self, title: str, tags: Iterable[str] = (), content: str = "") -> str:
        """Create a note and return its id."""
        args = ["create", title, "--format", "json", "--fields", "id"]
        tag_list = ",".join(normalize_tag(t) for t in tags if normalize_tag(t))
        if tag_list:
            args += ["--tags", tag_list]
        async with self._write_lock:
            payload = await self._run(*args, stdin=content)
        if isinstance(payload, list):
            payload = payload[0] if payload else {}
        if not isinstance(payload, dict) or not payload.get("id"):
            raise BearError("bearcli create returned no id")
        return str(payload["id"])

    async def overwrite(self, note_id: str, content: str, base: str) -> None:
        """Replace a note's whole content, guarded by the hash from `cat`."""
        async with self._write_lock:
            await self._run("overwrite", note_id, "--base", base, parse=False, stdin=content)

    async def trash(self, note_id: str) -> None:
        async with self._write_lock:
            await self._run("trash", note_id, parse=False)

    async def restore(self, note_id: str) -> None:
        async with self._write_lock:
            await self._run("restore", note_id, parse=False)

    async def archive(self, note_id: str) -> None:
        async with self._write_lock:
            await self._run("archive", note_id, parse=False)

    async def pin(self, note_id: str, target: str = "global") -> None:
        async with self._write_lock:
            await self._run("pin", "add", note_id, target, parse=False)

    async def unpin(self, note_id: str, target: str = "global") -> None:
        async with self._write_lock:
            await self._run("pin", "remove", note_id, target, parse=False)

    async def edit(self, note_id: str, find: str, replace: str, section: str = "") -> None:
        """One exact find/replace, the primitive todo triage will use."""
        args = ["edit", note_id]
        if section:
            args += ["--section", escape_flag(section)]
        args += ["--find", escape_flag(find), "--replace", escape_flag(replace)]
        async with self._write_lock:
            await self._run(*args, parse=False)

    async def tick_todo(self, note_id: str, line: str, done_line: str, section: str = "") -> None:
        """Flip one `[ ]` to `[x]`, matching the whole line.

        `--find` is a substring match, so a bare line would also hit a longer
        line that starts the same way. The note is read first: the line must
        still be present as a complete line, and the newline that ends it pins
        the match (the last line of a note has none).
        """
        current = await self.cat(note_id)
        lines = current.content.split("\n")
        if line not in lines:
            raise BearError(f"The line is no longer in the note: {line.strip()[:60]}", code="conflict")
        if lines[-1] == line and lines.count(line) == 1:
            await self.edit(note_id, line, done_line, section=section)
        else:
            await self.edit(note_id, line + "\n", done_line + "\n", section=section)

    # -- app -----------------------------------------------------------------

    async def open_in_app(self, note_id: str, header: str = "") -> None:
        args = ["app", "open", note_id]
        if header:
            args += ["--header", header]
        await self._run(*args, parse=False)


#: Text a bearcli text flag interprets: `\n`, `\t`, `\r`, `\\`.
_ESCAPE = str.maketrans({"\\": "\\\\", "\n": "\\n", "\t": "\\t", "\r": "\\r"})


def escape_flag(text: str) -> str:
    return text.translate(_ESCAPE)


def _count_from(payload: Any) -> int:
    """`list --count --format json` returns `{"count": N}`; accept older shapes too."""
    if isinstance(payload, dict):
        for key in ("count", "total"):
            if key in payload:
                return int(payload[key])
        return 0
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, (int, str)) and str(payload).strip().isdigit():
        return int(payload)
    return 0
