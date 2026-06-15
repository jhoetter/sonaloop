"""Documentation hub CONTENT — the bilingual data constants + co-located CSS.

Split out of `_docs.py` purely to keep each module under the LOC bar (the rendering logic and
routes live in `_docs.py`). Pure data: every (de, en) tuple is indexed by `li` (0=de, 1=en) at
render time by the page builders. No rendering happens here.
"""
from __future__ import annotations

from ._html import register_css

# ============================ Page registry ============================ #
# Ordered: drives the tab bar AND prev/next. Shape: (slug, icon, (label_de, label_en)). "" == Overview.
DOC_PAGES = [
    ("",             "compass",    ("Überblick", "Overview")),
    ("concepts",     "squareGrid", ("Konzepte", "Concepts")),
    ("how-it-works", "panel",      ("So funktioniert's", "How it works")),
    ("inspector",    "activity",   ("Live arbeiten", "Working live")),
    ("methodology",  "target",     ("Methodik", "Methodology")),
    ("mcp",          "prototype",  ("MCP-Referenz", "MCP reference")),
]

# ============================ Overview ============================ #
DOCS_INTRO = {
    "de": "Sonaloop ist ein **Research-Workspace** mit synthetischen Kunden-Personas, die ein echtes, "
          "wachsendes Gedächtnis haben. Sie reagieren in **Councils** auf deine Ideen, testen deine "
          "**Prototypen** und verdichten sich zu entscheidungsreifen **Reports**. Du bringst eine Frage "
          "mit — die Arbeit passiert gegen Personas, die sich erinnern, und jede Schlussfolgerung ist auf "
          "Evidenz zurückführbar.",
    "en": "Sonaloop is a **research workspace** built on synthetic customer personas that carry a real, "
          "growing memory. They react to your ideas in **councils**, test your **prototypes**, and roll up "
          "into decision-ready **reports**. You bring a question — the work happens against personas that "
          "remember, and every conclusion traces back to evidence.",
}
# The principles that make the output trustworthy — the user-facing replacement for the agent's
# authoring contract. Shape: (icon, (title_de, title_en), (body_de, body_en)).
PRINCIPLES = [
    ("target",
     ("Memory-geerdet", "Memory-grounded"),
     ("Jede Persona-Reaktion stammt aus angesammelter, gelebter Erfahrung — nichts wird erfunden, und "
      "jede Aussage lässt sich auf eine konkrete Erinnerung zurückführen.",
      "Every persona reaction comes from accumulated, lived experience — nothing is invented, and each "
      "statement traces back to a specific memory.")),
    ("councils",
     ("Nicht-direktiv", "Non-directional"),
     ("Personas werden nie dazu gebracht, deine Idee zu mögen. Skepsis, Gleichgültigkeit und Ablehnung "
      "sind echte, valide Ergebnisse.",
      "Personas are never nudged to like your idea. Skepticism, indifference and rejection are real, "
      "valid outcomes.")),
    ("compass",
     ("Du steuerst, du siehst zu", "You steer, you watch"),
     ("Du treibst die Recherche über deinen KI-Agenten (z. B. im Chat). Dieses Fenster zeigt dir alles "
      "read-only, während es entsteht.",
      "You drive the research through your AI agent (e.g. in chat). This window shows you everything "
      "read-only as it unfolds.")),
    ("squareGrid",
     ("Ein verknüpfter Graph", "One linked graph"),
     ("Personas, Councils, Prototypen und Reports sind Knoten in *einem* Graphen — wiederverwendbare "
      "Bausteine, die sich verbinden (ein Report kann zur Evidenz für die nächste Studie werden).",
      "Personas, councils, prototypes and reports are nodes in *one* graph — reusable building blocks "
      "that connect (a report can become evidence for the next study).")),
    ("syntheses",
     ("Präsentationsreif", "Presentation-grade"),
     ("Jeder Report ist von Haus aus vorzeigbar und als **PDF** oder **PPTX** exportierbar — kein "
      "Nacharbeiten, um Ergebnisse zu teilen.",
      "Every report is presentation-ready by default and exports to **PDF** or **PPTX** — no cleanup "
      "needed to share the result.")),
]

