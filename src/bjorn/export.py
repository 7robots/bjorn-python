"""Exporting a note to disk. Markdown only for now; PDF is on the roadmap."""

from __future__ import annotations

import re
from pathlib import Path

_UNSAFE_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


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


def export_markdown(content: str, destination: Path) -> Path:
    """Write the raw note text. The parent directory is created if missing."""
    destination = destination.expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    text = content if content.endswith("\n") else content + "\n"
    destination.write_text(text, encoding="utf-8")
    return destination
