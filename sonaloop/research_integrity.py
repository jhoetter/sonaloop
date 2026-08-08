"""Evidence posture and product-understanding invariants.

This module is deliberately independent from :mod:`sonaloop.services`.  The
plan engine, recorders, exports and web renderer all need the same answers:

* is this project governed by a product/stimulus policy?
* which concrete project records are admissible stimulus?
* may a claim call itself observed, or is it simulated/inferred/unsupported?

Keeping those decisions here prevents an MCP host (strong or weak) from
reinterpreting the contract in a prompt.  The vocabulary below is a versioned
data contract, not a classifier: the host declares posture and the server
validates the cited records.  Unstructured/undeclared claims fail safe as
``unsupported``.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .config import utc_now_iso
from .storage import Store


PRODUCT_UNDERSTANDING_SCHEMA = "sonaloop.product_understanding.v1"
CLAIM_POSTURE_SCHEMA = "sonaloop.claim_posture.v1"
CLAIM_POSTURES = frozenset({
    "observed", "memory_grounded", "inferred", "simulated", "unsupported",
})
PRODUCT_CAPABILITY_STATUSES = frozenset({
    "observed_present", "observed_absent", "inferred", "unknown",
})


class IntegrityError(Exception):
    """Stable error code that survives MCP/CLI stringification."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def operation_fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def project_policy(project: dict[str, Any] | None, plan: dict[str, Any] | None = None) -> dict[str, Any]:
    """The persisted integrity policy for one project.

    Plans created before this contract have no ``integrity`` block and stay
    readable.  New methodology plans copy their policy from methodology data;
    project policy may only add stricter flags, never erase plan requirements.
    """
    out: dict[str, Any] = {}
    for source in ((project or {}).get("integrity") or {}, (plan or {}).get("integrity") or {}):
        for key, value in source.items():
            if isinstance(value, bool):
                out[key] = bool(out.get(key)) or value
            elif key not in out:
                out[key] = value
    return out


def is_reaction_project(project: dict[str, Any] | None,
                        plan: dict[str, Any] | None = None) -> bool:
    policy = project_policy(project, plan)
    return bool(policy.get("stimulus_required") or policy.get("claim_posture_required"))


def _norm_ref(raw: Any) -> dict[str, str]:
    if isinstance(raw, str):
        token = raw.strip()
        if ":" in token:
            kind, rid = token.split(":", 1)
            return {"kind": kind.strip(), "id": rid.strip()}
        return {"kind": "", "id": token}
    raw = raw or {}
    out = {"kind": str(raw.get("kind") or "").strip(),
           "id": str(raw.get("id") or "").strip()}
    for key in ("anchor", "quote", "text", "role"):
        if str(raw.get(key) or "").strip():
            out[key] = str(raw[key]).strip()
    return out


def _project_asset(project: dict[str, Any], rid: str) -> dict[str, Any] | None:
    return next((a for a in (project.get("assets") or [])
                 if str(a.get("id") or "") == rid), None)


def _project_flow(project: dict[str, Any], rid: str) -> dict[str, Any] | None:
    return next((f for f in (project.get("flows") or [])
                 if str(f.get("id") or "") == rid), None)


def _project_artifact(project: dict[str, Any], rid: str) -> dict[str, Any] | None:
    return next((a for a in (project.get("artifacts") or [])
                 if str(a.get("id") or "") == rid), None)


