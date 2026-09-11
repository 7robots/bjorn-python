"""Modal screens: confirm, text prompt, format picker, new-note prompt, help."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static

from ..screen import SafeSelectMixin

_DIALOG_CSS = """
$dialog-width: 60;
"""


class ConfirmScreen(SafeSelectMixin, ModalScreen[bool]):
    DEFAULT_CSS = """
    ConfirmScreen {
        align: center middle;
    }
    ConfirmScreen > Vertical {
        width: 60;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    ConfirmScreen Horizontal {
        height: auto;
        align-horizontal: right;
        margin-top: 1;
    }
    ConfirmScreen Button {
        margin-left: 1;
    }
    """
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("y", "confirm", "Yes"),
        Binding("n", "cancel", "No"),
    ]

    def __init__(self, message: str, *, confirm_label: str = "Yes") -> None:
        super().__init__()
        self.message = message
        self.confirm_label = confirm_label

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self.message)
            with Horizontal():
                yield Button("Cancel", id="cancel")
                yield Button(self.confirm_label, id="confirm", variant="error")

    def on_mount(self) -> None:
        self.query_one("#confirm", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm")

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class TextPrompt(SafeSelectMixin, ModalScreen[str | None]):
    """One line of text; None on escape."""

    DEFAULT_CSS = """
    TextPrompt {
        align: center middle;
    }
    TextPrompt > Vertical {
        width: 70;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    TextPrompt Input {
        margin-top: 1;
    }
    TextPrompt .hint {
        color: $text-muted;
        margin-top: 1;
    }
    """
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, title: str, *, prefill: str = "", hint: str = "esc to cancel") -> None:
        super().__init__()
        self.title_text = title
        self.prefill = prefill
        self.hint = hint

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self.title_text)
            yield Input(value=self.prefill, id="value")
            yield Static(self.hint, classes="hint")

    def on_mount(self) -> None:
        box = self.query_one("#value", Input)
        box.focus()
        box.cursor_position = len(box.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip())

    def action_cancel(self) -> None:
        self.dismiss(None)


class FormatPrompt(SafeSelectMixin, ModalScreen[str | None]):
    """Pick an export format: one key per format, or arrows and enter. None on escape."""

    DEFAULT_CSS = """
    FormatPrompt {
        align: center middle;
    }
    FormatPrompt > Vertical {
        width: 70;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    FormatPrompt .choices {
        margin-top: 1;
    }
    FormatPrompt .hint {
        color: $text-muted;
        margin-top: 1;
    }
    """
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "choose", "Choose"),
        Binding("left,h", "move(-1)", "Previous", show=False),
        Binding("right,l", "move(1)", "Next", show=False),
    ]

    def __init__(self, formats, selected: str) -> None:
        super().__init__()
        self.formats = list(formats)
        ids = [f.id for f in self.formats]
        self.index = ids.index(selected) if selected in ids else 0

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Export as")
            yield Static(self._choices(), classes="choices", id="choices")
            yield Static("letter or ←/→ then enter · esc to cancel", classes="hint")

    def _choices(self) -> Text:
        text = Text()
        for i, fmt in enumerate(self.formats):
            if i:
                text.append("   ")
            style = "reverse bold" if i == self.index else ""
            text.append(f" {fmt.key} ", "bold" if i != self.index else style)
            text.append(f"{fmt.label} ", style)
        return text

    def action_move(self, delta: int) -> None:
        self.index = (self.index + delta) % len(self.formats)
        self.query_one("#choices", Static).update(self._choices())

    def action_choose(self) -> None:
        self.dismiss(self.formats[self.index].id)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_key(self, event) -> None:
        for fmt in self.formats:
            if event.character == fmt.key:
                event.stop()
                self.dismiss(fmt.id)
                return


class NewNotePrompt(SafeSelectMixin, ModalScreen[tuple[str, str] | None]):
    """Title and tags for a new note; None on escape."""

    DEFAULT_CSS = """
    NewNotePrompt {
        align: center middle;
    }
    NewNotePrompt > Vertical {
        width: 70;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    NewNotePrompt Label {
        margin-top: 1;
    }
    NewNotePrompt .hint {
        color: $text-muted;
        margin-top: 1;
    }
    """
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, *, default_tags: str = "") -> None:
        super().__init__()
        self.default_tags = default_tags

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("New note")
            yield Label("Title")
            yield Input(placeholder="Title", id="title")
            yield Label("Tags (comma-separated, no #)")
            yield Input(value=self.default_tags, id="tags")
            yield Static("enter to create and open in your editor · esc to cancel", classes="hint")

    def on_mount(self) -> None:
        self.query_one("#title", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        title = self.query_one("#title", Input).value.strip()
        if event.input.id == "title" and not title:
            return
        if event.input.id == "title":
            self.query_one("#tags", Input).focus()
            return
        if not title:
            self.query_one("#title", Input).focus()
            return
        self.dismiss((title, self.query_one("#tags", Input).value.strip()))

    def action_cancel(self) -> None:
        self.dismiss(None)


HELP_TEXT = """\
# Bjorn

Three columns: smart views and tags · notes · the rendered note.

| Key | Action |
|---|---|
| `tab` / `shift+tab` | cycle panes |
| `j` `k` / `↑` `↓` | move within a pane |
| `enter` | open the highlighted note in the reader, at the first match while searching |
| `1`–`7` | Notes, Untagged, Todo, Today, Pinned, Archive, Trash |
| `/` | search with Bear syntax (`@todo`, `#tag`, `"phrase"`, `-term`) |
| `esc` | clear the search and its highlights |
| `]` / `[` | next / previous match in the reader while searching |
| `n` | new note (title, tags) then edit |
| `e` | edit in `$VISUAL` / `$EDITOR` |
| `d` | move the note to the trash |
| `u` | restore from Trash or Archive |
| `p` | toggle the global pin |
| `x` | export the note: Markdown, HTML, plain text, RTF or TextBundle (`←` `→` pick, `export_format` sets the default) |
| `b` | open the note in Bear.app |
| `w` | make the highlighted tag the workspace; again to leave it (`W` also clears) |
| `f` | fold / unfold the highlighted tag's subtree |
| `F` | fold every tag, or unfold every tag when all are folded (within the workspace if one is set) |
| `t` | triage: every open todo in the workspace, grouped by note |
| `c` | cycle the columns: hide tags, then notes too, then show all three (or click ▮▮▮ in the note header) |
| `r` | refresh from Bear now |
| `?` | this help · `q` quit (asks first) |

In triage: `space` marks, `x` ticks the marked (or highlighted) todos in Bear,
`enter` goes to the note, `b` opens it in Bear at the section, `/` filters,
`r` reloads, `esc` or `q` closes. With `[reminders] enabled = true`, `a` adds marked
todos to Apple Reminders and rows show ⏰ (added) or ✓ (completed there).

Edits are hash-guarded: if the note changed in Bear while you were in the
editor, nothing is written and your version is kept in a temp file.
"""


class HelpScreen(SafeSelectMixin, ModalScreen[None]):
    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }
    HelpScreen > VerticalScroll {
        width: 80;
        height: 90%;
        border: thick $accent;
        background: $surface;
        padding: 0 2;
    }
    """
    BINDINGS = [Binding("escape,q,question_mark", "close", "Close")]

    def compose(self) -> ComposeResult:
        from textual.widgets import Markdown

        with VerticalScroll():
            yield Markdown(HELP_TEXT)

    def action_close(self) -> None:
        self.dismiss(None)