# ============================ Concepts ============================ #
# One artefact per entry, in plain language: WHAT it is + WHY it matters to you. `group` keys it into a
# role band. Shape: {art, icon, name (i18n key or None), group, what (de,en), why (de,en)}.
DOCS = [
    {"art": "persona", "icon": "personas", "name": "personas", "group": "foundation",
     "what": ("Ein synthetischer Kunde mit einer **SOUL** (wer er ist) und einem wachsenden Gedächtnis für "
              "alles, was er erlebt hat. Kein statisches Profil — er erinnert sich und entwickelt sich.",
              "A synthetic customer with a **SOUL** (who they are) and a growing memory of everything "
              "they've been through. Not a static profile — it remembers and evolves."),
     "why": ("Antworten kommen aus gelebter Erfahrung und verschieben sich mit der Zeit, statt jedes Mal "
             "denselben Satz zu wiederholen.",
             "Answers come from lived experience and shift over time, instead of repeating the same line.")},
    {"art": "project", "icon": "projects", "name": "projects", "group": "container",
     "what": ("Der Behälter für *eine* Studie — eine Frage, von offener Erkundung bis zur klaren Antwort. "
              "Alles, was zu dieser Frage gehört, lebt hier.",
              "The container for *one* study — a question, from open exploration to a clear answer. "
              "Everything belonging to that question lives here."),
     "why": ("Ein Ort, an dem du siehst, was erledigt und was offen ist — und wie jedes Stück zum Ergebnis beiträgt.",
             "One place to see what's done and what's open — and how each piece feeds the outcome.")},
    {"art": "council", "icon": "councils", "name": "councils", "group": "evidence",
     "what": ("Eine memory-geerdete **Debatte**, in der Personas auf eine Frage, ein Konzept oder eine "
              "Entscheidung reagieren — jede aus ihrer eigenen Erinnerung heraus.",
              "A memory-grounded **debate** where personas react to a question, a concept, or a decision — "
              "each speaking from its own memory."),
     "why": ("Echte, nachvollziehbare Reaktionen statt Meinungen: jede Aussage führt zurück auf die Erinnerung dahinter.",
             "Real, traceable reactions instead of opinions: any statement leads back to the memory behind it.")},
    {"art": "reference", "icon": "link", "name": "references_h", "group": "evidence",
     "what": ("Eine Website, ein externer Prototyp oder eine A/B-Variante, die in einem Council **im Raum** "
              "liegt — inklusive Capture-Status und Snapshot, wenn erfassbar.",
              "A website, external prototype or A/B variant placed **in the room** for a council — with "
              "capture status and a snapshot when available."),
     "why": ("Personas reagieren auf echtes Material, nicht auf eine Nacherzählung. Referenzen sind Links/Snapshots, "
             "keine hochgeladenen Dateien.",
             "Personas react to real material, not a retelling. References are links/snapshots, not uploaded files.")},
    {"art": "prototype", "icon": "prototype", "name": "prototypes_h", "group": "evidence",
     "what": ("Ein lauffähiger Mock — von der groben Skizze bis zum ausgefeilten Build —, den Personas "
              "tatsächlich anklicken und auf den sie reagieren.",
              "A runnable mock — from a rough sketch to a polished build — that personas actually click "
              "through and react to."),
     "why": ("Geerdete Reaktionen auf etwas *Echtes* statt auf eine Beschreibung — du siehst, was funktioniert, bevor du baust.",
             "Grounded reactions to something *real*, not a description — you see what works before you build.")},
    {"art": "flow", "icon": "compass", "name": "flows_h", "group": "evidence",
     "what": ("Ein geordneter Screen-Walkthrough aus Screenshot-Assets. Personas laufen Schritt für Schritt "
              "hindurch; Drop-off und Reibung werden pro Screen sichtbar.",
              "An ordered screen walkthrough built from screenshot assets. Personas walk it step by step; "
              "drop-off and friction become visible per screen."),
     "why": ("Der zuverlässige Testpfad, wenn ein Live-Browser zu teuer oder instabil wäre.",
             "The reliable test path when a live browser would be too expensive or unstable.")},
    {"art": "session", "icon": "activity", "name": "sessions", "group": "evidence",
     "what": ("Eine replaybare Nutzungsspur: was die Persona gesehen, getan, gedacht und entschieden hat — "
              "als Screen-Walkthrough, klickbarer Prototyp oder Live-Oberfläche.",
              "A replayable usage trace: what the persona saw, did, thought and decided — as a screen "
              "walkthrough, clickable prototype or live surface."),
     "why": ("Sie zeigt Verhalten und Reibung, nicht nur ein Urteil am Ende.",
             "It shows behavior and friction, not just a final opinion.")},
    {"art": "survey", "icon": "plan", "name": "surveys_h", "group": "evidence",
     "what": ("Ein versandfertiges Instrument mit Fragen und Antwortoptionen; echte Antworten können "
              "importiert und gegen Persona-Prognosen gelesen werden.",
              "A sendable instrument with questions and options; real responses can be imported and read "
              "against persona predictions."),
     "why": ("Es quantifiziert offene Spannungen, statt sie nur qualitativ stehen zu lassen.",
             "It quantifies open tensions instead of leaving them only qualitative.")},
    {"art": "asset", "icon": "file", "name": "assets_h", "group": "evidence",
     "what": ("Eine echte Datei im Projekt: Screenshot, Dokument, Export oder erzeugtes Deliverable — mit "
              "Herkunft, Richtung und Download.",
              "A real file in the project: screenshot, document, export or generated deliverable — with "
              "provenance, direction and download."),
     "why": ("Assets sind das Material, aus dem Flows, Evidenz und Deliverables entstehen. Sie sind Dateien, "
             "nicht Council-Referenzen.",
             "Assets are the material behind flows, evidence and deliverables. They are files, not council references.")},
    {"art": "hypothesis", "icon": "target", "name": "hypotheses_h", "group": "answer",
     "what": ("Eine falsifizierbare Wette: erwartete Metrik oder Richtung, Konfidenz und später der "
              "beobachtete Wert.",
              "A falsifiable bet: expected metric or direction, confidence, and later the observed value."),
     "why": ("Sie trennt Annahmen von Ergebnissen und macht Lernen auditierbar.",
             "It separates assumptions from outcomes and makes learning auditable.")},
    {"art": "decision", "icon": "flag", "name": "decisions_h", "group": "answer",
     "what": ("Ein Entscheidungsprotokoll: was beschlossen wurde, welche Evidenz es trägt und welche "
              "Alternative verworfen wurde.",
              "A decision record: what was chosen, which evidence supports it, and which alternative was rejected."),
     "why": ("Der Übergang von Research zu Handlung bleibt nachvollziehbar.",
             "The handoff from research to action remains traceable.")},
    {"art": "note", "icon": "panel", "name": None, "group": "evidence",
     "what": ("Eine leichtgewichtige Idee oder Beobachtung, überall in einer Studie festgehalten — von der "
              "rohen Beobachtung bis zur ausgearbeiteten Lösungs-Idee.",
              "A lightweight idea or observation captured anywhere in a study — from a raw observation to "
              "a worked-out solution idea."),
     "why": ("Die niedrigste Hürde, ein Signal festzuhalten, das später ein Council prüft oder ein Prototyp wird.",
             "The lowest-friction way to keep a signal you can later test in a council or turn into a prototype.")},
    {"art": "section", "icon": "squareGrid", "name": "section", "group": "structure",
     "what": ("Eine einfache Gruppierung zusammengehöriger Dinge in einer Studie — ein Cluster, ein Thema, eine Phase.",
              "A simple grouping of related items in a study — a cluster, a theme, a phase."),
     "why": ("Struktur, wie die Erkenntnisse natürlich zusammenfallen — ohne eine starre Vorlage zu erzwingen.",
             "Structure however the findings naturally group — without forcing a rigid template.")},
    {"art": "synthesis", "icon": "syntheses", "name": "syntheses", "group": "answer",
     "what": ("Die **Antwort** — Kernprobleme und Empfehlungen, und/oder eine erzählerische, "
              "präsentationsreife Aufbereitung der ganzen Studie.",
              "The **answer** — key problems and recommendations, and/or a narrative, presentation-grade "
              "write-up of the whole study."),
     "why": ("Präsentationsreif und als **PDF** exportierbar — und selbst zitierbare Evidenz, die in eine größere Studie einfließen kann.",
             "Presentation-grade and **PDF**-exportable — and itself citable evidence that can feed a larger study.")},
]
# Role tags over the artefacts (ordered). key -> (label_de, label_en, dot_color). A small colored tag on
# each card keeps the role visible while the cards pack into one dense grid (no sparse per-band sub-grids).
GROUPS = [
    ("foundation", ("Fundament", "Foundation", "var(--accent)")),
    ("container",  ("Container", "Container", "#2f6f9f")),
    ("evidence",   ("Evidenz", "Evidence", "#3d7b5f")),
    ("structure",  ("Struktur", "Structure", "#a66b1f")),
    ("answer",     ("Ergebnis", "Outcome", "#7a5ea6")),
]
GROUP_MAP = {k: v for k, v in GROUPS}   # key -> (label_de, label_en, dot_color)
# What every artefact is made of underneath — kept light; the "same idea looks the same everywhere" point.
PRIMITIVES = [
    ("Statement", "Eine Persona-Aussage: Text, Haltung, Belege. Vereint Council-Beiträge, Report-Stimmen und Prototyp-Reaktionen.",
     "A persona's utterance: text, stance, refs. Unifies council turns, report voices and prototype reactions."),
    ("Finding", "Ein Analyse-Item: Kernproblem, Empfehlung oder offene Frage — mit optionalem Score und Belegen.",
     "An analysis item: a key problem, recommendation or open question — with an optional score and refs."),
    ("Prompt", "Das Gestellte: eine Frage, ein Vorschlag, ein Ziel oder ein Fokus.",
     "The thing posed: a question, a proposal, a goal or a focus."),
    ("Ref", "Ein Beleg-Zeiger auf eine Erinnerung, ein Council, einen Prototyp-State oder ein Zitat.",
     "A grounding pointer to a memory, a council, a prototype state or a quote."),
    ("Stance", "Eine einzige Positivitäts-Skala (−2 ablehnend … +2 befürwortend). Vereint Haltung, Stimmung und Votes.",
     "One positivity scale (−2 oppose … +2 support). Unifies stance, sentiment and votes."),
]
# Per-artefact data shape. `holds` = plain-language key fields (de, en). `example` = a real, trimmed JSON
# record. `made` = the content primitives it composes (chips linking to the data model), or () for plain
# graph nodes; `made_note` = a (de, en) line on its graph role. Field names/JSON are the actual stored
# shape (sonaloop/models.py + spec/unified-artifact-schema.md).
SCHEMAS = {
    "persona": {
        "holds": (["**SOUL** — die autoritative Identität (Rolle, Firmen-Kontext, Werte, Eigenheiten)",
                   "Ziele, Constraints und Pain-Points",
                   "Avatar-Pfad + Provenienz (woraus die Persona abgeleitet wurde)",
                   "Das **Gedächtnis** liegt in eigenen, zeit-indizierten Records (s. u.)"],
                  ["**SOUL** — the authoritative identity (role, company context, values, quirks)",
                   "Goals, constraints and pain points",
                   "Avatar path + provenance (what the persona was derived from)",
                   "**Memory** lives in separate, time-indexed records (see below)"]),
        "made": (),
        "made_note": ("Eine Persona ist ein Graph-**Node**. Ihr Gedächtnis sind eigene Records — "
                      "`ExperienceEvent`, `DailySummary`, `PainPointObservation` — je mit `persona_id` und "
                      "Zeitstempel, sodass Recall und Zeitreise funktionieren.",
                      "A persona is a graph **Node**. Its memory is separate records — `ExperienceEvent`, "
                      "`DailySummary`, `PainPointObservation` — each keyed by `persona_id` and a timestamp, "
                      "so recall and time-travel work.")},
    "project": {
        "holds": (["Titel + Ziel (die *How-Might-We*-Frage) + Methodik & aktuelle Phase",
                   "Verknüpfte Studien (Reports), Councils, Notizen, Sections, Personas",
                   "Emergente Themen + `study_tags` (welches Thema welche Studie trägt)",
                   "Status (active / done)"],
                  ["Title + goal (the *How-Might-We*) + methodology & current phase",
                   "Linked studies (reports), councils, notes, sections, personas",
                   "Emergent themes + `study_tags` (which theme each study carries)",
                   "Status (active / done)"]),
        "made": (),
        "made_note": ("Ein Projekt ist der Container-**Node**; die Beziehungen zwischen seinen Knoten sind "
                      "typisierte **Edges** (`based_on`, `feeds_into`, `refines`, `answers`).",
                      "A project is the container **Node**; the relations between its nodes are typed "
                      "**Edges** (`based_on`, `feeds_into`, `refines`, `answers`).")},
    "council": {
        "holds": (["`prompts` — die gestellte(n) Frage(n) / das Proposal",
                   "`persona_ids` — wer teilnimmt",
                   "`statements` — jeder Beitrag (Text + Stance + Belege), gruppiert beim Rendern",
                   "`findings` — die Executive Summary + die verdichtete Erkenntnis",
                   "`votes` — formale Stimmen (nur im Decision-Modus)"],
                  ["`prompts` — the question(s) / proposal posed",
                   "`persona_ids` — who takes part",
                   "`statements` — every turn (text + stance + refs), grouped at render time",
                   "`findings` — the executive summary + the distilled finding",
                   "`votes` — formal votes (decision mode only)"]),
        "made": ("Prompt", "Statement", "Finding"),
        "made_note": None},
    "synthesis": {
        "holds": (["`prompts` — der Ausgangspunkt / das Ziel der Studie",
                   "`findings` — Kernprobleme, Empfehlungen (mit Aufwand·Nutzen-Score), offene Fragen",
                   "`statements` — die zitierten Persona-Stimmen",
                   "`references` — die Quell-Councils",
                   "`sections` — erzählerische, präsentationsreife Abschnitte mit Figuren"],
                  ["`prompts` — the study's starting point / goal",
                   "`findings` — key problems, recommendations (with effort·value score), open questions",
                   "`statements` — the quoted persona voices",
                   "`references` — the source councils",
                   "`sections` — narrative, presentation-grade sections with figures"]),
        "made": ("Prompt", "Finding", "Statement", "Ref"),
        "made_note": None},
    "prototype": {
        "holds": (["Name + Version + `tags` (Fidelity, z. B. lofi/midfi/hifi)",
                   "`path` / `entry` / `run` — wie der lauffähige Build gestartet wird",
                   "Optionaler Link zum Projekt + zur Notiz, aus der er gebaut wurde",
                   "Eine **Session** ist eine Persona, die ihn benutzt — als `statements`, geerdet in "
                   "beobachteten Prototyp-States"],
                  ["Name + version + `tags` (fidelity, e.g. lofi/midfi/hifi)",
                   "`path` / `entry` / `run` — how the runnable build is launched",
                   "Optional link to the project + the note it was built from",
                   "A **session** is a persona using it — as `statements`, grounded in observed prototype "
                   "states"]),
        "made": ("Statement", "Ref"),
        "made_note": ("Der Prototyp selbst ist ein **Node**; seine Sessions sind `Statements`, geerdet in "
                      "`prototype_state`-Refs (eine Reaktion ohne passenden beobachteten State wird abgelehnt).",
                      "The prototype itself is a **Node**; its sessions are `Statements` grounded in "
                      "`prototype_state` refs (a reaction with no matching observed state is rejected).")},
    "note": {
        "holds": (["`title` + `text` — die Idee oder Beobachtung",
                   "`kind` — immer `note` (das frühere „Concept“ ist hier aufgegangen)",
                   "`data` — optional strukturiert: `lens`, `artifact_kind`, `prototype_ids`",
                   "`created_at` — der Zeitpunkt im Studien-Timeline"],
                  ["`title` + `text` — the idea or observation",
                   "`kind` — always `note` (the former “concept” is merged in)",
                   "`data` — optional structured: `lens`, `artifact_kind`, `prototype_ids`",
                   "`created_at` — its point on the study timeline"]),
        "made": (),
        "made_note": ("Eine leichtgewichtige **Node** im Projekt-Graph. Wird sie gebaut, zeigt `data.prototype_ids` "
                      "auf ihren Prototyp.",
                      "A lightweight **Node** in the project graph. Once built, `data.prototype_ids` points at "
                      "its prototype.")},
    "section": {
        "holds": (["`title` + `kind` (z. B. theme, phase)",
                   "`member_ids` — beliebige Graph-Knoten (Councils, Notizen, Studien …)",
                   "`order` + optionaler `parent_id` für die Outline",
                   "`presentation` — optionale Darstellungs-Hinweise"],
                  ["`title` + `kind` (e.g. theme, phase)",
                   "`member_ids` — any graph nodes (councils, notes, studies …)",
                   "`order` + optional `parent_id` for the outline",
                   "`presentation` — optional display hints"]),
        "made": (),
        "made_note": ("Eine Section ist eine **Referenz**-Gruppierung, keine Container: ihre Mitglieder leben "
                      "weiter im Graphen und können in mehreren Sections auftauchen.",
                      "A section is a **reference** grouping, not containment: its members live on in the graph "
                      "and can appear in several sections.")},
}

