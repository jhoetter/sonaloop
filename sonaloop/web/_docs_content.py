"""Documentation hub CONTENT — the bilingual data constants + co-located CSS.

Split out of `_docs.py` purely to keep each module under the LOC bar (the rendering logic and
routes live in `_docs.py`). Pure data: every (de, en) tuple is indexed by `li` (0=de, 1=en) at
render time by the page builders. No rendering happens here.
"""
from __future__ import annotations

from . import _docs_styles as _docs_styles  # noqa: F401  (registers hub styles)

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
    ("network",
     ("Workspace-isoliert", "Workspace-isolated"),
     ("In Sonaloop Cloud bleibt jeder Datensatz in seinem Workspace. Mitglieder kommen über eine "
      "adressierte, einmalige Einladung und eine verifizierte E-Mail-Identität hinein — nie automatisch "
      "über eine ganze Domain. Admins können den aktiven Workspace vorübergehend mit den Rechten eines "
      "regulären Mitglieds ansehen; ihre dauerhafte Rolle bleibt dabei unverändert. Passwörter verwaltet "
      "der konfigurierte Login-Anbieter, nicht Sonaloop.",
      "In Sonaloop Cloud, every record stays inside its workspace. Members enter through an addressed, "
      "single-use invitation and a verified email identity — never automatically through an entire "
      "domain. Admins can temporarily inspect the active workspace with a regular member's permissions; "
      "their persistent role remains unchanged. Passwords are managed by the configured identity provider, "
      "not by Sonaloop.")),
    ("target",
     ("Claims bleiben ehrlich", "Claims stay honest"),
     ("Reaction Tests starten mit einem versionierten **Product Understanding** aus echten Screens, "
      "Flows oder Sessions. Remote-Screens werden direkt hochgeladen, vorab dekodiert und gescannt "
      "und als exakte, unveränderliche Flow-Version mit vollständiger Screen-Checkliste eingefroren. "
      "Jede Aussage bleibt als beobachtet, memory-geerdet, abgeleitet, simuliert "
      "oder unbelegt sichtbar. Ein Screenshot zeigt Produktzustand — nie beobachtetes Nutzerverhalten.",
      "Reaction Tests begin with versioned **Product Understanding** from real screens, flows, or "
      "sessions. Remote screens are uploaded directly, decoded and scanned before admission, then "
      "frozen as one exact immutable flow version with a complete screen checklist. Every claim stays "
      "visibly observed, memory-grounded, inferred, simulated, or "
      "unsupported. A screenshot shows product state — never observed user behavior.")),
    ("personas",
     ("Kohorten bleiben unabhängig", "Cohorts stay independent"),
     ("Vor einem Reaction Test prüft Sonaloop serverseitig Gedächtnistiefe, Herkunft, Profilalter, "
      "Hypothesen-Überlappung und mindestens eine skeptische, gleichgültige oder fachfremde "
      "Gegenstimme mit exaktem Zitat aus ihrem unabhängigen Vor-Projekt-Kontext. Produktstimulus "
      "und unabhängiger Zielkontext bleiben getrennt; hohe Überlappung wird auch bei tiefem Gedächtnis nicht ignoriert. Dünne oder "
      "zirkuläre Personas erzeugen echte Vertiefungs-/Neuauswahl-Arbeit; ein expliziter Override "
      "bleibt als Report-Einschränkung sichtbar.",
      "Before a Reaction Test, Sonaloop checks memory depth, provenance, profile age, hypothesis "
      "overlap, and at least one skeptical, indifferent, or non-target countervoice grounded by an "
      "exact quote from independent pre-project context. Product stimulus and independent target "
      "context stay separate; deep memory never waives high overlap. Thin or circular personas "
      "create real deepening/reselection work; an explicit override remains visible as a report "
      "limitation.")),
    ("activity",
     ("Modelle unter demselben Vertrag", "Models under one contract"),
     ("Provider werden mit denselben versionierten Aufgaben, Tools, Assets, Budgets und festen "
      "Qualitätsschwellen geprüft. Beim Reaction Test sind auch die zwei Council-To-dos "
      "(Verständnis sowie Vertrauen/Handlungsbereitschaft) Teil der Methodik; das Modell muss die "
      "Act-Schritte nicht erraten. Ein stärkeres Modell oder menschliche Prüfung kann helfen — "
      "Evidenz- und Completion-Gates werden dafür nie gelockert.",
      "Providers are tested with the same versioned tasks, tools, assets, budgets, and fixed quality "
      "thresholds. Reaction Test also declares its two Council todos (comprehension and trust/action "
      "readiness) in the methodology, so the model does not have to invent the Act lane. A stronger "
      "model or human review may help, but evidence and completion gates are "
      "never relaxed.")),
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
     "what": ("Eine Website, ein externer Prototyp oder eine A/B-Variante als **Stimulus** — "
              "inklusive Capture-Status und Snapshot, wenn erfassbar.",
              "A website, external prototype or A/B variant as a **stimulus** — with capture status "
              "and a snapshot when available."),
     "why": ("Personas reagieren auf echtes Material, nicht auf eine Nacherzählung. Referenzen sind Links/Snapshots, "
             "keine hochgeladenen Dateien und kein Testergebnis; das Ergebnis lebt in Council oder Session.",
             "Personas react to real material, not a retelling. References are links/snapshots, not uploaded files "
             "and not a test result; the result lives in a council or session.")},
    {"art": "prototype", "icon": "prototype", "name": "prototypes_h", "group": "evidence",
     "what": ("Ein testbares Projektobjekt — App, Flow, Dashboard, Cards, Comparison, Model oder Journey —, "
              "das Sonaloop ausführen, rendern und mit Sessions verbinden kann.",
              "A testable project object — app, flow, dashboard, cards, comparison, model or journey — "
              "that Sonaloop can run, render and connect to sessions."),
     "why": ("Geerdete Reaktionen auf etwas *Echtes* statt auf eine Beschreibung — du siehst, was funktioniert, bevor du baust.",
             "Grounded reactions to something *real*, not a description — you see what works before you build.")},
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
    {"art": "cloud_github", "icon": "network", "name": None, "group": "evidence",
     "what": ("Eine Cloud-Automation, die GitHub PRs, Issues, Comment-Commands und Preview-Deployments "
              "in Sonaloop-Reaction-Tests übersetzt und die Ergebnisse als Check Run, Kommentar, Label "
              "oder Patch-PR zurückschreibt.",
              "A Cloud automation that turns GitHub PRs, issues, comment commands and preview deployments "
              "into Sonaloop reaction tests, then writes results back as a Check Run, comment, label or "
              "Patch PR."),
     "why": ("User-Reaktionen wandern direkt in den Entwicklungsworkflow: Landing Pages, Feature-Issues "
             "und UI-Änderungen bekommen ein persona-geerdetes Signal, bevor sie shippen.",
             "User reaction moves directly into the development workflow: landing pages, feature issues "
             "and UI changes get a persona-grounded signal before they ship.")},
    {"art": "asset", "icon": "file", "name": "assets_h", "group": "evidence",
     "what": ("Eine echte Datei im Projekt: Screenshot, Dokument, Export oder erzeugtes Deliverable — mit "
              "Herkunft und Richtung. In der mandantenfähigen Cloud laufen Vorschau und Download "
              "über eine authentifizierte Route des aktiven Workspace; ungeschützte Datei-Rohpfade "
              "bleiben gesperrt. Remote-Screens kommen nur als begrenzter Direktupload hinein: ohne URL-"
              "Import, mit Bildprüfung, Scan, SHA-256 und Run-/Workspace-Bindung.",
              "A real file in the project: screenshot, document, export or generated deliverable — with "
              "provenance and direction. In multi-tenant Cloud its preview and download use an "
              "authenticated active-workspace route; unprotected raw file paths remain blocked. Remote "
              "screens enter only through a bounded direct upload: no URL import, with image validation, "
              "scan, SHA-256 and run/workspace binding."),
     "why": ("Assets sind das Material für Evidence, Walkthrough-Screens und Deliverables. Sie sind Dateien, "
             "nicht Council-Referenzen.",
             "Assets are the material behind evidence, walkthrough screens and deliverables. They are files, not council references.")},
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
                   "Avatar-Pfad + Provenienz; in der Cloud wird das Bild nur über die aktive Workspace-Grenze ausgeliefert",
                   "Das **Gedächtnis** liegt in eigenen, zeit-indizierten Records (s. u.)"],
                  ["**SOUL** — the authoritative identity (role, company context, values, quirks)",
                   "Goals, constraints and pain points",
                   "Avatar path + provenance; Cloud serves the image only through the active workspace boundary",
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
                   "Design-System-Kontext — Tokens, Fonts, Radius, Spacing, Density, Chartfarben und optionale Logos kommen dynamisch aus dem aktiven Workspace oder dem Sonaloop-Default",
                   "Optionaler Link zum Projekt + zur Notiz, aus der er gebaut wurde",
                   "Eine **Session** ist eine Persona, die ihn benutzt — als `statements`, geerdet in "
                   "beobachteten Prototyp-States"],
                  ["Name + version + `tags` (fidelity, e.g. lofi/midfi/hifi)",
                   "`path` / `entry` / `run` — how the runnable build is launched",
                   "Design-system context — tokens, fonts, radius, spacing, density, chart colors and optional logos dynamically come from the active workspace or the Sonaloop default",
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
    (("Produkt verstehen", "Understand the product"),
     ("Vor einem Reaction Test werden Ziel, Revision, Routen, Flows, Zustände und unbekannte "
      "Fähigkeiten gegen echte Evidenz inventarisiert — unbekannt ist besser als erraten.",
      "Before a Reaction Test, target, revision, routes, flows, states and unknown capabilities are "
      "inventoried against real evidence — unknown is better than guessed.")),
    (("Rahmen", "Frame"),
     ("Eine Forschungsfrage stellen, geerdet in der Erinnerung der Personas.",
      "Pose a research question, grounded in the personas' memory.")),
    (("Evidenz sammeln", "Gather evidence"),
     ("Councils laufen lassen, Prototypen testen, Signale festhalten.",
      "Run councils, test prototypes, capture signals.")),
    (("Prüfen", "Verify"),
     ("Erst schließen, wenn die Evidenz die Gates und zwei unabhängige Abschlussprüfungen erfüllt — "
      "ein Agent kann einen offenen Run nicht einfach als fertig markieren.",
      "Only close once the evidence clears the gates and two independent completion checks — "
      "an agent cannot simply mark an open run as finished.")),
]

