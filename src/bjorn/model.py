"""Pure functions over a `Snapshot`: views, tag tree, filtering, sorting.

Everything the three panes show is derived here from one snapshot, so the tag
counts, the smart-filter counts and the notes list always agree with each
other. Nothing in this module touches bearcli.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from .bear import Location, Note, Snapshot, normalize_tag


class View(str, Enum):
    """Sidebar entries above the tag tree, in Bear's order plus Pinned."""

    ALL = "all"
    UNTAGGED = "untagged"
    TODO = "todo"
    TODAY = "today"
    PINNED = "pinned"
    ARCHIVE = "archive"
    TRASH = "trash"

    @property
    def label(self) -> str:
        return _LABELS[self]

    @property
    def location(self) -> Location:
        if self is View.ARCHIVE:
            return Location.ARCHIVE
        if self is View.TRASH:
            return Location.TRASH
        return Location.NOTES

    @property
    def hotkey(self) -> str:
        return str(list(View).index(self) + 1)


_LABELS = {
    View.ALL: "Notes",
    View.UNTAGGED: "Untagged",
    View.TODO: "Todo",
    View.TODAY: "Today",
    View.PINNED: "Pinned",
    View.ARCHIVE: "Archive",
    View.TRASH: "Trash",
}


@dataclass(frozen=True, slots=True)
class Selection:
    """What the notes list is showing: a view, optionally narrowed to a tag,
    always inside the workspace, optionally narrowed further by search ids."""

    view: View = View.ALL
    tag: str = ""
    workspace: str = ""
    search_ids: tuple[str, ...] | None = None

    @property
    def scope_tag(self) -> str:
        """The tag that actually restricts the list: the selected tag if any,
        else the workspace."""
        return self.tag or self.workspace

    def describe(self) -> str:
        parts: list[str] = []
        if self.tag:
            parts.append(f"#{self.tag}")
        else:
            parts.append(self.view.label)
        if self.search_ids is not None:
            parts.append("search")
        return " · ".join(parts)


def in_workspace(note: Note, workspace: str) -> bool:
    return not workspace or note.has_tag(workspace)


def matches_view(note: Note, view: View, today: date | None = None) -> bool:
    if note.location != view.location:
        return False
    if view is View.UNTAGGED:
        return not note.tags
    if view is View.TODO:
        return note.todos > 0
    if view is View.TODAY:
        today = today or date.today()
        return note.modified_local_date() == today
    if view is View.PINNED:
        return note.pinned
    return True


def sort_notes(notes: list[Note], *, pinned_first: bool = True) -> list[Note]:
    """Bear's default: pinned on top, then newest modification first."""

    def key(note: Note):
        modified = note.modified.timestamp() if note.modified else 0.0
        return (0 if (pinned_first and note.pinned) else 1, -modified, note.title.casefold())

    return sorted(notes, key=key)


def select_notes(snapshot: Snapshot, selection: Selection, today: date | None = None) -> list[Note]:
    """The notes list for a selection, sorted."""
    tag = normalize_tag(selection.scope_tag)
    ids = set(selection.search_ids) if selection.search_ids is not None else None
    picked = [
        n
        for n in snapshot.notes
        if matches_view(n, selection.view, today)
        and (not tag or n.has_tag(tag))
        and in_workspace(n, selection.workspace)
        and (ids is None or n.id in ids)
    ]
    if ids is not None:
        order = {nid: i for i, nid in enumerate(selection.search_ids or ())}
        return sorted(picked, key=lambda n: order.get(n.id, len(order)))
    return sort_notes(picked)


def view_counts(snapshot: Snapshot, workspace: str = "", today: date | None = None) -> dict[View, int]:
    today = today or date.today()
    counts = {view: 0 for view in View}
    for note in snapshot.notes:
        if not in_workspace(note, workspace):
            continue
        for view in View:
            if matches_view(note, view, today):
                counts[view] += 1
    return counts


@dataclass(slots=True)
class TagNode:
    """One tag in the nested tree, with the count of notes carrying it or a child."""

    name: str
    path: str
    count: int = 0
    children: dict[str, "TagNode"] = field(default_factory=dict)

    def sorted_children(self) -> list["TagNode"]:
        return sorted(self.children.values(), key=lambda c: c.name.casefold())

    def walk(self):
        for child in self.sorted_children():
            yield child
            yield from child.walk()


def build_tag_tree(snapshot: Snapshot, workspace: str = "", location: Location = Location.NOTES) -> TagNode:
    """Nested tags from the active notes.

    bearcli lists ancestors alongside leaf tags (`#a`, `#a/b`, `#a/b/c`), so a
    note counts once for each level it carries. With a workspace, the root is
    the workspace tag itself and only its subtree is present.
    """
    root = TagNode(name="", path="")
    workspace = normalize_tag(workspace)
    for note in snapshot.notes:
        if note.location != location or not in_workspace(note, workspace):
            continue
        for tag in note.tags:
            if workspace and not (tag == workspace or tag.startswith(workspace + "/")):
                continue
            parts = tag.split("/")
            node = root
            for depth, part in enumerate(parts):
                path = "/".join(parts[: depth + 1])
                node = node.children.setdefault(part, TagNode(name=part, path=path))
            node.count += 1
    return root


def tag_count(tree: TagNode, tag: str) -> int:
    node = tree
    for part in normalize_tag(tag).split("/"):
        node = node.children.get(part)
        if node is None:
            return 0
    return node.count


def duplicate_titles(snapshot: Snapshot, titles: set[str]) -> dict[str, list[str]]:
    """Titles among `titles` that more than one active note carries -> ids.

    The iCloud sync trap: a whole-note overwrite while Bear is syncing can
    resurrect the previous version as a second note with the same title.
    """
    wanted = {t.casefold() for t in titles}
    seen: dict[str, list[str]] = {}
    for note in snapshot.in_location(Location.NOTES):
        key = note.title.casefold()
        if key in wanted:
            seen.setdefault(key, []).append(note.id)
    return {k: v for k, v in seen.items() if len(v) > 1}
