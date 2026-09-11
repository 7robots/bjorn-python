"""Left column: the smart views above a nested tag tree, like Bear's sidebar."""

from __future__ import annotations

from rich.cells import cell_len
from rich.style import Style
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Label, ListItem, ListView, Static, Tree
from textual.widgets.tree import TreeNode

from ..bear import Snapshot, display_tag
from ..icons import IconSet
from ..model import TagNode, View, build_tag_tree, view_counts


class ViewItem(ListItem):
    def __init__(self, view: View, count: int, icon: str = "") -> None:
        super().__init__(id=f"view-{view.value}")
        self.view = view
        self.count = count
        self.icon = icon

    DEFAULT_CSS = """
    ViewItem > Horizontal {
        height: 1;
    }
    ViewItem > Horizontal > .view-label {
        width: 1fr;
    }
    ViewItem > Horizontal > .view-count {
        width: 5;
        text-align: right;
        text-style: dim;
    }
    ViewItem > Horizontal > .view-hotkey {
        width: 3;
        text-align: right;
        color: $text-muted;
    }
    """

    def _text(self) -> Text:
        return Text.assemble(self.icon, self.view.label)

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Label(self._text(), id=f"label-{self.view.value}", classes="view-label")
            yield Label(str(self.count), classes="view-count")
            yield Label(self.view.hotkey, classes="view-hotkey")

    def update_count(self, count: int) -> None:
        self.count = count
        self.query_one(".view-count", Label).update(str(count))


class TagTree(Tree[str]):
    """The tag tree with every note count flush against the right edge.

    Textual caches each rendered line with the widget width in the key, so
    padding the label out to the width here re-renders correctly on resize.
    The padded label is the row, so the cursor and hover highlight span it
    like the smart-view rows above. A tag too long to fit keeps one space
    before its count and the tree scrolls sideways as before.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.counts: dict[str, int] = {}

    def render_label(self, node: TreeNode[str], base_style: Style, style: Style) -> Text:
        text = super().render_label(node, base_style, style)
        count = self.counts.get(node.data or "")
        if count is None:
            return text
        depth = 0
        parent = node.parent
        while parent is not None:
            depth += 1
            parent = parent.parent
        if not self.show_root:
            depth -= 1  # the hidden root draws no guide
        count_text = str(count)
        pad = self.size.width - depth * self.guide_depth - text.cell_len - cell_len(count_text)
        text.append(" " * max(pad, 1), style)
        text.append(count_text, style + Style(dim=True))
        return text


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
        #: Fold state by tag path, remembered across rebuilds (reloads, entering
        #: and leaving a workspace) so a tree the user folded stays folded.
        self._expanded: dict[str, bool] = {}

    def compose(self) -> ComposeResult:
        yield Static("BJORN", id="sidebar-header")
        yield ListView(*[ViewItem(v, 0, self.icons.for_view(v.value)) for v in View], id="views")
        yield Static("TAGS", id="tags-label")
        tree = TagTree("Tags", id="tags")
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
    def tree(self) -> TagTree:
        return self.query_one("#tags", TagTree)

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
            counts = view_counts(snapshot, workspace)
            for item in self.views.query(ViewItem):
                item.update_count(counts[item.view])
            tree = self.tree
            self._remember_folds()
            root = build_tag_tree(snapshot, workspace)
            tree.clear()
            tree.counts.clear()
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
            self.tree.counts[child.path] = child.count
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
        self.views.index = list(View).index(view)

    # -- events ----------------------------------------------------------------

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.list_view is not self.views or self._suppress:
            return
        if isinstance(event.item, ViewItem):
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
