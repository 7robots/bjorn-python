"""Phase 19: the search box completes @operators and #tags."""

from __future__ import annotations

import pytest

from bjorn.search_box import OPERATORS, QuerySuggester, complete, with_parents

TAGS = ["work/planning", "home/garden", "home", "techne/serial numbers", "diary"]


def test_operators_complete_in_list_order():
    assert complete("@to", TAGS) == "@todo"
    assert complete("@d", TAGS) == "@done"
    assert complete("@t", TAGS) == "@todo"


def test_parenthesised_operators_stop_at_the_paren():
    assert complete("@date", TAGS) == "@date("
    assert complete("@cd", TAGS) == "@cdate("


def test_tags_complete_including_paths():
    tags = with_parents(TAGS)
    assert complete("#wo", tags) == "#work"
    assert complete("#work/p", tags) == "#work/planning"
    assert complete("#home/g", tags) == "#home/garden"


def test_exact_prefix_forms():
    assert complete("!#ho", with_parents(TAGS)) == "!#home"
    assert complete("#*/g", with_parents(TAGS)) == "#*/garden"
    assert complete("#*/plan", with_parents(TAGS)) == "#*/planning"


def test_multi_word_tag_closes_with_hash():
    assert complete("#techne/ser", with_parents(TAGS)) == "#techne/serial numbers#"


def test_only_the_last_token_is_completed():
    assert complete("bulbs @to", TAGS) == "bulbs @todo"
    assert complete("Bulbs #WO", with_parents(TAGS)) == "Bulbs #work"


def test_nothing_for_plain_words_unknown_prefixes_or_trailing_space():
    assert complete("bulbs", TAGS) is None
    assert complete("@zzz", TAGS) is None
    assert complete("#nope", TAGS) is None
    assert complete("@todo ", TAGS) is None
    assert complete("", TAGS) is None
    assert complete("@todo", TAGS) is None  # already complete


def test_case_insensitive_match_keeps_the_candidate_spelling():
    assert complete("@TO", TAGS) == "@todo"
    assert complete("#Ho", with_parents(TAGS)) == "#home"
    # A full tag in another case: the box can only show a longer suggestion,
    # so the next candidate below it is offered.
    assert complete("#Home", with_parents(TAGS)) == "#home/garden"


def test_priority_follows_tag_order():
    assert complete("#h", ["home", "health"]) == "#home"
    assert complete("#h", ["health", "home"]) == "#health"


def test_with_parents_adds_ancestors_once():
    assert with_parents(["a/b/c", "a/b", "x"]) == ["a", "a/b", "a/b/c", "x"]


def test_every_operator_from_bearcli_help_is_listed():
    for op in ("@todo", "@done", "@task", "@title", "@pinned", "@untagged", "@date(", "@ocr", "@backlinks"):
        assert op in OPERATORS


@pytest.mark.asyncio
async def test_suggester_reads_tags_on_each_call():
    tags = ["home"]
    s = QuerySuggester(lambda: tags)
    assert await s.get_suggestion("#h") == "#home"
    tags[:] = ["health"]
    assert await s.get_suggestion("#h") == "#health"
    assert await s.get_suggestion("Bulbs #H") == "Bulbs #health"


# -- Phase 20: through the box --------------------------------------------------------

from helpers import loaded, titles, wait_until  # noqa: E402


async def type_text(pilot, text: str) -> None:
    for ch in text:
        await pilot.press({"@": "at", "#": "number_sign", " ": "space"}.get(ch, ch))


async def test_at_completes_and_right_accepts_and_enter_runs(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await pilot.press("slash")
        await pilot.pause()
        assert app.note_list.hint_visible
        await type_text(pilot, "@to")
        await wait_until(lambda: app.note_list.search_input._suggestion == "@todo")
        await pilot.press("right")
        await pilot.pause()
        assert app.note_list.search_input.value == "@todo"
        await pilot.press("enter")
        await wait_until(lambda: app.search_query == "@todo")
        await wait_until(lambda: set(titles(app)) == {"Sprint Planning", "Garden Plan"})


async def test_hash_completes_from_the_snapshot(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        await pilot.press("slash")
        await type_text(pilot, "bulbs #ho")
        await wait_until(lambda: app.note_list.search_input._suggestion == "bulbs #home")
        await type_text(pilot, "me/")
        await wait_until(lambda: app.note_list.search_input._suggestion == "bulbs #home/garden")
        await pilot.press("escape")


async def test_workspace_tags_come_first(make_app):
    app = make_app(workspace="home")
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        assert app.query_tags()[0] == "home"
        assert app.query_tags()[-1].startswith("work")


async def test_hint_hides_with_the_box(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await loaded(app, pilot)
        assert not app.note_list.hint_visible
        await pilot.press("slash")
        await pilot.pause()
        assert app.note_list.hint_visible
        await pilot.press("escape")
        await pilot.pause()
        assert not app.note_list.hint_visible
        assert not app.note_list.search_open
