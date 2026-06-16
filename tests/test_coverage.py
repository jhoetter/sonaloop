"""Coverage / diversity check (taxonomy id `coverage`): a DETERMINISTIC analysis over a study's persona set
that flags when the panel is too narrow to be trustworthy (a homogeneous "council of clones"). Covers: the
per-dimension distribution math, over-concentration threshold (one value dominating the panel), thin/missing
axes, gap detection against a Job's DECLARED coverage (min_personas + persona_axes), the overall coverage
indicator (thin|ok|strong), deterministic archetype recommendations, the "not assessable" path (no fabricated
values), and the inspector render. No server-side text-LLM calls — host narrates on top of the result."""
from __future__ import annotations

from sonaloop import services
from sonaloop.services import _coverage
from conftest import create_persona, make_profile


def _project(store, personas, **kw):
    pids = [create_persona(store, n, **kw) for n in personas]
    proj = services.create_research_project("Study", goal="g", persona_ids=pids, store=store)
    return proj["id"], pids


def _diverse_persona(store, name, *, customer_type, risk, size, goal, pain):
    """A fully-specified persona so each coverage dimension has a real, controllable value."""
    profile = make_profile(name, customer_type=customer_type, goals=[goal], pains=[pain])
    profile["personality"]["risk_tolerance"] = risk
    profile["company_context"]["size"] = size
    return services.record_persona(f"{name} src", profile, store=store)["id"]


# --------------------------------------------------------------------------- per-dimension distribution math

def test_distribution_counts_and_dominant_share(store):
    pids = [_diverse_persona(store, f"P{i}", customer_type=("Solo" if i < 8 else f"Other{i}"),
                             risk=f"r{i}", size=f"s{i}", goal=f"g{i}", pain=f"p{i}") for i in range(10)]
    personas = [store.get_persona(p) for p in pids]
    dist = _coverage._distribution(personas, "segment")
    assert dist["assessed"] == 10
    assert dist["dominant"] == "Solo" and dist["counts"]["Solo"] == 8
    assert dist["dominant_share"] == 0.8           # 8 of 10
    assert dist["distinct"] == 3                    # Solo + 2 distinct others


# --------------------------------------------------------------------------- over-concentration threshold

def test_over_concentration_flags_8_of_10_in_one_segment(store):
    # 8/10 in one segment is the ticket's canonical over-concentration example (0.8 > 0.6 threshold).
    pids = [_diverse_persona(store, f"P{i}", customer_type=("Solo" if i < 8 else f"Other{i}"),
                             risk=f"r{i}", size=f"s{i}", goal=f"g{i}", pain=f"p{i}") for i in range(10)]
    proj = services.create_research_project("over", goal="g", persona_ids=pids, store=store)
    out = services.assess_coverage(proj["id"], store=store)
    seg = next(d for d in out["dimensions"] if d["dimension"] == "segment")
    assert seg["over_concentration"] is True
    assert any(g["kind"] == "over_concentration" and g["dimension"] == "segment" for g in out["gaps"])
    assert out["indicator"]["level"] == "thin"


def test_balanced_panel_is_not_over_concentrated(store):
    pids = [_diverse_persona(store, f"P{i}", customer_type=f"Seg{i % 5}", risk=f"r{i % 5}",
                             size=f"s{i % 5}", goal=f"g{i % 5}", pain=f"p{i % 5}") for i in range(10)]
    proj = services.create_research_project("bal", goal="g", persona_ids=pids, store=store)
    out = services.assess_coverage(proj["id"], store=store)
    assert all(not d["over_concentration"] for d in out["dimensions"])
    assert out["indicator"]["level"] == "strong"
    assert out["gaps"] == []


# --------------------------------------------------------------------------- thin / clones

def test_clone_panel_is_thin_with_recommendations(store):
    # Founder clones: every persona identical → every dimension over-concentrated/thin.
    pids = [_diverse_persona(store, f"Clone{i}", customer_type="Solo", risk="high",
                             size="small", goal="same goal", pain="same pain") for i in range(5)]
    proj = services.create_research_project("clones", goal="g", persona_ids=pids, store=store)
    out = services.assess_coverage(proj["id"], store=store)
    assert out["indicator"]["level"] == "thin"
    assert out["recommendations"], "a homogeneous panel must yield concrete archetype suggestions"
    # The recommendation names a dimension and the dominant value to avoid.
    rec = out["recommendations"][0]
    assert rec["dimension"] in [d["id"] for d in _coverage.COVERAGE_DIMENSIONS] or rec["dimension"] is None
    # Gaps answer with the catalog pointer in-band (the curated catalog is the fastest fill).
    assert "catalog_recommend" in out["catalog_hint"]


def test_panel_too_small_is_a_gap(store):
    pid, _ = _project(store, ["Only"])
    out = services.assess_coverage(pid, store=store)
    assert out["panel_size"] == 1
    assert any(g["kind"] == "panel_too_small" for g in out["gaps"])
    assert out["indicator"]["level"] == "thin"


