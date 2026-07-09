---
description: Things 3 Todos, Projekte und Bereiche lesen, anlegen und aktualisieren. Nutzen, wenn nach offenen Aufgaben, dem Inbox-/Today-Stand oder Projektstruktur in Things 3 gefragt wird, oder wenn neue Todos/Projekte angelegt werden sollen.
when_to_use: Bei jeder Anfrage, die sich auf Things 3 / "meine Todos" / "meine Aufgaben" bezieht.
---

# Things 3 Skill

Dieses Plugin stellt den MCP-Server `things3` bereit, der lokal auf macOS läuft.

## Lesezugriff (kein Token nötig)
Direkter, read-only Zugriff auf die lokale Things-SQLite-Datenbank:
- `things_list_inbox`
- `things_list_today`
- `things_list_upcoming`
- `things_list_anytime`
- `things_list_someday`
- `things_list_projects`
- `things_list_areas`
- `things_search(query)`
- `things_get_todo(uuid)` — Details inkl. Notizen und Checklist-Items

## Schreibzugriff
- `things_add_todo(...)` und `things_add_project(...)` — funktionieren ohne Token (things:///add, things:///add-project).
- `things_update_todo(...)` und `things_complete_todo(...)` — benötigen einen Things-Auth-Token (things:///update), da Things aus Sicherheitsgründen Änderungen an bestehenden Objekten nur mit Token per URL-Scheme erlaubt.

Token holen: Things → Einstellungen → Allgemein → "Things-URLs aktivieren" → "Verwalten…". Der Token muss als Umgebungsvariable `THINGS_AUTH_TOKEN` gesetzt sein (z. B. in der Osaurus-MCP-Provider-Konfiguration für dieses Plugin, dort landet er im macOS Keychain).

## Hinweis zur Robustheit
Das Datenbankschema basiert auf dem seit Jahren stabilen, community-dokumentierten Things-3-Schema (u. a. verwendet von der `things.py`-Bibliothek). Es ist nicht offiziell von Cultured Code spezifiziert. Wenn Spaltennamen sich mit einem zukünftigen Things-Update ändern sollten, schlagen die Lesefunktionen mit einer klaren Fehlermeldung fehl statt falsche Daten zu liefern.
