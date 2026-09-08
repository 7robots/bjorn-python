# Bjorn: a Bear TUI
Bear mirror: 9473648C-66AF-4F3A-9621-C7472C38FC57

Status: approved 2026-09-08.

A three-column terminal front end for Bear (tag browser, notes list, rendered note),
built in Python with Textual, talking to Bear only through `bearcli`. Editing is
delegated to `$VISUAL`/`$EDITOR`. Locked notes are out of scope. Todo triage (as in
remtui) is a second plan that starts after this one's acceptance gate.

## Rulings

- 2026-09-08 — Pinned filter = any pin context: "great".
- 2026-09-08 — Archive and Trash sidebar locations: "sounds good".
- 2026-09-08 — PDF export: "we can defer PDF for now. let's call that a future phase."
- 2026-09-08 — Poll refresh: "seems reasonable. is there a simple bearcli query that
  will pick up latest edits?" (answered: cheap probe, see Decisions).
- 2026-09-08 — Export destination prefill: "sounds good".
- 2026-09-08 — Triage: "I'll want to push todo triage to be configurable -- either
  triage in bear OR push to apple reminders. probably a non-default config option to
  sync with apples reminders".
- 2026-09-08 — "go as far as you can with feature development across multiple
  phases, rather than short, incremental pauses to test".

## Decisions

- **Data path.** One snapshot per refresh: `bearcli list --format json --fields all`
  (~0.3 s for ~1000 notes) run on a worker. Tag tree, counts, and the smart filters
  Untagged / Todo / Today / Pinned are computed in memory from that snapshot, so the
  three panes always agree. `bearcli search` is used only for free-text search.
  Note bodies come from `bearcli cat <id> --format json` on selection (~30 ms),
  cached by id with the returned `hash`. Refresh: `r`, after every own write, after
  the editor returns, and on a poll. The poll is a cheap probe every `poll_seconds`
  (default 5, 0 disables): `list --sort modified:desc -n 1 --fields id,modified`
  plus `list --count` (~40 ms together); a full reload runs only when that pair
  changes.
