"""Usability sessions IN the project outline (tracker: project-page-sessions-live-under-their-
subject-in-the-outlin). The outline is the page: each session renders as an indented child row under
its SUBJECT row (the note→prototype tree mechanics), never as an appended flat section. The page
route GROUPS (outline_session_groups — it holds the Store); _outline_html stays pure rendering and
folds the prepared groups in via merge_session_items. Split out of _graph_outline.py (the LOC bar,
tests/test_loc_budget.py)."""
from __future__ import annotations

from urllib.parse import quote

from .. import services
from ._i18n import t
from ._primitive_taxonomy import primitive_color


def outline_session_groups(sessions: list[dict], store, prototype_sessions: list[dict] | None = None) -> dict[str, dict]:
    """Group a project's recorded usability sessions by subject key — the route-side seam. Each
    group: the subject, its sessions chronological (each enriched with a persona card for the
    child row's avatar chip), and at ≥2 walks the cross-session funnel (services.get_session_funnel)
    that powers the parent row's aggregate chip."""
    groups: dict[str, dict] = {}
    for s in sorted(sessions, key=lambda x: x.get("created_at", "")):
        subj = s.get("subject") or {}
        key = str(subj.get("id") or subj.get("url") or "")
        if not key:
            continue
        g = groups.setdefault(key, {"subject": subj, "sessions": []})
        p = store.get_persona(s.get("persona_id", "")) or {}
        sess = dict(s)
        sess["persona"] = {"id": p.get("id") or s.get("persona_id", "x"),
                           "display_name": p.get("display_name") or s.get("persona_id", "—"),
                           "avatar": p.get("avatar")}
        g["sessions"].append(sess)
    for s in sorted(prototype_sessions or [], key=lambda x: x.get("created_at", "")):
        proto = store.get_prototype(s.get("prototype_id", "")) or {}
        if not proto:
            continue
        key = proto["id"]
        subj = {"kind": "prototype", "id": proto["id"], "label": proto.get("name") or proto["id"]}
        g = groups.setdefault(key, {"subject": subj, "sessions": []})
        p = store.get_persona(s.get("persona_id", "")) or {}
        reaction = s.get("reaction") or {}
        steps = list(reaction.get("steps") or [])
        if not steps and reaction.get("friction"):
            steps = [{"friction": {"level": "hesitation", "note": str(reaction["friction"][0])}}]
        sess = dict(s)
        sess["subject"] = subj
        sess["outcome"] = {"completed": True, "summary": reaction.get("summary", "")}
        sess["steps"] = steps
        sess["persona"] = {"id": p.get("id") or s.get("persona_id", "x"),
                           "display_name": p.get("display_name") or s.get("persona_id", "—"),
                           "avatar": p.get("avatar")}
        g["sessions"].append(sess)
    for key, g in groups.items():
        if len(g["sessions"]) >= 2:
            g["funnel"] = services.get_session_funnel(g["subject"].get("kind", ""), key, store=store)
    return groups


def _funnel_chip(group: dict, key: str) -> dict | None:
    """The compact aggregate chip for the parent row (Linear's progress-chip affordance): session
    count + the drop-off read, linking to the filtered /sessions list. None below 2 sessions."""
    f = group.get("funnel")
    if not f:
        return None
    drops = [(r["step"], r["dropped"]) for r in f["rows"] if r["dropped"]]
    if not drops:
        tail = t("no_dropoffs")
    elif len(drops) == 1:
        tail = t("drop_at_step", n=drops[0][1], s=drops[0][0])
    else:
        tail = t("dropoffs_n", n=sum(d for _, d in drops))
    href = (f'/sessions?subject_kind={quote(group["subject"].get("kind", ""))}'
            f'&subject={quote(key)}')
    return {"text": f'{t("sessions_n", n=f["sessions"])} · {tail}', "href": href}


def _subject_slot(group: dict, key: str, pk, pmeta: dict) -> dict:
    """The ordering slot for sessions whose subject is not an existing prototype row.
    The slot is not itself rendered as a row; it only lets the session sit where the
    tested thing belongs without inventing another visible primitive."""
    subj, sessions = group["subject"], group["sessions"]
    ts = sessions[0].get("created_at", "")
    po, plabel = pmeta.get(pk, (99, ""))
    it = {"oid": f"subject:{key}", "color": primitive_color("session"), "title": subj.get("label") or key,
          "kind": t("sessions"), "href": "", "plabel": plabel, "po": po, "round": 0,
          "order": ts, "ts": ts, "indent": -1, "last_child": False, "pk": pk or "",
          "rkind": subj.get("kind", "")}
    it["plabel"] = it["plabel"] or it["kind"]      # plan-less: the kind stands in for the phase column
    return it


def _session_child_item(sess: dict, parent: dict, seq: int, last: bool) -> dict:
    """One session row.

    Prototype subjects keep sessions as indented executions under the prototype row. Non-prototype
    subjects use an invisible ordering slot and render as top-level SESSION rows. In both cases
    the kind column stays type-only: icon + SESSION, never a persona avatar."""
    kind = t("session_kind")
    under_visible_subject = parent.get("indent", 0) >= 0
    title = sess["persona"]["display_name"] if under_visible_subject else parent["title"]
    item = {"oid": sess["id"], "color": primitive_color("session"), "title": title,
            "kind": kind, "href": f'/sessions/{sess["id"]}', "plabel": parent["plabel"],
            "po": parent["po"], "round": parent["round"], "order": f'{parent["order"]}#s{seq:03d}',
            "ts": sess.get("created_at", ""), "indent": parent["indent"] + 1, "last_child": last,
            "rkind": "session", "session": sess, "pk": parent.get("pk", "")}
    return item


def merge_session_items(items: list[dict], groups: dict[str, dict], ideation, pmeta: dict,
                        proto_of: dict[str, str]) -> None:
    """Fold the session groups into the outline items IN PLACE. A prototype subject's
    sessions nest under the existing prototype row. Other subjects render directly as
    session rows so they do not create new visible artifact categories."""
    for key, grp in groups.items():
        oid = proto_of.get(key, "")
        parent = next((it for it in items if oid and it["oid"] == oid), None)
        if parent is None:
            parent = _subject_slot(grp, key, ideation, pmeta)
        chip = _funnel_chip(grp, key)
        if chip:
            parent["chip"] = chip
        n = len(grp["sessions"])
        for j, s in enumerate(grp["sessions"]):
            items.append(_session_child_item(s, parent, j, j == n - 1))
