"""Surveys — the outbound instrument: author → send out → collect real responses back.

The first artifact that COLLECTS data instead of presenting it. House triplet: brief_survey GATHERS
the project's open questions, contested council findings and the stance vocabulary; the host authors
the questions; record_survey VALIDATES + persists — no server-side text. export_survey renders a
self-contained static HTML form (the spa-min template; works from file://) whose submissions are
JSON payloads shaped exactly like SurveyResponse rows; import_survey_responses ingests them
(JSON list and/or CSV), survey_results aggregates per question — for stance_mapped questions with the
predicted-vs-actual strip (persona stance distribution from the derived_from councils vs the real
answer distribution) — and attach_survey_evidence loops real responses back onto a persona as
Evidence (source_type='survey') for calibration. Hosted collection endpoints are sonaloop-cloud's
job; core stays serverless.
Cross-module function references are bound at import time by services/__init__.py."""

from __future__ import annotations

import csv
import io
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .. import artifacts as _A
from .. import primitive_taxonomy_registry as _taxonomy_registry
from ..config import content_language, prototype_templates_dir, utc_now_iso
from ..models import Survey, SurveyResponse
from ..storage import Store
from ..suggestions import suggest_stances
from ._common import _require_research_project, slugify, stable_id, write_export


_QUESTION_KINDS = ("single", "multi", "scale", "text")
_SURVEY_STATUSES = ("draft", "open", "closed")


def survey_form(survey: dict[str, Any]) -> str:
    """Classify a survey through the primitive form registry.

    A multi-question survey exposes its dominant question kind for filtering and
    explanation. It does not become a separate `mixed` form; if no question kind
    is available, there is no form facet to show.
    """
    questions = survey.get("questions") or []
    kinds = Counter(q.get("kind") for q in questions if isinstance(q, dict) and q.get("kind"))
    if not kinds:
        return ""
    kind = str(kinds.most_common(1)[0][0])
    alias = {"single": "single_survey", "multi": "multi_survey",
             "scale": "scale_survey", "text": "text_survey",
             "ranking": "ranking_survey"}.get(kind, kind)
    form = _taxonomy_registry.resolve_form("survey", alias)
    return str((form or {}).get("id") or alias)


def survey_form_definition(survey: dict[str, Any]) -> dict[str, Any] | None:
    form_id = survey_form(survey)
    if not form_id:
        return None
    form = _taxonomy_registry.resolve_form("survey", form_id)
    if form is None:
        raise KeyError(f"No registered survey form '{form_id}'")
    return form


def _require_survey(store: Store, survey_id: str) -> dict[str, Any]:
    s = store.get_survey(survey_id)
    if not s:
        raise KeyError(f"Unknown survey: {survey_id}")
    return s


# --------------------------------------------------------------------------- validation

def _validate_question(raw: Any, i: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"questions[{i}] must be a dict {{id?, text, kind, options, stance_mapped?}}")
    text = str(raw.get("text") or "").strip()
    if not text:
        raise ValueError(f"questions[{i}].text is required (what the respondent is asked)")
    kind = raw.get("kind")
    if kind not in _QUESTION_KINDS:
        raise ValueError(f"questions[{i}].kind must be one of {'|'.join(_QUESTION_KINDS)}, got {kind!r}")
    options = [str(o).strip() for o in (raw.get("options") or []) if str(o).strip()]
    stance_mapped = bool(raw.get("stance_mapped"))
    if kind == "text":
        if options:
            raise ValueError(f"questions[{i}] is a text question — it takes no options")
        if stance_mapped:
            raise ValueError(f"questions[{i}]: stance_mapped is only valid on a scale question")
    else:
        if len(options) < 2:
            raise ValueError(f"questions[{i}] ({kind}) needs >= 2 non-empty options")
        if len(set(options)) != len(options):
            raise ValueError(f"questions[{i}] has duplicate options")
    if stance_mapped:
        if kind != "scale":
            raise ValueError(f"questions[{i}]: stance_mapped is only valid on a scale question")
        seen: dict[int, str] = {}
        for opt in options:
            st = _A.resolve_stance(opt)
            # "maps cleanly" = the option alias-resolves onto a canonical term, with NO raw fallback
            # (a label_raw/value_raw survivor means the scale silently bucketed an off-scale token).
            if st is None or "label_raw" in st or "value_raw" in st:
                raise ValueError(
                    f"questions[{i}] is stance_mapped but option {opt!r} does not map onto the "
                    "canonical stance scale — suggest_stances() names the valid terms + aliases")
            if st["value"] in seen:
                raise ValueError(
                    f"questions[{i}]: options {seen[st['value']]!r} and {opt!r} both map onto stance "
                    f"value {st['value']} — a stance_mapped scale must be unambiguous")
            seen[st["value"]] = opt
    return {"id": str(raw.get("id") or f"q{i + 1}"), "text": text, "kind": kind,
            "options": options, "stance_mapped": stance_mapped}