# ============================ How it works ============================ #
# The lifecycle pipeline (rendered as a visual flow). Shape: (icon, (title_de, title_en), (sub_de, sub_en)).
LIFECYCLE = [
    ("personas", ("Personas", "Personas"),
     ("Synthetische Kunden mit wachsender Erinnerung.", "Synthetic customers with growing memory.")),
    ("projects", ("Studie", "Study"),
     ("Eine Frage — von offen bis beantwortet.", "One question — from open to answered.")),
    ("councils", ("Evidenz", "Evidence"),
     ("Councils, Prototypen & Notizen.", "Councils, prototypes & notes.")),
    ("syntheses", ("Report", "Report"),
     ("Die entscheidungsreife Antwort.", "The decision-ready answer.")),
]
EVIDENCE_PILLS = [("councils", "Councils"), ("prototype", "Prototypes"), ("panel", "Notes")]
LOOP_NOTE = ("↻ Wiederholen, bis die Evidenz überzeugt.", "↻ Repeat until the evidence convinces.")

# How a study stays rigorous — a small repeating cycle (the plan engine, in plain language).
RIGOUR_STEPS = [
    (("Rahmen", "Frame"),
     ("Eine Forschungsfrage stellen, geerdet in der Erinnerung der Personas.",
      "Pose a research question, grounded in the personas' memory.")),
    (("Evidenz sammeln", "Gather evidence"),
     ("Councils laufen lassen, Prototypen testen, Signale festhalten.",
      "Run councils, test prototypes, capture signals.")),
    (("Prüfen", "Verify"),
     ("Erst schließen, wenn die Evidenz die Gates erfüllt — belegen statt behaupten.",
      "Only close once the evidence clears the gates — back it, don't assert it.")),
]

