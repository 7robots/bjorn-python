"""The empty page's picture: Shiny Frog's Astro-Bear wallpaper, fetched from
their own download URL on first use and cached, never shipped with Bjorn.

Whether the terminal can show a bitmap at all is decided by textual-image,
which must probe the terminal *before* Textual takes it over; `probe()` does
that and is called from the entry point. In a terminal without the Kitty
graphics protocol or Sixel, or when stdout is not a TTY (tests), there is no
picture and the reader falls back to the ASCII bear.
"""

from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps

WALLPAPER_URL = "https://sf-applications.s3.amazonaws.com/Bear/wallpapers/05/july-2020-wallpaper_ipad-10.2-2160x1620.png"
WALLPAPER_FILE = "astro-bear.png"
CREDIT = "Astro-Bear wallpaper by Shiny Frog — bear.app/wallpapers"

#: Terminals whose graphics support textual-image renders cleanly. Others,
#: SwiftTerm/Tecolot among them, answer the capability query but draw the
#: placeholder cells as ordinary glyphs and push the columns about.
GRAPHICS_TERMINALS = frozenset({"ghostty", "kitty", "wezterm", "iterm.app"})

STYLES = ("outline", "colour")
OUTLINE_WIDTH = 1080  # px; edges are found at this size so the lines survive scaling down
OUTLINE_INK = (150, 158, 176, 220)

#: The image widget class to use, set by `probe()`; None means "no bitmaps".
_image_widget: type | None = None
_probed = False


def cache_path(environ: dict[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    root = Path(env.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return root / "bjorn" / WALLPAPER_FILE


def resolve_image(configured: str, environ: dict[str, str] | None = None) -> Path | None:
    """The picture to show: the config's `empty_image` if it exists, else the
    cached wallpaper if it has been fetched, else None."""
    if configured:
        path = Path(configured).expanduser()
        return path if path.is_file() else None
    cached = cache_path(environ)
    return cached if cached.is_file() else None


def fetch_wallpaper(dest: Path, url: str = WALLPAPER_URL, timeout: float = 20.0) -> Path:
    """Download the wallpaper to `dest` (atomically). Blocking; run in a thread."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    with urllib.request.urlopen(url, timeout=timeout) as response, tmp.open("wb") as out:
        while chunk := response.read(1 << 16):
            out.write(chunk)
    tmp.replace(dest)
    return dest


def outline_path(source: Path, environ: dict[str, str] | None = None) -> Path:
    """Where the outline derived from `source` is cached; the name carries the
    source's size and mtime so a replaced picture is redrawn."""
    stat = source.stat()
    return cache_path(environ).parent / f"{source.stem}-outline-{stat.st_size}-{int(stat.st_mtime)}.png"


def make_outline(source: Path, dest: Path) -> Path:
    """Reduce a picture to its outlines, in one muted ink on a transparent
    ground, the way Bear draws its empty page. Blocking; run in a thread."""
    with Image.open(source) as opened:
        img = opened.convert("RGB")
        if img.width > OUTLINE_WIDTH:
            img = img.resize((OUTLINE_WIDTH, round(img.height * OUTLINE_WIDTH / img.width)), Image.LANCZOS)
    edges = ImageOps.grayscale(img).filter(ImageFilter.FIND_EDGES).filter(ImageFilter.MaxFilter(3))
    mask = edges.point(lambda v: 255 if v > 40 else 0).filter(ImageFilter.GaussianBlur(0.6))
    # FIND_EDGES rings the picture with a frame; leave it out.
    mask = mask.crop((3, 3, mask.width - 3, mask.height - 3))
    out = Image.new("RGBA", mask.size, (0, 0, 0, 0))
    out.paste(Image.new("RGBA", mask.size, OUTLINE_INK), mask=mask)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    out.save(tmp, format="PNG")
    tmp.replace(dest)
    return dest


def styled_image(source: Path, style: str, environ: dict[str, str] | None = None) -> Path:
    """The file to display for `source` in `style`: the source itself for
    "colour", else its cached outline, drawn if missing."""
    if style != "outline":
        return source
    dest = outline_path(source, environ)
    return dest if dest.is_file() else make_outline(source, dest)


def supports_graphics(environ: dict[str, str] | None = None) -> bool:
    """Is this a terminal whose graphics we trust? See GRAPHICS_TERMINALS."""
    env = os.environ if environ is None else environ
    if env.get("TERM_PROGRAM", "").strip().lower() in GRAPHICS_TERMINALS:
        return True
    return env.get("TERM", "") == "xterm-kitty" or bool(env.get("KITTY_WINDOW_ID")) or bool(env.get("GHOSTTY_RESOURCES_DIR"))


def probe(environ: dict[str, str] | None = None) -> None:
    """Ask the terminal what it can draw. Must run before the Textual app starts
    and only when stdout is a real terminal of a kind we trust."""
    global _image_widget, _probed
    _probed = True
    if not (sys.__stdout__ and sys.__stdout__.isatty()) or not supports_graphics(environ):
        return
    try:
        from textual_image.renderable import Image as auto_renderable
        from textual_image.renderable.sixel import Image as sixel_renderable
        from textual_image.renderable.tgp import Image as tgp_renderable
        from textual_image.widget import Image as auto_widget
    except Exception:  # pragma: no cover - optional at runtime
        return
    if auto_renderable in (tgp_renderable, sixel_renderable):
        _image_widget = auto_widget


def image_widget() -> type | None:
    """The widget class that draws real pixels here, or None to use the ASCII bear."""
    return _image_widget


def set_image_widget(cls: type | None) -> None:
    """For tests: pretend the terminal has (or lacks) bitmap support."""
    global _image_widget
    _image_widget = cls
