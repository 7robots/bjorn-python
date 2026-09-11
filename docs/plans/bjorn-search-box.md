# Bjorn: search operators in the search box
Bear mirror: C82B0EC3-0B91-442D-AB1C-A2447BBB2A51

Status: approved 2026-09-11.

The search box hands the query to bearcli unchanged, so Bear's whole syntax
already works; nothing in the UI says so. This plan makes the operators
discoverable where they are typed: inline completion of `@operators` and
`#tags` as you type, and a one-line cheat sheet under the box while it is
open. No new dependency: Textual's `Input` has a `Suggester` hook that draws
ghost text after the cursor and accepts it on `→`. Phase numbers continue
from the search-highlight plan (15–18).

## Rulings

- 2026-09-11 — "let's go ahead and work on the bear search operators."
- 2026-09-11 — "approved"

## Decisions

- **Approach.** Inline completion over a popup or scope toggles: it costs no
  keys, teaches the syntax by showing it, and degrades to nothing when you
  type a plain word. Toggles were rejected as a second grammar on top of
  Bear's; a popup as more UI than a one-line box warrants.
- **Completion.** `search_box.py: QuerySuggester(Suggester)` completes the
  last token of the value only, keeping the rest verbatim. A token starting
  with `@` completes from the operator list; `#` (or `!#`) from the tags in
  the current snapshot, `#*/` from sub-tag tails; anything else gets no
  suggestion. Case-insensitive prefix match; the first candidate in the
  order below wins. Cache off: the tag list changes with the snapshot.
- **Operators**, from `bearcli help search`, most used first: `@todo @done
  @task @today @yesterday @last7days @date( @ctoday @created7days @cdate(
  @title @tagged @untagged @pinned @images @files @attachments @code @locked
  @readonly @empty @untitled @wikilinks @backlinks @ocr`. `@lastXdays` and
  `@createdXdays` are offered with `7` as the placeholder digit; the
  parenthesised ones stop at `(` so the argument is left to type.
- **Tags** come from `snapshot.notes[*].tags`, unique, sorted, with the
  workspace's tags first when one is set. Multi-word tags complete with
  their closing `#`. The suggester holds a callable returning the current
  tag list so the app never pushes updates into it.
- **Cheat sheet.** A `Static` row under the input, visible only while the
  box is: `"phrase"  -term  #tag  @todo  @title  @today  @last7days  @pinned
  · → accepts a completion`. Muted colour, one line, truncated to width.
- **Keys.** None new. `→` at the end of the value accepts (Textual's
  default); `enter` runs the query as before; `esc` closes.
- **Docs.** README search row and the paragraph under the keys table, and
  the help screen's `/` row, name the completion and the hint row.

## Phases

### Phase 19 — Query suggester
Intent: `src/bjorn/search_box.py` with the operator list and
`QuerySuggester`, pure apart from the tag callable.
Verify: `uv run pytest tests/test_search_box.py -q` covering: `@to` → `@todo`,
`@d` → `@done` (order), `@date` → `@date(`, `#ho` → `#home` and `#home/g` →
`#home/garden`, `!#ho`, `#*/g` → `#*/garden`, multi-word tag closes with `#`,
last-token-only (`bulbs @to` → `bulbs @todo`), plain word → None, unknown
prefix → None, case-insensitive, workspace tags first.
Status: [x] done 2026-09-11 (12 passed)

### Phase 20 — Wire the box
Intent: `NoteList` builds the suggester with a tag callable from the app's
snapshot, attaches it to the input, shows the hint row with the box; README
and help updated.
Verify: `uv run pytest tests/test_search_box.py -q` (extended, through the fake
bearcli): typing `@to` shows ghost text `do`, `→` accepts and `enter` runs
`@todo` (list narrows to the todo notes), `#ho` completes to a snapshot tag,
the hint row is visible only while the box is, `esc` hides both.
Status: [ ]

### Phase 21 — Acceptance gate
Intent: end-to-end against live Bear, run once, headless through the app.
Verify: `uv run python tools/gate_search_box.py` opens the box, types `@to`,
asserts the suggestion, accepts, runs, asserts every listed note has an open
todo; types `#tec`, asserts a live tag completes; `esc` hides the hint row;
then the full suite `uv run pytest -q` once.
Status: [ ]
