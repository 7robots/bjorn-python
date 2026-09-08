"""Phase 6: todo parsing, keys, and the bearcli read path."""

from __future__ import annotations

import pytest

from bjorn.bear import BearError
from bjorn.todos import Todo, parse_todos, scan_rows

BODY = """# Sprint
#work

- [ ] top level, no section
## Tasks
- [x] done already
- [ ] write the release notes
  - [ ] nested child
* [ ] star bullet
1. not a todo
```
- [ ] inside a fence
```
### Sub
- [ ]  double  spaced   text
"""


def test_parse_todos_in_order_with_sections():
    todos = parse_todos(BODY, note_id="N", note_title="Sprint", note_tags=["work"])
    assert [t.text for t in todos] == [
        "top level, no section", "write the release notes", "nested child", "star bullet", "double  spaced   text",
    ]
    assert [t.section for t in todos] == ["# Sprint", "## Tasks", "## Tasks", "## Tasks", "### Sub"]
    assert todos[2].line == "  - [ ] nested child"
    assert todos[2].done_line == "  - [x] nested child"
    assert todos[1].header == "Tasks"
    assert todos[0].header == "Sprint"


def test_key_matches_remtui_scheme_and_ignores_spacing():
    a = Todo("N", "T", (), "Write  the notes", "- [ ] Write  the notes")
    b = Todo("N", "T", (), "write the notes", "- [ ] write the notes")
    c = Todo("M", "T", (), "write the notes", "- [ ] write the notes")
    assert a.key == b.key and len(a.key) == 12
    assert a.key != c.key
    import hashlib
    assert a.key == hashlib.sha1(b"N\nwrite the notes").hexdigest()[:12]


def test_scan_rows_counts_locked_and_notes():
    rows = [
        {"id": "A", "title": "A", "tags": ["#work"], "locked": "no", "content": "- [ ] one\n- [ ] two\n"},
        {"id": "B", "title": "B", "tags": [], "locked": "yes", "content": None},
        {"id": "C", "title": "C", "tags": ["#home"], "locked": "no", "content": "nothing open\n"},
    ]
    scan = scan_rows(rows)
    assert [t.text for t in scan.todos] == ["one", "two"]
    assert scan.todos[0].note_tags == ("work",)
    assert scan.locked == 1 and scan.notes == 1


async def test_todo_rows_scoped_by_workspace(client):
    rows = await client.todo_rows()
    assert [r["id"] for r in rows] == ["NOTE-PLANNING", "NOTE-GARDEN"]
    assert "content" in rows[0]
    scoped = await client.todo_rows("home")
    assert [r["id"] for r in scoped] == ["NOTE-GARDEN"]
    scan = scan_rows(rows)
    assert [t.text for t in scan.todos][:3] == ["write the release notes", "ask Priya about the API deprecation", "confirm the sunset date"]
    assert "this is inside a code block" not in [t.text for t in scan.todos]


async def test_tick_via_edit_is_scoped_to_the_section(client):
    todos = scan_rows(await client.todo_rows("home"))
    hydrangea = next(t for t in todos.todos if "hydrangea" in t.text)
    assert hydrangea.section == "## Next spring"
    await client.edit(hydrangea.note_id, hydrangea.line, hydrangea.done_line, section=hydrangea.section)
    content = (await client.cat("NOTE-GARDEN")).content
    assert "- [x] move the hydrangea" in content
    assert "- [ ] order bulbs for the front bed" in content
    with pytest.raises(BearError):
        await client.edit(hydrangea.note_id, hydrangea.line, hydrangea.done_line, section=hydrangea.section)
    with pytest.raises(BearError):
        await client.edit("NOTE-GARDEN", "- [ ] order bulbs for the front bed", "x", section="## Next spring")
