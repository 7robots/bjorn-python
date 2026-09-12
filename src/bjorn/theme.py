"""Bjorn's palettes.

Textual's own themes are all available; these are the ones Bjorn adds. The
colours are Bear's Red Graphite, sampled from the app: one coral red
(`#CD5654`) on graphite, with the dark sidebar the theme is known for beside a
white page.

The Rust Bjorn carries the same table in `src/ui/theme.rs`, so `theme = "..."`
in the shared config file means the same thing to both.

`BJORN_VARIABLES` names the colours the three columns need that Textual's
themes do not define. `BjornApp.get_theme_variable_defaults` derives them from
whichever theme is active, so every Textual theme keeps working; the themes
here override the ones that make Red Graphite look like Bear.
"""

from __future__ import annotations

from textual.app import App
from textual.theme import Theme

#: The config's default: Textual's own dark theme, which is what Bjorn has
#: always drawn in.
DEFAULT_THEME = "textual-dark"

#: Bjorn's own CSS variables, and the theme variable each falls back to.
#: `BjornApp.get_theme_variable_defaults` resolves the right-hand side against
#: the active theme.
BJORN_VARIABLES: dict[str, str] = {
    # The sidebar column. Red Graphite makes it graphite; everywhere else it
    # is the surface every other pane sits on.
    "bjorn-sidebar-background": "surface",
    "bjorn-sidebar-foreground": "foreground",
    "bjorn-sidebar-header-background": "primary-background",
    "bjorn-sidebar-header-foreground": "success",
    "bjorn-sidebar-cursor-blurred-background": "block-cursor-blurred-background",
    "bjorn-sidebar-cursor-blurred-foreground": "block-cursor-blurred-foreground",
    # The notes and reader headers.
    "bjorn-header-background": "primary-background",
    "bjorn-header-foreground": "success",
    # The rules between the columns and under each note row.
    "bjorn-rule": "panel-lighten-2",
    # Triage: the mark dot and the two Reminders states.
    "bjorn-marked": "warning",
    "bjorn-reminder-done": "success",
    "bjorn-reminder-added": "accent",
}

_RED = "#CD5654"

RED_GRAPHITE = Theme(
    name="red-graphite",
    primary=_RED,
    secondary="#8A8D92",
    accent=_RED,
    warning="#B7791F",
    error="#C0392B",
    success="#3F9D63",
    foreground="#2B2B2D",
    background="#FFFFFF",
    surface="#FDFDFD",
    panel="#F3F5F7",
    dark=False,
    variables={
        "bjorn-sidebar-background": "#2F3235",
        "bjorn-sidebar-foreground": "#D8DADC",
        "bjorn-sidebar-header-background": "#3A3D40",
        "bjorn-sidebar-header-foreground": "#D8DADC",
        "bjorn-sidebar-cursor-blurred-background": "#3F403F",
        "bjorn-sidebar-cursor-blurred-foreground": "#EDEEEF",
        "bjorn-header-background": "#F3F5F7",
        "bjorn-header-foreground": "#2B2B2D",
        "bjorn-rule": "#E3E4E6",
        "bjorn-marked": _RED,
        "bjorn-reminder-done": "#3F9D63",
        "bjorn-reminder-added": _RED,
        # Bear draws the selection as a soft grey with a red edge, not as a
        # block of colour; the focused cursor is the red one.
        "block-cursor-background": _RED,
        "block-cursor-foreground": "#FFFFFF",
        "block-cursor-text-style": "bold",
        "block-cursor-blurred-background": "#F3F5F7",
        "block-cursor-blurred-foreground": "#2B2B2D",
        "block-hover-background": "#F7F7F9",
        "footer-background": "#F3F5F7",
        "footer-foreground": "#4A4A4C",
        "footer-key-foreground": _RED,
        "footer-description-foreground": "#4A4A4C",
        # Headings are graphite in Bear; the red is for bullets, links and tags.
        "markdown-h1-color": "#2B2B2D",
        "markdown-h2-color": "#2B2B2D",
        "markdown-h3-color": "#2B2B2D",
        "input-cursor-background": _RED,
        "input-cursor-foreground": "#FFFFFF",
        # Bullets take their colour from these; in Bear they are red.
        "text-primary": _RED,
        "text-secondary": _RED,
        # Bear's scrollbars are grey furniture, not an accent.
        "scrollbar": "#D6D8DA",
        "scrollbar-hover": "#C3C5C8",
        "scrollbar-active": "#AEB0B3",
        "scrollbar-background": "#F3F5F7",
        "scrollbar-background-hover": "#F3F5F7",
        "scrollbar-background-active": "#F3F5F7",
        "scrollbar-corner-color": "#F3F5F7",
    },
)

