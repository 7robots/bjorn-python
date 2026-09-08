from bjorn.icons import DEFAULT_TAG_ICON, NERD_GLYPHS, EMOJI_GLYPHS, VIEW_ICONS, DEFAULT_TAG_ICONS, IconSet, detect_glyph_style, pad_glyph


def test_tables_cover_every_default():
    for name in list(DEFAULT_TAG_ICONS.values()) + list(VIEW_ICONS.values()) + [DEFAULT_TAG_ICON]:
        assert name in NERD_GLYPHS and name in EMOJI_GLYPHS
    assert set(NERD_GLYPHS) == set(EMOJI_GLYPHS)


def test_nerd_icons_for_known_tags_and_fallback():
    icons = IconSet("nerd")
    assert icons.for_tag("kybernetes") == pad_glyph("\U000f06a9")
    assert icons.for_tag("#Techne") == pad_glyph(NERD_GLYPHS["code"])
    assert icons.for_tag("brand-new") == pad_glyph(NERD_GLYPHS["tag"])
    assert icons.for_view("todo") == pad_glyph(NERD_GLYPHS["check-circle"])
    assert pad_glyph("\U000f06a9") == "\U000f06a9  "


def test_config_overrides_and_literal_emoji():
    icons = IconSet("emoji", {"#techne": "terminal", "veritas": "emoji:🎓", "bogus": ""})
    assert icons.for_tag("techne") == pad_glyph("▸")
    assert icons.for_tag("veritas") == "🎓 "
    assert icons.for_tag("bogus") == pad_glyph(EMOJI_GLYPHS["tag"])


def test_none_and_auto():
    assert IconSet("none").for_tag("techne") == ""
    assert IconSet("none").for_view("all") == ""
    assert detect_glyph_style({"TERM_PROGRAM": "ghostty"}) == "nerd"
    assert IconSet("garbage", environ={"TERM_PROGRAM": "WezTerm"}).style == "nerd"