# ============================ Working live (the inspector page) ============================ #
# What the inspector itself offers the human at the keyboard — the features you SEE, in plain
# language. Shape: (anchor, icon, (title_de, title_en), (body_de, body_en)); bodies are Markdown.
INSPECTOR_SECTIONS = [
    ("orientation", "book",
     ("Orientierung: vier Punkte, ein Modell", "Getting around: four items, one model"),
     ("Die Seitenleiste hat genau **vier** Einträge: **Projekte · Personas · Library · Activity** "
      "(Einstellungen & Doku sitzen im Footer). Das Denkmodell ist überall dasselbe: *Projekt → "
      "Phasen → Zeilen; Klick = Seitenpanel.* Das **Projekt ist das Zuhause** — alles, was eine Studie "
      "erzeugt oder benutzt (offene Fragen, Referenzen, Councils, Reports, Flows, Prototypen, "
      "Sessions, Umfragen, Hypothesen, Entscheidungen, Notizen, Assets), ist eine Zeile in "
      "seiner Phase. Die **Library** ist der projektübergreifende Browser über dieselben Primitives. "
      "Die Namensregel: **Referenzen** sind Websites, externe Prototypen oder A/B-Varianten im Council-Raum; "
      "**Assets** sind echte Dateien; **Sessions** sind Nutzungsspuren. **Assets** — empfangene "
      "Input-Dateien (Evidenz, via MCP angehängt) und von der Software erzeugte Dokumente "
      "(Deliverables) — erscheinen überall als **Datei-Karten**: Typ-Badge oder Vorschaubild, "
      "Dateiname mit Endung, Größe · Datum, genau ein Download/Öffnen-Symbol; sie haben eigene "
      "Detailseiten mit Herkunft (Quelle, Richtung, ersetzte Versionen). Der Chip **„N Dateien“** "
      "im Projekt-Kopf öffnet alle Dateien eines Projekts chronologisch als Karten-Raster. "
      "Ein Klick auf eine Zeile öffnet die "
      "**ganze Detailseite als Seitenpanel** (Notion-Stil): die Liste bleibt dahinter sichtbar, "
      "die URL bleibt die Listen-URL und bekommt `?d=<Detailpfad>` — neu laden oder teilen "
      "reproduziert exakt diese Ansicht (Liste + offenes Panel). Das ⤢-Symbol wechselt zur "
      "vollen Seite (die kanonische Detail-URL, die direkt geladen weiterhin die volle Seite "
      "zeigt), Esc/Zurück bringt die Liste samt URL zurück. Den **Run-Status** eines Projekts zeigt ein Chip im "
      "Projekt-Kopf (verlinkt aufs Run-Journal).",
      "The sidebar has exactly **four** items: **Projects · Personas · Library · Activity** "
      "(settings & docs live in the footer). One mental model runs the whole app: *project → "
      "phases → rows; click = slide-over.* The **project is the home** — everything a study produces "
      "or uses (open questions, references, councils, reports, flows, prototypes, sessions, surveys, "
      "hypotheses, decisions, notes, assets) is a row in its phase. The **Library** is the "
      "cross-project browser over those same primitives. Naming rule: **References** are websites, "
      "external prototypes or A/B variants in the council room; **Assets** are real files; "
      "**Sessions** are usage traces. **Assets** — input files received (evidence, attached via MCP) and "
      "documents the software generated (deliverables) — show up everywhere as **file cards**: "
      "type badge or image thumbnail, filename with extension, size · date, exactly one "
      "download/open icon; they have their own detail pages with provenance (source, direction, "
      "superseded versions). The **“N files”** chip in the project header opens all of a "
      "project's files chronologically as a card grid. "
      "Clicking a row opens the **full detail page as a slide-over** (Notion-style): "
      "the list stays visible behind it, and the URL stays the list URL plus `?d=<detail "
      "path>` — reloading or sharing it reproduces exactly this view (list + open panel). "
      "The ⤢ control expands to the full page (the canonical detail URL, which still renders "
      "full-page when loaded directly), and Esc/back restores the list and its URL. A project's "
      "**run state** shows as a chip in the project header (linking to the run journal).")),
    ("examples", "package",
     ("Beispielprojekte", "Example projects"),
     ("Fertige Demo-Studien liegen bei — darunter ein Onboarding-Showcase, eine B2B-Positioning-Studie "
      "und eine B2C-Pricing-Studie "
      "(mit Preis-Leiter und Head-to-Head). Auf einer leeren Datenbank zeigt die Startseite je einen "
      "**„Beispiel laden“**-Button; dein Agent kann sie auch per `load_example` laden, `sonaloop "
      "load-example` ebenso. Laden ist idempotent (kein Duplizieren beim erneuten Laden), und "
      "`remove_example` entfernt **nur** die Daten des Beispiels — nie deine eigenen.",
      "Finished demo studies ship with Sonaloop — including an onboarding showcase, a B2B positioning study and a B2C pricing study "
      "(with a willingness-to-pay ladder and a head-to-head). On an empty database the home page shows "
      "a **“Load example”** button for each; your agent can load them via `load_example`, or "
      "`sonaloop load-example` from the CLI. Loading is idempotent (re-loading never duplicates), and "
      "`remove_example` removes **only** the example's data — never yours.")),
    ("live", "zap",
     ("Live-Aktivität", "Live activity"),
     ("Jede Inspector-Seite ist live verbunden: nimmt dein Agent etwas auf (ein Council, eine Persona, "
      "einen Report), erscheint ein kleiner **Toast** mit Link — und die offene Seite lädt sich selbst "
      "neu, wenn es sie betrifft. Der **Activity**-Feed (`g` `a`) listet alles Zuletzt-Passierte "
      "chronologisch. Du schaust zu, während die Studie entsteht — kein manuelles Neuladen.",
      "Every inspector page is live: when your agent records something (a council, a persona, a report) "
      "a small **toast** appears with a link — and the page you're on reloads itself when it's "
      "affected. The **Activity** feed (`g` `a`) lists everything recent in order. You watch the study "
      "come together — no manual refreshing.")),
    ("runs", "play",
     ("Laufende Runs", "Runs"),
     ("Oben in der Leiste zeigt ein Status-Punkt, ob gerade Studien **aktiv** laufen — er wird "
      "**gelb**, wenn ein Projekt feststeckt (das stille Scheitern soll laut sein). Im "
      "Projekt-Kopf trägt jedes Projekt seinen eigenen **Run-Chip** (Zustand · letzte Aktivität). "
      "Beide verlinken auf das **Run-Journal** (`g` `r`) — eine bewusst schlichte Telemetrie-Seite "
      "mit jedem Projekt-Run und seiner letzten Aktivität; als Navigationspunkt taucht sie nicht "
      "auf.",
      "A status dot in the top bar shows whether studies are **running** right now — it turns "
      "**amber** when a project is stalled (the silent failure mode should be loud). In the "
      "project header every project carries its own **run chip** (state · last activity). Both "
      "link to the **run journal** (`g` `r`) — a deliberately plain telemetry page listing every "
      "project run with its last activity; it isn't a nav item.")),
    ("keyboard", "command",
     ("Tastatur & Palette", "Keyboard & palette"),
     ("`?` öffnet das Shortcut-Cheat-Sheet. **⌘K / Ctrl+K** öffnet die Befehls-Palette: zuletzt "
      "besuchte Einträge, Navigation (mit der Bibliothek als aufklappbarem Eintrag) und Aktionen — "
      "und beim Tippen eine Suche über alles (Personas, Councils, Reports, Sessions, Hypothesen, "
      "Entscheidungen, Umfragen …), nach Art gruppiert mit Projekt und Datum. Navigation per Chords: `g` `h` Home, `g` `p` Personas, `g` `c` "
      "Councils, `g` `s` Reports, `g` `a` Activity, `g` `r` Runs, `g` `d` Doku. In Listen und im "
      "Projekt-Outline: `j`/`k` bewegt den Fokus, `Enter` öffnet die Zeile als **Seitenpanel** "
      "(volle Detailseite, echte URL), `o` öffnet sie direkt als ganze Seite, `Esc` schließt "
      "das Panel. Auf Detailseiten blättern `[`/`]` zum Nachbarn. Beim Tippen in Felder ist alles deaktiviert.",
      "`?` opens the shortcut cheat sheet. **⌘K / Ctrl+K** opens the command palette: your recently "
      "visited records, navigation (with the library as one expandable entry) and actions — and, as "
      "you type, a search across everything (personas, councils, reports, sessions, hypotheses, "
      "decisions, surveys …), grouped by kind with project and date. Navigate with chords: `g` `h` home, `g` `p` personas, `g` `c` "
      "councils, `g` `s` reports, `g` `a` activity, `g` `r` runs, `g` `d` docs. In lists and the "
      "project outline `j`/`k` move focus, `Enter` opens the row as a **slide-over** (the full "
      "detail page, real URL), `o` opens it straight as a full page, and `Esc` closes the "
      "panel. On detail pages `[`/`]` step to the sibling record. Everything is disabled while you type in a field.")),
    ("tour", "compass",
     ("Produkt-Tour", "Product tour"),
     ("Die optionale Tour startet **nie von selbst**. Wenn du **„Tour starten“** wählst, lädt sie bei "
      "Bedarf das Showcase-Beispielprojekt und führt dann im Projektkontext durch echte Primitives: "
      "offene Frage, Referenz, Council, Survey, Report, Flow, Prototype, Session, Hypothese, "
      "Entscheidung, Notes, Assets und Library. "
      "`Esc` beendet sie jederzeit.",
      "The optional tour **never auto-starts**. When you choose **“Take the tour”**, it loads the "
      "showcase example project if needed, then walks real primitives in project context: open "
      "question, reference, council, survey, report, flow, prototype, session, hypothesis, decision, "
      "notes, assets, and the Library. `Esc` "
      "ends it any time.")),
    ("editing", "pencil",
     ("Was du bearbeiten kannst", "What you can edit"),
     ("Der Inspector ist eine Lese-Oberfläche mit einer klaren Grenze: **ansehen und bearbeiten, "
      "nie anlegen.** Neue Projekte, Notizen oder Sections entstehen ausschließlich über deinen "
      "Agenten (MCP/CLI) — die UI bietet dafür bewusst keinen Button. Bearbeiten und Löschen "
      "wohnen im **„…“-Menü**, das jeder Seitenkopf trägt (auch im Panel): **Bearbeiten** öffnet "
      "einen Dialog direkt über der Seite — Projekt-, Notiz- und Section-Metadaten sowie "
      "Persona-Metadaten (Name, Rolle, Segment, Branche). **Löschen** öffnet einen "
      "Bestätigungs-Dialog (bei Projekten und Personas tippst du den Namen). Generierter Text — "
      "Councils, Reports, Prototypen — bleibt unantastbar; Erinnerungen, SOULs und Evidenz komplett.",
      "The inspector is a reading surface with one clear boundary: **inspect and edit, never "
      "create.** New projects, notes or sections come exclusively from your agent (MCP/CLI) — the "
      "UI deliberately offers no button for them. Edit and delete live in the **“…” menu** every "
      "page header carries (in the side panel too): **Edit** opens a dialog right over the page — "
      "project, note and section metadata plus persona metadata (name, role, segment, industry). "
      "**Delete** opens a confirm dialog (projects and personas ask you to type the name). "
      "Generated text — councils, reports, prototypes — stays untouchable; memories, SOULs and "
      "evidence entirely so.")),
    ("filtering", "filter",
     ("Filtern wie in Linear", "Filtering, Linear-style"),
     ("Projekt-Outline und Library tragen eine **Filterleiste**: „Filter“ öffnet das Facetten-Menü "
      "(Typ, Phase, Persona, Status — in der Library Projekt, Status, bei Assets Richtung) mit "
      "ehrlichen Treffer-Zahlen pro Wert. Innerhalb einer Facette gilt ODER, zwischen Facetten "
      "UND. Aktive Filter erscheinen als Chips mit ×; der Zustand lebt in der **URL** "
      "(`?kind=council,decision&phase=…`) — teilbar, verlinkbar, Reload-fest. Trifft ein Filter "
      "nichts, sagt die Seite das und bietet „zurücksetzen“ an.",
      "The project outline and the Library carry a **filter bar**: “Filter” opens the facet menu "
      "(kind, phase, persona, status — in the Library project, status, plus direction on Assets) "
      "with honest per-value counts. Within a facet values OR, across facets they AND. Active "
      "filters become chips with ×; the state lives in the **URL** "
      "(`?kind=council,decision&phase=…`) — shareable, linkable, reload-proof. When a filter "
      "matches nothing, the page says so and offers “clear”.")),
    ("language", "globe",
     ("Sprache", "Language"),
     ("Die Oberfläche ist zweisprachig (Deutsch/Englisch) — der Umschalter sitzt im "
      "Einstellungs-Popover unten links. Die UI-Sprache ist **unabhängig** von der Inhalts-Sprache: "
      "generierte Inhalte folgen der Sprache, in der du mit deinem Agenten schreibst, und werden vom "
      "Umschalter nie angefasst.",
      "The chrome is bilingual (German/English) — the switcher lives in the settings popover, bottom "
      "left. The UI language is **independent** of the content language: generated content follows "
      "the language you write to your agent in, and the switcher never touches it.")),
    ("feedback", "chat",
     ("Feedback", "Feedback"),
     ("Unten in der Seitenleiste sitzt ein **Feedback**-Knopf: kurze Nachricht, optional deine "
      "E-Mail — die aktuelle Seite und die App-Version werden sichtbar mitgeschickt (nichts wird "
      "still gesammelt). Eingesendetes liest der Betreiber unter `/feedback` oder per `sonaloop "
      "feedback`; alternativ verlinkt das Formular ein vorausgefülltes GitHub-Issue.",
      "A **feedback** button sits at the bottom of the sidebar: a short message, optionally your "
      "email — the current page and app version are sent along visibly (nothing is collected "
      "silently). Submissions are read at `/feedback` or via `sonaloop feedback`; the form also "
      "links a prefilled GitHub issue as the public channel.")),
]

