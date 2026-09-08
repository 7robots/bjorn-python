"""Phase 8: the remctl client, link notes, and the key join."""

from __future__ import annotations

import pytest

from bjorn.reminders import KEY_PREFIX, LinkedReminder, RemctlError, join, link_key, link_notes, note_url
from bjorn.todos import Todo

T1 = Todo("N1", "Sprint", ("work",), "write the notes", "- [ ] write the notes", "## Tasks")
T2 = Todo("N1", "Sprint", ("work",), "ship it", "- [ ] ship it", "## Tasks")


def test_link_notes_and_key_round_trip():
    notes = link_notes(T1)
    assert notes.splitlines() == ["From Bear: Sprint", note_url("N1"), f"{KEY_PREFIX} {T1.key}"]
    assert link_key(notes) == T1.key
    assert link_key("no key here") == ""
    assert link_key("bear-todo: 9afbe7c1dc95") == "9afbe7c1dc95"  # what remtui wrote


def test_join_prefers_an_active_duplicate():
    active = LinkedReminder(1, "write the notes", False, T1.key)
    done = LinkedReminder(2, "write the notes", True, T1.key)
    assert join([T1, T2], [done]) == {T1.key: ("done", 2)}
    assert join([T1, T2], [done, active]) == {T1.key: ("added", 1)}
    assert join([T1, T2], [active, done]) == {T1.key: ("added", 1)}
    assert join([T2], [active]) == {}


def test_from_json_ignores_unlinked_rows():
    assert LinkedReminder.from_json({"id": 5, "title": "x", "completed": False, "notes": "plain"}) is None
    r = LinkedReminder.from_json({"id": "7", "title": "x", "completed": True, "list": "Work", "notes": link_notes(T1)})
    assert r == LinkedReminder(7, "x", True, T1.key, "Work")


async def test_client_add_and_search_against_fake(remctl):
    assert await remctl.linked_reminders() == []
    rid = await remctl.add(T1, list_title="Work", due="today")
    assert rid == 1
    linked = await remctl.linked_reminders()
    assert [(r.id, r.title, r.key, r.list_name, r.completed) for r in linked] == [(1, "write the notes", T1.key, "Work", False)]
    await remctl._run("done", "1")
    assert (await remctl.linked_reminders())[0].completed is True
    with pytest.raises(RemctlError):
        await remctl.add(T2, list_title="Nope")
    with pytest.raises(RemctlError):
        await remctl.add(T2, due="whenever")


async def test_missing_remctl_is_a_remctl_error():
    from bjorn.reminders import RemctlClient

    with pytest.raises(RemctlError):
        await RemctlClient("/nonexistent/remctl").linked_reminders()
