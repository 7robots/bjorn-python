"""Exporting a note to disk in one of several formats.

`FORMATS` is what the picker offers; `export_note` dispatches to a writer per
format. Writers are pure: they take the note's text, title and any attachment
bytes and write files. Fetching content and attachments is the app's job.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import render_html
from .render import to_text

_UNSAFE_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


@dataclass(frozen=True, slots=True)
class Format:
    id: str
    label: str
    key: str
    ext: str
    #: The writer wants the attachment bytes (images embedded or copied).
    needs_attachments: bool = False


FORMATS: tuple[Format, ...] = (
    Format("md", "Markdown", "m", "md"),
    Format("html", "HTML", "h", "html", needs_attachments=True),
    Format("txt", "Text", "t", "txt"),
)
DEFAULT_FORMAT = "md"


def format_by_id(format_id: str) -> Format:
    for fmt in FORMATS:
        if fmt.id == format_id:
            return fmt
    return format_by_id(DEFAULT_FORMAT)


def safe_filename(title: str, fallback: str = "note") -> str:
    """A filename from a note title: path separators and control characters
    become spaces, whitespace collapses, leading dots go."""
    name = _UNSAFE_RE.sub(" ", title)
    name = " ".join(name.split()).strip(" .")
    return name[:120] or fallback


def unique_path(path: Path) -> Path:
    """`path`, or `stem (2).ext`, `stem (3).ext`... if it already exists."""
    if not path.exists():
        return path
    n = 2
    while True:
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        if not candidate.exists():
            return candidate
        n += 1


def default_export_path(export_dir: Path, title: str, ext: str = "md") -> Path:
    return unique_path(export_dir.expanduser() / f"{safe_filename(title)}.{ext}")


def _prepare(destination: Path) -> Path:
    destination = destination.expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    return destination


def export_markdown(content: str, destination: Path) -> Path:
    """Write the raw note text. The parent directory is created if missing."""
    destination = _prepare(destination)
    text = content if content.endswith("\n") else content + "\n"
    destination.write_text(text, encoding="utf-8")
    return destination


def export_text(content: str, destination: Path) -> Path:
    destination = _prepare(destination)
    destination.write_text(to_text(content), encoding="utf-8")
    return destination


def export_html(content: str, title: str, destination: Path, images: dict[str, bytes] | None = None) -> Path:
    """One self-contained HTML file, images embedded."""
    destination = _prepare(destination)
    destination.write_text(render_html.render(content, title, images=images), encoding="utf-8")
    return destination


def export_note(fmt: Format, content: str, title: str, destination: Path, images: dict[str, bytes] | None = None) -> Path:
    """Write `content` as `fmt` to `destination`; returns what was written."""
    if fmt.id == "md":
        return export_markdown(content, destination)
    if fmt.id == "txt":
        return export_text(content, destination)
    if fmt.id == "html":
        return export_html(content, title, destination, images)
    raise ValueError(f"unknown export format {fmt.id}")
