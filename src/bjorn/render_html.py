"""Bear markdown to a self-contained HTML document, for export.

The pre-pass mirrors `render.preprocess` but emits HTML where the reader emits
Textual-friendly markdown: task boxes become disabled checkboxes, highlights
`<mark>`, underline `<u>`, the tag line a row of `.tag` spans. markdown-it-py's
`gfm-like` preset (tables, strikethrough, autolinks, inline HTML on) does the
rest. Attachment images are embedded as `data:` URIs when their bytes are given.
"""

from __future__ import annotations

import base64
import html
import mimetypes
import re
from urllib.parse import unquote

from markdown_it import MarkdownIt

from .render import _FENCE_RE, _HIGHLIGHT_RE, _TASK_DONE_RE, _TASK_OPEN_RE, _UNDERLINE_RE, is_tag_line, tags_in_line

STYLESHEET = """
:root { color-scheme: light dark; }
body { max-width: 44em; margin: 2em auto; padding: 0 1.5em; font: 16px/1.55 -apple-system, "Helvetica Neue", Helvetica, Arial, sans-serif; color: #222; background: #fff; }
@media (prefers-color-scheme: dark) { body { color: #ddd; background: #1e1e1e; } a { color: #8ab4f8; } mark { background: #6b5b00; color: inherit; } pre, code { background: #2a2a2a; } th, td { border-color: #444; } blockquote { border-color: #444; color: #aaa; } .tag { background: #3a3a3a; color: #ccc; } }
h1, h2, h3, h4 { line-height: 1.25; margin: 1.4em 0 0.5em; }
h1 { font-size: 1.8em; margin-top: 0; }
a { color: #c2410c; text-decoration: none; }
a:hover { text-decoration: underline; }
mark { background: #fde68a; padding: 0 0.15em; border-radius: 2px; }
pre, code { font: 0.92em/1.45 ui-monospace, "SF Mono", Menlo, monospace; background: #f4f4f4; border-radius: 4px; }
code { padding: 0.1em 0.3em; }
pre { padding: 0.8em 1em; overflow-x: auto; }
pre code { padding: 0; background: none; }
blockquote { margin: 1em 0; padding: 0 1em; border-left: 3px solid #ddd; color: #666; }
table { border-collapse: collapse; margin: 1em 0; }
th, td { border: 1px solid #ddd; padding: 0.35em 0.7em; text-align: left; }
img { max-width: 100%; height: auto; }
ul, ol { padding-left: 1.5em; }
li { margin: 0.15em 0; }
input[type=checkbox] { margin: 0 0.4em 0 0; vertical-align: -0.1em; }
.tags { margin: -0.5em 0 1.5em; }
.tag { display: inline-block; background: #eee; color: #555; border-radius: 1em; padding: 0.05em 0.7em; margin-right: 0.3em; font-size: 0.85em; }
hr { border: 0; border-top: 1px solid #ddd; margin: 2em 0; }
""".strip()

_LI_TASK_RE = re.compile(r"<li>\s*(<input type=\"checkbox\"[^>]*>)")


def prepare(content: str) -> str:
    """Bear markdown -> markdown with inline HTML for Bear's own marks."""
    out: list[str] = []
    in_fence = False
    for line in content.splitlines():
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue
        if is_tag_line(line):
            spans = "".join(f'<span class="tag">{html.escape(tag)}</span>' for tag in tags_in_line(line))
            out.append(f'<p class="tags">{spans}</p>')
            continue
        line = _TASK_OPEN_RE.sub(lambda m: f'{m.group(1)}<input type="checkbox" disabled>{m.group(2) or " "}', line)
        line = _TASK_DONE_RE.sub(lambda m: f'{m.group(1)}<input type="checkbox" disabled checked>{m.group(2) or " "}', line)
        line = _HIGHLIGHT_RE.sub(r"<mark>\1</mark>", line)
        line = _UNDERLINE_RE.sub(r"<u>\1</u>", line)
        out.append(line)
    return "\n".join(out) + "\n"


def data_uri(filename: str, data: bytes) -> str:
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def _parser(images: dict[str, bytes] | None, image_src: dict[str, str] | None) -> MarkdownIt:
    md = MarkdownIt("gfm-like")
    lookup_bytes = images or {}
    lookup_src = image_src or {}

    def render_image(self, tokens, idx, options, env):
        token = tokens[idx]
        src = token.attrGet("src") or ""
        name = unquote(src)
        if name in lookup_src:
            token.attrSet("src", lookup_src[name])
        elif name in lookup_bytes:
            token.attrSet("src", data_uri(name, lookup_bytes[name]))
        token.attrSet("alt", self.renderInlineAsText(token.children or [], options, env))
        return self.renderToken(tokens, idx, options, env)

    md.add_render_rule("image", render_image)
    return md


def render_body(content: str, *, images: dict[str, bytes] | None = None, image_src: dict[str, str] | None = None) -> str:
    """The note as an HTML fragment. `images` maps attachment filenames to
    bytes for embedding; `image_src` maps them to URLs to reference instead."""
    body = _parser(images, image_src).render(prepare(content))
    return _LI_TASK_RE.sub(r'<li class="task">\1', body)


def render(content: str, title: str, *, images: dict[str, bytes] | None = None, image_src: dict[str, str] | None = None) -> str:
    """A complete, self-contained HTML document."""
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"<title>{html.escape(title)}</title>\n<style>\n{STYLESHEET}\n</style>\n</head>\n<body>\n"
        f"{render_body(content, images=images, image_src=image_src)}</body>\n</html>\n"
    )
