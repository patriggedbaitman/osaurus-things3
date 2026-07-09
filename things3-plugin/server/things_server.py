#!/usr/bin/env python3
"""
Things 3 MCP-Server

Architektur folgt dem Muster des Raycast-Things-Plugins:
  - Lesen: direkter, read-only SQLite-Zugriff auf die lokale Things-Datenbank
    (schnell, funktioniert auch bei geschlossenem Things, keine Schreibkonflikte).
  - Schreiben (add): things:///add bzw. things:///add-project URL-Scheme,
    funktioniert ohne Auth-Token.
  - Schreiben (update/complete an bestehenden Objekten): things:///update
    URL-Scheme, benötigt aus Sicherheitsgründen einen Auth-Token
    (Things -> Einstellungen -> Allgemein -> Things-URLs aktivieren -> Verwalten).

Das SQLite-Schema ist nicht offiziell von Cultured Code dokumentiert, aber seit
Jahren stabil und Basis mehrerer bekannter Open-Source-Tools (u.a. things.py).
Wenn eine Spalte fehlt, bricht die jeweilige Funktion mit einer klaren
Fehlermeldung ab, statt stillschweigend falsche Daten zu liefern.
"""

import glob
import json
import os
import sqlite3
import subprocess
import urllib.parse
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("things3")

GROUP_CONTAINER = (
    Path.home()
    / "Library"
    / "Group Containers"
    / "JLMPQHK86H.com.culturedcode.ThingsMac"
)

AUTH_TOKEN = os.environ.get("THINGS_AUTH_TOKEN", "").strip()

# ---------------------------------------------------------------------------
# Datenbank-Zugriff
# ---------------------------------------------------------------------------


def find_database_path() -> Path:
    """Findet die aktuelle Things-SQLite-Datenbank im Group Container.

    Der genaue Dateiname (main.sqlite / main.sqlite3) und der ThingsData-*
    Ordnername können sich über Things-Versionen leicht unterscheiden, daher
    wird gesucht statt hart kodiert.
    """
    if not GROUP_CONTAINER.exists():
        raise FileNotFoundError(
            f"Things-Datenordner nicht gefunden unter {GROUP_CONTAINER}. "
            "Ist Things 3 installiert und wurde es mindestens einmal gestartet?"
        )

    candidates = glob.glob(
        str(GROUP_CONTAINER / "ThingsData-*" / "Things Database.thingsdatabase" / "main.sqlite*")
    )
    if not candidates:
        raise FileNotFoundError(
            "Things-Datenbankdatei nicht gefunden (main.sqlite unter "
            f"{GROUP_CONTAINER}/ThingsData-*/Things Database.thingsdatabase/). "
            "Ggf. hat sich das interne Speicherformat geändert."
        )
    # Bevorzugt die zuletzt geänderte Datei, falls mehrere ThingsData-* Ordner existieren.
    candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return Path(candidates[0])


@contextmanager
def db_connection():
    db_path = find_database_path()
    # immutable=1 + Nur-Lese-URI: verhindert Schreibkonflikte mit der laufenden Things-App
    uri = f"file:{urllib.parse.quote(str(db_path))}?immutable=1"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def run_query(sql: str, params: tuple = ()) -> list[dict]:
    try:
        with db_connection() as conn:
            cur = conn.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]
    except sqlite3.OperationalError as e:
        raise RuntimeError(
            f"SQLite-Abfrage fehlgeschlagen ({e}). Möglicherweise hat sich das "
            "Things-Datenbankschema geändert - bitte Tabellen-/Spaltennamen prüfen."
        ) from e


# TMTask.type: 0 = to-do, 1 = project, 2 = heading
# TMTask.status: 0 = offen, 2 = abgebrochen, 3 = erledigt
# TMTask.start: 0 = Inbox, 1 = Anytime, 2 = Someday

