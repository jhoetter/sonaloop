"""Speaker-note writer shared by default and uploaded-master PPTX exports."""
from __future__ import annotations

from typing import Any


def apply_speaker_notes(slide, spec: dict[str, Any]) -> bool:
    """Write structured presenter notes into the native notes body placeholder."""
    notes = dict(spec.get("speaker_notes") or {})
    if not notes:
        return False
    frame = slide.notes_slide.notes_text_frame
    frame.clear()
    sections: list[tuple[str, list[str]]] = []
    if notes.get("takeaway"):
        sections.append(("TAKEAWAY", [str(notes["takeaway"])]))
    if notes.get("talk_track"):
        timing = int(notes.get("timing_seconds") or 0)
        label = f"TALK TRACK · {timing} SEC" if timing else "TALK TRACK"
        sections.append((label, [str(notes["talk_track"])]))
    for key, label in (("evidence", "EVIDENCE"), ("caveats", "CAVEATS"),
                       ("backup", "BACKUP")):
        values = [str(value) for value in (notes.get(key) or []) if str(value).strip()]
        if values:
            sections.append((label, values))
    if notes.get("transition"):
        sections.append(("TRANSITION", [str(notes["transition"])]))
    first = True
    for label, values in sections:
        paragraph = frame.paragraphs[0] if first else frame.add_paragraph()
        first = False
        paragraph.text = label
        paragraph.level = 0
        for value in values:
            row = frame.add_paragraph()
            row.text = value
            row.level = 1
    return bool(sections)
