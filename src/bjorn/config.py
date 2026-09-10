"""User configuration: `${XDG_CONFIG_HOME:-~/.config}/bjorn/config.toml`.

Every key is optional. Example:

    editor = "nvim"
    export_dir = "~/Documents/exports"
    poll_seconds = 5
    workspace = "work"
    bearcli = "/usr/local/bin/bearcli"   # optional; default searches PATH, then Bear.app
    icon_style = "auto"          # auto | nerd | emoji | lucide | none
    mouse_pixels = true          # false works around SwiftTerm-based terminals (Tecolot)
    wallpaper = true             # fetch Shiny Frog's Astro-Bear for the empty page (Ghostty, kitty)
    empty_image = ""             # or a picture of your own for the empty page
    empty_image_style = "outline"  # outline (Bear-like line art) | colour

    [icons]                      # top-level tag -> Lucide icon name or emoji:<glyph>
    tech = "terminal"
    school = "emoji:🎓"

    [reminders]                  # triage can push todos to Apple Reminders (off by default)
    enabled = false
    list = "Bear"                # target list; remctl's default list when empty
    due = "today"                # due date for new reminders; "" for none
    remctl = ""                  # path to remctl; PATH when empty
"""

from __future__ import annotations

import os
import shutil
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

APP_NAME = "bjorn"
DEFAULT_EDITOR = "vim"
DEFAULT_POLL_SECONDS = 5


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME", "").strip()
    root = Path(base).expanduser() if base else Path.home() / ".config"
    return root / APP_NAME


def default_config_path() -> Path:
    return config_dir() / "config.toml"


@dataclass(slots=True)
class RemindersConfig:
    enabled: bool = False
    list: str = ""
    due: str = "today"
    remctl: str = ""


@dataclass(slots=True)
class Config:
    editor: str = ""
    export_dir: Path = field(default_factory=lambda: Path.home() / "Downloads")
    poll_seconds: int = DEFAULT_POLL_SECONDS
    workspace: str = ""
    bearcli: str = ""
    icon_style: str = "auto"
    icons: dict[str, str] = field(default_factory=dict)
    #: Let Textual use SGR-pixel mouse reporting when the terminal supports
    #: in-band resize. Off for terminals that report pixel geometry and mouse
    #: position in different units (SwiftTerm/Tecolot, 2026-09).
    mouse_pixels: bool = True
    #: Picture for the empty page in terminals that can draw one. Empty means
    #: Shiny Frog's Astro-Bear wallpaper, fetched once into the cache when
    #: `wallpaper` is true; a path here is used instead and never fetched.
    empty_image: str = ""
    wallpaper: bool = True
    #: "outline" reduces the picture to Bear-like line art; "colour" shows it as is.
    empty_image_style: str = "outline"
    reminders: RemindersConfig = field(default_factory=RemindersConfig)
    path: Path | None = None

    @classmethod
    def load(cls, path: Path | str | None = None) -> "Config":
        target = Path(path).expanduser() if path else default_config_path()
        cfg = cls(path=target)
        if not target.exists():
            return cfg
        with target.open("rb") as fh:
            data = tomllib.load(fh)
        cfg.editor = str(data.get("editor", "") or "").strip()
        export_dir = str(data.get("export_dir", "") or "").strip()
        if export_dir:
            cfg.export_dir = Path(export_dir).expanduser()
        poll = data.get("poll_seconds", DEFAULT_POLL_SECONDS)
        try:
            cfg.poll_seconds = max(0, int(poll))
        except (TypeError, ValueError):
            cfg.poll_seconds = DEFAULT_POLL_SECONDS
        cfg.workspace = str(data.get("workspace", "") or "").strip().strip("#")
        cfg.bearcli = str(data.get("bearcli", "") or "").strip()
        cfg.icon_style = str(data.get("icon_style", "auto") or "auto").strip().lower()
        icons = data.get("icons")
        if isinstance(icons, dict):
            cfg.icons = {str(k): str(v) for k, v in icons.items() if isinstance(v, str)}
        cfg.mouse_pixels = bool(data.get("mouse_pixels", True))
        cfg.empty_image = str(data.get("empty_image", "") or "").strip()
        cfg.wallpaper = bool(data.get("wallpaper", True))
        style = str(data.get("empty_image_style", "outline") or "outline").strip().lower()
        cfg.empty_image_style = "colour" if style in ("colour", "color") else "outline"
        section = data.get("reminders")
        if isinstance(section, dict):
            due = section.get("due", "today")
            cfg.reminders = RemindersConfig(
                enabled=bool(section.get("enabled", False)),
                list=str(section.get("list", "") or "").strip(),
                due="" if due is None else str(due).strip(),
                remctl=str(section.get("remctl", "") or "").strip(),
            )
        return cfg


def resolve_editor(config: Config, environ: dict[str, str] | None = None) -> str:
    """Config `editor`, then `$VISUAL`, then `$EDITOR`, then `vim`."""
    env = os.environ if environ is None else environ
    for candidate in (config.editor, env.get("VISUAL", ""), env.get("EDITOR", "")):
        if candidate and candidate.strip():
            return candidate.strip()
    return DEFAULT_EDITOR


def editor_available(command: str) -> bool:
    """The first word of the editor command must be runnable."""
    head = command.split()[0] if command.split() else ""
    if not head:
        return False
    path = Path(head).expanduser()
    if path.is_absolute():
        return path.exists() and os.access(path, os.X_OK)
    return shutil.which(head) is not None