TASK_BASE_SELECT = """
    SELECT
        t.uuid,
        t.title,
        t.notes,
        t.status,
        t.start,
        date(t.startDate, 'unixepoch') AS start_date,
        date(t.deadline, 'unixepoch') AS deadline,
        date(t.stopDate, 'unixepoch') AS completion_date,
        p.title AS project_title,
        a.title AS area_title,
        t.creationDate AS created,
        t.userModificationDate AS modified
    FROM TMTask t
    LEFT JOIN TMTask p ON t.project = p.uuid
    LEFT JOIN TMArea a ON t.area = a.uuid
    WHERE t.trashed = 0 AND t.type = 0
"""


def _tags_for(uuid: str) -> list[str]:
    rows = run_query(
        """
        SELECT tag.title FROM TMTaskTag tt
        JOIN TMTag tag ON tt.tags = tag.uuid
        WHERE tt.tasks = ?
        """,
        (uuid,),
    )
    return [r["title"] for r in rows]


# ---------------------------------------------------------------------------
# Lese-Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def things_list_inbox() -> list[dict]:
    """Listet alle Todos in der Things-Inbox (noch nicht einsortiert)."""
    return run_query(TASK_BASE_SELECT + " AND t.status = 0 AND t.start = 0 ORDER BY t.\"index\"")


@mcp.tool()
def things_list_today() -> list[dict]:
    """Listet alle für heute eingeplanten, offenen Todos."""
    return run_query(
        TASK_BASE_SELECT
        + " AND t.status = 0 AND t.start = 1 AND t.startDate IS NOT NULL "
        "ORDER BY t.todayIndex"
    )


@mcp.tool()
def things_list_upcoming() -> list[dict]:
    """Listet alle offenen Todos mit einem zukünftigen Startdatum oder Deadline."""
    return run_query(
        TASK_BASE_SELECT
        + " AND t.status = 0 AND (t.startDate IS NOT NULL OR t.deadline IS NOT NULL) "
        "AND t.start != 0 ORDER BY COALESCE(t.startDate, t.deadline)"
    )


@mcp.tool()
def things_list_anytime() -> list[dict]:
    """Listet offene Todos ohne festes Datum (Bucket 'Jederzeit')."""
    return run_query(
        TASK_BASE_SELECT + " AND t.status = 0 AND t.start = 1 AND t.startDate IS NULL "
        "ORDER BY t.\"index\""
    )


@mcp.tool()
def things_list_someday() -> list[dict]:
    """Listet Todos im Bucket 'Irgendwann'."""
    return run_query(TASK_BASE_SELECT + " AND t.status = 0 AND t.start = 2 ORDER BY t.\"index\"")


@mcp.tool()
def things_list_projects(include_completed: bool = False) -> list[dict]:
    """Listet Projekte, optional inklusive abgeschlossener Projekte."""
    status_clause = "" if include_completed else "AND t.status = 0"
    return run_query(
        f"""
        SELECT t.uuid, t.title, t.notes, t.status, a.title AS area_title
        FROM TMTask t
        LEFT JOIN TMArea a ON t.area = a.uuid
        WHERE t.trashed = 0 AND t.type = 1 {status_clause}
        ORDER BY t."index"
        """
    )


@mcp.tool()
def things_list_areas() -> list[dict]:
    """Listet alle Bereiche (Areas)."""
    return run_query("SELECT uuid, title FROM TMArea ORDER BY \"index\"")


@mcp.tool()
def things_search(query: str) -> list[dict]:
    """Volltextsuche über Titel und Notizen offener Todos."""
    like = f"%{query}%"
    return run_query(
        TASK_BASE_SELECT + " AND t.status = 0 AND (t.title LIKE ? OR t.notes LIKE ?) "
        "ORDER BY t.\"index\" LIMIT 50",
        (like, like),
    )


