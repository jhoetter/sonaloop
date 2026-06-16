"""Outline chip CONTRACT (tracker: outline-chip-contract-every-row-kind-declares-its-chips-enfo).

Every row KIND the project outline emits declares its chips through this ONE registry: either a
builder(item) -> chips html, or an explicit NO-CHIPS sentinel naming WHY the kind carries none
(so the registry stays an inventory, not a loophole). _graph_outline consults it for EVERY row.
An UNREGISTERED kind renders chip-less in production (a page must never crash over a chip) but
lands in UNDECLARED_KINDS, which the contract test (tests/test_outline_chip_contract.py) asserts
empty after a full render — a new row kind cannot ship without declaring its chips.

Pure rendering: builders read what already rides the row item (the graph node dict under `node`,
the session record under `session`); data enrichment stays in services (the sessions pattern)."""
from __future__ import annotations

from .. import artifacts as _A_art
from .. import presentation as _pres
from ._components import _label
from ._html import h, raw
from ._i18n import t
from ._presence import (
    decision_status_pill, hypothesis_status_pill,
    open_question_status_pill, survey_status_pill,
)


class NoChips:
    """Explicit 'this row kind carries no chips' declaration, with the reason (what other
    affordance already carries the row's signal)."""

    def __init__(self, reason: str):
        self.reason = reason


# Row kinds seen at render time WITHOUT a registered entry — the contract test interrogates
# this set; production falls back to no chips instead of crashing the page.
UNDECLARED_KINDS: set[str] = set()

# Council modes are a bounded code enum (services.council_mode) — membership-guard the dynamic
# t() prefix (tests/test_i18n.py allowlists "council_mode_").
_MODES = ("discovery", "evaluation", "decision")


def _council_chips(item: dict) -> str:
    """The mode tag only (derived the way the council page does — it rides node['mode']).
    V2 dropped the statement count: the avatars already say who debated, and the count lives
    on the detail/slide-over. The count stands in only when the mode is unknown (legacy rows
    keep a chip)."""
    node = item.get("node") or {}
    mode = node.get("mode")
    if mode in _MODES:
        return _label(t("council_mode_" + mode), "var(--blue)")
    return _label(t("chip_statements_n", n=int(node.get("n_statements") or 0)))


def _synthesis_chips(item: dict) -> str:
    """Finding count when the synthesis carries structured findings; a NARRATIVE synthesis
    (arc/gesamtbild prose, zero findings records) shows its source count instead — '0 findings'
    on a rich Define synthesis reads like a defect, not like 'thin' (ux-audit P5). A genuinely
    empty synthesis (no findings, no sources) still shows the honest 0. Amber while in progress."""
    node = item.get("node") or {}
    n_findings = int(node.get("n_findings") or 0)
    n_sources = int(node.get("council_count") or 0)
    chips = [_label(t("chip_sources_n", n=n_sources)) if n_findings == 0 and n_sources
             else _label(t("chip_findings_n", n=n_findings))]
    if node.get("status") == "in_progress":
        chips.append(_label(t("running"), "var(--amber)"))
    return "".join(chips)


def _report_chips(item: dict) -> str:
    return _label(t("n_sections", n=int((item.get("node") or {}).get("n_sections") or 0)))


def _note_chips(item: dict) -> str:
    """A concept note shows its artifact kind (label/color from present() — data, not code);
    built notes carry the built marker. A PLAIN note renders chip-less (V2: the default-kind
    "Observation" pill said nothing the NOTE row label didn't — what varies earns the chip)."""
    node = item.get("node") or {}
    ak = str(node.get("artifact_kind") or "")
    chips = []
    if ak:
        pr = _pres.present(ak)
        chips.append(_label(pr.get("label") or ak, pr.get("color")))
    if node.get("prototype_ids"):
        chips.append(_label(t("chip_built"), "var(--green)"))
    return "".join(chips)


def _friction_count(sess: dict) -> int:
    # mirror of pages/sessions.py:_friction_count (importing pages from here would cycle)
    return sum(1 for s in sess.get("steps") or []
               if next((r["value"] for r in _A_art.friction_terms()
                        if r["term"] == (s.get("friction") or {}).get("level")), 0) > 0)