def _validate_derived_from(refs: Any, project_id: str, store: Store) -> list[dict[str, Any]]:
    """Every derived_from Ref must RESOLVE — a survey may only claim to operationalize findings /
    open questions / councils that exist. open_question refs resolve against the project's own
    question pool (and cache the text as the `quote` display hint); everything else resolves live
    via artifacts.resolve_ref (which also validates part anchors, e.g. a synthesis finding id)."""
    out: list[dict[str, Any]] = []
    for i, raw in enumerate(refs or []):
        if not isinstance(raw, dict):
            raise ValueError(f"derived_from[{i}] must be a Ref dict {{kind, id, anchor?, role?}}")
        r = _A.validate_ref(raw)
        r.setdefault("role", "derived_from")
        kind, rid = r.get("kind"), r.get("id")
        if not rid:
            raise ValueError(f"derived_from[{i}] needs an id (the artifact it operationalizes)")
        if kind == "open_question":
            oq = next((o for o in store.list_open_questions(project_id) if o.get("id") == rid), None)
            if not oq:
                raise ValueError(f"derived_from[{i}] points at an unknown open question of this "
                                 f"project: {rid}")
            if not r.get("quote"):
                r["quote"] = oq.get("text", "")
        else:
            res = _A.resolve_ref(r, store)
            if not res.get("exists"):
                anchor = f"#{r['anchor']}" if r.get("anchor") else ""
                raise ValueError(f"derived_from[{i}] does not resolve: {kind}:{rid}{anchor}")
        out.append(r)
    return out


# --------------------------------------------------------------------------- brief → record

def contested_findings(project_id: str, store: Store) -> list[dict[str, Any]]:
    """The project's CONTESTED findings: councils whose statements span both positive and negative
    stances — exactly where a real-world answer is worth the postage. The shared context-pack
    gatherer behind brief_survey and brief_hypothesis."""
    contested: list[dict[str, Any]] = []
    for c in store.list_council_sessions():
        if c.get("project_id") != project_id:
            continue
        stances = [s.get("stance") for s in (c.get("statements") or []) if s.get("stance")]
        values = [st.get("value") for st in stances if st.get("value") is not None]
        if values and min(values) < 0 < max(values):       # genuinely mixed: support AND opposition
            contested.append({
                "council_id": c["id"], "prompt": c.get("prompt", ""),
                "stance_tally": _A.vote_tally(stances),
                "statements": [{"id": s.get("id"), "persona_id": s.get("persona_id"),
                                "stance": s.get("stance"), "text": (s.get("text") or "")[:240]}
                               for s in c.get("statements") or [] if s.get("stance")],
            })
    return contested


