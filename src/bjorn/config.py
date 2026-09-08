"""User configuration: `${XDG_CONFIG_HOME:-~/.config}/bjorn/config.toml`.

Every key is optional. Example:

    editor = "nvim"
    export_dir = "~/Documents/exports"
    poll_seconds = 5
    workspace = "work"
    bearcli = "/usr/local/bin/bearcli"
    icon_style = "auto"          # auto | nerd | emoji | lucide | none
    mouse_pixels = true          # false works around SwiftTerm-based terminals (Tecolot)

    [icons]                      # top-level tag -> Lucide icon name or emoji:<glyph>
    tech = "terminal"
    school = "emoji:🎓"
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
