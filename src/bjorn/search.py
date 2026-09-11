"""What in a Bear search query is matched against note text.

bearcli does the searching; this module only recovers the terms a query would
have matched so the reader and the list can highlight them. Operators
(`@todo`, `@title`, `@date(2026-01-01)`), tags (`#tag`, `!#tag`, `#*/sub`,
`#multi word#`) and negations (`-term`, `-"phrase"`) narrow the result set but
match no text, so they are dropped.
"""

from __future__ import annotations

import re

from .render import TAG_TOKEN_RE

_TOKEN_RE = re.compile(
    r"""
    (?P<neg>-)?                       # negation prefix
    (?:
        "(?P<phrase>[^"]*)"           # "quoted phrase"
      | @(?P<op>[\w-]+)(?:\([^)]*\))? # @operator, optional (argument)
      | !?(?P<tag>TAG)                # #tag, !#tag, #multi word#, #*/sub
      | (?P<word>\S+)                 # bare word
    )
    """.replace("TAG", TAG_TOKEN_RE.pattern.replace("#", r"\#")),  # verbose mode: # opens a comment
    re.VERBOSE,
)


def terms(query: str) -> list[str]:
    """Bare words and quoted phrases from `query`, in order, without
    duplicates. Empty when the query only narrows (operators, tags)."""
    found: list[str] = []
    for m in _TOKEN_RE.finditer(query):
        if m.group("neg") or m.group("op") is not None or m.group("tag") is not None:
            continue
        term = m.group("phrase") if m.group("phrase") is not None else m.group("word")
        term = (term or "").strip()
        if term and term.lower() not in (t.lower() for t in found):
            found.append(term)
    return found


def pattern(words: list[str]) -> re.Pattern[str] | None:
    """One case-insensitive regex matching any of `words` as substrings,
    longest first so a phrase wins over a word it contains. None when empty."""
    if not words:
        return None
    ordered = sorted(words, key=len, reverse=True)
    return re.compile("|".join(re.escape(w) for w in ordered), re.IGNORECASE)


def query_pattern(query: str) -> re.Pattern[str] | None:
    return pattern(terms(query))
