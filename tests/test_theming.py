"""Workspace design-system v2 contract."""
from __future__ import annotations

import pytest

from sonaloop import services
from sonaloop.theming import (
    COLOR_ROLES,
    FONT_ROLES,
    SPEC_VERSION,
    brand_context,
    chart_palette,
    compile_customer_design_system,
    customer_design_system_css,
    customer_theme_css,
    deck_theme,
    theme_override_vars,
    validate_customer_design_system_v2,
    validate_customer_theme,
)


def _data_dir(tmp_path, monkeypatch):
    from sonaloop import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return tmp_path


def _design_system() -> dict:
    return {
        "spec_version": SPEC_VERSION,
        "meta": {"name": "Acme workspace"},
        "brand": {
            "name": "Acme Research",
            "short_name": "Acme",
            "logo_variants": {
                "icon": {"kind": "image", "src": "data:image/png;base64,iVBORw0KGgo="},
                "lockup": {"kind": "image", "src": "data:image/png;base64,iVBORw0KGgo="},
            },
            "logo_preferred": "lockup",
            "deck_logo_preferred": "icon",
            "report_logo_preferred": "lockup",
        },
        "colors": {
            "light": {
                "paper": "#fffdf8",
                "panel": "#ffffff",
                "sidebar": "#f2efe8",
                "accent": "#007a5a",
                "accent_weak": "#e0f3ec",
                "ink": "#101010",
            },
            "dark": {
                "paper": "#101113",
                "panel": "#16171a",
                "sidebar": "#0d0e10",
                "accent": "#62d6b0",
                "accent_weak": "#12382f",
                "ink": "#f3f4f4",
            },
        },
        "typography": {
            "fonts": {
                "sans": {
                    "family": "Acme Sans",
                    "stack": ["Acme Sans", "Sona", "system-ui", "sans-serif"],
                },
                "mono": {
                    "family": "Acme Mono",
                    "stack": ["Acme Mono", "Sona Mono", "ui-monospace", "monospace"],
                },
            },
            "type_scale": {"t_body": "14px", "t_xl": "26px"},
        },
        "layout": {
            "radius": {"radius": "10px", "radius_lg": "14px"},
            "spacing": {"s_4": "18px"},
            "density": {"row": "42px"},
        },
        "charts": {
            "series": ["#007a5a", "#4c67d8", "#c37b22", "#cf4d5f"],
            "status": {"positive": "#007a5a", "warning": "#c37b22", "negative": "#cf4d5f",
                       "skeptical": "#a85d3d", "neutral": "#707070"},
            "grid": "#e5e5e5",
        },
        "deck": {
            "logo_preferred": "icon",
            "canvas_preferred": "canvas",
            "chart_series": ["#007a5a", "#4c67d8", "#c37b22", "#cf4d5f"],
        },
    }


def test_v2_roles_are_pinned():
    assert SPEC_VERSION == "workspace_design_system.v2"
    assert "accent" in COLOR_ROLES
    assert "paper" in COLOR_ROLES
    assert "skeptical" in COLOR_ROLES
    assert FONT_ROLES == ("sans", "serif", "mono", "display", "pixel")


def test_validate_merges_partial_payload_over_defaults():
    ds = validate_customer_design_system_v2(_design_system())
    assert ds["spec_version"] == SPEC_VERSION
    assert ds["brand"]["name"] == "Acme Research"
    assert ds["colors"]["light"]["accent"] == "#007a5a"
    assert ds["colors"]["light"]["muted"] == "#635e56"
    assert ds["typography"]["fonts"]["sans"]["family"] == "Acme Sans"
    assert ds["typography"]["fonts"]["serif"]["family"] == "Sona"
    assert ds["layout"]["radius"]["radius"] == "10px"
    assert ds["layout"]["spacing"]["s_1"] == "4px"
    assert ds["deck"]["boundary"] == "tokenized_master_deck"
    assert validate_customer_theme(_design_system()) == ds