def brief_survey(project_id: str, store: Store | None = None) -> dict[str, Any]:
    """GATHER everything needed to author a survey that is actually answerable against the graph:
    the project's OPEN questions, its CONTESTED findings (councils whose statements span both
    positive and negative stances — exactly where a real-world answer is worth the postage), and
    the canonical stance vocabulary (so stance_mapped scale options map cleanly). The host authors
    the questions; record_survey validates + persists."""
    store = store or Store()
    project = _require_research_project(store, project_id)
    open_qs = [o for o in store.list_open_questions(project["id"]) if o.get("status") == "open"]
    return {
        "schema": "survey", "project_id": project["id"], "goal": project.get("goal", ""),
        "open_questions": open_qs,
        "contested_findings": contested_findings(project["id"], store),
        "stance_scale": suggest_stances(),
        "instructions": (
            "Author the survey YOURSELF — the server never writes text. Operationalize the open "
            "questions and contested findings above into questions a real human can answer: each is "
            "{id?, text, kind: single|multi|scale|text, options (>= 2 for non-text), stance_mapped "
            "(scale only)}. A stance_mapped scale's options must map 1:1 onto the canonical stance "
            "scale (terms/aliases above) so real answers are directly comparable to the personas' "
            "predicted stances. Cite what each question operationalizes via derived_from refs "
            "({kind: open_question|council|synthesis, id, anchor?, role: 'derived_from'}) — "
            "record_survey REJECTS unresolvable refs and unmappable stance_mapped options. "
            "Keep the intro short and neutral; do not steer respondents toward a product thesis."),
    }


def record_survey(project_id: str, title: str, questions: list, intro: str = "",
                  derived_from: list | None = None, status: str = "draft",
                  slug: str | None = None, key: str | None = None,
                  store: Store | None = None) -> dict[str, Any]:
    """Persist a host-authored survey. Validates: every question's shape (kind vocabulary, >= 2
    unique options for non-text kinds, unique question ids), stance_mapped scale options map CLEANLY
    onto suggestions/stance_scale.json (alias-resolved, unambiguous, no silent bucketing), and every
    derived_from Ref resolves (open questions of this project; councils/syntheses live via
    resolve_ref, anchors included). Re-recording the same slug updates the instrument in place; pass
    a stable `key` for a deterministic id (idempotent upsert → resumable runs)."""
    store = store or Store()
    project = _require_research_project(store, project_id)
    title = str(title or "").strip()
    if not title:
        raise ValueError("title is required")
    if status not in _SURVEY_STATUSES:
        raise ValueError(f"status must be one of {'|'.join(_SURVEY_STATUSES)}, got {status!r}")
    if not isinstance(questions, list) or not questions:
        raise ValueError("questions must be a non-empty list — a survey with nothing to ask collects nothing")
    norm_q = [_validate_question(q, i) for i, q in enumerate(questions)]
    qids = [q["id"] for q in norm_q]
    if len(set(qids)) != len(qids):
        raise ValueError(f"question ids must be unique, got {qids}")
    norm_refs = _validate_derived_from(derived_from, project["id"], store)
    now = utc_now_iso()
    sslug = slugify(slug or title)
    existing = store.get_survey(sslug)
    sid = (existing or {}).get("id") or (stable_id("survey", key) if key
                                         else stable_id("survey", sslug, now))
    rec = Survey(id=sid, slug=sslug, project_id=project["id"], title=title,
                 intro=str(intro or ""), status=status, questions=norm_q, derived_from=norm_refs,
                 created_at=(existing or {}).get("created_at", now), updated_at=now).to_dict()
    store.upsert_survey(rec)
    from ..telemetry import capture_product_event
    capture_product_event(
        "survey_recorded",
        project_id=project["id"],
        subject_kind="survey",
        subject_id=rec["id"],
        properties={
            "question_count": len(norm_q),
            "survey_status": status,
            "created": existing is None,
        },
        idempotency_key=f"{rec['id']}:{rec['updated_at']}",
    )
    return {"survey": rec}


def get_survey(survey_id_or_slug: str, store: Store | None = None) -> dict[str, Any]:
    """One survey by id or slug, with its live response_count (the responses themselves stay in
    their own table — read them via survey_results / the store)."""
    store = store or Store()
    s = _require_survey(store, survey_id_or_slug)
    return {**s, "response_count": store.count_survey_responses(s["id"])}