def resolve_project_ref(project_id: str, raw: Any, store: Store,
                        *, observed_behavior: bool = False) -> dict[str, Any]:
    """Resolve a reference inside its project and state why it is admissible.

    ``observed_behavior`` is intentionally stricter than stimulus grounding:
    screenshots and captured copy prove what the product showed, not what a
    person actually did.  Only a session verified against a retained browser
    log may support an ``observed`` behavior claim.
    """
    project = store.get_research_project(project_id)
    if not project:
        raise IntegrityError("UNKNOWN_PROJECT", f"unknown research project: {project_id}")
    ref = _norm_ref(raw)
    kind, rid = ref["kind"], ref["id"]
    if not kind or not rid:
        raise IntegrityError("BAD_EVIDENCE_REF", "evidence refs require {kind, id}")

    if kind in {"asset", "screenshot", "document", "image"}:
        asset = _project_asset(project, rid)
        if not asset:
            raise IntegrityError("CROSS_PROJECT_EVIDENCE", f"asset {rid!r} is not on project {project_id}")
        if observed_behavior:
            raise IntegrityError(
                "OBSERVATION_EVIDENCE_REQUIRED",
                f"asset {rid!r} proves a product state, not observed behavior; cite a grounded session step",
            )
        return {"ref": {**ref, "kind": "asset"}, "class": "admitted_stimulus",
                "record": asset}

    if kind in {"flow", "screen_flow"}:
        flow = _project_flow(project, rid)
        if not flow:
            raise IntegrityError("CROSS_PROJECT_EVIDENCE", f"flow {rid!r} is not on project {project_id}")
        asset_ids = {str(a.get("id") or "") for a in (project.get("assets") or [])}
        if not flow.get("steps") or any(str(s.get("asset_id") or "") not in asset_ids
                                        for s in flow.get("steps") or []):
            raise IntegrityError("STIMULUS_NOT_ADMITTED", f"flow {rid!r} has missing/unadmitted screens")
        if flow.get("schema") == "sonaloop.flow_manifest.v1":
            canonical = next((m for m in (project.get("flow_manifests") or [])
                              if str(m.get("id") or "") == rid
                              and int(m.get("version") or 0) == int(flow.get("version") or 0)), None)
            if (not canonical
                    or str(canonical.get("manifest_digest") or "") != str(flow.get("manifest_digest") or "")):
                raise IntegrityError(
                    "STIMULUS_VERSION_MISMATCH",
                    f"flow {rid!r} is not the exact immutable admitted manifest version",
                )
            assets_by_id = {str(a.get("id") or ""): a for a in (project.get("assets") or [])}
            for step in canonical.get("steps") or []:
                asset = assets_by_id.get(str(step.get("asset_version_id") or "")) or {}
                if (str(asset.get("content_digest") or "") != str(step.get("content_digest") or "")
                        or (asset.get("admission") or {}).get("schema")
                        != "sonaloop.remote_screenshot_admission.v1"):
                    raise IntegrityError(
                        "STIMULUS_VERSION_MISMATCH",
                        f"flow {rid!r} references a changed or non-admitted screenshot version",
                    )
        if observed_behavior:
            raise IntegrityError(
                "OBSERVATION_EVIDENCE_REQUIRED",
                f"flow {rid!r} is a stimulus, not an observed behavior trace; cite a grounded session step",
            )
        return {"ref": {**ref, "kind": "flow"}, "class": "admitted_stimulus",
                "record": flow}

    if kind in {"artifact", "url_artifact", "captured_artifact"}:
        artifact = _project_artifact(project, rid)
        if not artifact:
            raise IntegrityError("CROSS_PROJECT_EVIDENCE", f"artifact {rid!r} is not on project {project_id}")
        snapshot = artifact.get("snapshot") or {}
        if not snapshot.get("ok") or not artifact.get("content_hash"):
            raise IntegrityError("STIMULUS_NOT_ADMITTED", f"artifact {rid!r} has no successful captured snapshot")
        if observed_behavior:
            raise IntegrityError(
                "OBSERVATION_EVIDENCE_REQUIRED",
                f"captured artifact {rid!r} proves product content, not observed behavior",
            )
        return {"ref": {**ref, "kind": "artifact"}, "class": "admitted_stimulus",
                "record": artifact}

    if kind in {"session", "usability_session", "prototype_session"}:
        session = store.get_usability_session(rid)
        if session:
            if str(session.get("project_id") or "") != project_id:
                raise IntegrityError("CROSS_PROJECT_EVIDENCE", f"session {rid!r} is not on project {project_id}")
        else:
            session = store.get_prototype_session(rid)
            proto = store.get_prototype(str((session or {}).get("prototype_id") or "")) if session else None
            if not session or str((proto or {}).get("project_id") or "") != project_id:
                raise IntegrityError("CROSS_PROJECT_EVIDENCE", f"session {rid!r} is not on project {project_id}")
        if not session.get("grounded_verified"):
            raise IntegrityError(
                "OBSERVATION_EVIDENCE_REQUIRED",
                f"session {rid!r} is not verified against a retained observed-state log",
            )
        if observed_behavior:
            anchor = str(ref.get("anchor") or "")
            if not anchor.startswith("step:"):
                raise IntegrityError(
                    "OBSERVATION_ANCHOR_REQUIRED",
                    f"observed behavior ref session:{rid} must cite an exact anchor such as step:2",
                )
            try:
                step_index = int(anchor.split(":", 1)[1])
            except ValueError:
                raise IntegrityError(
                    "OBSERVATION_ANCHOR_REQUIRED",
                    f"observed behavior ref session:{rid} has invalid anchor {anchor!r}",
                ) from None
            steps = session.get("steps")
            if not isinstance(steps, list):
                reaction = session.get("reaction") or {}
                steps = reaction.get("steps") or reaction.get("timeline") or []
            if not 0 <= step_index < len(steps):
                raise IntegrityError(
                    "OBSERVATION_ANCHOR_REQUIRED",
                    f"observed behavior ref session:{rid} points at nonexistent {anchor} "
                    f"(session has steps 0..{len(steps) - 1})",
                )
        return {"ref": {**ref, "kind": "session"}, "class": "grounded_observation",
                "record": session}

    if kind == "prototype":
        proto = store.get_prototype(rid)
        if not proto or str(proto.get("project_id") or "") != project_id:
            raise IntegrityError("CROSS_PROJECT_EVIDENCE", f"prototype {rid!r} is not on project {project_id}")
        if observed_behavior:
            raise IntegrityError("OBSERVATION_EVIDENCE_REQUIRED",
                                 f"prototype {rid!r} is not an observed behavior trace")
        return {"ref": ref, "class": "admitted_stimulus", "record": proto}

    if kind == "council":
        council = store.get_council_session(rid)
        if not council or str(council.get("project_id") or "") != project_id:
            raise IntegrityError("CROSS_PROJECT_EVIDENCE", f"council {rid!r} is not on project {project_id}")
        if observed_behavior:
            raise IntegrityError("OBSERVATION_EVIDENCE_REQUIRED",
                                 "a synthetic council cannot prove observed behavior")
        return {"ref": ref, "class": "simulated_evidence", "record": council}

    if kind == "synthesis":
        synthesis = store.get_synthesis(rid)
        if not synthesis or str(synthesis.get("project_id") or "") != project_id:
            raise IntegrityError("CROSS_PROJECT_EVIDENCE", f"synthesis {rid!r} is not on project {project_id}")
        if observed_behavior:
            raise IntegrityError("OBSERVATION_EVIDENCE_REQUIRED",
                                 "a synthesis cannot replace an observed behavior trace")
        return {"ref": ref, "class": "derived_evidence", "record": synthesis}

    if kind == "persona":
        if observed_behavior:
            raise IntegrityError("OBSERVATION_EVIDENCE_REQUIRED",
                                 f"{kind} evidence cannot prove observed product behavior")
        cohort = {str(pid) for pid in (project.get("persona_ids") or [])}
        persona = store.get_persona(rid)
        if not persona or str(persona.get("id") or "") not in cohort:
            raise IntegrityError(
                "CROSS_PROJECT_EVIDENCE",
                f"persona {rid!r} is not an existing member of project {project_id}'s cohort",
            )
        return {"ref": ref, "class": "persona_context", "record": persona}

    if kind == "evidence":
        if observed_behavior:
            raise IntegrityError("OBSERVATION_EVIDENCE_REQUIRED",
                                 "persona evidence cannot prove observed product behavior")
        evidence = store.get_evidence(rid)
        cohort = {str(pid) for pid in (project.get("persona_ids") or [])}
        if not evidence or str(evidence.get("persona_id") or "") not in cohort:
            raise IntegrityError(
                "CROSS_PROJECT_EVIDENCE",
                f"evidence {rid!r} is not owned by a persona in project {project_id}'s cohort",
            )
        return {"ref": ref, "class": "persona_context", "record": evidence}

    if kind in {"memory", "recall"}:
        if observed_behavior:
            raise IntegrityError("OBSERVATION_EVIDENCE_REQUIRED",
                                 f"{kind} evidence cannot prove observed product behavior")
        cohort = {str(pid) for pid in (project.get("persona_ids") or [])}
        event = store.get_experience_event(rid)
        evidence = store.get_evidence(rid)
        record = event or evidence
        owner = str((record or {}).get("persona_id") or "")
        if not record or owner not in cohort:
            raise IntegrityError(
                "MEMORY_REF_UNRESOLVED",
                f"{kind} {rid!r} must resolve to a real event/evidence owned by the project cohort",
            )
        return {"ref": ref, "class": "persona_context", "record": record}

    raise IntegrityError("BAD_EVIDENCE_REF", f"unsupported evidence ref kind {kind!r}")


