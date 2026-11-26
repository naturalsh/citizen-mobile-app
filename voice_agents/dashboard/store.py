"""Operator decisions, claims, resolutions and notes, kept apart from the brain's reports.

The brain rewrites a call's report on every turn, so an operator's decision written into
that file would be overwritten. Decisions live here instead, in a small SQLite file next to
the reports, and the dashboard merges them in. Every decision keeps who made it and when
(accountability, EU AI Act Article 14; Docs/Research/05).
"""
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

ACTIONS = ("confirm", "change", "escalate")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class OperatorStore:
    def __init__(self, path: Path):
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        # Tables are (re)created on every connection, so deleting the file (--reset) is safe
        # even while the dashboard runs.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("""CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY, call_id TEXT NOT NULL, action TEXT NOT NULL,
            level TEXT, operator TEXT NOT NULL, at TEXT NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS claims (
            incident_id TEXT PRIMARY KEY, operator TEXT NOT NULL, at TEXT NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS resolutions (
            incident_id TEXT PRIMARY KEY, operator TEXT NOT NULL, at TEXT NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY, incident_id TEXT NOT NULL, operator TEXT NOT NULL,
            at TEXT NOT NULL, text TEXT NOT NULL)""")
        return conn

    def decide(self, call_id: str, action: str, level: str | None, operator: str) -> dict:
        if action not in ACTIONS:
            raise ValueError(f"action must be one of {ACTIONS}")
        at = _now()
        with closing(self._connect()) as conn:
            conn.execute("INSERT INTO decisions (call_id, action, level, operator, at) VALUES (?, ?, ?, ?, ?)",
                         (call_id, action, level, operator, at))
        return {"call_id": call_id, "action": action, "level": level, "operator": operator, "at": at}

    def decisions(self) -> dict[str, dict]:
        """The latest decision per call. Escalating keeps an earlier confirmed level."""
        latest: dict[str, dict] = {}
        with closing(self._connect()) as conn:
            for row in conn.execute("SELECT call_id, action, level, operator, at FROM decisions ORDER BY id"):
                d = dict(row)
                previous = latest.get(d["call_id"])
                if d["action"] == "escalate" and previous and previous.get("level"):
                    d["level"] = previous["level"]
                    d["confirmed_level"] = True
                latest[d["call_id"]] = d
        return latest

    def undo(self, call_id: str, operator: str, within_s: int = 300) -> dict | None:
        """Remove this operator's latest decision on a call, if it was made in the last few minutes.

        Only your own, recent decision: an older or someone else's decision stays on record.
        """
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT id, operator, at, action, level FROM decisions WHERE call_id = ? "
                               "ORDER BY id DESC LIMIT 1", (call_id,)).fetchone()
            if not row or row["operator"] != operator:
                return None
            made = datetime.strptime(row["at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - made).total_seconds() > within_s:
                return None
            conn.execute("DELETE FROM decisions WHERE id = ?", (row["id"],))
            return {"call_id": call_id, "action": row["action"], "level": row["level"]}

    def history(self, call_id: str) -> list[dict]:
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT action, level, operator, at FROM decisions WHERE call_id = ? ORDER BY id",
                                (call_id,))
            return [dict(r) for r in rows]

    def claim(self, incident_id: str, operator: str) -> dict:
        at = _now()
        with closing(self._connect()) as conn:
            conn.execute("INSERT OR REPLACE INTO claims VALUES (?, ?, ?)", (incident_id, operator, at))
        return {"operator": operator, "at": at}

    def release(self, incident_id: str) -> None:
        with closing(self._connect()) as conn:
            conn.execute("DELETE FROM claims WHERE incident_id = ?", (incident_id,))

    def claims(self) -> dict[str, dict]:
        with closing(self._connect()) as conn:
            return {r["incident_id"]: {"operator": r["operator"], "at": r["at"]}
                    for r in conn.execute("SELECT * FROM claims")}

    def move(self, old_id: str, new_id: str) -> None:
        """A call joined an event, so its incident id changed from call:<id> to the event's.

        This happens mid-call, e.g. once the caller says where they are. The claim and notes
        follow the call; an existing claim on the event wins. A resolution doesn't carry over:
        it would close the other calls' event too.
        """
        with closing(self._connect()) as conn:
            conn.execute("INSERT OR IGNORE INTO claims SELECT ?, operator, at FROM claims WHERE incident_id = ?",
                         (new_id, old_id))
            conn.execute("DELETE FROM claims WHERE incident_id = ?", (old_id,))
            conn.execute("UPDATE notes SET incident_id = ? WHERE incident_id = ?", (new_id, old_id))

    # Resolving: the operator has dealt with the incident (e.g. help is on the way).
    def resolve(self, incident_id: str, operator: str) -> dict:
        at = _now()
        with closing(self._connect()) as conn:
            conn.execute("INSERT OR REPLACE INTO resolutions VALUES (?, ?, ?)", (incident_id, operator, at))
        return {"operator": operator, "at": at}

    def reopen(self, incident_id: str) -> None:
        with closing(self._connect()) as conn:
            conn.execute("DELETE FROM resolutions WHERE incident_id = ?", (incident_id,))

    def resolutions(self) -> dict[str, dict]:
        with closing(self._connect()) as conn:
            return {r["incident_id"]: {"operator": r["operator"], "at": r["at"]}
                    for r in conn.execute("SELECT * FROM resolutions")}

    # Notes: free text from operators, e.g. "Fire crew 3 sent, 14:10". Kept as a record.
    def add_note(self, incident_id: str, operator: str, text: str) -> dict:
        at = _now()
        with closing(self._connect()) as conn:
            cur = conn.execute("INSERT INTO notes (incident_id, operator, at, text) VALUES (?, ?, ?, ?)",
                               (incident_id, operator, at, text))
        return {"id": cur.lastrowid, "incident_id": incident_id, "operator": operator, "at": at, "text": text}

    def delete_note(self, note_id: int, operator: str, within_s: int = 300) -> bool:
        """Undo for a note: only your own, from the last few minutes."""
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT operator, at FROM notes WHERE id = ?", (note_id,)).fetchone()
            if not row or row["operator"] != operator:
                return False
            made = datetime.strptime(row["at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - made).total_seconds() > within_s:
                return False
            conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
            return True

    def notes(self) -> dict[str, list[dict]]:
        by_incident: dict[str, list[dict]] = {}
        with closing(self._connect()) as conn:
            for r in conn.execute("SELECT id, incident_id, operator, at, text FROM notes ORDER BY id"):
                by_incident.setdefault(r["incident_id"], []).append(dict(r))
        return by_incident