# ============================ Working live (the inspector page) ============================ #
# What the inspector itself offers the human at the keyboard — the features you SEE, in plain
# language. Shape: (anchor, icon, (title_de, title_en), (body_de, body_en)); bodies are Markdown.
INSPECTOR_SECTIONS = [
    ("orientation", "book",
     ("Orientierung: vier Punkte, ein Modell", "Getting around: four items, one model"),
     ("Die obere Seitenleiste hat genau **vier** Einträge: **Jobs · Methodiken · Formate · Personas** "
      "(Activity, Einstellungen & Doku sitzen im User-Menü unten links). Das Denkmodell ist überall dasselbe: *Job → "
      "Phasen → Zeilen; Klick = Seitenpanel.* Der **Job ist das Zuhause** — alles, was eine Studie "
      "erzeugt oder benutzt (offene Fragen, Referenzen, Councils, Reports, Prototypen, "
      "Sessions, Umfragen, Hypothesen, Entscheidungen, Notizen, Assets), ist eine Zeile in "
      "seiner Phase. **Formate** ist der jobübergreifende Browser über dieselben Primitives. "
      "Sie ist als Arbeitslandkarte gruppiert: **Frame** (offene Fragen, Hypothesen), "
      "**Material** (Referenzen, Assets, Prototypen), **Ask** (Councils, Surveys), **Test** "
      "(Sessions), **Capture** (Notes) und **Conclude** (Reports, "
      "Decisions). **Formate** verfeinern ein Primitive, ohne neue Dinge zu erfinden: "
      "Red-Team und Head-to-head sind Council-Formate, Website/externer Prototyp/A-B "
      "sind Referenz-Formate, und Prototyp-Formen sind Apps, Flows, Dashboards, Cards, "
      "Comparisons, Models, Journeys oder freie Canvases fuer Raeume, Karten, Boards und "
      "Simulationen. Die Namensregel: **Referenzen** sind Quellenlinks oder "
      "Snapshots im Raum; ein externer Prototyp bleibt eine Referenz, wenn Sonaloop nur darauf "
      "zeigt. **Prototypen** sind testbare Projektobjekte, die Sonaloop ausführen, rendern "
      "und mit Sessions verbinden kann. **A/B-Varianten** sind Stimuli; das eigentliche "
      "Testergebnis lebt in Council oder Session. **Assets** sind echte Dateien; **Sessions** "
      "sind Nutzungsspuren. **Assets** — empfangene "
      "Input-Dateien (Evidenz, via MCP angehängt) und von der Software erzeugte Dokumente "
      "(Deliverables) — erscheinen überall als **Datei-Karten**: Typ-Badge oder Vorschaubild, "
      "Dateiname mit Endung, Größe · Datum, genau ein Download/Öffnen-Symbol; sie haben eigene "
      "Detailseiten mit Herkunft (Quelle, Richtung, ersetzte Versionen). Im Projekt bleiben "
      "eingehende Dateien als **Assets**-Gruppe in der Outline sichtbar; alle Assets findest du "
      "zusätzlich im Formats-Browser unter Assets. "
      "Ein Klick auf eine Zeile öffnet die "
      "**ganze Detailseite als Seitenpanel** (Notion-Stil): die Liste bleibt dahinter sichtbar, "
      "die URL bleibt die Listen-URL und bekommt `?d=<Detailpfad>` — neu laden oder teilen "
      "reproduziert exakt diese Ansicht (Liste + offenes Panel). Das ⤢-Symbol wechselt zur "
      "vollen Seite (die kanonische Detail-URL, die direkt geladen weiterhin die volle Seite "
      "zeigt), Esc/Zurück bringt die Liste samt URL zurück. Den **Run-Status** eines Projekts zeigt ein Chip im "
      "Projekt-Kopf (verlinkt aufs Run-Journal). Hover-Bezüge in der Projektliste folgen dem "
      "Plan-DAG: Ein erzeugter Prototyp oder ein Modell zeigt seine Inputs aus der vorherigen "
      "Evidenz, auch wenn ein Methodik-Frame dazwischenliegt.",
      "The upper sidebar has exactly **four** items: **Jobs · Methodologies · Formats · Personas** "
      "(Activity, settings & docs live in the bottom-left user menu). One mental model runs the whole app: *job → "
      "phases → rows; click = slide-over.* The **job is the home** — everything a study produces "
      "or uses (open questions, references, councils, reports, prototypes, sessions, surveys, "
      "hypotheses, decisions, notes, assets) is a row in its phase. **Formats** is the "
      "cross-job browser over those same primitives. It is grouped as a work map: "
      "**Frame** (open questions, hypotheses), **Material** (references, assets, prototypes), **Ask** "
      "(councils, surveys), **Test** (sessions), **Capture** (notes), "
      "and **Conclude** (reports, decisions). **Formats** refine a primitive without "
      "creating new things: red-team and head-to-head are council formats, website/external "
      "prototype/A-B are reference formats, and prototype forms include apps, flows, dashboards, "
      "cards, comparisons, models, journeys and freeform canvases for rooms, maps, boards and "
      "simulations. Naming rule: **References** are source links or "
      "snapshots placed in the room; an external prototype stays a reference when Sonaloop only "
      "points at it. **Prototypes** are testable project objects Sonaloop can run, render or pair "
      "with sessions. **A/B variants** are stimuli; the actual test result lives in a council or "
      "session. **Assets** are real files; **Sessions** are usage traces. **Assets** — input files received (evidence, attached via MCP) and "
      "documents the software generated (deliverables) — show up everywhere as **file cards**: "
      "type badge or image thumbnail, filename with extension, size · date, exactly one "
      "download/open icon; they have their own detail pages with provenance (source, direction, "
      "superseded versions). Inside a job, incoming files stay visible as an **Assets** group in "
      "the outline; all assets are also available in the Formats browser under Assets. "
      "Clicking a row opens the **full detail page as a slide-over** (Notion-style): "
      "the list stays visible behind it, and the URL stays the list URL plus `?d=<detail "
      "path>` — reloading or sharing it reproduces exactly this view (list + open panel). "
      "The ⤢ control expands to the full page (the canonical detail URL, which still renders "
      "full-page when loaded directly), and Esc/back restores the list and its URL. A project's "
      "**run state** shows as a chip in the project header (linking to the run journal). Hover "
      "relations in the project outline follow the plan DAG: a generated prototype or model shows "
      "its inputs from prior evidence, even when a methodology frame sits between them.")),
    ("examples", "package",
     ("Beispielprojekte", "Example projects"),
     ("Fertige Demo-Studien liegen bei — darunter ein Onboarding-Showcase, eine B2B-Positioning-Studie "
      "und eine B2C-Pricing-Studie "
      "(mit Preis-Leiter und Head-to-Head). Im lokalen/single-user Inspector zeigt eine leere "
      "Datenbank je einen **„Beispiel laden“**-Button; dein Agent kann sie auch per `load_example` "
      "laden, `sonaloop load-example` ebenso. In der geteilten, Postgres-row-tenanted Cloud ist "
      "der Browser-Loader des Onboarding-Showcases standardmäßig deaktiviert. Laden ist "
      "idempotent (kein Duplizieren beim erneuten Laden), und "
      "`remove_example` entfernt **nur** die Daten des Beispiels — nie deine eigenen.",
      "Finished demo studies ship with Sonaloop — including an onboarding showcase, a B2B positioning study and a B2C pricing study "
      "(with a willingness-to-pay ladder and a head-to-head). In the local/single-user inspector, "
      "an empty database shows a **“Load example”** button for each; your agent can load them via "
      "`load_example`, or `sonaloop load-example` from the CLI. Shared, Postgres row-tenanted Cloud "
      "disables the onboarding showcase's browser loader by default. Loading is idempotent "
      "(re-loading never duplicates), and "
      "`remove_example` removes **only** the example's data — never yours.")),
    ("live", "zap",
     ("Live-Aktivität", "Live activity"),
     ("Jede Inspector-Seite ist live verbunden: nimmt dein Agent etwas auf (ein Council, eine Persona, "
      "einen Report), erscheint ein kleiner **Toast** mit Link — und die offene Seite lädt sich selbst "
      "neu, wenn es sie betrifft. Der **Activity**-Feed (`g` `a`) listet alles Zuletzt-Passierte "
      "chronologisch. Beim Löschen eines Projekts verschwinden auch dessen veraltete Activity-Links. "
      "Du schaust zu, während die Studie entsteht — kein manuelles Neuladen.",
      "Every inspector page is live: when your agent records something (a council, a persona, a report) "
      "a small **toast** appears with a link — and the page you're on reloads itself when it's "
      "affected. The **Activity** feed (`g` `a`) lists everything recent in order. Deleting a project "
      "also removes its stale Activity links. You watch the study "
      "come together — no manual refreshing.")),
    ("runs", "play",
     ("Laufende Runs", "Runs"),
     ("Oben in der Leiste zeigt ein Status-Punkt, ob gerade Studien **aktiv** laufen — er wird "
      "**gelb**, wenn ein Projekt feststeckt (das stille Scheitern soll laut sein). Im "
      "Projekt-Kopf trägt jedes Projekt seinen eigenen **Run-Chip** (Zustand · letzte Aktivität). "
      "Wenn der Server beim ersten Anlegen einen authentifizierten Akteur gebunden hat, zeigt der "
      "Projekt-Kopf außerdem dessen unveränderlichen Anzeigenamen. Retries und spätere Bearbeiter "
      "überschreiben ihn nicht; alte oder lokale Jobs ohne Attribution bleiben ohne Zuschreibung. "
      "Beide verlinken auf das **Run-Journal** (`g` `r`) — eine bewusst schlichte Telemetrie-Seite "
      "mit jedem Projekt-Run und seiner letzten Aktivität. **Läuft · stockt · Engine-abgeschlossen · "
      "Ausgabe unverifiziert** sind getrennte Zustände. Bei einem Problem nennt Sonaloop die "
      "einen verständlichen Wiederaufnahme-Hinweis. Erst wenn **Technische Diagnose** bewusst "
      "geöffnet wird, erscheinen die unerfüllte Invariante, die letzte sichere Operation, genau "
      "ein sicherer nächster Schritt und eine redigierte Support-Trace-Referenz; als "
      "Navigationspunkt taucht die Seite nicht "
      "auf. Verbindungs-Retries verwenden dieselbe Projekt-, Run- und Schritt-Operation erneut: Sie setzen "
      "den vorhandenen Run fort, statt doppelte Jobs oder Journalzeilen anzulegen. "
      "Ein Job kann serverseitig nur **einen aktiven Run** besitzen: Ein weiterer Start nennt "
      "die bestehende Run-ID und führt zur sicheren Fortsetzung. Löschen, Archivieren, Ersetzen und "
      "Run-Start teilen dieselbe prozessübergreifende Projektsperre; ein geschlossener oder gelöschter "
      "Job kann daher keinen neuen Run erhalten. Ein Hard-Delete ist nur für nie gestartete Container "
      "ohne Run-Historie möglich; Jobs mit Journal werden evidenzerhaltend archiviert. "
      "Die Aufmerksamkeitsansicht unterscheidet "
      "zwischen einem angelegten Job, dessen Run noch nie gestartet wurde, und einem still gewordenen "
      "Run, der fortgesetzt werden kann. In Cloud ruft ein Host mit exakter Job-ID direkt "
      "`continue_research_job` auf; ohne ID sucht er mit `list_unfinished_research_jobs`. Genau ein "
      "Treffer wird fortgesetzt, mehrere erfordern eine Auswahl. Die Fortsetzung nutzt den einzigen "
      "aktiven Run oder legt regelgebunden genau einen fehlenden beziehungsweise separaten "
      "Reparatur-Run an; sie legt niemals ein Ersatzprojekt an. "
      "Beim Cloud-Start gewinnt eine explizite Methodik immer. Sonst wählt `auto` aus "
      "datengetragenen Signalen der live Methodik-Registry; bei einem unklaren Ergebnis stellt "
      "Sonaloop genau eine Rückfrage und legt noch kein Projekt an. **Freiform** bleibt möglich, "
      "aber nur als bewusste Auswahl. Entscheidung, Confidence, Kandidaten und Override bleiben im Trace. "
      "Im Cloud-Front-Door fängt ein begrenzter, workspace-gebundener Request-Fingerprint sogar "
      "gleichzeitige Retries mit versehentlich neuen Attempt-IDs ab; das Zeitfenster beginnt beim "
      "ersten Auftrag und wird durch Aliase nicht verlängert. Eine absichtlich identische zweite "
      "Studie muss mit `new_job_intent=true` und einer frischen ID markiert werden. "
      "Jeder Schritt trägt ein begrenztes Dispatch-Token mit Workspace-, Run-, Task-, Input- und Output-Vertrag; ein "
      "identischer Retry liefert dasselbe Ergebnis, eine Inhaltsänderung nach dem Checkpoint scheitert. "
      "Das Speichern verknüpft und checkpointet den Schritt reparierbar genau einmal. Der Trace zeigt Sonaloops MCP-Grenze und Journal — nicht "
      "verdeckte Provider-Prompts, Reasoning, Berechtigungsdialoge oder host-interne Retries. "
      "Ein gültiger W3C-Trace wird fortgeführt und jeder Toolcall erhält einen eigenen Span; ohne "
      "Trace-Kontext bleibt jeder Call ein ehrlicher Interaktions-Trace, während der Run sie als "
      "PostHog-Session und MCP-Konversation zusammenhält. Cohort-Preflight-Ergebnisse erscheinen "
      "nur als geschlossene, filterbare Werte — niemals als freie Ergebnis-Texte. "
      "Cloud-Trace-Inhalt bleibt standardmäßig redigiert: Erst Deployment-Schalter, eine "
      "versionierte Owner-Freigabe je Workspace-Zweck **und** die explizite Call/Job-Zustimmung "
      "dürfen begrenzten Inhalt erfassen; PostHog und Hosted-Generations sind getrennte Zwecke. "
      "Widerruf gilt sofort für neue Receipts, alte Receipts ohne Policy-Snapshot bleiben Metadaten. "
      "Explizites Ersetzen oder Archivieren bewahrt Evidenz; es löscht nichts.",
      "A status dot in the top bar shows whether studies are **running** right now — it turns "
      "**amber** when a project is stalled (the silent failure mode should be loud). In the "
      "project header every project carries its own **run chip** (state · last activity). "
      "When the server bound an authenticated actor at the first create, the project header also "
      "shows that immutable display name. Retries and later editors cannot replace it; legacy or "
      "local jobs without attribution remain unattributed. Both "
      "link to the **run journal** (`g` `r`) — a deliberately plain telemetry page listing every "
      "project run with its last activity. **Running · stalled · engine-finished · output "
      "unverified** are distinct states. A problem first shows a human-readable recovery hint. "
      "The unmet invariant, last safe operation, one safe next action and redacted support-trace "
      "reference appear only after deliberately opening **Technical diagnostics**; it isn't a nav item. Connection retries reuse the same "
      "project and step operation: they resume the existing run instead of creating duplicate jobs "
      "or journal rows. "
      "A job can own only **one active run** at the server boundary: another start names the existing "
      "run id and directs the host to the safe continuation. Delete, archive, supersede and run creation "
      "share the same cross-process project lock, so a closed or deleted job cannot acquire a new run. "
      "Hard delete is limited to never-started containers without run history; jobs with a journal "
      "must be preserved through archive. "
      "The attention view distinguishes a created job whose run never started from a quiet run that can "
      "be resumed. In Cloud a host with the exact job id calls `continue_research_job` directly; without "
      "an id it searches with `list_unfinished_research_jobs`. One match proceeds, while several require "
      "a user choice. Continuation uses the sole active run or creates exactly one missing/separate repair "
      "run under the governed rules; it never creates a replacement project. "
      "At Cloud ingress an explicit methodology always wins. Otherwise `auto` ranks data-authored "
      "signals from the live methodology registry; an ambiguous result asks exactly one question and "
      "creates no project. **Freeform** remains available only as a deliberate choice. The trace keeps "
      "the decision, confidence, candidates and any override. "
      "Cloud's bounded, workspace-bound front-door fingerprint also collapses concurrent retries "
      "that accidentally carry fresh attempt ids; the window starts at first "
      "ingress and aliases do not extend it. An intentional identical second study requires "
      "`new_job_intent=true` and a fresh id. Each step carries a scoped dispatch token; recording its result links and "
      "checkpoints it repairably once, even after a retry. The token binds workspace, run, task, input "
      "and output contract; identical replay returns the same result and changed post-checkpoint content "
      "fails closed. Critic retries also remain one independent completion check. "
      "The trace covers Sonaloop's MCP boundary and journal, not hidden provider prompts, reasoning, "
      "permission dialogs or host-internal retries. Cloud trace content stays redacted by default: "
      "A valid W3C trace continues and every tool call gets its own span; without trace context, "
      "each call remains an honest interaction trace while the run groups them as a PostHog session "
      "and MCP conversation. Cohort-preflight results appear only as a closed filterable vocabulary, "
      "never as free-form result text. "
      "bounded content requires deployment switches, a versioned owner approval for each workspace "
      "purpose **and** explicit call/job consent; PostHog and hosted generations are separate purposes. "
      "Revocation applies immediately to new receipts, while legacy receipts without a policy snapshot "
      "stay metadata-only. Explicit superseding or archiving preserves evidence; "
      "it deletes nothing.")),
    ("keyboard", "command",
     ("Tastatur & Palette", "Keyboard & palette"),
     ("`?` öffnet das Shortcut-Cheat-Sheet. **⌘K / Ctrl+K** öffnet die Befehls-Palette: zuletzt "
      "besuchte Einträge, Navigation (mit Formaten als aufklappbarem Eintrag) und Aktionen — "
      "und beim Tippen eine Suche über alles (Personas, Councils, Reports, Sessions, Hypothesen, "
      "Entscheidungen, Umfragen …), nach Art gruppiert mit Projekt und Datum. Navigation per Chords: `g` `h` Home, `g` `p` Personas, `g` `c` "
      "Councils, `g` `s` Reports, `g` `a` Activity, `g` `r` Runs, `g` `d` Doku. In Listen und im "
      "Projekt-Outline: `j`/`k` bewegt den Fokus, `Enter` öffnet die Zeile als **Seitenpanel** "
      "(volle Detailseite, echte URL), `o` öffnet sie direkt als ganze Seite, `Esc` schließt "
      "das Panel. Auf Detailseiten blättern `[`/`]` zum Nachbarn. Beim Tippen in Felder ist alles deaktiviert.",
      "`?` opens the shortcut cheat sheet. **⌘K / Ctrl+K** opens the command palette: your recently "
      "visited records, navigation (with Formats as one expandable entry) and actions — and, as "
      "you type, a search across everything (personas, councils, reports, sessions, hypotheses, "
      "decisions, surveys …), grouped by kind with project and date. Navigate with chords: `g` `h` home, `g` `p` personas, `g` `c` "
      "councils, `g` `s` reports, `g` `a` activity, `g` `r` runs, `g` `d` docs. In lists and the "
      "project outline `j`/`k` move focus, `Enter` opens the row as a **slide-over** (the full "
      "detail page, real URL), `o` opens it straight as a full page, and `Esc` closes the "
      "panel. On detail pages `[`/`]` step to the sibling record. Everything is disabled while you type in a field.")),
    ("tour", "compass",
     ("Produkt-Tour", "Product tour"),
     ("Die optionale Tour startet **nie von selbst** und ist im lokalen/single-user Core "
      "standardmäßig verfügbar. Wenn du **„Tour starten“** wählst, lädt sie bei "
      "Bedarf das Showcase-Beispielprojekt und führt dann im Projektkontext durch echte Primitives: "
      "offene Frage, Referenz, Council, Survey, Report, Prototype, Session, Hypothese, "
      "Entscheidung, Notes, Assets und Formate. "
      "`Esc` beendet sie jederzeit. In einer geteilten, Postgres-row-tenanted Cloud sind Tour und "
      "Onboarding-Showcase-Browser-Loader standardmäßig aus; "
      "`SONALOOP_PRODUCT_TOUR_ENABLED` kann diese Voreinstellung explizit überschreiben.",
      "The optional tour **never auto-starts** and is available by default in local/single-user "
      "Core. When you choose **“Take the tour”**, it loads the "
      "showcase example project if needed, then walks real primitives in project context: open "
      "question, reference, council, survey, report, prototype, session, hypothesis, decision, "
      "notes, assets, and Formats. `Esc` "
      "ends it any time. In shared, Postgres row-tenanted Cloud, the tour and onboarding-showcase "
      "browser loader are off by default; `SONALOOP_PRODUCT_TOUR_ENABLED` explicitly overrides "
      "that default.")),
    ("editing", "pencil",
     ("Was du bearbeiten kannst", "What you can edit"),
     ("Der Inspector ist eine Lese-Oberfläche mit einer klaren Grenze: **ansehen und bearbeiten, "
      "nie anlegen.** Neue Projekte, Notizen oder Sections entstehen ausschließlich über deinen "
      "Agenten (MCP/CLI) — die UI bietet dafür bewusst keinen Button. Bearbeiten und Löschen "
      "wohnen im **„…“-Menü**, das jeder Seitenkopf trägt (auch im Panel): **Bearbeiten** öffnet "
      "einen Dialog direkt über der Seite — Projekt-Titel, Goal und Icon; Notiz- und Section-Metadaten sowie "
      "Persona-Metadaten (Name, Rolle, Segment, Branche). Projekt-Icons kannst du dort aus "
      "dem bestehenden Katalog wählen; ein Klick auf das Header-Icon öffnet denselben Dialog "
      "direkt am Icon-Picker. Custom-SVGs erzeugt/setzt dein Agent per MCP/CLI. "
      "**Löschen** öffnet einen "
      "Bestätigungs-Dialog (bei Projekten und Personas tippst du den Namen). Generierter Text — "
      "Councils, Reports, Prototypen — bleibt unantastbar; Erinnerungen, SOULs und Evidenz komplett.",
      "The inspector is a reading surface with one clear boundary: **inspect and edit, never "
      "create.** New projects, notes or sections come exclusively from your agent (MCP/CLI) — the "
      "UI deliberately offers no button for them. Edit and delete live in the **“…” menu** every "
      "page header carries (in the side panel too): **Edit** opens a dialog right over the page — "
      "project title, goal and icon; note and section metadata plus persona metadata (name, role, segment, industry). "
      "Project icons can be chosen there from the existing catalogue; clicking the header icon "
      "opens the same dialog directly at the icon picker. Custom SVGs are generated/set by your "
      "agent through MCP/CLI. **Delete** opens a confirm dialog (projects and personas ask you to type the name). "
      "Generated text — councils, reports, prototypes — stays untouchable; memories, SOULs and "
      "evidence entirely so.")),
    ("filtering", "filter",
     ("Filtern wie in Linear", "Filtering, Linear-style"),
     ("Job-Outline und Formate tragen eine **Filterleiste**: „Filter“ öffnet das Facetten-Menü "
      "(Typ, Phase, Persona, Status, Trace — in Formaten Job, Status, bei Assets Richtung) mit "
      "ehrlichen Treffer-Zahlen pro Wert. Innerhalb einer Facette gilt ODER, zwischen Facetten "
      "UND. Aktive Filter erscheinen als Chips mit ×; der Zustand lebt in der **URL** "
      "(`?kind=council,decision&phase=…`) — teilbar, verlinkbar, Reload-fest. Trifft ein Filter "
      "nichts, sagt die Seite das und bietet „zurücksetzen“ an.",
      "The job outline and Formats carry a **filter bar**: “Filter” opens the facet menu "
      "(kind, phase, persona, status, trace — in Formats job, status, plus direction on Assets) "
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
     ("Im User-Menü unten links sitzt **Feedback**: kurze Nachricht, optional deine E-Mail — die "
      "aktuelle Seite und die App-Version werden sichtbar mitgeschickt (nichts wird still gesammelt). "
      "Eingesendetes liest der Betreiber unter `/feedback` oder per `sonaloop feedback`; alternativ "
      "verlinkt das Formular ein vorausgefülltes GitHub-Issue.",
      "**Feedback** lives in the bottom-left user menu: a short message, optionally your email — the "
      "current page and app version are sent along visibly (nothing is collected silently). "
      "Submissions are read at `/feedback` or via `sonaloop feedback`; the form also links a "
      "prefilled GitHub issue as the public channel.")),
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

# Ready recipes — things you can ask your agent for. Shape: ((title_de, title_en), code, (desc_de, desc_en)).
RECIPES = [
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
     "Browsbare Guides und fertige Recipes.", "Browsable guides and ready recipes.",
     ["__extras__"]),
]



# ============================ Co-located CSS ============================ #
