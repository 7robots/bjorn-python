"""Phase 10: Bear markdown to HTML, and to plain text."""

from __future__ import annotations

from bjorn.render import to_text
from bjorn.render_html import prepare, render, render_body

NOTE = (
    "# Greenhouse\n#garden/greenhouse #multi word#\n\n"
    "## Frame\nThe ==ridge== beam is a single ~12'~ piece, *braced*.\n\n"
    "- [ ] hang the door\n- [x] level the footings\n  - [ ] nested\n\n"
    "| Panel | Qty |\n|---|---|\n| Roof | 6 |\n\n"
    "> a quote with `code`\n\n```\n- [ ] not a task ==nor a highlight==\n```\n\n"
    "See [REV](https://www.revrobotics.com) and ![the frame](Front%20bed.png).\n"
)


def test_prepare_turns_bear_marks_into_inline_html_outside_fences():
    out = prepare(NOTE)
    assert '<p class="tags"><span class="tag">#garden/greenhouse</span><span class="tag">#multi word#</span></p>' in out
    assert "<mark>ridge</mark>" in out and "<u>12'</u>" in out
    assert '- <input type="checkbox" disabled> hang the door' in out
    assert '- <input type="checkbox" disabled checked> level the footings' in out
    assert "- [ ] not a task ==nor a highlight==" in out, "fenced code is left alone"


def test_render_body_is_gfm_with_tasks_tables_and_links():
    body = render_body(NOTE)
    assert "<h1>Greenhouse</h1>" in body and "<h2>Frame</h2>" in body
    assert '<li class="task"><input type="checkbox" disabled> hang the door' in body
    assert "<table>" in body and "<td>Roof</td>" in body
    assert "<blockquote>" in body and "<code>code</code>" in body
    assert '<a href="https://www.revrobotics.com">REV</a>' in body
    assert '<img src="Front%20bed.png" alt="the frame" />' in body, "no bytes given: the link stays"
    assert "<em>braced</em>" in body


def test_render_embeds_attachments_as_data_uris_and_is_a_full_document():
    doc = render(NOTE, "Greenhouse", images={"Front bed.png": b"\x89PNG\r\n"})
    assert doc.startswith("<!DOCTYPE html>") and doc.rstrip().endswith("</html>")
    assert "<title>Greenhouse</title>" in doc and "<style>" in doc
    assert 'src="data:image/png;base64,iVBORw0K"' in doc
    assert 'alt="the frame"' in doc


def test_render_can_point_images_at_paths_instead():
    body = render_body("![](Front%20bed.png)", image_src={"Front bed.png": "assets/Front bed.png"})
    assert '<img src="assets/Front bed.png" alt="" />' in body


def test_title_is_escaped():
    assert "<title>A &lt;b&gt; &amp; c</title>" in render("# x", "A <b> & c")


def test_to_text_strips_markup_and_keeps_structure():
    text = to_text(NOTE)
    assert text.startswith("Greenhouse\n#garden/greenhouse #multi word#\n\nFrame\n")
    assert "The ridge beam is a single 12' piece, braced." in text
    assert "- ☐ hang the door\n- ☑ level the footings\n  - ☐ nested\n" in text
    assert "| Panel | Qty |\n|---|---|\n| Roof | 6 |" in text, "tables as written"
    assert "a quote with code" in text and ">" not in text.split("Frame")[1].split("|")[0]
    assert "- [ ] not a task ==nor a highlight==" in text, "fenced code as written, fences dropped"
    assert "See REV <https://www.revrobotics.com> and [image: Front bed.png]." in text
    assert text.endswith("\n") and "```" not in text


def test_to_text_bullets_and_bare_links():
    assert to_text("* star\n+ plus\n- dash\n1. one") == "- star\n- plus\n- dash\n1. one\n"
    assert to_text("[https://x.y](https://x.y)") == "https://x.y\n"
