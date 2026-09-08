# Roadmap

Single source of truth for planned and deferred work. The active plan lives in
`docs/plans/`.

## Next plan

- Todo triage: re-implement remtui's Bear triage screen (`b`) inside Bjorn —
  scan `@todo` notes in the workspace and tick items done via `bearcli edit`.
  Pushing to Apple Reminders through `remctl` is a non-default config option
  (ruling 2026-09-08). Starts after the Bjorn TUI plan's acceptance gate.
- PDF export (deferred 2026-09-08): markdown-it-py → HTML with a Bear-like
  stylesheet → headless Chromium-family browser (`--headless=new --print-to-pdf`,
  Edge/Chrome autodetected). Verified with Edge: the PDF lands but the process
  never exits, so poll for the file and terminate it.

## Deferred

- Attachments: list per note, save to disk (`bearcli attachments`).
- Tag management: rename / delete across notes (destructive, needs confirm).
- Archive a note from the TUI (`bearcli archive`).
- Section navigation in the note view from `bearcli outline`.
- Locked notes: show metadata only, explain why content is unavailable.
- Background change detection smarter than polling (Bear's SQLite mtime).
