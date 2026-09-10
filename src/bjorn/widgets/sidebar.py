"""Left column: the smart views above a nested tag tree, like Bear's sidebar."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Label, ListItem, ListView, Static, Tree
from textual.widgets.tree import TreeNode

from ..bear import Snapshot, display_tag
from ..icons import IconSet
from ..model import TagNode, View, build_tag_tree


class ViewItem(ListItem):
    DEFAULT_CSS = """
    ViewItem > Horizontal {
        height: 1;
    }
    ViewItem > Horizontal > .view-label {
        width: 1fr;
    }
    ViewItem > Horizontal > .view-hotkey {
        width: 1;
        color: $text-muted;
    }
    """

    def __init__(self, view: View, icon: str = "") -> None:
        super().__init__(id=f"view-{view.value}")
        self.view = view
        self.icon = icon

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Label(Text.assemble(self.icon, self.view.label), id=f"label-{self.view.value}", classes="view-label")
            yield Label(self.view.hotkey, classes="view-hotkey")


class Sidebar(Vertical):
    """Smart views (ListView) over the tag tree (Tree). Highlighting either one
    is a selection, as clicking is in Bear."""

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
    Sidebar > #views {
        height: auto;
        max-height: 9;
        border: none;
        padding: 0;
    }
    Sidebar > #views > ListItem {
        padding: 0 1;
    }
    Sidebar > #tags {
        height: 1fr;
        padding: 0;
        border: none;
    }
    Sidebar > #tags-label {
        height: 2;
        padding: 1 1 0 1;
        color: $text-muted;
        text-style: bold;
    }
    Sidebar:focus-within > #sidebar-header {
        color: $accent;
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
        self._quiet_view: View | None = None
        #: Fold state by tag path, remembered across rebuilds (reloads, entering
        #: and leaving a workspace) so a tree the user folded stays folded.
        self._expanded: dict[str, bool] = {}

    def compose(self) -> ComposeResult:
        yield Static("BJORN", id="sidebar-header")
        yield ListView(*[ViewItem(v, self.icons.for_view(v.value)) for v in View], id="views")
        yield Static("TAGS", id="tags-label")
        tree: Tree[str] = Tree("Tags", id="tags")
        tree.show_root = False
        tree.guide_depth = 2
        # A click on a tag selects it; only the arrow (or space) toggles the
        # subtree. With auto_expand a click collapsed the tag it was aiming at.
        tree.auto_expand = False
        yield tree

    @property
    def views(self) -> ListView:
        return self.query_one("#views", ListView)

    @property
    def tree(self) -> Tree:
        return self.query_one("#tags", Tree)

    # -- populate --------------------------------------------------------------

    def set_workspace(self, workspace: str) -> None:
        self._workspace = workspace
        header = self.query_one("#sidebar-header", Static)
        header.update(f"WORKSPACE {display_tag(workspace)}" if workspace else "BJORN")

    async def populate(self, snapshot: Snapshot, workspace: str, *, keep_tag: str = "") -> None:
        """Rebuild both lists from a snapshot without firing selection messages."""
        self._suppress = True
        try:
            self.set_workspace(workspace)
            tree = self.tree
            self._remember_folds()
            root = build_tag_tree(snapshot, workspace)
            tree.clear()
            # Every tag starts folded, as in a fresh Bear sidebar; a workspace
            # is one subtree, so it opens fully.
            self._fill(tree.root, root, expand_depth=0 if not workspace else 99)
            if keep_tag:
                self.move_to_tag(keep_tag)
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
        if cursor is not None and not expand and cursor.parent is not None and cursor.parent is not tree.root:
            top = cursor
            while top.parent is not None and top.parent is not tree.root:
                top = top.parent
            tree.move_cursor(top)
        return expand

    def _remember_folds(self) -> None:
        for node in self._all_nodes(self.tree.root):
            if node.allow_expand and node.data:
                self._expanded[str(node.data)] = node.is_expanded

    def _fill(self, parent: TreeNode, node: TagNode, expand_depth: int, depth: int = 0) -> None:
        for child in node.sorted_children():
            icon = self.icons.for_tag(child.path) if "/" not in child.path else ""
            label = Text.assemble(icon, child.name)
            if child.children:
                expand = self._expanded.get(child.path, depth < expand_depth)
                tn = parent.add(label, data=child.path, expand=expand)
                self._fill(tn, child, expand_depth, depth + 1)
            else:
                parent.add_leaf(label, data=child.path)

    def move_to_tag(self, tag: str) -> bool:
        """Put the tree cursor on a tag path, expanding ancestors, and select
        it unless a populate is in progress. False if the tag is absent."""
        for node in self._all_nodes(self.tree.root):
            if node.data == tag:
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
        node = self.tree.cursor_node
        return str(node.data) if node is not None and node.data else ""

    def select_view(self, view: View) -> None:
        """Move the highlight without announcing it: the caller applies the
        selection itself, and an echoed ViewSelected would re-apply it with no
        note kept."""
        if self.views.index != list(View).index(view):
            self._quiet_view = view
            self.views.index = list(View).index(view)

    # -- events ----------------------------------------------------------------

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.list_view is not self.views or self._suppress:
            return
        if isinstance(event.item, ViewItem):
            if event.item.view == self._quiet_view:
                self._quiet_view = None
                return
            self.post_message(self.ViewSelected(event.item.view))

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted) -> None:
        if self._suppress or not self.tree.has_focus:
            return
        if event.node.data:
            self.post_message(self.TagSelected(str(event.node.data)))

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        if event.node.data:
            self.post_message(self.TagSelected(str(event.node.data)))

    def on_descendant_focus(self, event) -> None:
        """Moving focus back onto a list re-applies its selection, so the notes
        pane follows whichever sidebar list the cursor is in."""
        if self._suppress:
            return
        if event.widget is self.tree:
            tag = self.highlighted_tag()
            if tag:
                self.post_message(self.TagSelected(tag))
        elif event.widget is self.views:
            item = self.views.highlighted_child
            if isinstance(item, ViewItem):
                self.post_message(self.ViewSelected(item.view))
