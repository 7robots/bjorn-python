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


def test_resolve_prefers_config_then_the_bundled_picture(tmp_path):
    assert wallpaper.resolve_image("") == wallpaper.DEFAULT_IMAGE and wallpaper.DEFAULT_IMAGE.is_file()
    assert wallpaper.resolve_image(str(tmp_path / "missing.png")) is None  # a configured path is never guessed around
    own = make_png(tmp_path / "own.png")
    assert wallpaper.resolve_image(str(own)) == own


@pytest.fixture
def unicode_image(monkeypatch):
    from textual_image.widget import UnicodeImage

    monkeypatch.setattr(wallpaper, "_image_widget", UnicodeImage)
    return UnicodeImage


async def test_empty_page_shows_the_picture_with_the_count_below(make_app, tmp_path, unicode_image):
    env = {"XDG_CACHE_HOME": str(tmp_path / "cache")}
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
        outlines = list(wallpaper.cache_dir(env).glob("astro-bear-outline-*.png"))
        assert len(outlines) == 1  # keyed out once and cached


async def test_wallpaper_off_or_no_graphics_keeps_the_ascii_bear(make_app, tmp_path, config, unicode_image, monkeypatch):
    env = {"XDG_CACHE_HOME": str(tmp_path / "cache")}
    config.wallpaper = False
    app = make_app(environ=env)
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await wait_until(lambda: app.note_view.empty)
        await pilot.pause(0.2)
        assert not app.note_view.has_picture and not wallpaper.cache_dir(env).exists()
        assert "(__)" in str(app.note_view.query_one("#note-art").render())
    config.wallpaper = True
    monkeypatch.setattr(wallpaper, "_image_widget", None)  # a terminal without bitmaps
    app = make_app(environ=env)
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await wait_until(lambda: app.note_view.empty)
        await pilot.pause(0.2)
        assert not app.note_view.has_picture


def test_outline_keys_the_ground_out_and_is_cached_by_source(tmp_path):
    env = {"XDG_CACHE_HOME": str(tmp_path / "cache")}
    source = tmp_path / "pic.png"
    img = PILImage.new("RGB", (400, 300), (28, 28, 30))
    for x in range(100, 300):
        img.putpixel((x, 150), (200, 200, 200))  # one bright line
        img.putpixel((x, 151), (110, 110, 110))  # one dimmer line: partly transparent
    img.save(source)
    out = wallpaper.styled_image(source, "outline", env)
    assert out.parent == wallpaper.cache_dir(env) and "outline" in out.name
    with PILImage.open(out) as result:
        assert result.mode == "RGBA" and result.size == (400, 300)
        alpha = result.getchannel("A")
        assert alpha.getpixel((5, 5)) == 0 and alpha.getpixel((200, 100)) == 0  # the ground is clear
        assert alpha.getpixel((200, 150)) == 255
        assert 0 < alpha.getpixel((200, 151)) < 255
        assert result.getpixel((200, 150))[:3] == wallpaper.OUTLINE_INK  # one ink, whatever the source colour
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
