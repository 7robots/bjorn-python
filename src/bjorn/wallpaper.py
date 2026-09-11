"""The empty page's picture: a line-art Astro-Bear bundled with Bjorn.

Whether the terminal can show a bitmap at all is decided by textual-image,
which must probe the terminal *before* Textual takes it over; `probe()` does
that and is called from the entry point, and only in terminals whose graphics
we trust. Elsewhere, and when stdout is not a TTY (tests), there is no picture
and the reader falls back to the ASCII bear.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PIL import Image, ImageOps

DEFAULT_IMAGE = Path(__file__).with_name("data") / "astro-bear.png"

#: Terminals whose graphics support textual-image renders cleanly. Others,
#: SwiftTerm/Tecolot among them, answer the capability query but draw the
#: placeholder cells as ordinary glyphs and push the columns about.
GRAPHICS_TERMINALS = frozenset({"ghostty", "kitty", "wezterm", "iterm.app"})

STYLES = ("outline", "colour")
#: The ink the outline is drawn in; alpha comes from each pixel's brightness,
#: scaled by OUTLINE_OPACITY so the drawing stays quiet behind the count.
OUTLINE_INK = (128, 134, 150)
OUTLINE_OPACITY = 0.55

#: The image widget class to use, set by `probe()`; None means "no bitmaps".
_image_widget: type | None = None


def cache_dir(environ: dict[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    return Path(env.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "bjorn"


def resolve_image(configured: str) -> Path | None:
    """The picture to show: the config's `empty_image` if it exists, else the
    bundled one. A configured path that is missing is not guessed around."""
    if configured:
        path = Path(configured).expanduser()
        return path if path.is_file() else None
    return DEFAULT_IMAGE if DEFAULT_IMAGE.is_file() else None


def outline_path(source: Path, environ: dict[str, str] | None = None) -> Path:
    """Where the outline derived from `source` is cached; the name carries the
    source's size and mtime so a replaced picture is redrawn."""
    stat = source.stat()
    ink = "%02x%02x%02x%02x" % (*OUTLINE_INK, round(OUTLINE_OPACITY * 255))
    return cache_dir(environ) / f"{source.stem}-outline-{ink}-{stat.st_size}-{int(stat.st_mtime)}.png"


def make_outline(source: Path, dest: Path) -> Path:
    """Lift line art off its background: every pixel becomes the one ink, with
    opacity from how much brighter it is than the (dark) ground, so the
    terminal's own background shows through in any theme. Blocking; run in a
    thread."""
    with Image.open(source) as opened:
        gray = ImageOps.grayscale(opened.convert("RGB"))
    histogram = gray.histogram()
    ground = max(range(256), key=lambda level: histogram[level])
    low, high = min(ground + 12, 254), 200
    span = max(high - low, 1)
    top = round(255 * OUTLINE_OPACITY)
    alpha = gray.point(lambda v: 0 if v <= low else top if v >= high else (v - low) * top // span)
    out = Image.new("RGBA", gray.size, OUTLINE_INK + (0,))
    out.putalpha(alpha)
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
    global _image_widget
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
