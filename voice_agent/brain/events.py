"""Group calls about the same event (Docs/Research/06_Report_Structure.md).

Each call is *suggested* to belong to an existing event when it reports the same hazard,
close in place and time. Otherwise it starts a new event and is flagged
new_event_suggested, because a new fire front or a new collapse deserves fast attention.

Grouping never hides a call: every call keeps its own report and urgency. Operators
can merge or split events later in the incident backend.

Events live in a small SQLite file so the voice worker and the messaging server, which
run as separate processes, group calls together.
"""
import difflib
import math
import os
import re
import sqlite3
import unicodedata
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .report import hazard_of

# How close two calls must be to count as the same event, per hazard: "category.subtype" first,
# then the category. A fire, an earthquake or "other" is one site (a building, a car); a wildfire,
# a flood, a storm or a landslide covers a wider area.
RULES = {
    #                 radius_m  window_h  compare
    "earthquake":     (200,     6,        "address"),
    "fire":           (150,     3,        "address"),
    "fire.wildfire":  (3000,    3,        "area"),
    "flood":          (1000,    12,       "area"),
    "storm":          (1000,    12,       "area"),
    "landslide":      (500,     12,       "area"),
    "other":          (300,     2,        "address"),
}


def _rule_key(report: dict) -> str | None:
    kind, subtype = hazard_of(report)
    key = f"{kind}.{subtype}" if f"{kind}.{subtype}" in RULES else kind
    return key if key in RULES else None
ADDRESS_SIMILARITY = 0.85

_STREET_WORDS = r"\b(odos|odou|street|st|road|rd|avenue|ave|sokak|sokagi|sk|caddesi|cadde|cd|bulvari|bulvar|blv|no|rue|leoforos)\b"


def _db_path() -> Path:
    return Path(os.getenv("BRAIN_OUTPUT_DIR", "output")) / "events.sqlite"


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10, isolation_level=None)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS members (
            call_id TEXT PRIMARY KEY, event_id TEXT NOT NULL, hazard TEXT NOT NULL,
            lat REAL, lon REAL, area TEXT, address TEXT, seen_at TEXT NOT NULL)"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS members_hazard ON members (hazard, seen_at)")
    return conn


_GREEK_PAIRS = {"ου": "ou", "αι": "ai", "ει": "ei", "οι": "oi", "μπ": "b", "ντ": "nt", "γκ": "g", "θ": "th", "χ": "ch", "ψ": "ps"}
_GREEK_LETTERS = str.maketrans("αβγδεζηικλμνξοπρσςτυφω", "avgdeziiklmnxoprsstyfo")


def _norm(text: str | None) -> str:
    """Lowercase, no accents, Greek in Latin letters, no street words or punctuation.

    'Οδός Θεμιστοκλέους 5' and 'Themistokleous 5' both become 'themistokleous 5'.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    for greek, latin in _GREEK_PAIRS.items():
        text = text.replace(greek, latin)
    text = text.translate(_GREEK_LETTERS).replace("ı", "i")
    text = re.sub(_STREET_WORDS, " ", text)
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _same_place(call: dict, other: sqlite3.Row, radius_m: float, compare: str) -> tuple[bool, float]:
    """Returns (match, score); higher score = better match."""
    if call["lat"] is not None and other["lat"] is not None:
        d = _distance_m(call["lat"], call["lon"], other["lat"], other["lon"])
        return d <= radius_m, 1 - d / (radius_m * 10)
    if compare == "area":
        return bool(call["area"]) and call["area"] == other["area"], 0.5
    if call["address"] and other["address"]:
        ratio = difflib.SequenceMatcher(None, call["address"], other["address"]).ratio()
        return ratio >= ADDRESS_SIMILARITY, ratio
    return False, 0


def suggest_event(report: dict) -> None:
    """Sets report["event_id"] and report["new_event_suggested"]. Safe to call every turn."""
    key = _rule_key(report)
    if not key:
        return
    hazard = key.replace(".", "_")  # stored and in event ids: evt-fire_wildfire-0001
    location = report["location"]
    aml = location.get("aml") or {}
    call = {
        "lat": aml.get("lat"),
        "lon": aml.get("lon"),
        "area": _norm(location.get("area")),
        "address": _norm(location.get("spoken_address")),
    }
    if call["lat"] is None and not call["area"] and not call["address"]:
        return  # nothing to compare yet

    radius_m, window_h, compare = RULES[key]
    now = datetime.now(timezone.utc)
    since = (now - timedelta(hours=window_h)).isoformat()

    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN IMMEDIATE")  # one writer at a time across processes
        try:
            rows = conn.execute(
                "SELECT * FROM members WHERE hazard = ? AND seen_at >= ? AND call_id != ?",
                (hazard, since, report["call_id"]),
            ).fetchall()
            best_event, best_score = None, -1.0
            for row in rows:
                match, score = _same_place(call, row, radius_m, compare)
                if match and score > best_score:
                    best_event, best_score = row["event_id"], score

            current = conn.execute("SELECT event_id FROM members WHERE call_id = ?", (report["call_id"],)).fetchone()
            if best_event:
                event_id = best_event
            elif current and current["event_id"].startswith(f"evt-{hazard}-"):
                event_id = current["event_id"]  # started its own event and still matches nothing else
            else:
                n = conn.execute("SELECT COUNT(DISTINCT event_id) FROM members").fetchone()[0] + 1
                while conn.execute("SELECT 1 FROM members WHERE event_id = ?", (f"evt-{hazard}-{n:04d}",)).fetchone():
                    n += 1
                event_id = f"evt-{hazard}-{n:04d}"

            # Upsert in place (not INSERT OR REPLACE), so a call keeps its rowid and its place in line.
            conn.execute(
                """INSERT INTO members VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (call_id) DO UPDATE SET event_id = excluded.event_id, hazard = excluded.hazard,
                    lat = excluded.lat, lon = excluded.lon, area = excluded.area,
                    address = excluded.address, seen_at = excluded.seen_at""",
                (report["call_id"], event_id, hazard, call["lat"], call["lon"], call["area"], call["address"], now.isoformat()),
            )
            # "New" means this call opened the event, so it stays true after others join.
            first = conn.execute(
                "SELECT call_id FROM members WHERE event_id = ? ORDER BY rowid LIMIT 1", (event_id,)
            ).fetchone()["call_id"]
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    report["event_id"] = event_id
    report["new_event_suggested"] = first == report["call_id"]


def calls_in_event(event_id: str) -> list[str]:
    """Call IDs grouped under an event, in the order they joined (for the dashboard)."""
    with closing(_connect()) as conn:
        rows = conn.execute("SELECT call_id FROM members WHERE event_id = ? ORDER BY rowid", (event_id,))
        return [r[0] for r in rows]