def admitted_stimuli(project_id: str, store: Store) -> list[dict[str, Any]]:
    """Concrete, project-owned stimulus records suitable for a Reaction Test."""
    project = store.get_research_project(project_id) or {}
    out: list[dict[str, Any]] = []
    for asset in project.get("assets") or []:
        if (asset.get("direction") or "in") == "in" and asset.get("id"):
            out.append({"kind": "asset", "id": asset["id"], "title": asset.get("title", "")})
    for flow in project.get("flows") or []:
        try:
            resolve_project_ref(project_id, {"kind": "flow", "id": flow.get("id")}, store)
        except IntegrityError:
            continue
        out.append({"kind": "flow", "id": flow["id"], "title": flow.get("title", "")})
    for artifact in project.get("artifacts") or []:
        try:
            resolve_project_ref(project_id, {"kind": "artifact", "id": artifact.get("id")}, store)
        except IntegrityError:
            continue
        out.append({"kind": "artifact", "id": artifact["id"], "title": artifact.get("title", "")})
    for session in store.list_usability_sessions(project_id=project_id):
        if session.get("grounded_verified"):
            out.append({"kind": "session", "id": session["id"],
                        "title": str((session.get("subject") or {}).get("label") or "Observed session")})
    for session in store.list_prototype_sessions():
        proto = store.get_prototype(str(session.get("prototype_id") or "")) or {}
        if proto.get("project_id") == project_id and session.get("grounded_verified"):
            out.append({"kind": "session", "id": session["id"], "title": "Observed prototype session"})
    # Stable dedupe when the same session is available through compatibility paths.
    seen: set[tuple[str, str]] = set()
    return [row for row in out if not ((row["kind"], row["id"]) in seen
                                       or seen.add((row["kind"], row["id"])))]


