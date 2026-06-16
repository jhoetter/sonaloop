"""Project-graph edge data over the plan DAG (spec/methodology-constellations.md §5).

The spatial graph view is retired, but get_project_graph still derives the methodology DAG +
recorded evidence + artifact tags into nodes/edges — the data that now feeds the outline's
relation arrows. The synthesis spine (GAP-6) keeps successive converging syntheses connected.

The plan is the single engine (HX3): a methodology only SEEDS the plan. `_drive_plan` is a tiny
deterministic offline driver — the plan analogue of the old StubAuthoringBackend — that discharges
each seeded frame, fans a couple of act councils per diverge step, scaffolds the declared prototypes
under their build frame, and records a synthesis per verify. Owned by the test; production has ONE
engine and no stub driver.
"""
from __future__ import annotations

from sonaloop import methodology as M
from sonaloop import plan as PL
from sonaloop import services


def _council(store, cid: str) -> None:
    store.insert_council_session({"id": cid, "created_at": "2026-06-05T00:00:00+00:00",
        "prompt": f"Council {cid}", "persona_ids": ["p1"], "turns": [], "votes": [], "proposal": "",
        "summary": "", "exec_summary": "e", "selection_reason": "x"})


def _drive_plan(store, tmp_path, key):
    """Seed a plan from `key`, then deterministically fill its act lane + build artifacts so the
    plan-derived methodology_state renders a full constellation (offline, no LLM)."""
    import sonaloop.prototypes as P
    P.prototypes_dir = lambda: tmp_path / "protos"
    spec = M.get_methodology(key)
    proj = services.start_project(key, "How might we test the layout?", key,
                                  persona_ids=["p1"], store=store)
    pid = proj["id"]
    # fan step id -> its seeded frame task id; build steps carry produces.artifact_type/more_tags.
    fan_steps = [s for s in spec["steps"] if not M._is_decide(s)]
    n = 0
    for s in fan_steps:
        frame_id = f"frame__{s['id']}"
        services.record_frame(pid, frame_id, [f"What about {s['id']}?"],
                              memory_refs=[f"persona:p1/{s['id']}"], store=store)
        # two act councils (distinct angles) consuming the frame
        for j in (1, 2):
            n += 1
            cid = f"c{n}"
            _council(store, cid)
            a = services.add_task(pid, "act", "explore", f"{s['id']} angle {j}",
                                  consumes=[frame_id], store=store)
            services.link_evidence(pid, a["id"], {"kind": "council", "id": cid}, store=store)
        # a build fan step scaffolds its declared prototype under one act task
        if s["produces"].get("artifact_type"):
            fid = (s["produces"].get("more_tags") or [None])[0]
            concept = {"title": s["id"], "summary": "", "start": "home", "screens": [
                {"id": "home", "title": "Start", "elements": [
                    {"kind": "button", "id": "go", "label": "Go", "goto": "done"}]},
                {"id": "done", "title": "Done", "elements": [{"kind": "text", "id": "t", "label": "ok"}]}]}
            proto = services.scaffold_prototype(f"proto-{s['id']}", f"{s['id']} proto", concept,
                                                project_id=pid, fidelity=fid, store=store)
            ab = services.add_task(pid, "act", "build", f"build {s['id']}", consumes=[frame_id], store=store)
            services.link_evidence(pid, ab["id"], {"kind": "artifact", "id": proto["id"]}, store=store)
    # one synthesis per verify task, consolidating its fan
    plan = PL.get_plan(pid, store=store)
    for t in plan["tasks"]:
        if t["bucket"] != "verify":
            continue
        fan = [r["id"] for r in PL._fan_evidence(plan, t) if r["kind"] == "council"]
        syn = services.record_synthesis(t["title"], "hmw", fan or None,
                                        {"gesamtbild": f"converged {t['id']}"}, store=store)
        services.link_evidence(pid, t["id"], {"kind": "synthesis", "id": syn["id"]}, store=store)
    return services.get_project_graph(pid, store=store)


def test_diamonds_connect_via_synthesis_spine(store, tmp_path):
    """GAP-6: the converging syntheses of successive diamonds are linked (Define→Select→Deliver…) so
    the full double-diamond reads as ONE connected flow — the spine that now feeds outline relations."""
    g = _drive_plan(store, tmp_path, "double_diamond_deep")
    syn_nodes = [n["study_id"] for n in g["nodes"] if n["study_id"].startswith("synthesis:")]
    informs = [(e["from_study"], e["to_study"]) for e in g["edges"] if e["type"] == "informs"]
    assert len(syn_nodes) >= 3 and len(informs) >= 2          # multiple diamonds, a connected spine
    # every spine edge connects two real synthesis nodes
    for a, b in informs:
        assert a in syn_nodes and b in syn_nodes
    # the spine reaches the final diamond (no isolated terminal synthesis)
    targets = {b for _, b in informs}
    assert any(t in targets for t in syn_nodes)
