"""Hermetic test fixtures: every test gets its own temp SQLite DB and a temp
ROOT so rendered SOUL/MEMORY files never touch the real data/ directory. No
network: embeddings are disabled and all text is host-authored (stubbed)."""
from __future__ import annotations

import pytest

from sonaloop import services
from sonaloop.storage import Store


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("PERSONA_COUNCIL_DISABLE_EMBEDDINGS", "1")
    monkeypatch.setenv("PERSONA_COUNCIL_CONTENT_LANGUAGE", "en")
    monkeypatch.setenv("PERSONA_COUNCIL_UI_LANGUAGE", "en")
    # Example personas load from the vendored catalog snapshot, never the network
    # (the "No network" contract) — skip the live catalog_pull refresh.
    monkeypatch.setenv("SONALOOP_EXAMPLES_REFRESH_FROM_CATALOG", "0")
    # SOUL/MEMORY/avatars render under ROOT/data/... — point ROOT at the tmp dir.
    # Submodules read config.ROOT dynamically (single source), so patching it here
    # reaches every service without any package-level fan-out.
    from sonaloop import config
    monkeypatch.setattr(config, "ROOT", tmp_path)
    # The asset binary store + export download URLs resolve against the LIVE
    # config.DATA_DIR (the dir the web app serves at /data) — keep it in the tmp dir.
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    yield


@pytest.fixture
def store():
    return Store()


def make_profile(name: str, *, customer_type: str = "Solo architect", title: str = "Owner",
                 pains=None, goals=None, tools=None) -> dict:
    """A minimal but schema-valid host-authored profile (validate_profile_payload)."""
    return {
        "display_name": name,
        "identity_traits": {k: "unspecified" for k in (
            "gender_presentation", "gender_confidence", "age_range",
            "appearance_notes", "avatar_profile", "avatar_constraints")},
        "segment": {"customer_type": customer_type, "market": "market", "region": "region", "firm_size": "1"},
        "demographics": {"age": 40},
        "role": {"title": title, "responsibilities": "does the work", "seniority": "owner", "decision_power": "full"},
        "company_context": {"industry": "industry", "size": "small", "stack": "stack", "operating_model": "solo"},
        "goals": goals or [f"{name} goal"],
        "constraints": ["limited time"],
        "tool_ids": ["cad", "e_mail"],
        "tools": tools or ["CAD", "E-Mail"],
        "relationships": [{"name": "Client", "type": "customer", "friction": "slow replies"}],
        "personality": {"working_style": "pragmatic", "communication_style": "direct",
                        "risk_tolerance": "medium", "character_notes": "skeptical of hype"},
        "pain_points": pains or [f"{name} pain alpha", f"{name} pain beta"],
        "success_criteria": ["it saves real time"],
    }


def create_persona(store: Store, name: str, **kw) -> str:
    """Create a persona through the host-authored record path; return its id."""
    persona = services.record_persona(f"{name} — source description", make_profile(name, **kw), store=store)
    return persona["id"]