# ============================ Methodology ============================ #
# Double Diamond as the worked EXAMPLE of the diverge → converge rhythm (one of many methodologies).
DD_PHASES = [
    ("Discover", "diverge",
     ("Reale, gelebte Pains breit über Personas und Blickwinkel aufdecken. Noch keine Lösungen.",
      "Surface real, lived pains broadly across personas and angles. No solutions yet.")),
    ("Define", "converge",
     ("Die Breite zu **einem** Kernproblem und einem scharfen Point-of-View verdichten.",
      "Cluster the breadth into **one** core problem and a sharp Point-of-View.")),
    ("Develop", "diverge",
     ("Mehrere Lösungskandidaten erzeugen und einen echten, minimalen Prototyp bauen.",
      "Generate several solution candidates and build one real, minimal prototype.")),
    ("Deliver", "converge",
     ("Personas den Prototyp **benutzen** lassen und zu einer baubaren Spec konvergieren.",
      "Have personas **use** the prototype and converge to a buildable spec.")),
]
RHYTHM = {"diverge": ("Öffnen", "Diverge"), "converge": ("Verdichten", "Converge")}

# Ready playbooks — things you can ask your agent for. Shape: ((title_de, title_en), code, (desc_de, desc_en)).
PLAYBOOKS = [
    (("Council abhalten", "Run a council"), "run_council",
     ("Lass die Personas ein Thema debattieren, geerdet in ihrer Erinnerung.",
      "Have the personas debate a topic, grounded in their memory.")),
    (("Synthese", "Synthesize"), "synthesize",
     ("Councils iterieren, bis genug Erkenntnis da ist — zu **einem** wachsenden Report.",
      "Iterate councils until there's enough insight — into **one** growing report.")),
    (("Design-Thinking-Projekt", "Design-thinking project"), "design_thinking",
     ("Eine *How-Might-We*-Frage von offen bis zur baubaren Spec führen.",
      "Take a *How-Might-We* from an open question to a buildable spec.")),
    (("Research-Plan komponieren", "Compose a research plan"), "compose_research_plan",
     ("Übergib ein beliebiges Research-Ziel — der Agent entwirft und fährt die ganze Studie.",
      "Hand over any research goal — the agent designs and runs the whole study.")),
]