def survey_respondent_personas(survey_id: str, store: Store | None = None) -> list[str]:
    """The persona-sourced respondents of a survey (ux-contract §10 W11): the distinct
    `persona:<id>` respondent keys of its imported responses, first-seen order. Anonymous
    keys (street-panel `r_…`) carry no persona participation and are skipped — they have
    no avatar to attribute."""
    store = store or Store()
    pids: list[str] = []
    for r in store.list_survey_responses(survey_id):
        key = str(r.get("respondent_key") or "")
        if key.startswith("persona:"):
            pid = key.split(":", 1)[1]
            if pid and pid not in pids:
                pids.append(pid)
    return pids


def list_surveys(project_id: str | None = None, store: Store | None = None) -> list[dict[str, Any]]:
    """List surveys (optionally per project), each with its live response_count + the
    persona-sourced respondents' crew (`personas`/`voices`, the council-node shape) so the
    row surfaces can render the avatar group (ux-contract §10 W11)."""
    store = store or Store()
    from ._research import _persona_stubs
    out = []
    for s in store.list_surveys(project_id):
        pids = survey_respondent_personas(s["id"], store=store)
        out.append({**s, "response_count": store.count_survey_responses(s["id"]),
                    "voices": len(pids), "personas": _persona_stubs(store, pids)})
    return out


# --------------------------------------------------------------------------- export (sendable form)

# Survey form runtime, appended to the spa-min template (which renders header/intro from the
# concept JSON; with no screens its generic script draws nothing — this script owns the body).
# Self-contained: no network needed; works from file://. Submissions build a JSON payload shaped
# EXACTLY like a SurveyResponse row and either POST it (a baked post_url, overridable via ?post=)
# or download it as a file the respondent sends back. Hosted endpoints are sonaloop-cloud's job.
_FORM_RUNTIME = r"""<style>
  fieldset.q{border:1px solid var(--line);border-radius:9px;background:var(--panel);margin:0 0 16px;padding:14px 16px}
  fieldset.q legend{font-weight:600;padding:0 6px}
  fieldset.q label.opt{display:block;margin:6px 0;cursor:pointer}
  fieldset.q textarea{font:inherit;width:100%;border:1px solid var(--line);border-radius:7px;padding:8px 10px}
  #send{font:inherit;border:0;background:var(--accent);color:#fff;border-radius:8px;padding:10px 18px;cursor:pointer}
  #send[disabled]{opacity:.55;cursor:default}
  #status{color:var(--muted);font-size:13px;margin-top:10px}
</style>
<script>
(function(){
  var C = JSON.parse(document.getElementById('concept').textContent);
  var S = C.survey || {}, L = C.labels || {};
  var POST = new URLSearchParams(location.search).get('post') || C.post_url || '';
  var form = document.createElement('form'); form.id = 'survey'; form.noValidate = true;
  (S.questions || []).forEach(function(q, qi){
    var fs = document.createElement('fieldset'); fs.className = 'q'; fs.dataset.id = q.id; fs.dataset.kind = q.kind;
    var lg = document.createElement('legend'); lg.textContent = (qi + 1) + '. ' + q.text; fs.appendChild(lg);
    if (q.kind === 'text') {
      var ta = document.createElement('textarea'); ta.name = q.id; ta.rows = 3; fs.appendChild(ta);
    } else {
      (q.options || []).forEach(function(opt){
        var lab = document.createElement('label'); lab.className = 'opt';
        var inp = document.createElement('input');
        inp.type = (q.kind === 'multi') ? 'checkbox' : 'radio';
        inp.name = q.id; inp.value = opt;
        lab.appendChild(inp); lab.appendChild(document.createTextNode(' ' + opt));
        fs.appendChild(lab);
      });
    }
    form.appendChild(fs);
  });
  var btn = document.createElement('button'); btn.type = 'submit'; btn.id = 'send';
  btn.textContent = L.submit || 'Submit'; form.appendChild(btn);
  var status = document.createElement('p'); status.id = 'status'; form.appendChild(status);
  document.getElementById('screens').appendChild(form);
  function rand(){
    var a = new Uint8Array(8);
    if (window.crypto && window.crypto.getRandomValues) { window.crypto.getRandomValues(a); }
    else { for (var i = 0; i < a.length; i++) a[i] = Math.floor(Math.random() * 256); }
    return Array.prototype.map.call(a, function(b){ return ('0' + b.toString(16)).slice(-2); }).join('');
  }
  function payload(){
    var answers = [];
    (S.questions || []).forEach(function(q){
      if (q.kind === 'multi') {
        var vals = [].slice.call(form.querySelectorAll('input[name="' + q.id + '"]:checked'))
          .map(function(i){ return i.value; });
        if (vals.length) answers.push({question_id: q.id, value: vals});
      } else if (q.kind === 'text') {
        var v = ((form.elements[q.id] || {}).value || '').trim();
        if (v) answers.push({question_id: q.id, value: v});
      } else {
        var c = form.querySelector('input[name="' + q.id + '"]:checked');
        if (c) answers.push({question_id: q.id, value: c.value});
      }
    });
    return {id: 'sresp_' + rand(), survey_id: S.id, respondent_key: 'r_' + rand(),
            submitted_at: new Date().toISOString(), answers: answers, source: 'html_form'};
  }
  function download(p){
    var blob = new Blob([JSON.stringify(p, null, 2)], {type: 'application/json'});
    var a = document.createElement('a'); a.href = URL.createObjectURL(blob);
    a.download = 'survey-response-' + p.id + '.json';
    document.body.appendChild(a); a.click(); a.remove();
  }
  form.addEventListener('submit', function(e){
    e.preventDefault();
    var p = payload();
    if (!p.answers.length) { status.textContent = L.empty || 'Please answer at least one question.'; return; }
    if (POST) {
      fetch(POST, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(p)})
        .then(function(r){
          if (!r.ok) throw new Error(r.status);
          status.textContent = L.sent || 'Thank you — your response was sent.'; btn.disabled = true;
        })
        .catch(function(){
          download(p);
          status.textContent = L.saved || 'Could not send — your response was downloaded instead; please return the file.';
        });
    } else {
      download(p);
      status.textContent = L.saved || 'Thank you — your response was downloaded; please return the file.';
      btn.disabled = true;
    }
  });
})();
</script>"""

