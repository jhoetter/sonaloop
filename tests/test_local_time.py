"""Browser-local timestamp contract.

The server commonly runs in UTC, while readers should see their own timezone.  Keep
the absolute instant in ``datetime`` and let the shell localize every current and
dynamically inserted timestamp.
"""

import os
import shutil
import subprocess

import pytest

from sonaloop.web import ui
from sonaloop.web._components import APP_JS


def test_local_ts_normalizes_historical_naive_values_as_utc():
    rendered = str(ui.local_ts("2026-08-11T13:50:00"))

    assert '<time class="sl-local-time"' in rendered
    assert 'datetime="2026-08-11T13:50:00+00:00"' in rendered
    assert 'data-local-time="datetime"' in rendered
    assert ">11 Aug · 13:50 UTC</time>" in rendered


def test_local_date_converts_instants_but_keeps_domain_dates_fixed():
    instant = str(ui.local_date("2026-08-11T23:50:00+00:00"))
    domain_date = str(ui.local_date("2026-08-11"))

    assert 'data-local-time="date"' in instant
    assert ">11 Aug 2026 UTC</time>" in instant
    assert 'data-local-time=' not in domain_date
    assert 'datetime="2026-08-11"' in domain_date


def test_shell_localizes_initial_spa_and_drawer_timestamps():
    assert "Intl.DateTimeFormat" in APP_JS
    assert "time[data-local-time]" in APP_JS
    assert "spa:load" in APP_JS
    assert "MutationObserver" in APP_JS
    assert "timeStyle:'long'" in APP_JS


@pytest.mark.skipif(not shutil.which("node"), reason="Node is optional")
def test_browser_intl_respects_zurich_summer_and_winter_offsets():
    script = """
const fmt = new Intl.DateTimeFormat('de-CH', {hour:'2-digit', minute:'2-digit', hourCycle:'h23'});
console.log(fmt.format(new Date('2026-08-11T13:50:00+00:00')));
console.log(fmt.format(new Date('2026-01-11T13:50:00+00:00')));
"""
    env = {**os.environ, "TZ": "Europe/Zurich"}
    times = subprocess.check_output(["node", "-e", script], text=True, env=env).splitlines()

    assert times == ["15:50", "14:50"]
