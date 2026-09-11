"""Exporting a note to disk in one of several formats.

`FORMATS` is what the picker offers; `export_note` dispatches to a writer per
format. Writers are pure: they take the note's text, title and any attachment
bytes and write files. Fetching content and attachments is the app's job.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import render_html
from .render import to_text

_UNSAFE_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


class ExportError(Exception):
    """A writer could not produce its file (a converter missing or failing)."""


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
    Format("rtf", "RTF", "r", "rtf", needs_attachments=True),
)
DEFAULT_FORMAT = "md"


def format_by_id(format_id: str) -> Format:
    for fmt in FORMATS:
        if fmt.id == format_id:
            return fmt
    return format_by_id(DEFAULT_FORMAT)


def extension_for(fmt: Format, has_attachments: bool) -> str:
    """RTF with images is an `.rtfd` package so the pictures travel; textutil
    drops them from a flat `.rtf`."""
    if fmt.id == "rtf" and has_attachments:
        return "rtfd"
    return fmt.ext


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


def export_rtf(content: str, title: str, destination: Path, images: dict[str, bytes] | None = None) -> Path:
    """RTF through macOS `textutil`, from the HTML rendering. A destination
    ending in `.rtfd` becomes a package with the images inside (textutil
    names them itself); a flat `.rtf` carries text and tables only."""
    if shutil.which("textutil") is None:
        raise ExportError("RTF export needs textutil, which ships with macOS.")
    destination = _prepare(destination)
    kind = "rtfd" if destination.suffix.lower() == ".rtfd" else "rtf"
    with tempfile.TemporaryDirectory(prefix="bjorn-rtf-") as tmp:
        source = Path(tmp) / "note.html"
        source.write_text(render_html.render(content, title, images=images if kind == "rtfd" else None), encoding="utf-8")
        result = subprocess.run(
            ["textutil", "-convert", kind, str(source), "-output", str(destination)],
            capture_output=True, text=True, check=False,
        )
    # textutil exits 0 even when it fails; the output is the only reliable signal.
    if result.returncode != 0 or not destination.exists():
        detail = (result.stderr or result.stdout).strip().splitlines()
        raise ExportError(detail[0] if detail else "textutil wrote nothing")
    return destination


def export_note(fmt: Format, content: str, title: str, destination: Path, images: dict[str, bytes] | None = None) -> Path:
    """Write `content` as `fmt` to `destination`; returns what was written."""
    if fmt.id == "md":
        return export_markdown(content, destination)
    if fmt.id == "txt":
        return export_text(content, destination)
    if fmt.id == "html":
        return export_html(content, title, destination, images)
    if fmt.id == "rtf":
        return export_rtf(content, title, destination, images)
    raise ValueError(f"unknown export format {fmt.id}")
