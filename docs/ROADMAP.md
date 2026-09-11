# Roadmap

Single source of truth for planned and deferred work. The active plan lives in
`docs/plans/`.

## Completed plans

- Bjorn TUI: `docs/plans/bjorn-tui.md` (2026-09-08).
- Todo triage: `docs/plans/bjorn-triage.md` (2026-09-08).
- Export formats: `docs/plans/bjorn-export.md` (2026-09-11).
- Search highlighting and jump-to-match: `docs/plans/bjorn-search.md` (2026-09-11).

## Active plan

- Search operators in the search box: `docs/plans/bjorn-search-box.md`
  (approved 2026-09-11).

## Next

- PDF export (deferred 2026-09-08, approach open 2026-09-11). The tested route
  is the HTML renderer from the export plan fed to a headless Chromium-family
  browser (`--headless=new --print-to-pdf`; verified with Edge, which writes the
  file but never exits, so poll for it and terminate). Jefferson's concern:
  making export depend on a headless browser being installed and behaving.
  Alternatives to weigh when this comes up: macOS-native rendering of the HTML
  through WebKit or an NSAttributedString print operation (a small Swift
  helper or PyObjC, no browser), or a pure-Python PDF writer at the cost of a
  dependency and weaker CSS. Decide before building.
- EPUB export (deferred 2026-09-11): a zip skeleton (mimetype, container.xml,
  OPF, nav, one XHTML chapter, images) around the export plan's HTML renderer;
  stdlib only, verify once in Apple Books.

## Deferred

- Search highlights inside fenced code and table cells (2026-09-11): they
  render through their own widgets (`MarkdownFence` keeps highlighted code,
  table cells are separate `Static`s), so the block walk skips them and they
  never count as matches. Worth doing only if body matches in code turn out
  to matter.
- The reader's match count before the first `]` covers the rendered head
  only on a truncated note; the jump renders the rest and corrects it
  (2026-09-11).
- Persist the body previews (`~/.cache/bjorn/previews.json`, keyed by note id
  and modification stamp) so a cold start lists metadata only, about 0.6 s on
  two thousand notes instead of 1.8 s. The in-memory cache already covers
  every reload after the first (2026-09-10).
- Rendering a very long note in full (170 KB, ~5 s) is Textual's `Markdown`
  mounting one widget per block; the head-then-rest split hides it while
  browsing. A paged or lazily mounted reader would remove it (2026-09-10).
- Notes list snippet line (first body line, as Bear shows) — needs content
  for every listed note; cache-backed or via a bearcli field if one appears.
- Permanent delete from the Trash view: bearcli has no command for it today.

- Attachments: list per note, save to disk (`bearcli attachments`).
- Tag management: rename / delete across notes (destructive, needs confirm).
- Archive a note from the TUI (`bearcli archive`).
- Section navigation in the note view from `bearcli outline`.
- Locked notes: show metadata only, explain why content is unavailable.
- Background change detection smarter than polling (Bear's SQLite mtime).
- Triage follow-ons: edit a todo's text from the screen; snooze a reminder's
  due date; triage `@done` items (un-tick); a "Todo in workspace" smart view.
