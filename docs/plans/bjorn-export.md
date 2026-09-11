# Bjorn: export formats
Bear mirror: FDCFF362-4ADA-4494-8FF8-7B36EE8DCB4A

Status: approved 2026-09-11.

Export the highlighted note as HTML, plain text, RTF or TextBundle in addition
to Markdown. One renderer turns Bear's markdown into HTML; the other formats
are conversions or packagings of that or of the source text. No new Python
dependency: markdown-it-py ships with Textual, `textutil` ships with macOS,
`bearcli attachments save` returns attachment bytes. Phase numbers continue
from the triage plan (6–9).

## Rulings

- 2026-09-11 — "let's hold off on the PDF and Epub export right now and
  prioritize html, txt, rtf, and textbundle."
- 2026-09-11 — "one modification to the PDF entry. I'm not sure about making
  our pdf export dependent on a headless web browser operation. we don't need
  to solve that right now, but document the concern so that we can talk about
  it later. otherwise, go ahead and get started."

## Decisions

- **Picker.** `x` opens a one-row format prompt: `m` Markdown, `h` HTML, `t`
  Text, `r` RTF, `b` TextBundle; `enter` takes the preselected one, `esc`
  cancels. Then the existing path prompt, prefilled with the export directory
  and the right extension. Config `export_format = "md"` sets the preselection.
- **Renderer.** `render_html.py`: a Bear pre-pass shared with `render.preprocess`
  (task boxes, `==highlight==`, `~underline~`, the tag line, fenced code left
  alone), then markdown-it-py with the `gfm-like` preset plus tables and
  strikethrough. Highlights become `<mark>`, underline `<u>`, task boxes
  disabled `<input type="checkbox">`, the tag line a row of `.tag` spans.
  Attachment links (`![](name%20with%20spaces.png)`) resolve against the
  note's attachment list; other links pass through. A small Bear-like
  stylesheet is inlined. `<title>` is the note's title.
- **HTML.** One self-contained file: images embedded as `data:` URIs. Notes
  with no attachments need no bearcli call beyond `cat`.
- **Text.** The source with markdown markers removed: heading `#`s, emphasis
  and highlight markers, link targets (`[text](url)` → `text <url>`), list
  bullets kept as `- `, task boxes as `☐`/`☑`, tables and fenced code kept
  as written, the tag line kept. `render.strip_markup` grows out of the
  preview code so both agree.
- **RTF.** `textutil -convert rtf` over the HTML file, output to the chosen
  path. When the note has image attachments the output is `.rtfd` (a package
  folder) so the images travel; the phase verifies textutil embeds `data:`
  images, else images are written next to the HTML first as `file:` links.
- **TextBundle.** A `.textbundle` folder per the 2.0 spec: `info.json`
  (`version: 2`, `type: net.daringfireball.markdown`, `transient: false`),
  `text.md` with attachment links rewritten to `assets/<filename>`, and
  `assets/` holding every attachment from `bearcli attachments save`. The
  markdown inside is the raw Bear text, so the bundle round-trips into Bear,
  Ulysses and iA Writer.
- **Attachments.** `BearClient.attachments(note_id)` lists them,
  `BearClient.attachment(note_id, filename)` returns bytes (bearcli refuses a
  TTY, so stdout is always a pipe here). The fake bearcli gains both commands
  with a seeded note carrying one image so every path is tested end to end.
  Locked notes cannot be exported in any format, as today.
- **Files.** `render_html.py`, `export.py` (one `export_note(fmt, ...)` entry
  and one writer per format), `widgets/modals.py` (format prompt), `config.py`
  (`export_format`), `fake_bearcli.py` (attachments), README keys and config.

## Phases

### Phase 10 — HTML renderer and attachment access
Intent: `render_html.render(content, title, images)` with the Bear pre-pass,
stylesheet and data-URI images; `BearClient.attachments` / `attachment`; the
fake bearcli's `attachments list` / `save` and a seeded image note; the
existing preview `strip` code reshaped into `render.strip_markup`.
Verify: `uv run pytest tests/test_render_html.py tests/test_bear.py`
Status: [x] done 2026-09-11 (28 passed with test_render.py; full suite 115)

### Phase 11 — Format picker, HTML and Text exports
Intent: `x` opens the format prompt then the path prompt; `export_format`
config; `export_note` writes `.html` (self-contained) and `.txt`; help and
README updated.
Verify: `uv run pytest tests/test_export.py`
Status: [x] done 2026-09-11 (13 passed with test_config.py; full suite 119)

### Phase 12 — RTF
Intent: `.rtf` via `textutil` from a temporary HTML file, `.rtfd` when images
are present; a clear notice when `textutil` is missing (non-macOS).
Verify: `uv run pytest tests/test_export.py -k rtf` (skipped where textutil is absent)
Status: [ ] pending

### Phase 13 — TextBundle
Intent: `.textbundle` folder with `info.json`, `text.md` (links rewritten to
`assets/`), and every attachment saved into `assets/`.
Verify: `uv run pytest tests/test_export.py -k textbundle`
Status: [ ] pending

### Phase 14 — Acceptance gate
Intent: against the live database, export one note that carries two image
attachments, a table, a task list, a highlight and a nested tag in each of the
five formats; open the HTML in Safari, the RTF(D) in TextEdit, the TXT in a
text editor, and import the TextBundle into Bear as a new note; confirm images
and formatting survive in each. Full suite once.
Verify: `uv run pytest && uv run bjorn` (checklist above)
Status: [ ] pending

## Deferred (see docs/ROADMAP.md)

PDF (approach undecided: the headless-browser route is in question, see ROADMAP). EPUB (zip skeleton around the HTML
renderer). Exporting several notes at once. A per-format default directory.