def reaction_stimuli(project_id: str, store: Store) -> list[dict[str, Any]]:
    """Stimulus versions the current Product Understanding actually inspected.

    Legacy/non-remote projects retain the admitted-stimulus behavior. Once a
    Product Understanding freezes a remote manifest, though, the Reaction Test
    may cite only that exact manifest and its exact covered asset versions. A
    later upload/manifest is useful candidate evidence for a *new* preflight,
    but cannot silently enter the already-bound test.
    """
    admitted = admitted_stimuli(project_id, store)
    project = store.get_research_project(project_id) or {}
    current = current_product_understanding(project)
    binding = (current or {}).get("stimulus_manifest") or {}
    manifest_id = str(binding.get("manifest_id") or "")
    if not manifest_id:
        return admitted
    allowed = {("flow", manifest_id)}
    allowed.update(
        ("asset", str(row.get("asset_version_id") or ""))
        for row in ((current or {}).get("coverage_checklist") or [])
        if str(row.get("asset_version_id") or "")
    )
    return [row for row in admitted if (str(row.get("kind") or ""),
                                        str(row.get("id") or "")) in allowed]


def current_product_understanding(project: dict[str, Any] | None) -> dict[str, Any] | None:
    versions = (project or {}).get("product_understanding_versions") or []
    current_id = str((project or {}).get("product_understanding_current_id") or "")
    if current_id:
        found = next((v for v in versions if str(v.get("id") or "") == current_id), None)
        if found:
            return found
    return versions[-1] if versions else None


def render_product_understanding_context(record: dict[str, Any] | None) -> str:
    """Compact, citable stimulus block for councils/reports (never persona memory)."""
    if not record:
        return ""
    target = record.get("target") or {}
    lines = [
        "PRODUCT UNDERSTANDING (external stimulus; do not treat as persona memory)",
        f"Artifact: {record.get('id')} · schema {record.get('schema')}",
        f"Target: {target.get('name') or target.get('identity') or target.get('url') or 'unknown'}",
        f"Revision: {record.get('revision')} · observed at {record.get('observed_at')}",
    ]
    manifest = record.get("stimulus_manifest") or {}
    if manifest:
        lines.append(
            f"Frozen stimulus: {manifest.get('manifest_id')} v{manifest.get('manifest_version')} "
            f"· {manifest.get('manifest_digest')} · target {manifest.get('target_revision')}"
        )
        lines.append(
            f"Coverage: {len(record.get('coverage_checklist') or [])} exact screenshot versions inspected"
        )
    for claim in record.get("capabilities") or []:
        refs = ", ".join(f"{r.get('kind')}:{r.get('id')}" for r in claim.get("evidence_refs") or [])
        suffix = f" [{refs}]" if refs else ""
        lines.append(f"- {claim.get('status')}: {claim.get('claim')}{suffix}")
    unknowns = [c.get("claim") for c in record.get("capabilities") or [] if c.get("status") == "unknown"]
    if unknowns:
        lines.append("Unknowns: " + " · ".join(str(x) for x in unknowns if x))
    return "\n".join(lines)