RED_GRAPHITE_DARK = Theme(
    name="red-graphite-dark",
    primary=_RED,
    secondary="#8A8D92",
    accent=_RED,
    warning="#E0A458",
    error="#E05C5C",
    success="#6FB98F",
    foreground="#D7D9DC",
    background="#1B1C1E",
    surface="#232528",
    panel="#2E3135",
    dark=True,
    variables={
        "bjorn-sidebar-background": "#1F2123",
        "bjorn-sidebar-foreground": "#D7D9DC",
        "bjorn-sidebar-header-background": "#2E3135",
        "bjorn-sidebar-header-foreground": "#E0736A",
        "bjorn-sidebar-cursor-blurred-background": "#462C2D",
        "bjorn-sidebar-cursor-blurred-foreground": "#D7D9DC",
        "bjorn-header-background": "#2E3135",
        "bjorn-header-foreground": "#E0736A",
        "bjorn-rule": "#3A3D42",
        "bjorn-marked": "#E0A458",
        "bjorn-reminder-done": "#6FB98F",
        "bjorn-reminder-added": _RED,
        "block-cursor-background": _RED,
        "block-cursor-foreground": "#FFF3F2",
        "block-cursor-text-style": "bold",
        "block-cursor-blurred-background": "#4A2F30",
        "block-cursor-blurred-foreground": "#D7D9DC",
        "footer-background": "#2E3135",
        "footer-foreground": "#D7D9DC",
        "footer-key-foreground": "#E0736A",
        "footer-description-foreground": "#D7D9DC",
        "markdown-h1-color": "#EDEFF2",
        "markdown-h2-color": "#EDEFF2",
        "markdown-h3-color": "#EDEFF2",
        "input-cursor-background": _RED,
        "input-cursor-foreground": "#FFF3F2",
        "text-primary": "#E0736A",
        "text-secondary": "#E0736A",
        "scrollbar": "#3A3D42",
        "scrollbar-hover": "#4A4E54",
        "scrollbar-active": "#5A5E64",
        "scrollbar-background": "#1B1C1E",
        "scrollbar-background-hover": "#1B1C1E",
        "scrollbar-background-active": "#1B1C1E",
        "scrollbar-corner-color": "#1B1C1E",
    },
)

#: Registered on the app at start-up, on top of Textual's own.
THEMES: tuple[Theme, ...] = (RED_GRAPHITE, RED_GRAPHITE_DARK)


#: `get_theme_variable_defaults` by theme name. A theme's colours never change
#: once it is defined, and Textual asks on every stylesheet refresh.
_VARIABLE_CACHE: dict[str, dict[str, str]] = {}


class ThemedApp(App):
    """An app that knows Bjorn's palettes and its extra CSS variables.

    Bjorn's widgets style themselves with `$bjorn-...` variables, which do not
    exist in a plain Textual app, so anything hosting them inherits from here.
    """

    def __init__(self, *args, theme: str = DEFAULT_THEME, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        for extra in THEMES:
            self.register_theme(extra)
        # Before the stylesheet is parsed, so the columns are drawn in the
        # configured palette from the first frame. An unknown name keeps the
        # default rather than stopping the app: the config file is shared with
        # the Rust Bjorn, which offers its own list.
        wanted = theme if theme in self.available_themes else DEFAULT_THEME
        if wanted != self.theme:
            self.theme = wanted

    def get_theme_variable_defaults(self) -> dict[str, str]:
        """Bjorn's own CSS variables, resolved against whichever theme is
        active, so every Textual theme works and the palettes here need only
        override the ones they want to differ.

        Textual asks for this on every stylesheet refresh, and generating a
        colour system is not cheap, so the answer is cached per theme."""
        theme = self.current_theme
        cached = _VARIABLE_CACHE.get(theme.name)
        if cached is None:
            variables = theme.to_color_system().generate()
            cached = {name: variables[source] for name, source in BJORN_VARIABLES.items()}
            _VARIABLE_CACHE[theme.name] = cached
        return dict(cached)
