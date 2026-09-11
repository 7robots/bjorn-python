"""Left column: the smart views and the nested tag tree in one list, like Bear's sidebar.

One `Tree` holds both, so the cursor runs from the last smart view straight
into the tags with the arrow keys, and `tab` leaves the column for the notes
list from either. Between the two groups sit three rows that the cursor skips:
two blank ones and the TAGS heading.
"""

from __future__ import annotations

from rich.cells import cell_len
from rich.style import Style
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Static, Tree
from textual.widgets.tree import TreeNode

from ..bear import Snapshot, display_tag
from ..icons import IconSet
from ..model import TagNode, View, build_tag_tree, view_counts

#: Node data: a smart view is `("view", View)`, a tag is its bare path, and the
#: rows between the groups carry None so the cursor never rests on them.
ViewData = tuple[str, View]
TAGS_HEADING = "TAGS"
GAP_ROWS = 2


def view_of(node: TreeNode | None) -> View | None:
    data = node.data if node is not None else None
    return data[1] if isinstance(data, tuple) and data and data[0] == "view" else None


def tag_of(node: TreeNode | None) -> str:
    data = node.data if node is not None else None
    return data if isinstance(data, str) else ""


class SidebarTree(Tree[object]):
    """Smart views over the tags, every count flush against the right edge.

    Textual caches each rendered line with the widget width in the key, so
    padding the label out to the width here re-renders correctly on resize.
    The padded label is the row, so the cursor and hover highlight span it.
    A tag too long to fit keeps one space before its count and the tree
    scrolls sideways as before. Smart-view rows end with their hotkey.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.counts: dict[str, int] = {}
        self.view_counts: dict[View, int] = {}

    def render_label(self, node: TreeNode[object], base_style: Style, style: Style) -> Text:
        text = super().render_label(node, base_style, style)
        view = view_of(node)
        if view is not None:
            count, tail = str(self.view_counts.get(view, 0)), f"  {view.hotkey}"
        elif (tag := tag_of(node)) and tag in self.counts:
            count, tail = str(self.counts[tag]), ""
        elif node.data is None and text.plain == TAGS_HEADING:
            text.stylize("bold")
            return text
        else:
            return text
        depth = 0
        parent = node.parent
        while parent is not None:
            depth += 1
            parent = parent.parent
        if not self.show_root:
            depth -= 1  # the hidden root draws no guide
        pad = self.size.width - depth * self.guide_depth - text.cell_len - cell_len(count) - cell_len(tail)
        text.append(" " * max(pad, 1), style)
        text.append(count, style + Style(dim=True))
        if tail:
            text.append(tail, style + Style(dim=True))
        return text

    def validate_cursor_line(self, value: int) -> int:
        """Never rest on a gap row: carry on in the direction of travel, or, at
        the edge, back the other way."""
        line = super().validate_cursor_line(value)
        if self._selectable(line):
            return line
        forward = 1 if line >= self.cursor_line else -1
        for step in (forward, -forward):
            probe = line + step
            while 0 <= probe <= self.last_line:
                if self._selectable(probe):
                    return probe
                probe += step
        return line

    def _selectable(self, line: int) -> bool:
        node = self.get_node_at_line(line)
        return node is not None and node.data is not None


class Sidebar(Vertical):
    """Highlighting a smart view or a tag is a selection, as clicking is in Bear."""

    DEFAULT_CSS = """
    Sidebar {
        width: 30;
        min-width: 20;
        height: 1fr;
        border-right: solid $panel-lighten-2;
    }
    Sidebar > #sidebar-header {
        height: 1;
        padding: 0 1;
        background: $primary-background;
        color: $success;
        text-style: bold;
    }
    Sidebar > #sidebar-tree {
        height: 1fr;
        padding: 0;
        border: none;
    }
    Sidebar.focused > #sidebar-header {
        background: $accent;
        color: $text;
    }
    """

    class ViewSelected(Message):
        def __init__(self, view: View) -> None:
            super().__init__()
            self.view = view

    class TagSelected(Message):
        def __init__(self, tag: str) -> None:
            super().__init__()
            self.tag = tag

    def __init__(self, icons: IconSet | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.icons = icons or IconSet("none")
        self._workspace = ""
        self._suppress = False
        #: Fold state by tag path, remembered across rebuilds (reloads, entering
        #: and leaving a workspace) so a tree the user folded stays folded.
        self._expanded: dict[str, bool] = {}

    def compose(self) -> ComposeResult:
        yield Static("BJORN", id="sidebar-header")
        tree = SidebarTree("Bjorn", id="sidebar-tree")
        tree.show_root = False
        tree.guide_depth = 2
        # A click on a row selects it; only the arrow (or space) toggles the
        # subtree. With auto_expand a click collapsed the tag it was aiming at.
        tree.auto_expand = False
        yield tree

    @property
    def tree(self) -> SidebarTree:
        return self.query_one("#sidebar-tree", SidebarTree)

    # -- populate --------------------------------------------------------------

    def set_workspace(self, workspace: str) -> None:
        self._workspace = workspace
        header = self.query_one("#sidebar-header", Static)
        header.update(f"WORKSPACE {display_tag(workspace)}" if workspace else "BJORN")

    async def populate(self, snapshot: Snapshot, workspace: str, *, keep_tag: str = "", keep_view: View = View.ALL) -> None:
        """Rebuild the column from a snapshot without firing selection messages.
        The cursor lands on `keep_tag` when it is still there, else on `keep_view`."""
        self._suppress = True
        try:
            self.set_workspace(workspace)
            tree = self.tree
            self._remember_folds()
            root = build_tag_tree(snapshot, workspace)
            tree.clear()
            tree.counts.clear()
            tree.view_counts = view_counts(snapshot, workspace)
            for view in View:
                tree.root.add_leaf(Text.assemble(self.icons.for_view(view.value), view.label), data=("view", view))
            for _ in range(GAP_ROWS):
                tree.root.add_leaf("", data=None)
            tree.root.add_leaf(TAGS_HEADING, data=None)
            # Every tag starts folded, as in a fresh Bear sidebar; a workspace
            # is one subtree, so it opens fully.
            self._fill(tree.root, root, expand_depth=0 if not workspace else 99)
            if not (keep_tag and self.move_to_tag(keep_tag)):
                self.select_view(keep_view)
        finally:
            self._suppress = False

    def toggle_all_folds(self) -> bool:
        """Collapse every tag in the tree if any is open, else expand every one.
        Scoped by construction: inside a workspace the tree holds only that
        subtree. Returns True when the result is expanded."""
        tree = self.tree
        branches = [n for n in self._all_nodes(tree.root) if n.allow_expand]
        expand = not any(n.is_expanded for n in branches)
        for node in branches:
            node.expand() if expand else node.collapse()
        self._remember_folds()
        cursor = tree.cursor_node
        if cursor is not None and not expand and tag_of(cursor) and cursor.parent is not tree.root:
            top = cursor
            while top.parent is not None and top.parent is not tree.root:
                top = top.parent
            tree.move_cursor(top)
        return expand

    def _remember_folds(self) -> None:
        for node in self._all_nodes(self.tree.root):
            if node.allow_expand and tag_of(node):
                self._expanded[tag_of(node)] = node.is_expanded

    def _fill(self, parent: TreeNode, node: TagNode, expand_depth: int, depth: int = 0) -> None:
        for child in node.sorted_children():
            icon = self.icons.for_tag(child.path) if "/" not in child.path else ""
            label = Text.assemble(icon, child.name)
            self.tree.counts[child.path] = child.count
            if child.children:
                expand = self._expanded.get(child.path, depth < expand_depth)
                tn = parent.add(label, data=child.path, expand=expand)
                self._fill(tn, child, expand_depth, depth + 1)
            else:
                parent.add_leaf(label, data=child.path)

    def tag_roots(self) -> list[TreeNode]:
        """The top-level tag nodes, below the smart views and the heading."""
        return [n for n in self.tree.root.children if tag_of(n)]

    def view_node(self, view: View) -> TreeNode:
        return next(n for n in self.tree.root.children if view_of(n) is view)

    def move_to_tag(self, tag: str) -> bool:
        """Put the cursor on a tag path, expanding ancestors, and select it
        unless a populate is in progress. False if the tag is absent."""
        for node in self._all_nodes(self.tree.root):
            if tag_of(node) == tag:
                ancestor = node.parent
                while ancestor is not None:
                    ancestor.expand()
                    ancestor = ancestor.parent
                if node.line == -1:
                    # expand() only marks the tree dirty; the node gets its line
                    # on the next rebuild, which any line lookup forces.
                    self.tree.get_node_at_line(0)
                self.tree.move_cursor(node)
                if not self._suppress:
                    self.post_message(self.TagSelected(tag))
                return True
        return False

    def _all_nodes(self, node: TreeNode):
        for child in node.children:
            yield child
            yield from self._all_nodes(child)

    def highlighted_tag(self) -> str:
        return tag_of(self.tree.cursor_node)

    def highlighted_view(self) -> View | None:
        return view_of(self.tree.cursor_node)

    def select_view(self, view: View) -> None:
        """Put the cursor on a smart view without announcing it; callers apply
        the selection themselves."""
        was = self._suppress
        self._suppress = True
        try:
            self.tree.move_cursor(self.view_node(view))
        finally:
            self._suppress = was

    # -- events ----------------------------------------------------------------

    def _announce(self, node: TreeNode | None) -> None:
        view = view_of(node)
        if view is not None:
            self.post_message(self.ViewSelected(view))
        elif tag := tag_of(node):
            self.post_message(self.TagSelected(tag))

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted) -> None:
        if self._suppress or not self.tree.has_focus:
            return
        self._announce(event.node)

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        if not self._suppress:
            self._announce(event.node)

    def on_descendant_focus(self, event) -> None:
        """Moving focus back onto the column re-applies its selection, so the
        notes pane follows the cursor."""
        self.add_class("focused")
        if not self._suppress and event.widget is self.tree:
            self._announce(self.tree.cursor_node)

    def on_descendant_blur(self, event) -> None:
        self.remove_class("focused")