def _url_artifact_chips(item: dict) -> str:
    """The A/B label + the capture status (captured green / reference-only amber) — the
    reproducibility signal a council-pool artifact carries. URL artifacts are outline rows on the
    DEFAULT view (tracker: sonaloop/project-presence-contract); `kind` is bounded by the code enum
    services ARTIFACT_KINDS, normalized on add_artifact."""
    node = item.get("node") or {}
    chips = []
    if item.get("format"):
        chips.append(_label(str(item["format"]), "var(--blue)"))
    chips.append(_label(str(node.get("label") or "?")))
    if (node.get("snapshot") or {}).get("ok"):
        chips.append(_label(t("artifact_captured"), "var(--green)"))
    else:
        chips.append(_label(t("artifact_capture_failed"), "var(--amber)"))
    return "".join(chips)


def _session_chips(item: dict) -> str:
    """Outcome (completed green / dropped red) + friction count — ≤2 chips (V2). The step
    count and the grounded check moved to the detail/slide-over: the outcome and where it
    rubbed are what a row reader decides on."""
    sess = item.get("session") or {}
    out = sess.get("outcome") or {}
    chips = [_label(t("completed"), "var(--green)") if out.get("completed")
             else _label(t("outcome_dropped", n=out.get("dropoff_step", 0)), "var(--red)")]
    n_fr = _friction_count(sess)
    if n_fr:
        chips.append(_label(t("friction_n", n=n_fr), "var(--amber)"))
    return "".join(str(c) for c in chips)


def _prototype_chips(item: dict) -> str:
    """Fidelity tag + sessions count (§3.2). The count covers recorded reactions AND usability
    walks (node['n_sessions'], enriched by the graph builder); when the row already carries the
    aggregate funnel chip the count would repeat it, so only the fidelity remains."""
    node = item.get("node") or {}
    chips = []
    if node.get("fidelity"):
        chips.append(_label(_pres.present(node["fidelity"])["short"], "#00897b"))
    if not item.get("chip") or not chips:             # the funnel chip already says "N sessions · …"
        chips.append(_label(t("sessions_n", n=int(node.get("n_sessions") or 0))))
    return "".join(chips)


def _decision_chips(item: dict) -> str:
    """Status pill (adopted/proposed/superseded) + the evidence count it rests on (§3.2)."""
    node = item.get("node") or {}
    return decision_status_pill(node.get("status", "proposed")) + _label(
        t("chip_evidence_n", n=len(node.get("based_on") or [])))


def _survey_chips(item: dict) -> str:
    """Lifecycle pill + n responses (V2: ≤2 chips — the response count is the survey's
    signal; the question count lives on the detail page)."""
    node = item.get("node") or {}
    return (survey_status_pill(node.get("status", "draft"))
            + _label(t("n_responses", n=int(node.get("response_count") or 0))))


def _hypothesis_chips(item: dict) -> str:
    return hypothesis_status_pill((item.get("node") or {}).get("status", "open"))


def _open_question_chips(item: dict) -> str:
    return open_question_status_pill((item.get("node") or {}).get("status", "open"))


REGISTRY: dict[str, object] = {}


def _register(kind: str, entry) -> None:
    REGISTRY[kind] = entry


_register("council", _council_chips)
_register("synthesis", _synthesis_chips)
_register("report", _report_chips)
_register("note", _note_chips)
_register("session", _session_chips)
_register("url_artifact", _url_artifact_chips)
_register("prototype", _prototype_chips)
_register("decision", _decision_chips)
_register("survey", _survey_chips)
_register("hypothesis", _hypothesis_chips)
_register("open_question", _open_question_chips)
# Assets left the chip vocabulary with V9: they render as `.sl-file--row` FILE rows
# (direction pill + size live ON the file row — _presence.file_card), not as olrows.

def chips_html(item: dict) -> str:
    """The single consult point for an outline row: its declared chips wrapped in the .ol-chips
    slot, '' for a declared-chipless kind. An unknown kind renders chip-less and is recorded in
    UNDECLARED_KINDS (the contract test fails on it; production never crashes)."""
    kind = str(item.get("rkind") or "")
    entry = REGISTRY.get(kind)
    if entry is None:
        UNDECLARED_KINDS.add(kind)
        return ""
    if isinstance(entry, NoChips):
        return ""
    chips = str(entry(item))
    if item.get("trace_health") == "orphaned":
        chips += str(_label("unused after phase close", "var(--amber)"))
    return h("span", {"class_": "ol-chips"}, raw(chips)) if chips else ""
