"""User-menu hover PARITY gate.

The utility rows moved into the user menu, but they still need the same hover treatment
as the nav rows. This gate drives the REAL app with a real pointer (the
test_browser_harness skip pattern) and asserts the full hover treatment:

  1. the hover background paints (and matches the nav rows' computed hover background),
  2. the row's leading visual REACTS — an icon plays a non-`none` animation, or the `?`
     keycap presses (a non-identity transform).
"""
from __future__ import annotations

import socket
import threading
import time

import pytest

from sonaloop import browser, web


@pytest.mark.skipif(not browser.available(), reason="chromium not installed")
def test_user_menu_rows_hover_like_nav_rows():
    import uvicorn

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(web.create_app(), host="127.0.0.1", port=port,
                                           log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while not server.started:
        assert time.time() < deadline, "app did not boot"
        time.sleep(0.05)

    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            pg = b.new_context(viewport={"width": 1440, "height": 900}).new_page()
            pg.goto(f"http://127.0.0.1:{port}/projects", wait_until="load")
            pg.wait_for_timeout(400)

            # the nav rows' reference hover background (a NON-active row)
            nav = pg.locator(".sl-sb-scroll .sl-nav a:not(.is-active)").first
            nav.hover()
            pg.wait_for_timeout(200)
            nav_bg = nav.evaluate("el => getComputedStyle(el).backgroundColor")
            assert nav_bg not in ("rgba(0, 0, 0, 0)", "transparent")

            pg.locator(".sl-um-trigger").click()
            pg.wait_for_timeout(150)
            targets = pg.locator(".sl-um-pop .sl-um-row, .sl-um-pop .sl-um-control, .sl-um-pop .sl-um-choice:has(svg)")
            n = targets.count()
            assert n >= 10, "utility rows + appearance/language controls expected"
            for i in range(n):
                row = targets.nth(i)
                pg.mouse.move(0, 0)
                pg.wait_for_timeout(120)
                row.hover()
                pg.wait_for_timeout(250)
                bg = row.evaluate("el => getComputedStyle(el).backgroundColor")
                if "sl-um-choice" not in (row.get_attribute("class") or ""):
                    assert bg == nav_bg, f"user-menu row {i}: hover bg {bg} != nav {nav_bg}"
                # liveliness: an animating icon part
                alive = row.evaluate("""el => {
                  for (const n of el.querySelectorAll('svg, svg *')) {
                    const cs = getComputedStyle(n);
                    if (cs.animationName && cs.animationName !== 'none') return 'icon';
                    if (cs.transform && !['none', 'matrix(1, 0, 0, 1, 0, 0)'].includes(cs.transform))
                      return 'icon';
                  }
                  return '';
                }""")
                assert alive, f"user-menu row {i} shows no hover liveliness"
            b.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
