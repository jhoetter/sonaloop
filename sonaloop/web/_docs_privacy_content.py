"""Bilingual Cloud privacy copy for the in-app documentation hub."""

from __future__ import annotations


CLOUD_PRIVACY_DE = (
    "In Sonaloop Cloud bleibt jeder Datensatz in seinem Workspace. Mitglieder kommen über eine "
    "adressierte, einmalige Einladung und eine verifizierte E-Mail-Identität hinein — nie automatisch "
    "über eine ganze Domain. Admins können den aktiven Workspace vorübergehend mit den Rechten eines "
    "regulären Mitglieds ansehen; ihre dauerhafte Rolle bleibt dabei unverändert. Passwörter verwaltet "
    "der konfigurierte Login-Anbieter, nicht Sonaloop. Bei neuen Cloud-Jobs zeigt die Übersicht den "
    "unveränderlichen, authentifizierten Ersteller. Ältere Jobs bleiben ohne Zuschreibung, solange "
    "nicht ein Workspace-Owner eine exakte Projekt-zu-Mitglied-Zuordnung ausdrücklich bestätigt; "
    "eine solche Support-Korrektur wird auditiert und nie aus Titeln oder späteren Bearbeitern erraten. "
    "Wenn Cloud beim ersten Anlegen zusätzlich einen bekannten MCP-Client beobachtet hat, ergänzt die "
    "Zeile ein festes `via Mistral`, `via ChatGPT`, `via Claude` oder ähnliches Label. Diese "
    "Connector-Beobachtung belegt weder das verborgene Modell noch den Inference-Anbieter; unbekannte "
    "oder widersprüchliche Clients bleiben ohne Label. Für die Betriebsanalyse kann Cloud "
    "erfolgreiche authentifizierte Ansichten und abgeschlossene Produktaktionen als "
    "pseudonymisierte, inhaltsfreie Ereignisse erfassen — etwa einen geöffneten Job, eine Session "
    "oder einen fertigen Run. Die Produktfunktionen senden dabei nicht direkt an einen Anbieter: "
    "ein austauschbarer Telemetrie-Dienst prüft feste Metadaten, legt sie im retry-fähigen Outbox "
    "ab und exportiert derzeit nach PostHog. Namen, E-Mails, Titel, URLs, Suchbegriffe und Research-Text "
    "werden nicht exportiert; eine ausgelieferte Ansicht belegt außerdem nicht, dass sie gelesen wurde."
)

CLOUD_PRIVACY_EN = (
    "In Sonaloop Cloud, every record stays inside its workspace. Members enter through an addressed, "
    "single-use invitation and a verified email identity — never automatically through an entire "
    "domain. Admins can temporarily inspect the active workspace with a regular member's permissions; "
    "their persistent role remains unchanged. Passwords are managed by the configured identity provider, "
    "not by Sonaloop. For new Cloud jobs, the overview shows the immutable authenticated creator. "
    "Older jobs remain unattributed unless a workspace owner explicitly attests an exact "
    "project-to-member mapping; that support correction is audited and never guessed from titles "
    "or later editors. When Cloud also observed a recognized MCP client on the first creation "
    "request, the byline adds a fixed `via Mistral`, `via ChatGPT`, `via Claude`, or similar label. "
    "That connector observation is not proof of the hidden model or inference provider; unknown or "
    "conflicting clients stay unlabeled. For operational analytics, Cloud may record successful "
    "authenticated views and completed product actions as pseudonymous, content-free events — for "
    "example an opened job, a session, or a finished run. Product functions do not send directly to "
    "a vendor: a replaceable telemetry service validates closed metadata, persists it in the "
    "retryable outbox, and currently exports to PostHog. Names, email addresses, titles, URLs, search "
    "terms and research text are not exported, and a delivered view is not proof it was actually read."
)
