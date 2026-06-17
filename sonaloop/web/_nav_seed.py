"""Seed the core sidebar through the SAME public registry an extension uses.

There is no privileged path for the core's own nav: it registers its sections and
items via register_nav_section/register_nav_item exactly as sonaloop-cloud or
sonaloop-research would, so downstream sections sit beside these (ordered by `order`).
Imported for its side effects by _components (the render side lives in _nav there).

Four workspace items, period (spec/ux-contract.md §3.5): Jobs and Formats are the
primary containers, Methodologies explain the process a project runs through, and Personas
are the participants. Activity is the live feed and lives in the user-menu utility cluster.
Runs retired from the nav (the project-header run chip + /runs journal carry it);
Documentation lives in the user-menu cluster (web/_components._user_menu) — reference,
not workspace. Labels are lambdas so they resolve per request (i18n)."""
from __future__ import annotations

from ._i18n import t
from ._ext import register_nav_section, register_nav_item

register_nav_section("workspace", label=None, order=0)

_CORE_NAV = {
    "workspace": [
        ("/projects", "projects", "projects", lambda: t("projects")),
        ("/methodologies", "methodologies", "target", lambda: t("methodologies_h")),
        ("/library", "library", "book", lambda: t("library_h")),
        ("/personas", "personas", "personas", lambda: t("personas")),
    ],
}

for _section, _items in _CORE_NAV.items():
    for _order, (_href, _key, _icon, _label) in enumerate(_items):
        register_nav_item(_section, _href, _key, _icon, _label, _order)
