# Bjorn: search highlighting and jump-to-match
Bear mirror: 84627A9A-7D49-423F-90AF-6422C938527E

Status: approved 2026-09-11.

`/` already finds notes whose only match is in the body, because bearcli
searches full text. Bjorn then shows nothing about *where* the match is: the
list rows show the title and the leading preview, and the reader renders the
note plain. This plan highlights the query's terms in the reader and the list
rows, and adds keys to jump between matches in the reader. Phase numbers
continue from the export plan (10–14).

## Rulings

- 2026-09-11 — "I'd like to highlight the search results and a jump-to-match"
- 2026-09-11 — "approved, let's get started"
- 2026-09-11 — "as a future roadmap item, I'd also want to consider ways to
  surface some of bearcli's search options in the search box, but not ready
  to tackle that yet" (ROADMAP line under Next).

## Decisions

- **Terms.** `search.py: terms(query) -> list[str]` extracts what Bear would
  match against text: bare words and `"quoted phrases"`. Operators (`@todo`,
  `@title`, `@date(...)`), tags (`#tag`, `!#tag`, `#*/tag`) and negations
  (`-term`, `-"phrase"`) are dropped. `@title foo` keeps `foo`. An empty
  result (query was operators only) means nothing to highlight.
  `pattern(terms)` builds one case-insensitive regex, longest term first,
  escaped. Bear matches substrings, so no word boundaries.
- **Reader.** After `Markdown.update`, `NoteView.highlight(pattern)` walks the
  rendered `MarkdownBlock`s, applies `Content.highlight_regex` to each block's
  content through `set_content`, and records the blocks that matched, in
  document order. Highlighted blocks: headers, paragraphs, list items, block
  quotes. Fenced code and table cells render through their own widgets and
  are left unhighlighted (ROADMAP line if it matters). Style `reverse bold`,
  theme-independent. Re-applied when the truncated head is completed by
  `render_full`, and when a new note is shown while the search is active.
  Cleared by `esc` (clear search) and when a note is shown with no query.
- **Jump.** `]` next match, `[` previous, global bindings, no-ops with no
  active search. Each scrolls the reader so the match's block sits at the
  top and moves focus into the reader. Matches past the rendered head render
  the rest first. `enter` on a list row while a search is active goes to the
  first match instead of the top. The reader header shows `match k/n` after
  the title; `n` is the count of matching blocks, one per block even when a
  block holds several hits.
- **List rows.** `NoteItem.render` applies the same pattern to the title and
  the preview rows with the same style. The preview stays the leading body
  text: showing the first *matching* line needs every listed note's content,
  which is the existing ROADMAP snippet item and out of scope here.
- **Plumbing.** `app.search_query` already holds the live query; the app
  compiles the pattern once per search and passes it to `NoteView` and
  `NoteList`. No new bearcli calls; nothing new persisted.
- **Docs.** README key table, in-app help and the search row of the keys
  section gain `]` `[` and the `enter` behaviour; phase 16 lands them.

## Keys

| Key | Action |
|---|---|
| `]` / `[` | next / previous match in the reader (search active) |
| `enter` | on a list row, into the reader at the first match when a search is active |

## Phases

### Phase 15 — Term extraction
Intent: `src/bjorn/search.py` with `terms` and `pattern`, pure functions.
Verify: `uv run pytest tests/test_search_terms.py -q` covering words, phrases,
every operator family dropped, negations dropped, `@title foo` -> `foo`,
operators-only -> `[]`, regex escaping, case-insensitivity, longest-first.
Status: [x] done 2026-09-11 (10 passed)

### Phase 16 — Reader highlighting and jump
Intent: `NoteView.highlight`, `]` `[` bindings, `enter` to first match,
`match k/n` in the header, re-highlight after `render_full`, clear on `esc`;
README, help text and keys table updated.
Verify: `uv run pytest tests/test_search_highlight.py -q` through the fake
bearcli: a body-only term highlights the paragraph's Content spans, `]` moves
the scroll to the second block and updates `k/n`, `[` moves back, `enter` from
the list lands on the first match, `esc` leaves no highlight spans, a
truncated long note completes before jumping past the head.
Status: [x] done 2026-09-11 (5 passed; full suite 140)

### Phase 17 — List row highlighting
Intent: `NoteItem.render` highlights the pattern in the title and preview.
Verify: `uv run pytest tests/test_search_highlight.py -q` (extended): a row
whose title or preview holds the term carries the highlight style; a row
with a body-only match shows none; rows are plain after `esc`.
Status: [ ]

### Phase 18 — Acceptance gate
Intent: end-to-end against live Bear, run once, headless through the app.
Verify: `uv run python tools/gate_search.py` searches a term known to be
body-only (`hash-guarded`), asserts the note lists, the reader has highlight
spans, `]` scrolls and the header reads `match 1/n`, `[` returns, list-row
highlights appear for a title term, and `esc` clears everything, then the
full suite `uv run pytest -q` once.
Status: [ ]