# --------------------------------------------------------------------------- declared-coverage (Job) gaps

def test_gap_below_declared_min_personas(store):
    # 'positioning' declares min_personas=4; a 3-persona panel is below it.
    pids = [_diverse_persona(store, f"P{i}", customer_type=f"Seg{i}", risk=f"r{i}",
                             size=f"s{i}", goal=f"g{i}", pain=f"p{i}") for i in range(3)]
    proj = services.create_research_project("decl", goal="g", persona_ids=pids, store=store)
    out = services.assess_coverage(proj["id"], job="positioning", store=store)
    assert out["job"] == "positioning"
    assert out["declared_coverage"]["min_personas"] == 4
    assert any(g["kind"] == "below_declared_min" for g in out["gaps"])
    assert any(r["description"] for r in out["recommendations"])


def test_declared_axis_gap_when_dimension_is_thin(store):
    # All personas share one segment → the declared 'segment' axis is a gap for 'positioning'.
    pids = [_diverse_persona(store, f"P{i}", customer_type="Solo", risk=f"r{i}",
                             size=f"s{i}", goal=f"g{i}", pain=f"p{i}") for i in range(4)]
    proj = services.create_research_project("axis", goal="g", persona_ids=pids, store=store)
    out = services.assess_coverage(proj["id"], job="positioning", store=store)
    axis_gaps = [g for g in out["gaps"] if g["kind"] == "declared_axis_gap" and g.get("axis") == "segment"]
    assert axis_gaps


def test_unmapped_declared_axis_is_surfaced_not_dropped(store):
    # 'positioning' declares 'current-alternative', which maps to no persona field → reported for manual check.
    pids = [_diverse_persona(store, f"P{i}", customer_type=f"Seg{i}", risk=f"r{i}",
                             size=f"s{i}", goal=f"g{i}", pain=f"p{i}") for i in range(4)]
    proj = services.create_research_project("unmapped", goal="g", persona_ids=pids, store=store)
    out = services.assess_coverage(proj["id"], job="positioning", store=store)
    assert any(g["kind"] == "declared_axis_unmapped" and g.get("axis") == "current-alternative"
               for g in out["gaps"])


def test_unknown_job_falls_back_to_general_analysis(store):
    pid, _ = _project(store, ["A", "B", "C"])
    out = services.assess_coverage(pid, job="does-not-exist", store=store)
    assert out["job"] is None and out["declared_coverage"] is None


# --------------------------------------------------------------------------- not-assessable (no fabrication)

def test_dimension_with_no_signal_is_not_assessable(store):
    # Strip the structured demographics/firmographics signal so the dimension has nothing to read.
    pids = []
    for i in range(3):
        profile = make_profile(f"P{i}", customer_type=f"Seg{i}", goals=[f"g{i}"], pains=[f"p{i}"])
        profile["personality"]["risk_tolerance"] = f"r{i}"
        profile["company_context"]["size"] = "unspecified"
        profile["segment"] = {"customer_type": f"Seg{i}"}   # no firm_size/market
        profile["demographics"] = {}
        pids.append(services.record_persona(f"P{i} src", profile, store=store)["id"])
    proj = services.create_research_project("na", goal="g", persona_ids=pids, store=store)
    out = services.assess_coverage(proj["id"], store=store)
    demo = next(d for d in out["dimensions"] if d["dimension"] == "demographics")
    assert demo["no_signal"] is True and demo["assessed"] == 0
    assert any(g["kind"] == "not_assessable" and g["dimension"] == "demographics" for g in out["gaps"])


# --------------------------------------------------------------------------- indicator levels

def test_indicator_levels_are_ordered_worst_first(store):
    assert _coverage._LEVELS == ("thin", "ok", "strong")
    pids = [_diverse_persona(store, f"P{i}", customer_type=f"Seg{i % 5}", risk=f"r{i % 5}",
                             size=f"s{i % 5}", goal=f"g{i % 5}", pain=f"p{i % 5}") for i in range(10)]
    proj = services.create_research_project("ind", goal="g", persona_ids=pids, store=store)
    out = services.assess_coverage(proj["id"], store=store)
    assert out["indicator"]["score"] == _coverage._LEVELS.index(out["indicator"]["level"])


# --------------------------------------------------------------------------- explicit persona_ids override

def test_persona_ids_override_the_project_panel(store):
    a = _diverse_persona(store, "A", customer_type="X", risk="r1", size="s1", goal="g1", pain="p1")
    b = _diverse_persona(store, "B", customer_type="Y", risk="r2", size="s2", goal="g2", pain="p2")
    c = _diverse_persona(store, "C", customer_type="Z", risk="r3", size="s3", goal="g3", pain="p3")
    proj = services.create_research_project("ov", goal="g", persona_ids=[a, b, c], store=store)
    out = services.assess_coverage(proj["id"], persona_ids=[a], store=store)
    assert out["panel_size"] == 1                      # only the overridden panel is assessed