- **Filter semantics.** Untagged = no tags. Todo = `todos > 0`. Today = modified
  today in local time (Bear's `@today`). Pinned = any pin context, global or in-tag
  (`@pinned` matches global only and currently returns nothing). Archive and Trash
  are extra sidebar locations backed by `list --location`, read-only plus Restore.
- **Rendering.** Textual `Markdown` widget, progressive (first ~80 lines on
  highlight, full render on focus, librarian's pattern). Preprocessing before
  render: task lines `- [ ]` / `- [x]` become `☐` / `☑` (Textual's `gfm-like`
  parser has no tasklist plugin), Bear-only `==highlight==` and `~underline~`
  become plain text, the tag line under the H1 is styled as a tag row.
- **Editor.** `$VISUAL`, then `$EDITOR`, then `vim`, overridable in config. Flow:
  `cat --format json` → temp `.md` → `with self.suspend(): subprocess.run(editor)`
  → if bytes changed, `overwrite <id> --base <hash>` from stdin. A rejected write
  (note changed in Bear meanwhile) keeps the temp file and reports its path.
  After any overwrite the next refresh checks the title for a second id and warns
  (iCloud duplicate trap, bear-notes skill).
- **Create.** Modal asks for title; tags default to the workspace tag or the
  selected tag. `create "Title" --tags t --format json --fields id`, then the
  editor opens on the new note.
- **Delete.** `trash <id>` behind a confirm modal. Restore from the Trash view.
- **Workspace.** `w` on a tag scopes the whole app to that subtree: tag browser
  shows only it, smart filters and search are restricted to it, new notes default
  to it, the header names it. `W` clears. `bjorn --tag <tag>` starts scoped.
- **Export.** `x` exports the note as Markdown (raw note text) to a destination
  Input prefilled with `<export_dir>/<title>.md`. PDF is deferred (ROADMAP); the
  headless-Chromium route was verified 2026-09-08 with Edge and is recorded there.
- **Config.** `~/.config/bjorn/config.toml`: `editor`, `export_dir`
  (default `~/Downloads`), `poll_seconds`, `workspace`.
- **Structure.** src layout, `src/bjorn/`: `bear.py` (client + models),
  `render.py` (preprocess), `export.py`, `config.py`, `app.py`, `widgets/`
  (`tag_tree.py`, `note_list.py`, `note_view.py`, modals), `fake_bearcli.py` for
  tests. Widgets talk to the app with nested `Message` subclasses; the app owns
  selection state. Python ≥3.12, `textual>=8.2.8`, `markdown-it-py`; dev:
  pytest, pytest-asyncio (auto), pytest-timeout. `uv` throughout.
- **Tests.** Real subprocesses against `fake_bearcli.py` (remtui's pattern),
  Textual `Pilot` for the UI, no snapshot tests.

## Keys

| Key | Action | Key | Action |
|---|---|---|---|
| `tab` / `shift+tab` | cycle panes | `/` | search (Bear syntax) |
| `j` `k` `enter` | move / open in pane | `esc` | clear search / close modal |
| `n` | new note | `d` | trash note (confirm) |
| `e` | edit in $EDITOR | `x` | export menu |
| `p` | toggle global pin | `o` | open in Bear.app |
| `w` / `W` | set / clear workspace | `r` | refresh |
| `1`–`7` | All, Untagged, Todo, Today, Pinned, Archive, Trash | `?` `q` | help, quit |

## Phases

### Phase 1 — Skeleton and read path
Intent: repo, package, `BearClient` (list, cat, tags) with typed models over
`bearcli --format json`, `fake_bearcli.py`, and the three-column layout browsing
real notes read-only with progressive markdown rendering and preprocessing.
Verify: `uv run pytest tests/test_bear.py tests/test_render.py tests/test_model.py tests/test_layout.py`
Status: [x] done 2026-09-08 (23 passed)

### Phase 2 — Navigation
Intent: nested tag tree with counts, smart filters (Untagged / Todo / Today /
Pinned / Archive / Trash), free-text search via `bearcli search`, workspace
scoping (`w`/`W`, `--tag`), `o` open in Bear, `r` and poll refresh.
Verify: `uv run pytest tests/test_filters.py tests/test_workspace.py tests/test_search.py`
Status: [x] done 2026-09-08 (12 passed)

### Phase 3 — Writes
Intent: edit via `$EDITOR` with hash-guarded overwrite and conflict handling,
create with modal + editor, trash with confirm, restore, pin toggle, duplicate
title warning after writes.
Verify: `uv run pytest tests/test_edit.py tests/test_create_delete.py tests/test_pin.py`
Status: [x] done 2026-09-08 (11 passed)

### Phase 4 — Export and config
Intent: Markdown export with destination prompt; `config.toml`; help modal;
`install.sh`; README.
Verify: `uv run pytest tests/test_export.py tests/test_config.py && uv run pytest`
Status: [x] done 2026-09-08 (54 passed)

### Phase 5 — Acceptance gate
Intent: one scripted pass against the live Bear database, read from the terminal.
Checklist: launch `uv run bjorn`; browse `#techne` and render a long note; hit each
smart filter and compare counts with `bearcli search "@todo" --count` etc.; set and
clear a workspace; create a note under `#techne/dev`, edit it in `$EDITOR`, confirm
the change in Bear.app, pin/unpin, export it as `.md` and open it,
trash it, restore it from Trash, trash it again; quit. Full suite passes once.
Verify: `uv run pytest && uv run bjorn` (checklist above)
Status: [ ] not started

## Deferred (see docs/ROADMAP.md)

Todo triage (second plan). PDF export. Attachments (list, save). Tag rename/delete. Archive
from the TUI. Section-level navigation from `bearcli outline`. Locked notes.
