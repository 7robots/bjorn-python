"""Terminal glyphs for the sidebar: top-level tags and the smart views.

Icons are named with Lucide names (the vocabulary librarian and Obsidian's
Notebook Navigator use) and rendered in one of two styles:

``nerd``
    Material Design Icons from Nerd Fonts. Needs a Nerd Font in the terminal.
``emoji``
    Plain emoji, for terminals without one.
``lucide``
    Lucide's own icon font, emitted by name from the bundled
    ``data/lucide-codepoints.json`` (lucide-static LUCIDE_VERSION). Opt-in: the
    terminal must map that Private Use Area range onto ``lucide.ttf`` (see the
    README), and doing so displaces the Nerd Font sets living in U+E000-U+E7FF.

``auto`` picks between nerd and emoji by looking at the terminal; it never
picks lucide. Names prefixed with ``emoji:`` are literal glyphs and pass
through unchanged. ``none`` renders no icons at all.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from rich.cells import cell_len

GlyphStyle = Literal["nerd", "emoji", "lucide"]
IconStyle = Literal["auto", "nerd", "emoji", "lucide", "none"]
ICON_STYLES: tuple[str, ...] = ("auto", "nerd", "emoji", "lucide", "none")
FALLBACK_GLYPH_STYLE: GlyphStyle = "emoji"

#: The lucide-static release the bundled codepoints (and the font you install)
#: must come from. Lucide reassigns codepoints between releases.
LUCIDE_VERSION = "1.43.0"
LUCIDE_CODEPOINTS_PATH = Path(__file__).with_name("data") / "lucide-codepoints.json"

#: Glyphs are padded to this many cells plus one separating space, so labels
#: line up whether the glyph is single- or double-width.
ICON_CELL_WIDTH = 2

NERD_GLYPHS: dict[str, str] = {
    "archive": "\U000f003c",  # md-archive
    "atom": "\U000f0768",  # md-atom
    "book": "\U000f00ba",  # md-book
    "book-open": "\U000f00bd",  # md-book_open
    "bookmark": "\U000f00c0",  # md-bookmark
    "bot": "\U000f06a9",  # md-robot
    "brain": "\U000f09d1",  # md-brain
    "briefcase": "\U000f00d6",  # md-briefcase
    "calendar": "\U000f00ed",  # md-calendar
    "check-circle": "\U000f05e0",  # md-check_circle
    "clipboard-list": "\U000f10d4",  # md-clipboard_list
    "code": "\U000f0174",  # md-code_tags
    "compass": "\U000f018b",  # md-compass
    "computer": "\U000f0322",  # md-laptop
    "database": "\U000f01bc",  # md-database
    "file-text": "\U000f0219",  # md-file_document
    "flask-conical": "\U000f0093",  # md-flask
    "folder": "\U000f024b",  # md-folder
    "gamepad-2": "\U000f0296",  # md-gamepad
    "globe": "\U000f01e7",  # md-earth
    "graduation-cap": "\U000f0474",  # md-school
    "heart": "\U000f02d1",  # md-heart
    "home": "\U000f02dc",  # md-home
    "landmark": "\U000f0070",  # md-bank
    "leaf": "\U000f032a",  # md-leaf
    "library": "\U000f0331",  # md-library
    "lightbulb": "\U000f0335",  # md-lightbulb
    "lock": "\U000f033e",  # md-lock
    "flower": "\U000f024a",  # md-flower
    "music": "\U000f075a",  # md-music
    "notebook": "\U000f082e",  # md-notebook
    "palette": "\U000f03d8",  # md-palette
    "pencil": "\U000f03eb",  # md-pencil
    "pin": "\U000f0403",  # md-pin
    "rocket": "\U000f0463",  # md-rocket
    "search": "\U000f0349",  # md-magnify
    "settings": "\U000f0493",  # md-cog
    "star": "\U000f04ce",  # md-star
    "sun": "\U000f05a8",  # md-white_balance_sunny
    "tag": "\U000f04f9",  # md-tag
    "tags": "\U000f04fb",  # md-tag_multiple
    "terminal": "\U000f018d",  # md-console
    "trash": "\U000f01b4",  # md-delete
    "trees": "\U000f0405",  # md-pine_tree
    "trophy": "\U000f0538",  # md-trophy
    "users": "\U000f0849",  # md-account_group
    "wrench": "\U000f05b7",  # md-wrench
    "zap": "\U000f0241",  # md-flash
}

EMOJI_GLYPHS: dict[str, str] = {
    "archive": "\U0001f5c4",  # 🗄
    "atom": "⚛",
    "book": "\U0001f4d5",  # 📕
    "book-open": "\U0001f4d6",  # 📖
    "bookmark": "\U0001f516",  # 🔖
    "bot": "\U0001f916",  # 🤖
    "brain": "\U0001f9e0",  # 🧠
    "briefcase": "\U0001f4bc",  # 💼
    "calendar": "\U0001f4c5",  # 📅
    "check-circle": "✅",
    "clipboard-list": "\U0001f4cb",  # 📋
    "code": "⌨",
    "compass": "\U0001f9ed",  # 🧭
    "computer": "\U0001f4bb",  # 💻
    "database": "\U0001f5c3",  # 🗃
    "file-text": "\U0001f4c4",  # 📄
    "flask-conical": "\U0001f9ea",  # 🧪
    "folder": "\U0001f4c1",  # 📁
    "gamepad-2": "\U0001f3ae",  # 🎮
    "globe": "\U0001f30d",  # 🌍
    "graduation-cap": "\U0001f393",  # 🎓
    "heart": "❤",
    "home": "\U0001f3e0",  # 🏠
    "landmark": "\U0001f3db",  # 🏛
    "leaf": "\U0001f342",  # 🍂
    "library": "\U0001f4da",  # 📚
    "lightbulb": "\U0001f4a1",  # 💡
    "lock": "\U0001f512",  # 🔒
    "flower": "\U0001f338",  # 🌸
    "music": "\U0001f3b5",  # 🎵
    "notebook": "\U0001f4d3",  # 📓
    "palette": "\U0001f3a8",  # 🎨
    "pencil": "✏",
    "pin": "\U0001f4cc",  # 📌
    "rocket": "\U0001f680",  # 🚀
    "search": "\U0001f50d",  # 🔍
    "settings": "⚙",
    "star": "⭐",
    "sun": "☀",
    "tag": "\U0001f3f7",  # 🏷
    "tags": "\U0001f3f7",  # 🏷
    "terminal": "▸",
    "trash": "\U0001f5d1",  # 🗑
    "trees": "\U0001f332",  # 🌲
    "trophy": "\U0001f3c6",  # 🏆
    "users": "\U0001f465",  # 👥
    "wrench": "\U0001f527",  # 🔧
    "zap": "⚡",
}



@lru_cache(maxsize=1)
def lucide_glyphs() -> dict[str, str]:
    """Every Lucide icon name -> the codepoint in lucide.ttf, loaded once."""
    with LUCIDE_CODEPOINTS_PATH.open("rb") as fh:
        data = json.load(fh)
    return {name: chr(int(code)) for name, code in data.items()}


def glyph_table(style: str) -> dict[str, str]:
    if style == "lucide":
        return lucide_glyphs()
    if style == "nerd":
        return NERD_GLYPHS
    return EMOJI_GLYPHS

#: Icon names for top-level tags when the config says nothing. Unknown tags get
#: DEFAULT_TAG_ICON.
DEFAULT_TAG_ICONS: dict[str, str] = {
    "work": "briefcase",
    "home": "home",
    "projects": "folder",
    "ideas": "lightbulb",
    "journal": "notebook",
    "books": "book-open",
    "reading": "book-open",
    "tech": "code",
    "code": "code",
    "garden": "leaf",
    "travel": "compass",
    "health": "heart",
    "music": "music",
    "robotics": "bot",
    "school": "graduation-cap",
}
DEFAULT_TAG_ICON = "tag"

#: Icon names for the smart views, keyed by View.value.
VIEW_ICONS: dict[str, str] = {
    "all": "notebook",
    "untagged": "tag",
    "todo": "check-circle",
    "today": "calendar",
    "pinned": "pin",
    "archive": "archive",
    "trash": "trash",
}

NERD_FONT_TERMINALS = frozenset({"ghostty", "wezterm"})
FONT_DIRECTORIES = (Path.home() / "Library" / "Fonts", Path("/Library/Fonts"))
FONT_SUFFIXES = frozenset({".ttf", ".otf", ".ttc", ".dfont"})


def has_nerd_font_terminal(environ: dict[str, str] | None = None) -> bool:
    env = os.environ if environ is None else environ
    return env.get("TERM_PROGRAM", "").strip().lower() in NERD_FONT_TERMINALS


def has_nerd_font_installed() -> bool:
    for directory in FONT_DIRECTORIES:
        try:
            entries = list(directory.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.suffix.lower() in FONT_SUFFIXES and "nerd" in entry.name.lower():
                return True
    return False


def detect_glyph_style(environ: dict[str, str] | None = None) -> GlyphStyle:
    """Nerd when the terminal bundles the symbols or a Nerd Font is installed,
    emoji otherwise. A heuristic; `icon_style` in config overrides it."""
    if has_nerd_font_terminal(environ) or has_nerd_font_installed():
        return "nerd"
    return FALLBACK_GLYPH_STYLE


def pad_glyph(glyph: str) -> str:
    if not glyph:
        return ""
    return glyph + " " * max(0, ICON_CELL_WIDTH - cell_len(glyph)) + " "


class IconSet:
    """Resolved icon style plus the per-tag overrides from config."""

    def __init__(self, style: str = "auto", tag_icons: dict[str, str] | None = None, environ: dict[str, str] | None = None) -> None:
        style = (style or "auto").strip().lower()
        if style not in ICON_STYLES:
            style = "auto"
        self.enabled = style != "none"
        if style == "auto":
            self.style: GlyphStyle = detect_glyph_style(environ)
        elif style in ("nerd", "emoji", "lucide"):
            self.style = style  # type: ignore[assignment]
        else:
            self.style = FALLBACK_GLYPH_STYLE
        self.tag_icons = {k.strip().strip("#").casefold(): v.strip() for k, v in (tag_icons or {}).items() if v and v.strip()}

    def glyph(self, name: str) -> str:
        """A padded glyph for an icon name, `emoji:<literal>`, or ""."""
        if not self.enabled or not name:
            return ""
        if name.startswith("emoji:"):
            return pad_glyph(name[len("emoji:"):])
        table = glyph_table(self.style)
        return pad_glyph(table.get(name, table[DEFAULT_TAG_ICON]))

    def for_tag(self, top_level_tag: str) -> str:
        key = top_level_tag.strip().strip("#").casefold()
        name = self.tag_icons.get(key) or DEFAULT_TAG_ICONS.get(key, DEFAULT_TAG_ICON)
        return self.glyph(name)

    def for_view(self, view_value: str) -> str:
        return self.glyph(VIEW_ICONS.get(view_value, DEFAULT_TAG_ICON))
