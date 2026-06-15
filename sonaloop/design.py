"""Public design-system surface — the single contract sonaloop-cloud and
sonaloop-research consume, so the paying surfaces never hand-roll the brand.

These are the vendored ``sonaloop-design`` assets (synced from the design repo by
``scripts/sync_icons.sh`` into the private ``_icons`` / ``_tokens`` /
``_components_css`` / ``_pixel_font`` modules). This module is the *stable public
name*: web extensions and standalone SSR pages import from ``sonaloop.design``, never
from the underscore modules. Keeping the privates as the sync targets means the
vendoring story is unchanged while the public surface stays put across core refactors.

Typical use in a standalone page (one that can't mount the app shell — a login, portal
or intake page) that still has to look exactly like the core web::

    from sonaloop.design import STANDALONE_CSS, icon
    html = f"<style>{STANDALONE_CSS}{page_layout_css}</style>... {icon('sonaloop')} ..."
"""

from __future__ import annotations

from ._components_css import COMPONENTS_CSS
from ._icons import (
    figure,
    figure_names,
    hifi,
    hifi_anim_css,
    hifi_names,
    icon,
    names,
)
from ._pixel_font import PIXEL_FONT_CSS
from ._tokens import TOKENS_CSS

#: The full stylesheet a standalone SSR page needs to match the core web: the pixel
#: font (the logo "loop" face), the design tokens (``--sl-*`` custom properties incl.
#: light/dark), and the ``.sl-*`` component contracts. Append only genuinely
#: page-specific layout CSS after this — never a brand hex or a copied component rule.
STANDALONE_CSS = PIXEL_FONT_CSS + TOKENS_CSS + COMPONENTS_CSS

__all__ = [
    "COMPONENTS_CSS",
    "PIXEL_FONT_CSS",
    "STANDALONE_CSS",
    "TOKENS_CSS",
    "figure",
    "figure_names",
    "hifi",
    "hifi_anim_css",
    "hifi_names",
    "icon",
    "names",
]
