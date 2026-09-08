"""Turn Bear's markdown into something Textual's `Markdown` widget renders well.

Textual parses with markdown-it's `gfm-like` preset, which has no task-list
plugin and knows nothing of Bear's `==highlight==` and `~underline~`. The
transformations here are textual and line-based, and skip fenced code blocks.
"""

from __future__ import annotations

import re

#: How many lines are rendered while the list cursor is still moving. Textual's
#: `Markdown` mounts one widget per block, so a long note costs seconds to
#: render in full; the rest arrives once the cursor settles or the pane is
#: focused (librarian's pattern).
BROWSE_LINES = 80
#: A note this long or shorter is completed automatically a moment after the
#: cursor stops. Beyond it, the rest waits for the pane to be focused.
AUTO_COMPLETE_LINES = 200

_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_TASK_OPEN_RE = re.compile(r"^(\s*(?:[-*+]|\d+[.)])\s+)\[ \](\s+|$)")
_TASK_DONE_RE = re.compile(r"^(\s*(?:[-*+]|\d+[.)])\s+)\[[xX]\](\s+|$)")
_HIGHLIGHT_RE = re.compile(r"==(?=\S)(.+?)(?<=\S)==")
_UNDERLINE_RE = re.compile(r"(?<![~\w])~(?=\S)([^~\n]+?)(?<=\S)~(?![~\w])")
#: A Bear tag token: `#word`, `#nested/child`, `#multi word#`. Tags never carry
#: a space after the `#`, which is what separates them from headings.
TAG_TOKEN_RE = re.compile(r"#[^\s#][^#\n]*?#(?=\s|$)|#[^\s#]+")
_TAG_LINE_RE = re.compile(rf"^\s*(?:{TAG_TOKEN_RE.pattern})(?:\s+(?:{TAG_TOKEN_RE.pattern}))*\s*$")
_HEADING_RE = re.compile(r"^#{1,6}\s+\S")

OPEN_BOX = "☐"
DONE_BOX = "☑"


def is_tag_line(line: str) -> bool:
    """A line made only of Bear tags, such as the one under the title."""
    return bool(line.strip()) and not _HEADING_RE.match(line) and bool(_TAG_LINE_RE.match(line))


def tags_in_line(line: str) -> list[str]:
    return TAG_TOKEN_RE.findall(line)


def preprocess(content: str) -> str:
    """Bear markdown -> Textual-friendly markdown."""
    out: list[str] = []
    in_fence = False
    for line in content.splitlines():
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue
        if is_tag_line(line):
            out.append(" ".join(f"`{tag}`" for tag in tags_in_line(line)))
            continue
        line = _TASK_OPEN_RE.sub(lambda m: f"{m.group(1)}{OPEN_BOX}{m.group(2) or ' '}", line)
        line = _TASK_DONE_RE.sub(lambda m: f"{m.group(1)}{DONE_BOX}{m.group(2) or ' '}", line)
        line = _HIGHLIGHT_RE.sub(r"**\1**", line)
        line = _UNDERLINE_RE.sub(r"\1", line)
        out.append(line)
    text = "\n".join(out)
    if content.endswith("\n"):
        text += "\n"
    return text


def head_of(content: str, max_lines: int) -> tuple[str, bool]:
    """The first `max_lines` lines and whether anything was left out."""
    lines = content.splitlines()
    if len(lines) <= max_lines:
        return content, False
    return "\n".join(lines[:max_lines]), True


def strip_title_and_tags(content: str) -> str:
    """Body text without the H1 and the tag line under it: what the note list
    snippet and the export-by-title path want to look at."""
    lines = content.splitlines()
    i = 0
    if i < len(lines) and lines[i].startswith("# "):
        i += 1
    while i < len(lines) and (not lines[i].strip() or is_tag_line(lines[i])):
        i += 1
    return "\n".join(lines[i:])


def snippet(content: str, width: int = 80) -> str:
    """First line of body text, for the notes list."""
    for line in strip_title_and_tags(content).splitlines():
        text = line.strip().lstrip("#>-*+ ").strip()
        if text:
            return text[:width]
    return ""
