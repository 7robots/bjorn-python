from bjorn.icons import (
    DEFAULT_TAG_ICON, DEFAULT_TAG_ICONS, EMOJI_GLYPHS, LUCIDE_VERSION, NERD_GLYPHS, VIEW_ICONS,
    IconSet, detect_glyph_style, lucide_glyphs, pad_glyph,
)


def test_tables_cover_every_default_in_every_style():
    lucide = lucide_glyphs()
    for name in list(DEFAULT_TAG_ICONS.values()) + list(VIEW_ICONS.values()) + [DEFAULT_TAG_ICON]:
        assert name in NERD_GLYPHS and name in EMOJI_GLYPHS and name in lucide, name
    assert set(NERD_GLYPHS) == set(EMOJI_GLYPHS)
    # Every curated name is a real Lucide name, so [icons] values work in all styles.
    assert set(NERD_GLYPHS) <= set(lucide)


def test_lucide_style_emits_font_codepoints():
    lucide = lucide_glyphs()
    assert len(lucide) > 2000 and LUCIDE_VERSION == "1.43.0"
    assert lucide["bot"] == "\ue1bb" and lucide["tag"] == "\ue17f"
    assert all(0xE000 <= ord(g) <= 0xE7FF for g in lucide.values())
    icons = IconSet("lucide")
    assert icons.for_tag("kybernetes") == pad_glyph("\ue1bb")
    assert icons.for_tag("unknown") == pad_glyph(lucide["tag"])
    assert icons.glyph("sparkles") == pad_glyph(lucide["sparkles"])  # any Lucide name, not just the curated set
    assert IconSet("auto", environ={"TERM_PROGRAM": "ghostty"}).style == "nerd"  # auto never picks lucide


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
