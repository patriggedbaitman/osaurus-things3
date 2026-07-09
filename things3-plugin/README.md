# things3 — Claude-Plugin für Things 3

MCP-Server + Skill, der Things 3 in Osaurus (und jeden anderen Claude-Plugin-
bzw. MCP-fähigen Client) einbindet. Architektur orientiert sich am
Raycast-Things-Plugin:

| Operation | Mechanismus | Auth-Token nötig |
|---|---|---|
| Lesen (Inbox, Today, Upcoming, Projekte, Suche, Details) | direkter, read-only SQLite-Zugriff auf die lokale Things-DB | nein |
| Todo/Projekt anlegen | `things:///add`, `things:///add-project` URL-Scheme | nein |
| Bestehendes Todo ändern/abhaken | `things:///update` URL-Scheme | **ja** |

## Installation

### Voraussetzungen
- macOS mit Things 3 (mind. einmal gestartet, damit die DB existiert)
- Python 3 mit dem `mcp`-Paket:
  ```bash
  pip3 install --break-system-packages -r server/requirements.txt
  ```
- macOS-Berechtigung: Things muss unter Systemeinstellungen → Datenschutz &
  Sicherheit → Automation ggf. für das aufrufende Programm freigegeben sein
  (für den `open things:///...` Aufruf).

### In Osaurus importieren
Osaurus kann komplette Claude-Plugins direkt aus einem GitHub-Repo oder
lokalen Ordner importieren (Plugins → Claude Plugins → Import). Dieser Ordner
ist bereits im erwarteten Format:

```
things3-plugin/
├── .claude-plugin/plugin.json   ← Manifest mit inline mcpServers-Eintrag
├── server/things_server.py      ← der eigentliche MCP-Server
└── skills/things3/SKILL.md      ← Nutzungshinweise für das Modell
```

Push das Verzeichnis in ein (auch privates) GitHub-Repo und importiere die
Repo-URL in Osaurus, oder importiere den lokalen Pfad direkt, falls die
Osaurus-Version das unterstützt.

### Auth-Token für Schreibzugriff auf bestehende Todos
Nur nötig für `things_update_todo` / `things_complete_todo`:
1. Things → Einstellungen → Allgemein → „Things-URLs aktivieren" → „Verwalten…"
2. Token kopieren
3. In Osaurus beim Import als Wert für `THINGS_AUTH_TOKEN` hinterlegen
   (landet automatisch im macOS Keychain, siehe Osaurus-Doku zu Claude-Plugins)

## Bekannte Einschränkung
Das SQLite-Schema (`TMTask`, `TMArea`, `TMTag`, `TMChecklistItem`) ist nicht
offiziell von Cultured Code veröffentlicht, sondern community-reverse-
engineered und seit Jahren stabil (u. a. Basis der `things.py`-Bibliothek).
Falls ein zukünftiges Things-Update das Schema ändert, melden die
Lesefunktionen einen klaren SQLite-Fehler statt falscher Daten. In dem Fall:
`sqlite3 "<DB-Pfad>" ".schema TMTask"` gegen die dann aktuelle Datenbank
laufen lassen und die Spaltennamen in `server/things_server.py` anpassen.

## Tools im Überblick
`things_list_inbox`, `things_list_today`, `things_list_upcoming`,
`things_list_anytime`, `things_list_someday`, `things_list_projects`,
`things_list_areas`, `things_search`, `things_get_todo`, `things_add_todo`,
`things_add_project`, `things_update_todo`, `things_complete_todo`