def _claim_posture(raw: Any) -> str:
    posture = str(raw or "unsupported").strip().lower()
    if posture not in CLAIM_POSTURES:
        raise IntegrityError(
            "BAD_CLAIM_POSTURE",
            f"claim posture must be one of {', '.join(sorted(CLAIM_POSTURES))}; got {posture!r}",
        )
    return posture


def validate_claim(project_id: str, raw: dict[str, Any], store: Store,
                   *, claim_id: str) -> dict[str, Any]:
    if not isinstance(raw, dict) or not str(raw.get("text") or "").strip():
        raise IntegrityError("BAD_CLAIM", "claims require non-empty text")
    posture = _claim_posture(raw.get("posture") or (raw.get("meta") or {}).get("claim_posture"))
    refs = [_norm_ref(r) for r in (raw.get("refs") or [])]
    if posture != "unsupported" and not refs:
        raise IntegrityError("CLAIM_EVIDENCE_REQUIRED",
                             f"{posture} claim {claim_id!r} needs at least one evidence ref")
    resolved = []
    for ref in refs:
        resolved.append(resolve_project_ref(project_id, ref, store,
                                            observed_behavior=(posture == "observed")))
    if posture == "memory_grounded" and not any(r["class"] == "persona_context" for r in resolved):
        raise IntegrityError("MEMORY_EVIDENCE_REQUIRED",
                             f"memory_grounded claim {claim_id!r} must cite memory/evidence/recall")
    if posture == "simulated" and not any(r["class"] in {
            "persona_context", "simulated_evidence", "admitted_stimulus", "derived_evidence",
    } for r in resolved):
        raise IntegrityError("SIMULATION_EVIDENCE_REQUIRED",
                             f"simulated claim {claim_id!r} lacks persona/stimulus/council evidence")
    return {
        "id": str(raw.get("id") or claim_id),
        "text": str(raw["text"]).strip(),
        "posture": posture,
        "refs": [r["ref"] for r in resolved] if resolved else refs,
    }