@mcp.tool()
def things_get_todo(uuid: str) -> dict:
    """Liefert Detailinformationen zu einem Todo inkl. Tags und Checklist-Items."""
    rows = run_query(TASK_BASE_SELECT.replace("WHERE t.trashed = 0 AND t.type = 0", "WHERE t.uuid = ?"), (uuid,))
    if not rows:
        raise ValueError(f"Kein Todo mit uuid={uuid} gefunden.")
    todo = rows[0]
    todo["tags"] = _tags_for(uuid)
    todo["checklist"] = run_query(
        "SELECT title, status FROM TMChecklistItem WHERE task = ? ORDER BY \"index\"",
        (uuid,),
    )
    return todo


# ---------------------------------------------------------------------------
# Schreib-Tools (things:/// URL-Scheme)
# ---------------------------------------------------------------------------


def _open_things_url(command: str, params: dict[str, Any]) -> None:
    clean = {k: v for k, v in params.items() if v not in (None, "", [])}
    query = urllib.parse.urlencode(clean, quote_via=urllib.parse.quote)
    url = f"things:///{command}?{query}"
    subprocess.run(["open", url], check=True)


@mcp.tool()
def things_add_todo(
    title: str,
    notes: Optional[str] = None,
    when: Optional[str] = None,
    deadline: Optional[str] = None,
    tags: Optional[list[str]] = None,
    list_title: Optional[str] = None,
    checklist_items: Optional[list[str]] = None,
) -> str:
    """Legt ein neues Todo an.

    when: 'today' | 'tomorrow' | 'evening' | 'anytime' | 'someday' | YYYY-MM-DD
    deadline: YYYY-MM-DD
    list_title: Titel eines existierenden Projekts oder Bereichs
    """
    params: dict[str, Any] = {
        "title": title,
        "notes": notes,
        "when": when,
        "deadline": deadline,
        "list": list_title,
    }
    if tags:
        params["tags"] = ",".join(tags)
    if checklist_items:
        params["checklist-items"] = "\n".join(checklist_items)
    _open_things_url("add", params)
    return f"Todo '{title}' wurde in Things angelegt."


@mcp.tool()
def things_add_project(
    title: str,
    notes: Optional[str] = None,
    area_title: Optional[str] = None,
    when: Optional[str] = None,
    tags: Optional[list[str]] = None,
    todos: Optional[list[str]] = None,
) -> str:
    """Legt ein neues Projekt an, optional mit initialen Todos."""
    params: dict[str, Any] = {
        "title": title,
        "notes": notes,
        "area": area_title,
        "when": when,
    }
    if tags:
        params["tags"] = ",".join(tags)
    if todos:
        params["to-dos"] = "\n".join(todos)
    _open_things_url("add-project", params)
    return f"Projekt '{title}' wurde in Things angelegt."


def _require_token() -> str:
    if not AUTH_TOKEN:
        raise RuntimeError(
            "Kein Things-Auth-Token gesetzt (Umgebungsvariable THINGS_AUTH_TOKEN). "
            "Token holen: Things -> Einstellungen -> Allgemein -> "
            "'Things-URLs aktivieren' -> 'Verwalten...'."
        )
    return AUTH_TOKEN


@mcp.tool()
def things_update_todo(
    uuid: str,
    title: Optional[str] = None,
    notes: Optional[str] = None,
    when: Optional[str] = None,
    deadline: Optional[str] = None,
    add_tags: Optional[list[str]] = None,
) -> str:
    """Aktualisiert ein bestehendes Todo. Benötigt THINGS_AUTH_TOKEN."""
    token = _require_token()
    params: dict[str, Any] = {
        "id": uuid,
        "title": title,
        "notes": notes,
        "when": when,
        "deadline": deadline,
        "auth-token": token,
    }
    if add_tags:
        params["add-tags"] = ",".join(add_tags)
    _open_things_url("update", params)
    return f"Todo {uuid} wurde aktualisiert."


@mcp.tool()
def things_complete_todo(uuid: str) -> str:
    """Markiert ein Todo als erledigt. Benötigt THINGS_AUTH_TOKEN."""
    token = _require_token()
    _open_things_url("update", {"id": uuid, "completed": "true", "auth-token": token})
    return f"Todo {uuid} wurde als erledigt markiert."


if __name__ == "__main__":
    mcp.run()
