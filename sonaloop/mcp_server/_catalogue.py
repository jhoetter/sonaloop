"""Auto-generated tool CATALOGUE — a browsable, by-domain index of the MCP surface.

Derived from the live tool modules (AST-parsed at request time), so it can never drift from the real
registry: every `@mcp.tool` / `@mcp.resource` / `@mcp.prompt` in a `_tools_*.py` file appears here,
grouped by its module's domain. Exposed as the `sonaloop://guide/catalogue` resource.
"""
from __future__ import annotations

import ast
import pathlib

# Friendly domain labels + a useful reading ORDER (the ESV happy path first, plumbing last).
_DOMAIN_LABELS = {
    "plan": "Plan engine & run loop (the core ESV path)",
    "council": "Councils & syntheses",
    "prototypes": "Prototypes & proband sessions",
    "usability": "Usability sessions (replayable traces)",
    "walkthrough": "Live walkthroughs (policy-guarded real-SaaS sessions)",
    "surveys": "Surveys (outbound instruments — real responses back)",
    "hypotheses": "Hypotheses (falsifiable predictions scored against reality)",
    "decisions": "Decision records (what we decided, on which evidence, rejecting what)",
    "sections": "Sections, notes & organization",
    "research": "Research projects, graph & report",
    "jobs": "Jobs (presets + sharpen-the-question)",
    "methodology": "Methodologies (plan seeds)",
    "personas": "Personas (profiles + evidence)",
    "catalog": "Persona catalog (browse, recommend & pull from sonaloop-data)",
    "simulation": "Simulation & memory (days/months/recall/timeline)",
    "eval": "Evaluation & critics",
}
_ORDER = ["plan", "council", "prototypes", "usability", "walkthrough", "surveys", "hypotheses",
          "decisions", "sections", "research", "jobs", "methodology", "personas", "catalog",
          "simulation", "eval"]


def _deco_name(d: ast.expr) -> str:
    """The decorator's attribute name: @mcp.tool() -> 'tool', @mcp.resource(...) -> 'resource'."""
    target = d.func if isinstance(d, ast.Call) else d
    return target.attr if isinstance(target, ast.Attribute) else ""


def _entries_in_file(path: pathlib.Path) -> list[tuple[str, str, str]]:
    """(name, kind, one-line) for every mcp.tool/resource/prompt-decorated def in a module file."""
    out: list[tuple[str, str, str]] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except Exception:
        return out
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        kinds = [k for k in (_deco_name(d) for d in node.decorator_list) if k in ("tool", "resource", "prompt")]
        if not kinds:
            continue
        doc = ast.get_docstring(node) or ""
        first = " ".join(doc.strip().split())[:150] if doc else ""
        out.append((node.name, kinds[0], first))
    return out


def catalogue_data() -> dict:
    """Structured catalogue — the same by-domain index `catalogue_md()` renders, but as data so a UI can
    lay it out richly (domain cards, per-domain tables) instead of parsing Markdown. Single source: the
    live `_tools_*.py` modules, AST-parsed at call time. Shape:
        {total, ndomains, domains:[{key, label, items:[{name, desc}]}], extras:[{name, kind, desc}]}.
    """
    base = pathlib.Path(__file__).parent
    by_domain: dict[str, list[tuple[str, str]]] = {}
    extras: list[dict] = []
    for f in sorted(base.glob("_tools_*.py")):
        domain = f.stem.replace("_tools_", "")
        for name, kind, first in _entries_in_file(f):
            if kind == "tool":
                by_domain.setdefault(domain, []).append((name, first))
            else:
                extras.append({"name": name, "kind": kind, "desc": first})
    ordered = _ORDER + [d for d in sorted(by_domain) if d not in _ORDER]
    domains = []
    for d in ordered:
        items = by_domain.get(d) or []
        if not items:
            continue
        domains.append({"key": d, "label": _DOMAIN_LABELS.get(d, d),
                        "items": [{"name": n, "desc": desc} for n, desc in sorted(items)]})
    total = sum(len(x["items"]) for x in domains)
    return {"total": total, "ndomains": len(domains), "domains": domains,
            "extras": sorted(extras, key=lambda e: e["name"])}


def catalogue_md() -> str:
    base = pathlib.Path(__file__).parent
    by_domain: dict[str, list[tuple[str, str, str]]] = {}
    extras: list[tuple[str, str, str]] = []          # resources + prompts (not domain tools)
    for f in sorted(base.glob("_tools_*.py")):
        domain = f.stem.replace("_tools_", "")
        for name, kind, first in _entries_in_file(f):
            if kind == "tool":
                by_domain.setdefault(domain, []).append((name, kind, first))
            else:
                extras.append((name, kind, first))
    total = sum(len(v) for v in by_domain.values())
    ndomains = sum(1 for v in by_domain.values() if v)
    lines = [
        "# Sonaloop — tool catalogue (by domain)",
        "",
        f"_{total} tools across {ndomains} domains — auto-generated from the live modules._",
        "",
        "Start with the **`sonaloop://guide/research`** resource for the canonical path "
        "(cloud: begin_research_job when exposed; core fallback: personas → start_project → "
        "start_run → loop run_step with dispatch_token → finish). This is the full browsable "
        "index; every tool's response also carries a `next_recommended_tool` hint.",
        "",
    ]
    ordered = _ORDER + [d for d in sorted(by_domain) if d not in _ORDER]
    for d in ordered:
        items = by_domain.get(d) or []
        if not items:
            continue
        lines.append(f"## {_DOMAIN_LABELS.get(d, d)}  ({len(items)})")
        for name, _kind, first in sorted(items):
            lines.append(f"- **{name}** — {first or '—'}")
        lines.append("")
    if extras:
        lines.append("## Resources & prompts")
        for name, kind, first in sorted(extras):
            lines.append(f"- **{name}** ({kind}) — {first or '—'}")
        lines.append("")
    return "\n".join(lines)
