from __future__ import annotations

import pytest

from sonaloop import services
from sonaloop.config import partition_dir


def test_project_creation_assigns_random_existing_icon(store):
    project = services.create_research_project("Icon defaults", goal="pick a mark", store=store)
    names = set(services.available_project_icons()["icons"])
    assert project["icon"]["kind"] == "regular"
    assert project["icon"]["name"] in names
    listed = services.list_research_projects(store=store)[0]
    assert listed["icon"] == project["icon"]


def test_project_graph_carries_icon_for_detail_header(store):
    project = services.create_research_project("Graph icon", store=store, icon="compass")
    graph = services.get_project_graph(project["id"], store=store)
    assert graph["project"]["icon"] == {"kind": "regular", "name": "compass"}


def test_plan_project_graph_carries_icon_for_detail_header(store):
    project = services.start_project("Plan graph icon", "keep the header icon", store=store,
                                     icon="target")
    graph = services.get_project_graph(project["id"], store=store)
    assert graph["project"]["icon"] == {"kind": "regular", "name": "target"}


def test_set_project_icon_saves_sanitized_custom_svg(store):
    project = services.create_research_project("Custom icon", store=store)
    svg = '<svg viewBox="0 0 24 24" onclick="bad()"><path d="M4 12h16"/></svg>'
    out = services.set_project_icon(project["id"], svg=svg, store=store)
    icon = out["icon"]
    assert icon["kind"] == "custom"
    assert "onclick" not in icon["svg"]
    assert (partition_dir() / "project-icons" / icon["svg_path"].rsplit("/", 1)[1]).exists()
    assert "project-custom-icon" in services.project_icon_svg(icon)


def test_rejects_unsafe_project_icon_svg(store):
    project = services.create_research_project("Bad icon", store=store)
    with pytest.raises(ValueError):
        services.set_project_icon(project["id"], svg='<svg><script>alert(1)</script></svg>',
                                  store=store)


def test_generate_project_icon_persists_svg(store):
    project = services.create_research_project("Pricing check", goal="what should we charge",
                                               store=store)
    out = services.generate_project_icon(project["id"], prompt="pricing", store=store)
    assert out["icon"]["kind"] == "custom"
    assert out["icon"]["svg_path"].endswith(".svg")
    assert services.get_research_project(project["id"], store=store)["icon"]["kind"] == "custom"
