# Bjorn

A terminal front end for [Bear](https://bear.app), built with Python and
[Textual](https://textual.textualize.io). Three columns, like the app: smart
views and a nested tag tree on the left, the notes list in the middle, the
rendered note on the right. Everything goes through `bearcli`, the command
line tool that ships inside Bear.app, so Bjorn works with Bear open or closed
and never touches the database directly.

Editing is delegated to your editor (`$VISUAL`, then `$EDITOR`, then `vim`).
Writes back are hash-guarded: if the note changed in Bear while you were
editing, nothing is written and your version is kept in a temp file.

## Install

Requires macOS with Bear installed (`bearcli` at `/usr/local/bin/bearcli`),
Python 3.12+, and [uv](https://docs.astral.sh/uv/).

```sh
git clone https://github.com/7robots/bjorn.git
cd bjorn
./install.sh          # puts a `bjorn` launcher in ~/bin
bjorn                 # or: uv run bjorn
bjorn --tag techne    # start scoped to a tag subtree
bjorn --demo          # sample notes through a built-in fake bearcli, no Bear needed
```

## Keys

| Key | Action | Key | Action |
|---|---|---|---|
| `tab` / `shift+tab` | cycle panes | `/` | search (Bear syntax) |
| `j` `k` `↑` `↓` | move within a pane | `esc` | clear the search |
| `enter` / click | read the highlighted note / highlight it | `1`–`7` | Notes, Untagged, Todo, Today, Pinned, Archive, Trash |
| `n` | new note (title, tags), then edit | `d` | move the note to the trash |
| `e` | edit in `$EDITOR` | `u` | restore from Trash or Archive |
| `p` | toggle the global pin | `x` | export as Markdown |
| `o` | open in Bear.app | `w` / `W` | set / clear the workspace |
| `r` | refresh now | `?` `q` | help, quit |

The **workspace** is a tag subtree that scopes the whole app: the tag tree
shows only it, the smart views count only inside it, search results are
filtered to it, and new notes default to it.

Views are computed from one `bearcli list` snapshot, so the counts in the
sidebar and the notes list always agree. **Pinned** means any pin, global or
inside a tag. **Today** means modified today, local time.

## Configuration

`~/.config/bjorn/config.toml` (or `$XDG_CONFIG_HOME/bjorn/config.toml`). Every
key is optional:

```toml
editor = "nvim"               # overrides $VISUAL / $EDITOR
export_dir = "~/Downloads"    # where `x` proposes to write
poll_seconds = 5              # 0 disables the background refresh
workspace = "techne"          # start scoped to this tag
bearcli = "/usr/local/bin/bearcli"
icon_style = "auto"           # auto | nerd | emoji | none

[icons]                       # top-level tag -> Lucide icon name, or emoji:<glyph>
techne = "terminal"
veritas = "emoji:🎓"
```

Top-level tags and the smart views carry icons: Nerd Font (Material Design)
glyphs when the terminal is Ghostty or WezTerm or a Nerd Font is installed,
emoji otherwise. Built-in defaults cover `veritas`, `techne`, `anthologia`,
`melete`, `poietikos`, `kybernetes`, `architekton` and `publish`; anything else
gets a tag glyph. Names are Lucide's (`bot`, `book-open`, `compass`, ...); see
`src/bjorn/icons.py` for the table.

The poll is cheap: two `bearcli list` probes (about 40 ms) and a full reload
only when something changed.

## Development

```sh
uv sync
uv run pytest          # the suite drives a fake bearcli as a real subprocess
uv run bjorn --demo
```

The plan and its status live in `docs/plans/bjorn-tui.md`; deferred work in
`docs/ROADMAP.md`.
