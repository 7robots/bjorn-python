"""Inline completion for the search box: `@operators` and `#tags`.

Textual's `Input` asks its `Suggester` for a completion of the whole value
and draws the extra characters as ghost text; `→` at the end accepts. Only
the last token is completed here, the rest of the value is kept verbatim.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from textual.binding import Binding
from textual.suggester import Suggester
from textual.widgets import Input

#: bearcli's search operators, most used first. The parenthesised ones stop
#: at `(` so the argument is left to type; X-day forms offer 7 as the digit.
OPERATORS: tuple[str, ...] = (
    "@todo", "@done", "@task",
    "@today", "@yesterday", "@last7days", "@date(",
    "@ctoday", "@created7days", "@cdate(",
    "@title", "@tagged", "@untagged", "@pinned",
    "@images", "@files", "@attachments", "@code",
    "@locked", "@readonly", "@empty", "@untitled",
    "@wikilinks", "@backlinks", "@ocr",
)

#: The cheat-sheet row shown under the box while it is open.
HINT = '"phrase"  -term  #tag  #*/subtag  @todo  @title  @today  @last7days  @pinned  ·  tab or → accepts a completion'


def with_parents(tags: Sequence[str]) -> list[str]:
    """`tags` plus every ancestor path, order kept, no duplicates."""
    out: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        parts = tag.split("/")
        for i in range(1, len(parts) + 1):
            path = "/".join(parts[:i])
            if path not in seen:
                seen.add(path)
                out.append(path)
    return out


def _tag_token(tag: str) -> str:
    """How the tag is typed in a query: multi-word tags close with `#`."""
    return f"#{tag}#" if " " in tag else f"#{tag}"


def _first_prefixed(candidates: Sequence[str], prefix: str) -> str | None:
    folded = prefix.lower()
    for c in candidates:
        if c.lower().startswith(folded) and c.lower() != folded:
            return c
    return None


def complete_token(token: str, tags: Sequence[str]) -> str | None:
    """The completed form of `token`, or None when nothing applies."""
    if token.startswith("@"):
        return _first_prefixed(OPERATORS, token)
    bang = token.startswith("!#")
    if not bang and not token.startswith("#"):
        return None
    body = token[2:] if bang else token[1:]
    prefix = "!" if bang else ""
    if body.startswith("*/"):
        found = _first_prefixed(_tails(tags), body[2:])
        return None if found is None else f"{prefix}#*/{found}"
    found = _first_prefixed(list(tags), body)
    if found is not None:
        return prefix + _tag_token(found)
    # No path starts this way: offer the sub-tag form, which is how Bear
    # reaches a tag by its tail (`#Build` matches nothing, `#*/Build` does).
    found = _first_prefixed(_tails(tags), body)
    return None if found is None else f"{prefix}#*/{found}"


def _tails(tags: Sequence[str]) -> list[str]:
    """Every tag's tail below its first segment: `a/b/c` gives `b/c` and `c`."""
    tails: list[str] = []
    for tag in tags:
        parts = tag.split("/")
        for i in range(1, len(parts)):
            tail = "/".join(parts[i:])
            if tail not in tails:
                tails.append(tail)
    return tails


def complete(value: str, tags: Sequence[str]) -> str | None:
    """`value` with its last token completed, or None."""
    if not value or value.endswith(" "):
        return None
    head, sep, token = value.rpartition(" ")
    done = complete_token(token, tags)
    return None if done is None else head + sep + done


class QuerySuggester(Suggester):
    """Completes the last token of the search box from bearcli's operators
    and the current snapshot's tags. `tags` is called on every keystroke so
    the list follows the snapshot; its order is the priority order."""

    def __init__(self, tags: Callable[[], Sequence[str]]) -> None:
        # Case-sensitive so the value reaches us verbatim; matching folds itself.
        super().__init__(use_cache=False, case_sensitive=True)
        self._tags = tags

    async def get_suggestion(self, value: str) -> str | None:
        return complete(value, with_parents(self._tags()))


class SearchInput(Input):
    """The search box: `tab` accepts the ghost completion like `→` does, and
    only moves focus when there is nothing to accept."""

    BINDINGS = [Binding("tab", "accept_or_focus_next", "Accept", show=False)]

    def action_accept_or_focus_next(self) -> None:
        if self._suggestion and len(self._suggestion) > len(self.value):
            self.cursor_position = len(self.value)
            self.action_cursor_right()
        else:
            self.screen.focus_next()