# Form chrome in the survey's CONTENT language (the questions/intro are host-authored; these four
# strings are static form chrome, not generated content). Data here, not scattered literals.
_FORM_LABELS = {
    "de": {"submit": "Absenden", "empty": "Bitte beantworte mindestens eine Frage.",
           "sent": "Danke — deine Antwort wurde gesendet.",
           "saved": "Danke — deine Antwort wurde als Datei gespeichert; bitte sende sie zurück."},
    "en": {"submit": "Submit", "empty": "Please answer at least one question.",
           "sent": "Thank you — your response was sent.",
           "saved": "Thank you — your response was downloaded; please return the file."},
}


def export_survey(survey_id: str, post_url: str | None = None, out: str | None = None,
                  store: Store | None = None) -> dict[str, Any]:
    """Render the survey as a SENDABLE, self-contained static HTML form built from the spa-min
    template — host it anywhere or mail the file; it works from file:// with zero dependencies.
    Submissions produce a JSON payload shaped exactly like a SurveyResponse row: with a `post_url`
    (baked here, or overridden at fill-time via `?post=`) the form POSTs it; otherwise (or on POST
    failure) it downloads the payload for the respondent to send back. Either path round-trips
    through import_survey_responses — live collection endpoints stay out of core (sonaloop-cloud).
    Exporting a draft survey flips its status to `open` (it is out in the world now)."""
    store = store or Store()
    survey = _require_survey(store, survey_id)
    tpl = (prototype_templates_dir() / "spa-min" / "index.html").read_text(encoding="utf-8")
    labels = _FORM_LABELS.get(content_language(), _FORM_LABELS["en"])
    concept = {
        "title": survey["title"], "summary": survey.get("intro", ""), "screens": [],
        "survey": {"id": survey["id"], "slug": survey["slug"], "title": survey["title"],
                   "intro": survey.get("intro", ""), "questions": survey["questions"]},
        "post_url": post_url or "", "labels": labels,
    }
    from ..prototypes import _esc
    # One-pass fill: sequential .replace() would re-scan already-substituted text, so a sentinel
    # appearing INSIDE a value (a title literally named __CONCEPT_JSON__) could splice the concept
    # JSON into an HTML text context.
    fills = {"__TITLE__": _esc(survey["title"]),
             "__SUMMARY__": _esc(survey.get("intro", "")),
             "__CONCEPT_JSON__": json.dumps(concept, ensure_ascii=False).replace("</", "<\\/")}
    html = re.sub(r"__(?:TITLE|SUMMARY|CONCEPT_JSON)__", lambda m: fills[m.group(0)], tpl)
    html = html.replace("</body>", _FORM_RUNTIME + "\n</body>")
    from ..config import partition_dir
    data_root = partition_dir().resolve()
    target = Path(out) if out else partition_dir() / "exports" / "surveys" / f"{survey['slug']}.html"
    if not target.is_absolute():
        target = partition_dir() / target
    if not target.resolve().is_relative_to(data_root):
        raise ValueError(f"export path escapes the data dir ({data_root}): {out!r}")
    path = write_export(html, target)
    if survey.get("status") == "draft":
        survey["status"] = "open"
        survey["updated_at"] = utc_now_iso()
        store.upsert_survey(survey)
    return {"survey_id": survey["id"], "slug": survey["slug"], "path": path,
            "post_url": post_url or "", "status": survey["status"]}


