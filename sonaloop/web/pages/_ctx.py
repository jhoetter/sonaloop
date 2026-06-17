"""Shared render toolkit for the page modules (spec/roadmap.md R2).

Every `web/pages/*.py` does `from ._ctx import *` to get the common imports (services, Store, the h()
builder, the i18n t, and the shared render helpers) without repeating a 15-line header in each file.
This is the same re-export pattern web/__init__ already uses. Page modules add only their own
route-specific imports (e.g. the calendar helpers) on top."""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

from fastapi import Query
from fastapi.responses import HTMLResponse

from ... import services
from ...storage import Store
from ...presentation import glyph_icon
from .._i18n import t, _lang
from .._components import (
    _esc, _icon, _avatar, _avatar_src, _label, _pills, _md, _prose, _layout, _empty_state, _doc, _list_page,
    _star, _status_color, _EDGE_COLORS, _theme_color, _artifact_present, _study_lead, _hero,
    _display_title,
)
from .._synthesis import (
    _area, _sentiment_section, _synthesis_html, _persona_voices_html,
)
from .._graph import _plan_html, _outline_html
from .._detail import _relations_html, _properties_html, detail_page, detail_eyebrow, detail_form_rows
from .._ext import render_detail_extra
from .._rail import _page_rail
from .._routes_lists import _projects_page, _persona_row
from .._html import raw, h, fragment
from .._vm import study_head
from .. import ui

__all__ = [_n for _n in dir() if not _n.startswith("__")]