def apply_claim_postures(project_id: str, statements: list[dict[str, Any]],
                         findings: list[dict[str, Any]], raw_claims: list[dict[str, Any]] | None,
                         store: Store, *, prose_present: bool = False) -> tuple[
                             list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Validate/stamp every structured claim and return the artifact posture envelope.

    Persona statements in a Reaction Test are simulated reactions by definition;
    the server stamps that posture.  Findings without an explicit posture are
    retained as ``unsupported`` (an inspectable draft) rather than laundering
    them into findings.  Non-reaction projects remain backward compatible unless
    an author explicitly opts into posture metadata.
    """
    project = store.get_research_project(project_id) or {}
    plan = store.get_research_plan(project_id)
    governed = is_reaction_project(project, plan)
    explicit = bool(raw_claims) or any((x.get("meta") or {}).get("claim_posture")
                                       for x in [*statements, *findings])
    if not governed and not explicit:
        return statements, findings, {}

    claims: list[dict[str, Any]] = []
    stamped_statements: list[dict[str, Any]] = []
    for index, statement in enumerate(statements):
        st = dict(statement)
        meta = dict(st.get("meta") or {})
        declared = meta.get("claim_posture") or ("simulated" if governed else "unsupported")
        raw = {"id": st.get("id") or f"statement:{index}", "text": st.get("text") or "",
               "posture": declared, "refs": st.get("refs") or []}
        claim = validate_claim(project_id, raw, store, claim_id=f"statement:{index}")
        meta["claim_posture"] = claim["posture"]
        st["meta"] = meta
        st["refs"] = claim["refs"]
        stamped_statements.append(st)
        claims.append(claim)

    stamped_findings: list[dict[str, Any]] = []
    for index, finding in enumerate(findings):
        f = dict(finding)
        meta = dict(f.get("meta") or {})
        raw = {"id": f.get("id") or f"finding:{index}", "text": f.get("text") or "",
               "posture": meta.get("claim_posture") or "unsupported",
               "refs": f.get("refs") or []}
        claim = validate_claim(project_id, raw, store, claim_id=f"finding:{index}")
        meta["claim_posture"] = claim["posture"]
        f["meta"] = meta
        f["refs"] = claim["refs"]
        stamped_findings.append(f)
        claims.append(claim)

    for index, raw in enumerate(raw_claims or []):
        claims.append(validate_claim(project_id, raw, store, claim_id=f"claim:{index}"))

    counts = {posture: sum(1 for c in claims if c["posture"] == posture)
              for posture in sorted(CLAIM_POSTURES)}
    # Unstructured prose is not silently treated as evidence.  It is covered
    # only when the author supplied an explicit top-level claim inventory.
    prose_uncovered = bool(prose_present and not raw_claims)
    verified = bool(claims) and not counts["unsupported"] and not prose_uncovered
    envelope = {
        "schema": CLAIM_POSTURE_SCHEMA,
        "default": "unsupported",
        "claims": claims,
        "counts": counts,
        "prose_uncovered": prose_uncovered,
        "verified": verified,
    }
    return stamped_statements, stamped_findings, envelope


def stamp_derived_finding(finding: dict[str, Any],
                          statements: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Carry source refs/posture onto a deterministic format aggregate.

    Head-to-head, price, red-team and ideation adapters append a server-derived
    finding. It is an inference over the supplied statement rows, not a new
    observation. Without citable source rows it stays explicitly unsupported,
    which keeps Reaction Test completion fail-closed.
    """
    out = dict(finding)
    refs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for statement in statements or []:
        for raw in statement.get("refs") or []:
            ref = _norm_ref(raw)
            token = _canonical(ref)
            if ref.get("kind") and ref.get("id") and token not in seen:
                seen.add(token)
                refs.append(ref)
    if refs and not out.get("refs"):
        out["refs"] = refs
    meta = dict(out.get("meta") or {})
    meta.setdefault("claim_posture", "inferred" if (out.get("refs") or []) else "unsupported")
    out["meta"] = meta
    return out


def artifact_posture_gaps(record: dict[str, Any], label: str) -> list[str]:
    posture = record.get("claim_posture") or {}
    if not posture:
        return [f"{label} has no {CLAIM_POSTURE_SCHEMA} envelope"]
    gaps = []
    if posture.get("prose_uncovered"):
        gaps.append(f"{label} contains prose not covered by an explicit claim inventory")
    unsupported = int((posture.get("counts") or {}).get("unsupported") or 0)
    if unsupported:
        gaps.append(f"{label} contains {unsupported} unsupported claim(s)")
    if not posture.get("verified"):
        gaps.append(f"{label} is an unverified hypothesis draft")
    return gaps


def claim_posture_markdown(envelope: dict[str, Any] | None, *, de: bool = False) -> list[str]:
    """Self-contained Markdown block used by council/report exports."""
    if not envelope:
        return []
    heading = "Claim-Herkunft" if de else "Claim provenance"
    state = (("vollständig" if envelope.get("verified") else "unverifizierter Hypothesenentwurf")
             if de else
             ("complete" if envelope.get("verified") else "unverified hypothesis draft"))
    lines = [f"## {heading}", f"**Status:** {state}"]
    if envelope.get("prose_uncovered"):
        lines.append("**Warnung:** Nicht inventarisierte Prosa." if de
                     else "**Warning:** Uninventoried prose.")
    for claim in envelope.get("claims") or []:
        refs = ", ".join(
            f"{ref.get('kind')}:{ref.get('id')}"
            + (f"@{ref.get('anchor')}" if ref.get("anchor") else "")
            for ref in claim.get("refs") or []
        )
        suffix = f" — {refs}" if refs else ""
        lines.append(f"- `{claim.get('posture', 'unsupported')}` {claim.get('text', '')}{suffix}")
    lines.append("")
    return lines


def reaction_task_gaps(project_id: str, task: dict[str, Any], plan: dict[str, Any],
                       store: Store) -> list[str]:
    """Blocking gaps for Reaction Test act/verify completion."""
    project = store.get_research_project(project_id) or {}
    if not is_reaction_project(project, plan):
        return []
    gaps: list[str] = []
    current = current_product_understanding(project)
    if not current:
        gaps.append("record the mandatory Product Understanding preflight")
    if (project_policy(project, plan).get("cohort_preflight_required")):
        from .cohort_integrity import current_cohort_preflight, preflight_satisfies_project
        cohort_gate = current_cohort_preflight(project)
        if not cohort_gate:
            gaps.append("record the mandatory cohort-integrity preflight")
        elif not preflight_satisfies_project(project, store):
            gaps.append(
                f"cohort-integrity gate is {cohort_gate.get('status')!r} or stale for the current cohort"
            )
    stimuli = reaction_stimuli(project_id, store)
    if not stimuli:
        gaps.append("admit a concrete stimulus (asset, captured artifact, defined flow, or grounded session)")

    if task.get("bucket") not in {"act", "verify"}:
        return gaps
    refs = [r for r in (task.get("produces") or []) if r.get("kind") != "frame"]
    if not refs:
        gaps.append("task has no linked evidence")
        return gaps
    stimulus_ids = {(s["kind"], s["id"]) for s in stimuli}
    for ref in refs:
        kind, rid = str(ref.get("kind") or ""), str(ref.get("id") or "")
        if kind == "council":
            rec = store.get_council_session(rid) or {}
            gaps.extend(artifact_posture_gaps(rec, f"council:{rid}"))
            if (project_policy(project, plan).get("cohort_preflight_required")):
                from .cohort_integrity import current_cohort_preflight
                gate = current_cohort_preflight(project) or {}
                countervoices = set((gate.get("representation") or {}).get(
                    "countervoice_persona_ids") or [])
                participants = set(rec.get("persona_ids") or [])
                if (gate.get("status") != "overridden" and countervoices
                        and not (countervoices & participants)):
                    gaps.append(
                        f"council:{rid} excludes every declared skeptical/indifferent/non-target voice"
                    )
                if gate.get("status") != "overridden" and countervoices & participants:
                    declarations = {row.get("persona_id"): row for row in
                                    (gate.get("representation") or {}).get("declarations") or []}
                    expressed = False
                    for statement in rec.get("statements") or []:
                        pid = str(statement.get("persona_id") or "")
                        if pid not in countervoices:
                            continue
                        stance = statement.get("stance")
                        value = stance.get("value") if isinstance(stance, dict) else stance
                        if not isinstance(value, (int, float)) or isinstance(value, bool):
                            continue
                        posture = str((declarations.get(pid) or {}).get("posture") or "")
                        if ((posture == "skeptical" and value <= -1)
                                or (posture == "indifferent" and value == 0)
                                or (posture == "non_target" and value <= 0)):
                            expressed = True
                            break
                    if not expressed:
                        gaps.append(
                            f"council:{rid} includes a grounded countervoice but no statement "
                            "expresses its declared non-positive structured stance"
                        )
            cited = {(str(r.get("kind") or ""), str(r.get("id") or ""))
                     for c in (rec.get("claim_posture") or {}).get("claims") or []
                     for r in c.get("refs") or []}
            if not cited & stimulus_ids:
                gaps.append(f"council:{rid} does not cite the admitted stimulus")
        elif kind == "synthesis":
            rec = store.get_synthesis(rid) or {}
            gaps.extend(artifact_posture_gaps(rec, f"synthesis:{rid}"))
        elif kind in {"session", "usability_session", "prototype_session"}:
            try:
                resolve_project_ref(project_id, {"kind": "session", "id": rid, "anchor": "step:0"},
                                    store, observed_behavior=True)
            except IntegrityError as exc:
                gaps.append(str(exc))
        elif (kind, rid) not in stimulus_ids:
            gaps.append(f"{kind}:{rid} is not an admitted Reaction Test evidence type")
    return list(dict.fromkeys(gaps))


def product_understanding_payload(
    project_id: str,
    target: dict[str, Any],
    revision: str,
    routes: list[Any],
    flows: list[Any],
    states: list[Any],
    capabilities: list[dict[str, Any]],
    evidence_refs: list[Any],
    store: Store,
    *,
    observed_at: str,
    record_id: str,
    version: int,
    supersedes: str = "",
    prior: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate and normalize one immutable Product Understanding version."""
    if not isinstance(target, dict):
        raise IntegrityError("BAD_PRODUCT_UNDERSTANDING", "target must be an object")
    identity = str(target.get("identity") or target.get("name") or target.get("url") or "").strip()
    if not identity:
        raise IntegrityError("BAD_PRODUCT_UNDERSTANDING",
                             "target needs identity, name or url")
    revision = str(revision or "").strip()
    if not revision:
        raise IntegrityError("BAD_PRODUCT_UNDERSTANDING",
                             "revision is required (use an explicit 'unknown', never omit it)")
    observed_at = str(observed_at or "").strip()
    if not observed_at or "T" not in observed_at:
        raise IntegrityError("BAD_PRODUCT_UNDERSTANDING", "observed_at must be an ISO-8601 timestamp")

    root_refs = [resolve_project_ref(project_id, r, store)["ref"] for r in (evidence_refs or [])]

    def inventory(items: list[Any], label: str) -> list[dict[str, Any]]:
        out = []
        for index, raw in enumerate(items or []):
            row = dict(raw) if isinstance(raw, dict) else {"label": str(raw)}
            text = str(row.get("path") or row.get("name") or row.get("label")
                       or row.get("state") or "").strip()
            if not text:
                raise IntegrityError("BAD_PRODUCT_UNDERSTANDING",
                                     f"{label}[{index}] needs path/name/label/state")
            refs = [resolve_project_ref(project_id, r, store)["ref"]
                    for r in (row.get("evidence_refs") or [])]
            if not refs:
                raise IntegrityError(
                    "INVENTORY_EVIDENCE_REQUIRED",
                    f"{label}[{index}] {text!r} needs at least one project evidence ref",
                )
            clean = {k: v for k, v in row.items() if k != "evidence_refs"}
            clean["evidence_refs"] = refs
            out.append(clean)
        return out

    routes_out = inventory(routes, "routes")
    flows_out = inventory(flows, "flows")
    states_out = inventory(states, "states")
    if not (routes_out or flows_out or states_out):
        raise IntegrityError("BAD_PRODUCT_UNDERSTANDING",
                             "record at least one observed route, flow or state")
    if not capabilities:
        raise IntegrityError("BAD_PRODUCT_UNDERSTANDING", "capabilities must not be empty")

    previous_by_key = {str(c.get("key") or ""): c for c in (prior or {}).get("capabilities") or []
                       if c.get("key")}
    capabilities_out = []
    for index, raw in enumerate(capabilities):
        if not isinstance(raw, dict) or not str(raw.get("claim") or "").strip():
            raise IntegrityError("BAD_PRODUCT_UNDERSTANDING",
                                 f"capabilities[{index}] needs a claim")
        claim = str(raw["claim"]).strip()
        key = str(raw.get("key") or _stable_id("capability", claim.casefold())).strip()
        status = str(raw.get("status") or "").strip()
        if status not in PRODUCT_CAPABILITY_STATUSES:
            raise IntegrityError(
                "BAD_CAPABILITY_STATUS",
                f"capability {claim!r} status must be one of "
                f"{', '.join(sorted(PRODUCT_CAPABILITY_STATUSES))}",
            )
        refs = [resolve_project_ref(project_id, r, store)["ref"]
                for r in (raw.get("evidence_refs") or [])]
        if status in {"observed_present", "observed_absent", "inferred"} and not refs:
            raise IntegrityError("CAPABILITY_EVIDENCE_REQUIRED",
                                 f"{status} capability {claim!r} needs evidence_refs")
        attempt = raw.get("verification_attempt") or {}
        if status == "observed_absent":
            if not isinstance(attempt, dict) or not str(
                    attempt.get("procedure") or attempt.get("description") or "").strip():
                raise IntegrityError(
                    "ABSENCE_VERIFICATION_REQUIRED",
                    f"observed_absent capability {claim!r} needs a documented verification_attempt",
                )
        previous = previous_by_key.get(key)
        row = {
            "id": _stable_id("puc", project_id, record_id, key),
            "key": key,
            "claim": claim,
            "status": status,
            "evidence_refs": refs,
            "verification_attempt": attempt if attempt else None,
        }
        if previous:
            row["supersedes"] = previous.get("id")
            if previous.get("status") != status or previous.get("claim") != claim:
                row["revision_reason"] = str(raw.get("revision_reason") or "later observation")
        capabilities_out.append({k: v for k, v in row.items() if v not in (None, "")})

    return {
        "schema": PRODUCT_UNDERSTANDING_SCHEMA,
        "id": record_id,
        "version": version,
        "project_id": project_id,
        "target": dict(target),
        "revision": revision,
        "observed_at": observed_at,
        "routes": routes_out,
        "flows": flows_out,
        "states": states_out,
        "capabilities": capabilities_out,
        "evidence_refs": root_refs,
        "supersedes": supersedes,
        "created_at": utc_now_iso(),
    }
