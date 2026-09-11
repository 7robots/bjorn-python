"""Phase 15: which parts of a Bear query would match note text."""

from __future__ import annotations

from bjorn.search import pattern, query_pattern, terms


def test_words_and_phrases_in_order():
    assert terms('bulbs "spring planting" garden') == ["bulbs", "spring planting", "garden"]


def test_operators_dropped_including_arguments():
    assert terms("@todo @title @date(2026-01-01) @last7days @ctoday foo") == ["foo"]


def test_tags_dropped_in_every_spelling():
    assert terms("#work !#work #*/planning #multi word# foo") == ["foo"]


def test_negations_dropped():
    assert terms('foo -bar -"not this" baz') == ["foo", "baz"]


def test_title_scope_keeps_the_term():
    assert terms("@title foo") == ["foo"]


def test_operators_only_is_empty():
    assert terms("@todo #work -draft") == []
    assert pattern([]) is None
    assert query_pattern("@todo") is None


def test_duplicates_collapse_case_insensitively():
    assert terms("Foo foo FOO") == ["Foo"]


def test_pattern_escapes_and_ignores_case():
    p = pattern(["a.b", "c+d"])
    assert p is not None
    assert p.search("xx A.B yy") is not None
    assert p.search("xx AxB yy") is None
    assert p.search("C+D") is not None


def test_pattern_prefers_the_longest_alternative():
    p = pattern(["plan", "spring planting"])
    assert p is not None
    m = p.search("a spring planting day")
    assert m is not None and m.group(0) == "spring planting"


def test_substring_match_no_word_boundaries():
    p = query_pattern("bulb")
    assert p is not None and p.search("lightbulbs") is not None
