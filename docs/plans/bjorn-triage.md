# Bjorn: todo triage

Status: DRAFT, awaiting approval.

A triage screen inside Bjorn that gathers every open `- [ ]` item from the
`@todo` notes in scope, lets you tick items done in Bear, jump to the note, or
open it in Bear at the right section. Pushing items to Apple Reminders through
`remctl` is a non-default option that reuses remtui's link scheme, so reminders
remtui already created are recognised. Phase numbers continue from the first
plan (1–5).

## Rulings

- 2026-09-08 — "I'll want to push todo triage to be configurable -- either
  triage in bear OR push to apple reminders. probably a non-default config
  option to sync with apples reminders".

## Decisions

- **Scope.** The triage set is the `@todo` notes inside the workspace (all
  active notes when none is set). One `bearcli search "@todo #<workspace>"
  --format json --fields id,title,tags,locked,content` per load; locked notes
  are counted, not parsed. `/` filters rows by text inside the screen.
- **Parsing.** remtui's parser, ported verbatim: `^(\s*)([-*+]) \[ \]\s+(\S.*?)\s*$`,
  fenced code skipped, the nearest heading above each item kept as its section
  address. A todo's key is `sha1(note_id + "\n" + normalized text)[:12]`, the
  same key remtui writes, so existing `bear-todo:` reminders join up.
- **Screen.** A full `Screen` (not a modal) pushed by `t`, rows grouped under
  note headers: `☐ text` with the section in dim, and, in Reminders mode, a
  status glyph (`⏰` added, `✓` completed). Cursor with `j`/`k`, `space` marks.
- **Tick in Bear.** `x` ticks the highlighted row (or every marked row) via
  `bearcli edit <id> --section <heading> --find <line> --replace <done line>`;
  more than one row asks first. Edits are atomic per note; a miss (the line
  changed in Bear) is reported and the screen reloads.
- **Navigate.** `enter` closes the screen and selects the note in the notes
  list with the reader scrolled to the top; `b` opens it in Bear.app with
  `--header` set to the item's section.
- **Reminders mode.** `[reminders] enabled = true` in config (default false;
  `list`, `due = "today"`, `remctl` path optional). Adds `a`: create a reminder
  per marked row with `remctl add --list L --due D --notes "<From Bear: title>
  \n<bear://…open-note?id=…>\nbear-todo: <key>" -- <text>`. On load, `remctl
  search "bear-todo:" --completed --json` is joined to the rows by key; a
  completed reminder marks its row so `x` can tick Bear to match. Nothing is
  written into Bear on add. Without `remctl` on PATH the mode is off with a
  notice.
- **Refresh.** After any tick the main snapshot reloads (todo counts change).
  `r` reloads the screen from Bear and, in Reminders mode, from remctl.
- **Files.** `todos.py` (parser, key, `Todo`), `reminders.py` (remctl client,
  link notes, join), `widgets/triage.py` (screen), `fake_remctl.py` for tests
  (mirrors remtui's), config `[reminders]` section. Tests: parser and join are
  pure; the screen runs against the fake bearcli and fake remctl as real
  subprocesses.

## Keys (triage screen)

| Key | Action | Key | Action |
|---|---|---|---|
| `t` | open triage (from the main screen) | `esc` `q` | close |
| `j` `k` | move | `space` | mark / unmark |
| `x` | tick in Bear (marked rows, or the highlighted one) | `enter` | go to the note |
| `b` | open in Bear at the section | `/` | filter |
| `a` | add marked to Reminders (Reminders mode only) | `r` | reload |

## Phases

### Phase 6 — Todo model and parser
Intent: `todos.py` with `Todo`, `parse_todos`, keys and done-lines; `BearClient`
gains `todo_notes(workspace)`; the fake bearcli gains `--fields content` on
search (it has it) and an `edit --section` path that matches the real tool.
Verify: `uv run pytest tests/test_todos.py`
Status: [ ] not started

### Phase 7 — Triage screen
Intent: `t` opens the screen scoped to the workspace; grouped rows, cursor,
mark, filter, `x` tick with confirm for many, `enter` to the note, `b` to Bear
at the section, `r` reload; main snapshot reloads after ticks; help updated.
Verify: `uv run pytest tests/test_triage_screen.py`
Status: [ ] not started

### Phase 8 — Reminders mode
Intent: `[reminders]` config, `reminders.py` (remctl client, link notes, key
join), `fake_remctl.py`, `a` to add marked rows, status glyphs from the join,
graceful off state when remctl is missing or disabled.
Verify: `uv run pytest tests/test_reminders.py tests/test_triage_reminders.py && uv run pytest`
Status: [ ] not started

### Phase 9 — Acceptance gate
Intent: one pass against the live database, Reminders mode on with a scratch
list. Checklist: `uv run bjorn --tag techne`, `t`; confirm the row count equals
the open boxes in `bearcli search "@todo #techne" --fields id,title,todos`;
`enter` lands on the right note; `b` opens Bear at the section; mark two rows
in a scratch note, `x`, confirm both boxes ticked in Bear.app; enable
Reminders with `list = "Bjorn Scratch"`, `a` on one row, confirm the reminder
in Reminders.app carries the `bear-todo:` line, complete it there, `r`, see the
row marked done, `x` it; delete the scratch list and note. Full suite once.
Verify: `uv run pytest && uv run bjorn --tag techne` (checklist above)
Status: [ ] not started

## Deferred (see docs/ROADMAP.md)

Editing a todo's text from the screen. Snoozing (moving a reminder's due date).
Triage of `@done` items (un-ticking). A sidebar smart view for "Todo in
workspace" beyond the existing Todo count.