# --------------------------------------------------------------------------- import (responses back)

def _rows_from_csv(text: str, survey: dict[str, Any]) -> list[dict[str, Any]]:
    """CSV batch → response rows. Columns: optional respondent_key / submitted_at / source, plus one
    column per question id; multi-select cells separate options with ';'."""
    qids = {q["id"] for q in survey["questions"]}
    multi = {q["id"] for q in survey["questions"] if q["kind"] == "multi"}
    rows: list[dict[str, Any]] = []
    for rec in csv.DictReader(io.StringIO(text)):
        answers = []
        for k, v in rec.items():
            if k is None:  # DictReader parks overflow fields of a ragged row under None
                raise ValueError(f"CSV row has more fields than the header declares: {v!r}")
            if k in ("respondent_key", "submitted_at", "source") or v is None:
                continue
            v = v.strip()
            if not v:
                continue
            if k not in qids:
                raise ValueError(f"CSV column {k!r} is not a question id of this survey "
                                 f"(questions: {sorted(qids)})")
            answers.append({"question_id": k,
                            "value": ([p.strip() for p in v.split(";") if p.strip()]
                                      if k in multi else v)})
        rows.append({"respondent_key": (rec.get("respondent_key") or "").strip(),
                     "submitted_at": (rec.get("submitted_at") or "").strip(),
                     "source": (rec.get("source") or "").strip(), "answers": answers})
    return rows


