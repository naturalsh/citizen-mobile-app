"""Request limit for Gemini, to protect the small spending budget.

The Gemini project has a €5 spending cap, but Google can still charge for usage inside a
roughly 10-minute processing window before the cap takes effect. A runaway loop or several
test runs in a row could go past it. So every Gemini request is counted here first, and
above the limit the brain stops calling Gemini and hands callers to a human operator.

    .venv/bin/python -m brain.usage     # show current usage

Counts live in output/budget.sqlite (BRAIN_BUDGET_DIR), shared by every process started from
the repository root on this machine (voice worker, messaging server, eval runner). When the limit activates, a warning
threshold is crossed, or calls are allowed again, the user is told three ways: a log
line, a macOS notification, and output/BUDGET_LIMIT_REACHED.txt while the limit is on.
"""
import logging
import os
import sqlite3
import subprocess
import sys
import time
from contextlib import closing
from datetime import datetime
from pathlib import Path

MAX_PER_HOUR = int(os.getenv("BRAIN_MAX_REQUESTS_PER_HOUR", "300"))
MAX_PER_DAY = int(os.getenv("BRAIN_MAX_REQUESTS_PER_DAY", "1500"))
WARN_AT = 0.8  # warn once usage passes this share of either limit
NOTIFY = os.getenv("BRAIN_LIMIT_NOTIFY", "on") != "off"  # macOS notifications

log = logging.getLogger("brain.budget")


class LimitReached(Exception):
    """The request limit is used up: don't call Gemini."""


def _output_dir() -> Path:
    # Not BRAIN_OUTPUT_DIR: the eval runner moves that elsewhere, but its requests must count too.
    return Path(os.getenv("BRAIN_BUDGET_DIR", "output"))


def _flag_file() -> Path:
    return _output_dir() / "BUDGET_LIMIT_REACHED.txt"


def _connect() -> sqlite3.Connection:
    path = _output_dir() / "budget.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10, isolation_level=None)
    conn.execute("CREATE TABLE IF NOT EXISTS requests (at REAL NOT NULL, what TEXT NOT NULL)")
    conn.execute("CREATE INDEX IF NOT EXISTS requests_at ON requests (at)")
    conn.execute("CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    return conn


def _counts(conn: sqlite3.Connection, now: float) -> tuple[int, int]:
    hour = conn.execute("SELECT COUNT(*) FROM requests WHERE at > ?", (now - 3600,)).fetchone()[0]
    day = conn.execute("SELECT COUNT(*) FROM requests WHERE at > ?", (now - 86400,)).fetchone()[0]
    return hour, day


def _flip(conn: sqlite3.Connection, key: str, on: bool) -> bool:
    """Set a shared on/off flag. True if it changed, so each change is announced once."""
    row = conn.execute("SELECT value FROM state WHERE key = ?", (key,)).fetchone()
    was_on = bool(row and row[0] == "on")
    if was_on == on:
        return False
    conn.execute("INSERT OR REPLACE INTO state VALUES (?, ?)", (key, "on" if on else "off"))
    return True


def spend(what: str) -> None:
    """Count one Gemini request, or raise LimitReached if the hour or day limit is used up."""
    now = time.time()
    announce, refused = [], False
    with closing(_connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")  # one process at a time
        try:
            hour, day = _counts(conn, now)
            if hour >= MAX_PER_HOUR or day >= MAX_PER_DAY:
                refused = True
                if _flip(conn, "limit", True):
                    announce.append(("limit", hour, day))
                conn.execute("COMMIT")
            else:
                conn.execute("INSERT INTO requests VALUES (?, ?)", (now, what))
                hour, day = hour + 1, day + 1
                if _flip(conn, "limit", False):
                    announce.append(("resumed", hour, day))
                if hour >= WARN_AT * MAX_PER_HOUR or day >= WARN_AT * MAX_PER_DAY:
                    if _flip(conn, "warned", True):
                        announce.append(("warning", hour, day))
                elif hour < 0.5 * MAX_PER_HOUR and day < 0.5 * MAX_PER_DAY:
                    _flip(conn, "warned", False)  # warn again next time usage climbs
                conn.execute("DELETE FROM requests WHERE at < ?", (now - 2 * 86400,))
                conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    for kind, hour, day in announce:
        _announce(kind, hour, day)
    if refused:
        raise LimitReached(f"Gemini request limit reached: {hour}/{MAX_PER_HOUR} this hour, {day}/{MAX_PER_DAY} today")


def status() -> dict:
    """Current usage, for the eval runner and `python -m brain.usage`."""
    with closing(_connect()) as conn:
        hour, day = _counts(conn, time.time())
        row = conn.execute("SELECT value FROM state WHERE key = 'limit'").fetchone()
    return {
        "hour": hour, "max_per_hour": MAX_PER_HOUR, "day": day, "max_per_day": MAX_PER_DAY,
        # On from the first refused request until one is allowed again (as announced),
        # and only while usage is still at the limit.
        "limit_on": bool(row and row[0] == "on") and (hour >= MAX_PER_HOUR or day >= MAX_PER_DAY),
    }


def _announce(kind: str, hour: int, day: int) -> None:
    usage = f"{hour}/{MAX_PER_HOUR} requests this hour, {day}/{MAX_PER_DAY} today"
    if kind == "limit":
        title = "Gemini limit reached"
        message = f"The brain stopped calling Gemini ({usage}). Callers are handed to an operator."
        log.error("BUDGET LIMIT ACTIVE: %s", message)
        _flag_file().write_text(
            f"{datetime.now():%Y-%m-%d %H:%M:%S}  {message}\n"
            "Calls to Gemini resume automatically when usage drops below the limit.\n"
            "Limits: BRAIN_MAX_REQUESTS_PER_HOUR / BRAIN_MAX_REQUESTS_PER_DAY in .env.\n",
            encoding="utf-8",
        )
    elif kind == "resumed":
        title = "Gemini calls resumed"
        message = f"Back under the limit ({usage})."
        log.warning("BUDGET LIMIT OFF: %s", message)
        _flag_file().unlink(missing_ok=True)
    else:
        title = "Gemini usage at 80%"
        message = f"{usage}. The brain stops calling Gemini at the limit."
        log.warning("BUDGET WARNING: %s", message)
    _notify(title, message, sound=kind == "limit")


def _notify(title: str, message: str, sound: bool) -> None:
    """macOS notification. Never lets a failure here affect a call."""
    if not NOTIFY or sys.platform != "darwin":
        return
    text = message.replace('"', "'")
    script = f'display notification "{text}" with title "{title}"' + (' sound name "Basso"' if sound else "")
    try:
        subprocess.run(["osascript", "-e", script], timeout=5, check=False, capture_output=True)
    except Exception:
        log.debug("could not show a notification", exc_info=True)