# ============================ MCP reference taxonomy ============================ #
# The catalogue groups tools by their source module (`_tools_*.py`), which is faithful but exposes code
# jargon. For the docs we relabel each domain in plain language and organize the domains into a small,
# legible two-level taxonomy. Keyed by the domain `key` catalogue_data() returns; unknown keys fall back
# to the raw catalogue label. DOMAIN_META: key -> (title_de, title_en, desc_de, desc_en).
DOMAIN_META = {
    "personas":   ("Personas", "Personas",
                   "Personas anlegen und in echten Quellen erden.", "Create personas and ground them in real sources."),
    "simulation": ("Simulation & Erinnerung", "Simulation & memory",
                   "Tage/Monate simulieren und Persona-Erinnerung abrufen.", "Simulate days/months and recall persona memory."),
    "research":   ("Projekt-Graph & Report", "Project graph & report",
                   "Der Studien-Container, sein Graph und der finale Report.", "The study container, its graph, and the final report."),
    "plan":       ("Plan & Steuerung", "Plan & run loop",
                   "Projekt anlegen und die Analyze→Act→Verify-Schleife fahren.", "Create a project and drive the analyze→act→verify loop."),
    "methodology":("Methodiken", "Methodologies",
                   "Die Phasen-Konstellation einer Studie wählen oder bauen.", "Pick or compose the phase constellation a study runs."),
    "council":    ("Councils & Reports", "Councils & reports",
                   "Persona-Debatten abhalten und zu Reports verdichten.", "Hold persona debates and fold them into reports."),
    "prototypes": ("Prototypen & Tests", "Prototypes & testing",
                   "Lauffähige Mocks bauen und von Personas benutzen lassen.", "Build runnable mocks and have personas use them."),
    "sections":   ("Notizen & Struktur", "Notes & structure",
                   "Signale festhalten und Knoten in Sections gruppieren.", "Capture signals and group nodes into sections."),
    "eval":       ("Evaluation & Kritik", "Evaluation & critics",
                   "Runs bewerten und Abdeckung/Qualität kritisieren.", "Score runs and critique coverage/quality."),
}
# Super-groups organize the domains into a lifecycle-shaped taxonomy. Shape: (title_de, title_en, desc_de,
# desc_en, [domain_keys]). The synthetic "__extras__" key carries resources & prompts.
SUPER_GROUPS = [
    ("Personas & Erinnerung", "Personas & memory",
     "Wer reagiert — und ihr Gedächtnis.", "Who reacts — and their memory.",
     ["personas", "simulation"]),
    ("Eine Studie fahren", "Running a study",
     "Der Container, die Plan-Engine und die Methodik.", "The container, the plan engine and the methodology.",
     ["research", "plan", "methodology"]),
    ("Evidenz & Reports", "Evidence & reports",
     "Councils, Prototypen, Notizen — und die Reports, die sie verdichten.",
     "Councils, prototypes, notes — and the reports that fold them up.",
     ["council", "prototypes", "sections"]),
    ("Evaluation", "Evaluation",
     "Qualität und Abdeckung prüfen.", "Check quality and coverage.",
     ["eval"]),
    ("Ressourcen & Prompts", "Resources & prompts",
     "Browsbare Guides und fertige Playbooks.", "Browsable guides and ready playbooks.",
     ["__extras__"]),
]