def _validate_response(raw: Any, i: int, survey: dict[str, Any], source: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"responses[{i}] must be a dict {{respondent_key?, submitted_at?, answers}}")
    questions = {q["id"]: q for q in survey["questions"]}
    answers_in = raw.get("answers")
    if not isinstance(answers_in, list) or not answers_in:
        raise ValueError(f"responses[{i}].answers must be a non-empty list of {{question_id, value}}")
    answers: list[dict[str, Any]] = []
    for j, a in enumerate(answers_in):
        if not isinstance(a, dict) or not a.get("question_id"):
            raise ValueError(f"responses[{i}].answers[{j}] must be {{question_id, value}}")
        q = questions.get(a["question_id"])
        if not q:
            raise ValueError(f"responses[{i}].answers[{j}] references an unknown question: "
                             f"{a['question_id']!r} (questions: {sorted(questions)})")
        v = a.get("value")
        if q["kind"] == "multi":
            vals = [str(x).strip() for x in (v if isinstance(v, list) else [v])
                    if str(x or "").strip()]
            bad = [x for x in vals if x not in q["options"]]
            if not vals or bad:
                raise ValueError(f"responses[{i}].answers[{j}]: {bad or 'empty'} not in the options "
                                 f"of {q['id']} ({q['options']})")
            v = vals
        elif q["kind"] == "text":
            v = str(v or "").strip()
            if not v:
                raise ValueError(f"responses[{i}].answers[{j}]: empty text answer for {q['id']}")
        else:                                                  # single | scale: one of the options
            v = str(v or "").strip()
            if v not in q["options"]:
                raise ValueError(f"responses[{i}].answers[{j}]: {v!r} is not an option of "
                                 f"{q['id']} ({q['options']})")
        answers.append({"question_id": q["id"], "value": v})
    # Ids must derive only from what the BATCH carries — folding in a generated timestamp would
    # mint fresh ids on every import and double-count the same rows (idempotency is the contract).
    # Without respondent_key AND submitted_at, identical anonymous answer-sets collapse to one row.
    submitted_raw = str(raw.get("submitted_at") or "").strip()
    rkey = str(raw.get("respondent_key") or "").strip() \
        or stable_id("anon", survey["id"], json.dumps(answers, sort_keys=True), submitted_raw)
    rid = str(raw.get("id") or "") or stable_id("sresp", survey["id"], rkey, submitted_raw)
    submitted = submitted_raw or utc_now_iso()
    return SurveyResponse(id=rid, survey_id=survey["id"], respondent_key=rkey,
                          submitted_at=submitted, answers=answers,
                          source=str(raw.get("source") or "").strip() or source,
                          created_at=utc_now_iso()).to_dict()


def import_survey_responses(survey_id: str, responses: list | None = None,
                            csv_text: str | None = None, source: str = "import",
                            store: Store | None = None) -> dict[str, Any]:
    """Ingest a batch of REAL responses — a JSON list (the export form's payload shape: each row
    {respondent_key?, submitted_at?, answers: [{question_id, value}], source?, id?}) and/or a CSV
    (one column per question id; ';' separates multi-select options). Every answer is validated
    against the instrument (known question id, value within the options / non-empty text). Ids are
    deterministic from what the batch itself carries — (survey, respondent_key, submitted_at), with
    anonymous rows content-addressed by their answers — so re-importing the same batch is idempotent;
    rows with neither respondent_key nor submitted_at collapse when their answers are identical.
    `source` labels the batch on rows that don't carry their own."""
    store = store or Store()
    survey = _require_survey(store, survey_id)
    rows = list(responses or [])
    if csv_text:
        rows += _rows_from_csv(csv_text, survey)
    if not rows:
        raise ValueError("nothing to import — pass `responses` (a JSON list) and/or `csv_text`")
    recs = [_validate_response(raw, i, survey, source) for i, raw in enumerate(rows)]
    for rec in recs:                                   # validate the WHOLE batch before any write
        store.insert_survey_response(rec)
    total = store.count_survey_responses(survey["id"])
    from ..telemetry import capture_product_event
    capture_product_event(
        "survey_responses_imported",
        project_id=survey["project_id"],
        subject_kind="survey",
        subject_id=survey["id"],
        properties={
            "batch_kind": "mixed" if csv_text and responses else ("csv" if csv_text else "json"),
            "imported_count": len(recs),
            "total_response_count": total,
        },
    )
    return {"survey_id": survey["id"], "imported": len(recs), "total_responses": total}


# --------------------------------------------------------------------------- results (predicted vs actual)

