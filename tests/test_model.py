from datetime import date, datetime, timezone

from bjorn.bear import Location, Note, Snapshot
from bjorn.model import Selection, View, build_tag_tree, duplicate_titles, select_notes, tag_count, view_counts

TODAY = date(2026, 9, 8)


def mk(id, title, tags=(), *, modified="2026-09-01T12:00:00Z", pins=(), todos=0, location=Location.NOTES):
    return Note(
        id=id, title=title, tags=tuple(tags), pins=tuple(pins), todos=todos, location=location,
        modified=datetime.fromisoformat(modified.replace("Z", "+00:00")),
    )


def snap():
    return Snapshot(notes=[
        mk("1", "A", ["work", "work/sprint"], pins=["global"], todos=2, modified="2026-09-08T12:00:00Z"),
        mk("2", "B", ["home", "home/garden"], pins=["#home"], modified="2026-09-07T12:00:00Z"),
        mk("3", "C", ["home"], modified="2026-09-06T12:00:00Z"),
        mk("4", "D", [], modified="2026-09-05T12:00:00Z"),
        mk("5", "E", ["work"], location=Location.TRASH),
        mk("6", "F", ["work"], location=Location.ARCHIVE),
        mk("7", "A", ["work"], modified="2026-09-04T12:00:00Z"),
    ])


def test_view_counts_and_pinned_means_any_pin():
    counts = view_counts(snap(), today=TODAY)
    assert counts[View.ALL] == 5
    assert counts[View.UNTAGGED] == 1
    assert counts[View.TODO] == 1
    assert counts[View.TODAY] == 1
    assert counts[View.PINNED] == 2
    assert counts[View.ARCHIVE] == 1 and counts[View.TRASH] == 1


def test_workspace_scopes_counts_and_tree():
    counts = view_counts(snap(), workspace="home", today=TODAY)
    assert counts[View.ALL] == 2 and counts[View.UNTAGGED] == 0 and counts[View.PINNED] == 1
    tree = build_tag_tree(snap(), workspace="home")
    assert [c.path for c in tree.sorted_children()] == ["home"]
    assert tag_count(tree, "home") == 2 and tag_count(tree, "home/garden") == 1
    full = build_tag_tree(snap())
    assert [c.path for c in full.sorted_children()] == ["home", "work"]
    assert tag_count(full, "work") == 2  # trash and archive excluded


def test_select_notes_sorts_pinned_first_then_newest():
    assert [n.id for n in select_notes(snap(), Selection(), today=TODAY)] == ["1", "2", "3", "4", "7"]
    assert [n.id for n in select_notes(snap(), Selection(tag="home"), today=TODAY)] == ["2", "3"]
    assert [n.id for n in select_notes(snap(), Selection(view=View.TRASH), today=TODAY)] == ["5"]
    assert [n.id for n in select_notes(snap(), Selection(view=View.TODO, workspace="home"), today=TODAY)] == []


def test_search_ids_keep_bearcli_order_and_respect_scope():
    sel = Selection(search_ids=("4", "2", "5", "1"))
    assert [n.id for n in select_notes(snap(), sel, today=TODAY)] == ["4", "2", "1"]
    sel = Selection(workspace="home", search_ids=("4", "2", "1"))
    assert [n.id for n in select_notes(snap(), sel, today=TODAY)] == ["2"]


def test_duplicate_titles_only_among_active_notes():
    assert duplicate_titles(snap(), {"a"}) == {"a": ["1", "7"]}
    assert duplicate_titles(snap(), {"e"}) == {}
    assert Selection(tag="x", search_ids=()).describe() == "#x · search"