# ============================ Co-located CSS ============================ #
register_css(r"""
/* ==== Documentation hub: the standard page header (eyebrow/.h1/.lead — W7) + tabs in the measure ==== */
.doc-head{margin-bottom:2px}
.doc-head .h1{display:flex;align-items:center;gap:12px}
.doc-tabs{margin:8px 0 24px}
.doc-p{color:var(--muted);font-size:var(--t-body);line-height:1.6;margin:0 0 16px;max-width:74ch}
.doc-p strong{color:var(--ink)}
.doc-p p{margin:0;max-width:none}
.doc-note{color:var(--ink);font-size:var(--t-sm);background:var(--panel-2);border:1px solid var(--line-2);border-radius:var(--radius-md,10px);padding:11px 14px;max-width:74ch}
.doc-note p,.doc-note{margin:0}

/* ==== Documentation: two-column wrap + sticky on-this-page rail ==== */
.doc-wrap{display:flex;align-items:flex-start;gap:38px;margin-top:18px}
.doc-main{flex:1;min-width:0}.doc-main.wide{margin-top:18px}
.doc-main [id]{scroll-margin-top:16px}
.doc-toc{width:188px;flex-shrink:0;position:sticky;top:14px}
.toc-nav{display:flex;flex-direction:column;gap:2px;border-left:1px solid var(--line);padding-left:14px}
.toc-lbl{font-size:var(--t-xs,11px);font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--faint);margin-bottom:6px}
.toc-nav a{color:var(--muted);font-size:var(--t-sm);text-decoration:none;padding:4px 0;transition:color 110ms}
.toc-nav a:hover{color:var(--ink)}
.doc-block{margin-top:38px}.doc-block:first-child{margin-top:0}
.doc-sub-h{font-size:var(--t-md);font-weight:650;letter-spacing:-.01em;margin:0 0 12px}

/* ==== Overview: principle tiles + landing cards ==== */
.principles{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}
.ptile-ic{color:var(--accent);margin-bottom:9px}
.ptile-t{font-weight:650;font-size:var(--t-md);letter-spacing:-.01em;margin-bottom:5px}
.ptile-b{color:var(--muted)}.ptile-b p{margin:0;max-width:none}
.navgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px}
.navcard{display:flex;flex-direction:column;gap:8px;text-decoration:none;transition:border-color 120ms,box-shadow 120ms}
.navcard:hover{border-color:var(--accent);box-shadow:0 1px 3px rgba(0,0,0,.04)}
.navcard-ic{color:var(--accent)}
.navcard-t{font-weight:650;font-size:var(--t-md);letter-spacing:-.01em;color:var(--ink)}
.navcard-b{color:var(--muted);font-size:var(--t-sm);line-height:1.5}

/* ==== Concepts: one dense grid, role shown as a per-card tag ==== */
.concept-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px;align-items:start}
.doccard{display:flex;flex-direction:column;text-decoration:none;color:inherit;transition:border-color 120ms,box-shadow 120ms}
.doccard:hover{border-color:var(--accent);box-shadow:0 1px 3px rgba(0,0,0,.04)}
.doccard:hover .doc-open{color:var(--accent)}
.doc-open{margin-top:12px;padding-top:10px;border-top:1px dashed var(--line-2);font-size:var(--t-xs,11px);font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--faint);transition:color 120ms}
.doc-h{display:flex;align-items:center;gap:9px;margin-bottom:8px}
.rico{display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;width:28px;height:28px;border-radius:var(--radius-sm);background:var(--panel-2)}
.doc-h .rico svg{width:17px;height:17px}
.doc-name{font-size:var(--t-md);font-weight:650;letter-spacing:-.01em;flex:1;min-width:0}
.doc-gtag{display:inline-flex;align-items:center;gap:5px;flex-shrink:0;font-size:var(--t-xs,11px);font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.03em}
.doc-gdot{width:6px;height:6px;border-radius:50%;flex-shrink:0}
.doc-what{color:var(--ink);line-height:1.6}.doc-what p{margin:0;max-width:none}
.doc-why{margin-top:11px;padding-top:10px;border-top:1px solid var(--line-2);font-size:var(--t-sm);color:var(--muted);line-height:1.5}
.doc-why-lbl{display:block;font-size:var(--t-xs,11px);font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--faint);margin-bottom:3px}
.doc-why strong{color:var(--ink)}
/* ==== Concepts: data-model (three layers + five primitives w/ JSON) ==== */
.rico.lg{width:34px;height:34px}.rico.lg svg{width:20px;height:20px}
.doc-code{margin:0;background:var(--panel-2);border:1px solid var(--line-2);border-radius:var(--radius-md,10px);padding:13px 15px;overflow-x:auto}
.doc-code code{font-family:var(--mono,'Geist Mono',monospace);font-size:var(--t-xs,12px);line-height:1.6;color:var(--ink);white-space:pre;background:none;border:0;padding:0}
.dl-layers{display:flex;flex-direction:column;gap:2px;margin-top:6px}
.dl-layer{display:flex;gap:14px;padding:12px 0;border-bottom:1px solid var(--line-2)}
.dl-layer:last-child{border-bottom:0}
.dl-layer-n{flex-shrink:0;width:26px;height:26px;border-radius:50%;background:var(--panel-2);color:var(--accent);font-weight:650;font-size:var(--t-sm);display:flex;align-items:center;justify-content:center}
.dl-layer-main{min-width:0}
.dl-layer-t{font-weight:650;font-size:var(--t-md);letter-spacing:-.01em;margin-bottom:3px}
.dl-layer-b{color:var(--muted)}.dl-layer-b p{margin:0;max-width:none}
.prim-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}

.prim-card-h{margin-bottom:6px}
.prim-card-n{font-family:var(--mono,'Geist Mono',monospace);font-size:var(--t-sm);font-weight:700;color:var(--accent)}
.prim-card-d{color:var(--muted);font-size:var(--t-sm);line-height:1.5;margin-bottom:10px}
.prim-chips{display:flex;flex-wrap:wrap;gap:7px}
.prim-chip{font-family:var(--mono,'Geist Mono',monospace);font-size:var(--t-sm);font-weight:600;color:var(--accent);background:var(--panel-2);border:1px solid var(--line-2);border-radius:20px;padding:3px 11px;text-decoration:none;transition:border-color 110ms}
.prim-chip:hover{border-color:var(--accent)}

/* ==== How it works: lifecycle pipeline ==== */
.flow{display:flex;align-items:stretch;gap:0;flex-wrap:wrap;margin-top:6px}
.flow-stage{flex:1 1 150px;min-width:140px;border:1px solid var(--line);border-radius:var(--radius-md,10px);padding:14px 15px;background:var(--panel);display:flex;flex-direction:column;gap:4px}
.flow-stage.wide{flex:1.3 1 180px;border-color:var(--accent);background:color-mix(in srgb,var(--accent) 5%,var(--panel))}
.flow-ic{display:inline-flex;color:var(--accent);margin-bottom:4px}.flow-ic svg{width:19px;height:19px}
.flow-t{font-weight:650;font-size:var(--t-md);letter-spacing:-.01em}
.flow-s{color:var(--muted);font-size:var(--t-sm);line-height:1.5}
.flow-pills{display:flex;flex-wrap:wrap;gap:5px;margin-top:8px}
.flow-pill{display:inline-flex;align-items:center;gap:4px;font-size:var(--t-xs,11px);font-weight:500;color:var(--ink);background:var(--panel);border:1px solid var(--line-2);border-radius:20px;padding:2px 9px}
.flow-pill svg{width:12px;height:12px;color:var(--accent)}
.flow-arrow{display:flex;align-items:center;justify-content:center;color:var(--faint);font-size:19px;padding:0 9px;flex-shrink:0}
.flow-loop{margin-top:12px;font-size:var(--t-sm);color:var(--accent);font-weight:500;text-align:center;background:var(--panel-2);border:1px dashed var(--line);border-radius:20px;padding:7px 14px}

/* ==== How it works: rigour cycle ==== */
.cyc{display:flex;align-items:stretch;gap:0;flex-wrap:wrap;margin-top:6px}
.cyc-step{flex:1 1 180px;min-width:160px;border:1px solid var(--line-2);border-radius:var(--radius-md,10px);padding:14px 15px;background:var(--panel-2)}
.cyc-n{width:24px;height:24px;border-radius:50%;background:var(--panel);border:1px solid var(--line);color:var(--accent);font-weight:650;font-size:var(--t-sm);display:flex;align-items:center;justify-content:center;margin-bottom:8px}
.cyc-t{font-weight:650;font-size:var(--t-md);letter-spacing:-.01em;margin-bottom:4px}
.cyc-b{color:var(--muted);font-size:var(--t-sm);line-height:1.5}
.flow-arrow.loopback{font-size:22px;color:var(--accent)}

/* ==== Methodology: catalogue cards + DD phases + playbooks ==== */
.methgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px}

.methcard-h{display:flex;align-items:baseline;justify-content:space-between;gap:8px;margin-bottom:6px}
.methcard-n{font-weight:650;font-size:var(--t-md);letter-spacing:-.01em}
.methcard-c{font-size:var(--t-xs,11px);color:var(--faint);font-weight:600;flex-shrink:0}
.methcard-d{color:var(--muted);font-size:var(--t-sm);line-height:1.5;margin-bottom:10px}
.methcard-when{color:var(--faint);font-size:var(--t-sm);line-height:1.5;margin-bottom:10px}
.methcard-when b{color:var(--muted);font-weight:600}
.step-pills{display:flex;flex-wrap:wrap;gap:5px}
.step-pill{font-size:var(--t-xs,11px);color:var(--ink);background:var(--panel-2);border:1px solid var(--line-2);border-radius:20px;padding:2px 9px}
.ddphases{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-top:6px}
.ddphase{border:1px solid var(--line-2);border-radius:var(--radius-md,10px);padding:13px 15px;background:var(--panel);border-top:3px solid var(--line)}
.ddphase.diverge{border-top-color:var(--accent)}
.ddphase.converge{border-top-color:var(--amber,#d08700)}
.dd-rhythm{font-size:var(--t-xs,11px);font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--faint)}
.dd-name{font-weight:650;font-size:var(--t-md);letter-spacing:-.01em;margin:3px 0 6px}
.dd-intent{color:var(--muted)}.dd-intent p{margin:0;max-width:none}
.plays{display:flex;flex-direction:column;gap:0}
.play{display:flex;gap:16px;align-items:baseline;padding:11px 0;border-bottom:1px solid var(--line-2)}
.play:last-child{border-bottom:0}
.play-l{flex-shrink:0;min-width:210px;display:flex;flex-direction:column;gap:2px}
.play-name{font-weight:600;font-size:var(--t-sm);color:var(--ink)}
.play-code{font-family:var(--mono,'Geist Mono',monospace);font-size:var(--t-xs,11px);color:var(--accent)}
.play-desc{color:var(--muted);font-size:var(--t-sm);line-height:1.6}.play-desc strong{color:var(--ink)}

/* ==== MCP reference: two-level taxonomy (super-group index → domains → tools) ==== */
.mcp-superindex{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px;margin:22px 0 8px}

.mcp-super-card-h{display:flex;align-items:baseline;justify-content:space-between;gap:8px}
.mcp-super-card-t{font-weight:650;font-size:var(--t-md);letter-spacing:-.01em}
.mcp-super-card-n{flex-shrink:0;font-size:var(--t-xs,11px);font-weight:700;color:var(--accent);background:var(--panel-2);border-radius:20px;padding:1px 8px}
.mcp-super-card-d{color:var(--muted);font-size:var(--t-sm);line-height:1.5;margin:4px 0 10px}
.mcp-pills{display:flex;flex-wrap:wrap;gap:6px}
.mcp-pill{display:inline-flex;align-items:center;gap:5px;font-size:var(--t-xs,11px);font-weight:500;color:var(--ink);background:var(--panel-2);border:1px solid var(--line-2);border-radius:20px;padding:2px 9px;text-decoration:none;transition:border-color 110ms}
.mcp-pill:hover{border-color:var(--accent)}
.mcp-pill-c{color:var(--faint);font-weight:700}
.mcp-super{margin-top:44px;scroll-margin-top:16px}
.mcp-super-h{font-size:var(--t-lg);font-weight:650;letter-spacing:-.02em;margin:0 0 4px;padding-bottom:10px;border-bottom:2px solid var(--line)}
.mcp-domain{margin-top:26px;scroll-margin-top:16px}
.mcp-domain-h{display:flex;align-items:baseline;gap:10px;margin-bottom:11px}
.mcp-domain-t{font-size:var(--t-md);font-weight:650;letter-spacing:-.01em}
.mcp-domain-c{flex-shrink:0;font-size:var(--t-xs,11px);font-weight:700;color:var(--accent);background:var(--panel-2);border-radius:20px;padding:1px 8px}
.mcp-domain-d{color:var(--muted);font-size:var(--t-sm)}
.mcp-tools{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:8px}
.mcp-tool{border:1px solid var(--line-2);border-radius:var(--radius-sm);padding:9px 12px;background:var(--panel)}
.mcp-tool-n{display:inline-block;font-family:var(--mono,'Geist Mono',monospace);font-size:var(--t-sm);font-weight:600;color:var(--accent);margin-bottom:3px}
.mcp-tool-d{display:block;color:var(--muted);font-size:var(--t-sm);line-height:1.5}
.mcp-kind{font-size:var(--t-xs,10px);text-transform:uppercase;letter-spacing:.04em;color:var(--faint);font-weight:700;margin-right:2px}

/* ==== Documentation: prev/next footer ==== */
.doc-pn{display:flex;justify-content:space-between;gap:12px;margin-top:48px;padding-top:20px;border-top:1px solid var(--line)}
.pn{display:flex;flex-direction:column;gap:3px;text-decoration:none;min-width:160px}
.pn.next{text-align:right;align-items:flex-end}
.pn-eye{font-size:var(--t-xs,11px);text-transform:uppercase;letter-spacing:.05em;color:var(--faint);font-weight:600}
.pn-lab{display:flex;align-items:center;gap:5px;color:var(--ink);font-weight:600;font-size:var(--t-sm);transition:color 120ms}
.pn:hover .pn-lab{color:var(--accent)}

@media(max-width:900px){.doc-toc{display:none}.doc-wrap{gap:0}.flow-arrow{display:none}.flow,.cyc{gap:10px}}
""")