def test_v2_rejects_unknown_keys_and_unsafe_values(tmp_path, monkeypatch):
    _data_dir(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="unknown design-system key"):
        validate_customer_design_system_v2({"components": {}})
    with pytest.raises(ValueError, match=SPEC_VERSION):
        validate_customer_design_system_v2({"spec_version": "workspace_design_system.v1"})
    bad = _design_system()
    bad["colors"]["light"]["accent"] = "red!important"
    with pytest.raises(ValueError, match="colors.light.accent"):
        validate_customer_design_system_v2(bad)
    bad = _design_system()
    bad["typography"]["fonts"]["sans"]["stack"] = ["Acme;body{display:none}"]
    with pytest.raises(ValueError, match="unsafe CSS token"):
        validate_customer_design_system_v2(bad)
    bad = _design_system()
    bad["brand"]["logo_variants"]["lockup"] = {"kind": "image", "src": "https://cdn/logo.png"}
    with pytest.raises(ValueError, match="local asset"):
        validate_customer_design_system_v2(bad)


def test_local_asset_refs_stay_inside_data_dir(tmp_path, monkeypatch):
    data = _data_dir(tmp_path, monkeypatch)
    (data / "brand").mkdir()
    (data / "brand" / "logo.png").write_bytes(b"")
    ds = _design_system()
    ds["brand"]["logo_variants"]["lockup"] = {"kind": "image", "src": "brand/logo.png"}
    assert validate_customer_design_system_v2(ds)["brand"]["logo_variants"]["lockup"]["src"] == "brand/logo.png"
    ds["brand"]["logo_variants"]["lockup"] = {"kind": "image", "src": "../outside.png"}
    with pytest.raises(ValueError, match="escapes the data dir"):
        validate_customer_design_system_v2(ds)


def test_compiler_produces_css_brand_charts_deck_and_stable_hash():
    compiled = compile_customer_design_system(_design_system())
    assert compiled["compiled_hash"] == compile_customer_design_system(_design_system())["compiled_hash"]
    assert compiled["brand"] == {
        "name": "Acme Research",
        "short_name": "Acme",
        "logo": "data:image/png;base64,iVBORw0KGgo=",
        "logo_role": "lockup",
    }
    assert compiled["charts"]["series"][0] == "#007a5a"
    assert compiled["deck"]["series"][0] == "#007a5a"
    assert compiled["css_vars"]["light"]["--accent"] == "#007a5a"
    assert compiled["css_vars"]["light"]["--sl-accent"] == "#007a5a"
    assert compiled["css_vars"]["light"]["--sl-sans"] == '"Acme Sans",Sona,system-ui,sans-serif'
    assert compiled["css_vars"]["light"]["--radius"] == "10px"
    assert 'id="theme-overrides"' in compiled["css"]
    assert ':root[data-theme="dark"]' in compiled["css"]


def test_individual_surface_helpers_match_compiler():
    ds = validate_customer_design_system_v2(_design_system())
    assert theme_override_vars(ds)["--bg"] == "#fffdf8"
    assert theme_override_vars(ds, scheme="dark")["--accent"] == "#62d6b0"
    assert brand_context(ds)["short_name"] == "Acme"
    assert chart_palette(ds)["status"]["warning"] == "#c37b22"
    assert deck_theme(ds)["font_role"] == "sans"
    assert customer_design_system_css(ds) == customer_theme_css(ds)


def _synthesis(store):
    return services.record_synthesis(
        "Acme study", "hmw", [], {"gesamtbild": "Overall positive."},
        goal="Does it land?", store=store)


def test_html_bundle_accepts_v2_design_system(store, tmp_path, monkeypatch):
    _data_dir(tmp_path, monkeypatch)
    syn = _synthesis(store)
    out = services.export_synthesis_html(syn["id"], store=store, theme_overrides=_design_system())
    html = (tmp_path / "export" / "share" / out["token"] / "index.html").read_text(encoding="utf-8")
    assert '<style id="theme-overrides">' in html
    assert "--accent:#007a5a" in html
    assert "--sl-sans:\"Acme Sans\",Sona,system-ui,sans-serif" in html
    assert html.index('<style id="theme-overrides">') > html.index(":root{--bg:")


def test_exports_validate_v2_before_any_work(store, tmp_path, monkeypatch):
    _data_dir(tmp_path, monkeypatch)
    syn = _synthesis(store)
    bad = {"spec_version": SPEC_VERSION, "colors": {"light": {"accent": "red!important"}}}
    with pytest.raises(ValueError, match="colors.light.accent"):
        services.export_synthesis_html(syn["id"], store=store, theme_overrides=bad)
    with pytest.raises(ValueError, match="colors.light.accent"):
        services.export_synthesis_pdf(syn["id"], store=store, theme_overrides=bad)