def _predicted_distribution(survey: dict[str, Any], store: Store) -> dict[str, Any]:
    """The personas' PREDICTED stance distribution: every statement stance from the derived_from
    councils (a derived_from synthesis contributes the councils it consolidates), tallied onto the
    canonical scale — with refs into the councils that made the prediction."""
    council_ids: list[str] = []
    for r in survey.get("derived_from") or []:
        if r.get("kind") == "council" and r.get("id"):
            council_ids.append(r["id"])
        elif r.get("kind") == "synthesis" and r.get("id"):
            council_ids.extend((store.get_synthesis(r["id"]) or {}).get("council_ids") or [])
    council_ids = list(dict.fromkeys(council_ids))
    counts = {term["term"]: 0 for term in _A.stance_terms()}
    n = 0
    for cid in council_ids:
        for st in (store.get_council_session(cid) or {}).get("statements") or []:
            stance = st.get("stance") or {}
            if stance.get("value") is None:
                continue
            resolved = _A.resolve_stance(stance["value"])
            if resolved:
                counts[resolved["label"]] += 1
                n += 1
    return {"counts": counts, "n": n,
            "refs": [{"kind": "council", "id": cid, "role": "predicted_by"} for cid in council_ids]}


def survey_results(survey_id: str, store: Store | None = None) -> dict[str, Any]:
    """Aggregate the imported responses per question: option counts (single/scale/multi), collected
    texts (text). For stance_mapped questions, the PREDICTED-VS-ACTUAL strip: the persona stance
    distribution from the derived_from councils' statements next to the real answers' distribution
    (answers resolved onto the same canonical scale), with refs into the predicting councils."""
    store = store or Store()
    survey = _require_survey(store, survey_id)
    responses = store.list_survey_responses(survey["id"])
    by_q: dict[str, list] = {}
    for r in responses:
        for a in r.get("answers") or []:
            by_q.setdefault(a.get("question_id", ""), []).append(a.get("value"))
    predicted = None
    questions = []
    for q in survey["questions"]:
        vals = by_q.get(q["id"], [])
        row: dict[str, Any] = {"question_id": q["id"], "text": q["text"], "kind": q["kind"],
                               "stance_mapped": q.get("stance_mapped", False), "answered": len(vals)}
        if q["kind"] == "text":
            row["answers"] = [str(v) for v in vals][:50]
        else:
            counts = {opt: 0 for opt in q["options"]}
            for v in vals:
                for x in (v if isinstance(v, list) else [v]):
                    counts[str(x)] = counts.get(str(x), 0) + 1
            row["counts"] = counts
        if q.get("stance_mapped"):
            actual = {term["term"]: 0 for term in _A.stance_terms()}
            n = 0
            for v in vals:
                st = _A.resolve_stance(v)
                if st:
                    actual[st["label"]] += 1
                    n += 1
            if predicted is None:
                predicted = _predicted_distribution(survey, store)
            row["comparison"] = {"predicted": predicted, "actual": {"counts": actual, "n": n}}
        questions.append(row)
    return {"survey_id": survey["id"], "title": survey["title"], "status": survey["status"],
            "responses": len(responses),
            "respondents": len({r.get("respondent_key") for r in responses}),
            "questions": questions}


# --------------------------------------------------------------------------- evidence loop-back

def attach_survey_evidence(survey_id: str, persona_id: str, notes: str | None = None,
                           store: Store | None = None) -> dict[str, Any]:
    """Loop the REAL responses back onto a persona as Evidence (source_type='survey') so the next
    brief/revision sees how reality answered where the simulation only predicted. The evidence
    content is a compact JSON of the per-question aggregates (incl. the predicted-vs-actual
    comparison for stance_mapped questions) — calibration data, not raw PII."""
    store = store or Store()
    results = survey_results(survey_id, store=store)
    if not results["responses"]:
        raise ValueError("no responses imported yet — import_survey_responses first; "
                         "there is nothing to attach")
    summary = {"survey_id": results["survey_id"], "title": results["title"],
               "responses": results["responses"], "respondents": results["respondents"],
               "questions": [{k: v for k, v in q.items() if k != "text"} | {"text": q["text"][:200]}
                             for q in results["questions"]]}
    ev = attach_evidence(  # noqa: F821 (bound)
        persona_id, "survey", json.dumps(summary, ensure_ascii=False),
        notes or f"Real survey responses: {results['title']} ({results['responses']} responses)",
        store)
    return {"evidence": ev, "survey_id": results["survey_id"], "responses": results["responses"]}
