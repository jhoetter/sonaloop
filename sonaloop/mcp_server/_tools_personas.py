from __future__ import annotations

import time
from typing import Any

from .. import services
from ..avatar import AVATAR_DISABLED_NOTE, avatars_enabled, generate_persona_avatar
from ._env import _env


def register_personas(mcp):
    # ================= Persona / identity =================
    @mcp.tool()
    def brief_persona(description: str, segment_hint: str | None = None, evidence: str | None = None) -> dict[str, Any]:
        """Gather the prompt + frame to AUTHOR one persona profile from a source
        description. You write the profile JSON from `instructions`, then call
        record_persona. Detects/persists the content language from the description.
        BEFORE authoring: the curated catalog has 300+ ready-made personas with lived
        memory (catalog_search / catalog_recommend → catalog_pull) — author only what
        the catalog does not already cover."""
        t = time.perf_counter()
        return _env("brief_persona", services.brief_persona(description, segment_hint, evidence), t)

    @mcp.tool()
    def record_persona(description: str, profile: dict[str, Any], segment_hint: str | None = None,
                       evidence: str | None = None, generate_avatar: bool = False) -> dict[str, Any]:
        """Validate + persist the persona profile you authored from brief_persona.
        This is the create path (no server-side text generation)."""
        t = time.perf_counter()
        return _env("record_persona", services.record_persona(description, profile, segment_hint, evidence, generate_avatar), t)

    @mcp.tool()
    def get_persona(persona_id: str) -> dict[str, Any]:
        """Full persona record + recent calendar/experience/pain points."""
        t = time.perf_counter()
        return _env("get_persona", services.get_persona(persona_id), t)

    @mcp.tool()
    def persona_readiness(persona_id: str) -> dict[str, Any]:
        """Structural readiness of one persona: profile specificity, independent grounding,
        lived events/facts, calendar continuity and authored capabilities."""
        t = time.perf_counter()
        return _env("persona_readiness", services.persona_readiness(persona_id), t)

    @mcp.tool()
    def brief_persona_memory_onboarding(persona_id: str, days: int = 28) -> dict[str, Any]:
        """Plan the gather→author→write-back sequence that turns a static persona profile
        into a critic-checked lived-memory baseline. No memory is fabricated by this read."""
        t = time.perf_counter()
        return _env("brief_persona_memory_onboarding",
                    services.brief_persona_memory_onboarding(persona_id, days), t)

    @mcp.tool()
    def list_personas(filters: dict[str, Any] | None = None, compact: bool = True,
                      limit: int = 25, cursor: str | None = None) -> dict[str, Any]:
        """Lean one-line overview of personas (slug/name/age/role/segment) — drill in with
        get_persona for the full profile. Pass compact=False for full profiles (large).
        Paginated per the shared convention (docs/pagination.md): `limit` (default 25) +
        opaque `cursor` over a stable name/slug sort; answers {items, total, has_more,
        next_cursor} — `total` counts the whole filtered set, `next_cursor` is present
        exactly when has_more. A cursor only fits the filter set it was issued under;
        no params → the first page (backward compatible)."""
        t = time.perf_counter()
        def key(p: dict[str, Any]) -> str:
            return f'{(p.get("display_name") or "").casefold()}\x1f{p.get("slug") or p.get("id", "")}'
        rows = sorted(services.list_personas(filters, compact=compact), key=key)
        page = services.paginate(rows, key, limit=limit, cursor=cursor,
                                 filters={"filters": filters or {}, "compact": bool(compact)})
        return _env("list_personas", page, t)

    @mcp.tool()
    def get_persona_soul(persona_id: str) -> dict[str, Any]:
        """The persona's SOUL.md (authoritative identity + grown drift)."""
        t = time.perf_counter()
        return _env("get_persona_soul", services.get_persona_soul(persona_id), t)

    @mcp.tool()
    def prepare_persona_agent_context(persona_id: str, task: str | None = None, recent_events: int = 8) -> dict[str, Any]:
        """Build the launch context for a persona subagent (SOUL + state + recent events)."""
        t = time.perf_counter()
        return _env("prepare_persona_agent_context", services.prepare_persona_agent_context(persona_id, task, recent_events), t)

    @mcp.tool()
    def preview_persona_update(persona_id: str, patch: dict[str, Any],
                               expected_updated_at: str | None = None) -> dict[str, Any]:
        """Validate an editable-field patch and return its diff/current version without writing."""
        t = time.perf_counter()
        return _env("preview_persona_update",
                    services.preview_persona_update(persona_id, patch, expected_updated_at), t)

    @mcp.tool()
    def update_persona(persona_id: str, patch: dict[str, Any], reason: str,
                       expected_updated_at: str | None = None) -> dict[str, Any]:
        """Apply a host-authored patch to a persona's profile; records a revision with the reason.
        A `capabilities` patch ({rungs:{see,walk,drive,login}, tech_comfort: 1-5 (see
        suggest_tech_comfort), devices, accessibility, provenance}) is validated (shape +
        vocabulary) and merged into a full normalized profile, marked authored."""
        t = time.perf_counter()
        return _env("update_persona",
                    services.update_persona(persona_id, patch, reason, expected_updated_at), t)

    @mcp.tool()
    def suggest_tech_comfort() -> dict[str, Any]:
        """The CANONICAL tech-comfort vocabulary for a persona's capability profile
        (capabilities.tech_comfort) — call this before declaring/patching one. Each item is
        {term, value, label_key, hint, aliases} in comfort order (novice → expert); the behavioral
        `hint` is the pace/voice contract session briefs weave into their anti-steering context.
        Like the friction scale this set is CLOSED: a known alias resolves to its level, but an
        unknown one is REJECTED on write. Derived live from suggestions/tech_comfort.json."""
        t = time.perf_counter()
        return _env("suggest_tech_comfort", services.suggest_tech_comfort(), t)

    @mcp.tool()
    def refresh_persona_from_source(persona_id: str, force: bool = False) -> dict[str, Any]:
        """Refresh a persona from where it came from. Catalog-pulled personas re-pull from
        their recorded catalog ref (drift-safe: a locally modified profile is skipped and
        reported unless force=True — catalog_status shows the drift). Native personas answer
        with the re-authoring recipe (brief_persona -> author -> record_persona) in-band."""
        t = time.perf_counter()
        return _env("refresh_persona_from_source",
                    services.refresh_persona_from_source(persona_id, force=force), t)

    @mcp.tool()
    def generate_avatar(persona_id: str, style: str | None = None) -> dict[str, Any]:
        """Generate (or regenerate) the persona's avatar image — needs OPENAI_API_KEY.
        Without the key this degrades gracefully (in-band note, no error)."""
        t = time.perf_counter()
        if not avatars_enabled():
            # Cold start without the optional key is normal — answer in-band, never raise.
            return _env("generate_avatar",
                        {"avatar": None, "skipped": True, "note": AVATAR_DISABLED_NOTE}, t)
        return _env("generate_avatar", generate_persona_avatar(persona_id, style), t)

    # ----- persona evidence + export — relocated here (M3) -----
    @mcp.tool()
    def attach_evidence(persona_id: str, source_type: str, content_or_path: str, notes: str | None = None) -> dict[str, Any]:
        """Attach a real-world SOURCE (doc/url/note) to a persona to ground its claims."""
        t = time.perf_counter()
        return _env("attach_evidence", services.attach_evidence(persona_id, source_type, content_or_path, notes), t)

    @mcp.tool()
    def export_persona(persona_id: str, format: str = "json") -> dict[str, Any]:
        """Export one persona (profile + SOUL/memory) as json/markdown."""
        t = time.perf_counter()
        return _env("export_persona", services.export_persona(persona_id, format), t)

    @mcp.tool()
    def assess_coverage(project: str, job: str | None = None,
                        persona_ids: list[str] | None = None) -> dict[str, Any]:
        """Coverage / diversity check over a study's PERSONA SET — a deterministic analysis that flags when
        the panel is too narrow to be trustworthy (a homogeneous "council of clones"). `project` is a
        research-project id (its persona_ids are the panel; override with persona_ids). With a `job` taxonomy
        id the panel is ALSO checked against that Job's declared coverage (min_personas + persona_axes).
        Returns an indicator (thin|ok|strong), per-dimension distribution + flags, concrete gaps, and
        recommended archetypes to add — plus a `catalog_hint` when gaps exist (catalog_recommend can
        usually fill them from 300+ ready-made personas). No prose generation, no persistence."""
        t = time.perf_counter()
        return _env("assess_coverage", services.assess_coverage(project, job, persona_ids), t)
