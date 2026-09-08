# Roadmap

Single source of truth for planned and deferred work. The active plan lives in
`docs/plans/`.

## Active plan

- Todo triage: `docs/plans/bjorn-triage.md` (approved 2026-09-08).

## Next

- PDF export (deferred 2026-09-08): markdown-it-py → HTML with a Bear-like
  stylesheet → headless Chromium-family browser (`--headless=new --print-to-pdf`,
  Edge/Chrome autodetected). Verified with Edge: the PDF lands but the process
  never exits, so poll for the file and terminate it.

## Deferred

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
