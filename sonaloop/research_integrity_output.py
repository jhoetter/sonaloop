"""Presentation helpers for research-integrity records."""
from __future__ import annotations

from typing import Any


def claim_posture_markdown(envelope: dict[str, Any] | None, *, de: bool = False) -> list[str]:
    """Return the self-contained claim-provenance block used by council/report exports."""
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
