"""The empty page's picture: fetched once from Shiny Frog, cached, optional."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image as PILImage

from bjorn import wallpaper
from bjorn.widgets.note_view import NoteView

from helpers import first_note, loaded, wait_until


def make_png(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    PILImage.new("RGB", (40, 30), (30, 50, 90)).save(path)
    return path


def test_resolve_prefers_config_then_cache_then_nothing(tmp_path):
    env = {"XDG_CACHE_HOME": str(tmp_path / "cache")}
    assert wallpaper.resolve_image("", env) is None
    cached = make_png(wallpaper.cache_path(env))
    assert cached == tmp_path / "cache" / "bjorn" / "astro-bear.png"
    assert wallpaper.resolve_image("", env) == cached
    assert wallpaper.resolve_image(str(tmp_path / "missing.png"), env) is None  # a configured path is never guessed around
    own = make_png(tmp_path / "own.png")
    assert wallpaper.resolve_image(str(own), env) == own


def test_fetch_writes_atomically_from_the_url(tmp_path):
    source = make_png(tmp_path / "source.png")
    dest = tmp_path / "cache" / "bjorn" / "astro-bear.png"
    got = wallpaper.fetch_wallpaper(dest, url=source.as_uri())
    assert got == dest and dest.read_bytes() == source.read_bytes()
    assert not dest.with_suffix(".part").exists()


@pytest.fixture
def unicode_image(monkeypatch):
    from textual_image.widget import UnicodeImage

    monkeypatch.setattr(wallpaper, "_image_widget", UnicodeImage)
    return UnicodeImage


async def test_empty_page_shows_the_cached_picture_with_the_count_below(make_app, tmp_path, unicode_image):
    env = {"XDG_CACHE_HOME": str(tmp_path / "cache")}
    make_png(wallpaper.cache_path(env))
    app = make_app(environ=env)
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await wait_until(lambda: app.note_view.has_picture)
        assert app.note_view.query_one("#note-picture").__class__ is unicode_image
        assert str(app.note_view.query_one("#note-count").render()) == "5 notes"
        await pilot.press("3")
        await wait_until(lambda: str(app.note_view.query_one("#note-count").render()) == "2 notes")
        await first_note(app, pilot)
        assert not app.note_view.empty and not app.note_view.has_picture
        await pilot.press("1")
        await wait_until(lambda: app.note_view.has_picture)


async def test_missing_picture_is_fetched_once_and_credited(make_app, tmp_path, unicode_image, monkeypatch):
    env = {"XDG_CACHE_HOME": str(tmp_path / "cache")}
    source = make_png(tmp_path / "source.png")
    monkeypatch.setattr(wallpaper, "WALLPAPER_URL", source.as_uri())
    calls: list[Path] = []
    real = wallpaper.fetch_wallpaper

    def counting(dest, url=wallpaper.WALLPAPER_URL, timeout=20.0):
        calls.append(dest)
        return real(dest, url=source.as_uri(), timeout=timeout)

    monkeypatch.setattr(wallpaper, "fetch_wallpaper", counting)
    app = make_app(environ=env)
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await wait_until(lambda: app.note_view.has_picture)
        assert calls == [wallpaper.cache_path(env)] and wallpaper.cache_path(env).is_file()
        await pilot.pause()
        assert any("Shiny Frog" in n.message for n in app._notifications)


async def test_wallpaper_off_or_no_graphics_keeps_the_ascii_bear(make_app, tmp_path, config, unicode_image, monkeypatch):
    env = {"XDG_CACHE_HOME": str(tmp_path / "cache")}
    config.wallpaper = False
    app = make_app(environ=env)
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await wait_until(lambda: app.note_view.empty)
        await pilot.pause(0.2)
        assert not app.note_view.has_picture and not wallpaper.cache_path(env).exists()
        assert "(__)" in str(app.note_view.query_one("#note-art").render())
    config.wallpaper = True
    make_png(wallpaper.cache_path(env))
    monkeypatch.setattr(wallpaper, "_image_widget", None)  # a terminal without bitmaps
    app = make_app(environ=env)
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await wait_until(lambda: app.note_view.empty)
        await pilot.pause(0.2)
        assert not app.note_view.has_picture


def test_outline_is_transparent_line_art_and_cached_by_source(tmp_path):
    env = {"XDG_CACHE_HOME": str(tmp_path / "cache")}
    source = tmp_path / "pic.png"
    img = PILImage.new("RGB", (400, 300), (30, 50, 90))
    for x in range(100, 300):
        for y in range(100, 200):
            img.putpixel((x, y), (240, 240, 250))  # a bright box: its edges are the only lines
    img.save(source)
    out = wallpaper.styled_image(source, "outline", env)
    assert out.parent == wallpaper.cache_path(env).parent and "outline" in out.name
    with PILImage.open(out) as result:
        assert result.mode == "RGBA"
        alpha = result.getchannel("A")
        opaque = sum(1 for v in alpha.tobytes() if v > 128)
        assert 0 < opaque < 0.1 * result.width * result.height  # a few lines, mostly transparent
        assert alpha.getpixel((5, 5)) == 0 and alpha.getpixel((200, 150)) == 0  # flat areas are clear
        assert alpha.getpixel((100 - 3, 150 - 3)) > 128  # the box's left edge is drawn (shifted by the 3px crop)
    assert wallpaper.styled_image(source, "outline", env) == out  # cached
    assert wallpaper.styled_image(source, "colour", env) == source


def test_only_trusted_terminals_get_graphics():
    assert wallpaper.supports_graphics({"TERM_PROGRAM": "ghostty"})
    assert wallpaper.supports_graphics({"TERM_PROGRAM": "WezTerm"})
    assert wallpaper.supports_graphics({"TERM": "xterm-kitty"})
    assert wallpaper.supports_graphics({"KITTY_WINDOW_ID": "1"})
    assert not wallpaper.supports_graphics({"TERM_PROGRAM": "Apple_Terminal"})
    assert not wallpaper.supports_graphics({"TERM_PROGRAM": "Tecolot", "TERM": "xterm-256color"})
    assert not wallpaper.supports_graphics({})
