"""Turn the brain's call reports into incidents for the operator dashboard.

One report per call is written by the brain to output/reports/ (Docs/Research/06). Calls
with the same event_id are one incident (e.g. one collapsed building). The queue is sorted
the way dispatch systems sort it: highest urgency first, unclaimed before claimed, then the
longest waiting (research summary in dashboard/README.md).

Urgency: the brain only *suggests* it. An operator decision (dashboard/store.py) replaces
the suggestion for that call; until then the dashboard shows it as "AI-suggested".
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from brain.report import hazard_of  # category and subtype, also for old reports
from brain.tools import ADVICE

log = logging.getLogger("dashboard")

LEVELS = ["life_threat", "urgent", "needs_help", "information"]
RANK = {level: i for i, level in enumerate(LEVELS)}
UNKNOWN_RANK = len(LEVELS)  # no urgency suggested yet: last
# A call is "on the line" while its report says in_progress and it changed recently. Older
# in_progress reports are usually calls that dropped without a proper ending.
LIVE_WINDOW = timedelta(minutes=10)


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if value else None


class ReportFolder:
    """Reads report files, re-parsing only the ones that changed since the last read."""

    def __init__(self, folder: Path):
        self.folder = folder
        self._cache: dict[Path, tuple[float, dict]] = {}

    def read(self) -> list[dict]:
        reports, seen = [], set()
        for path in sorted(self.folder.glob("*.json")) if self.folder.exists() else []:
            seen.add(path)
            try:
                mtime = path.stat().st_mtime
                cached = self._cache.get(path)
                if not cached or cached[0] != mtime:
                    cached = (mtime, json.loads(path.read_text(encoding="utf-8")))
                    self._cache[path] = cached
                reports.append(cached[1])
            except (OSError, ValueError):
                log.warning("skipping unreadable report %s", path.name)  # e.g. caught mid-write
        for gone in set(self._cache) - seen:
            del self._cache[gone]
        return reports


def demo_times(reports: list[dict], now: datetime, window: timedelta = timedelta(minutes=40)) -> dict[str, timedelta]:
    """Demo mode replays old test calls: shift them so they look like the last 40 minutes, in order."""
    ordered = sorted(reports, key=lambda r: r.get("created_at") or "")
    shifts = {}
    for i, r in enumerate(ordered):
        created = parse_time(r.get("created_at")) or now
        target = now - window + window * (i + 1) / max(len(ordered), 1) - timedelta(seconds=30)
        shifts[r["call_id"]] = target - created
    return shifts


def latest_per_case(reports: list[dict]) -> list[dict]:
    """Demo mode: the eval runs each scripted case many times; keep only its latest call.

    Eval call ids look like "eval-<case id>-<4 hex>", so one call per case is left.
    """
    latest: dict[str, dict] = {}
    for r in reports:
        case = r.get("call_id", "").rsplit("-", 1)[0]
        if case not in latest or (r.get("created_at") or "") > (latest[case].get("created_at") or ""):
            latest[case] = r
    return list(latest.values())


def animal_label(animal: dict) -> str:
    """'🐾 1 cat trapped': animals have their own tags, never counted as people."""
    count = animal.get("count") or 1
    states = [s for s, on in (("trapped", animal.get("trapped")), ("injured", animal.get("injured"))) if on]
    return f"🐾 {count} {animal.get('kind') or 'animal'}{' ' + ', '.join(states) if states else ''}"


def advice_title(key: str) -> str:
    hazard, _, topic = key.partition(".")
    return f"{hazard.replace('_', ' ').capitalize()}: {topic.replace('_', ' ')}" if key in ADVICE else key


PEOPLE_FIELDS = ("total", "trapped", "injured", "cannot_walk", "unresponsive", "dead")


def people_counts(people: list | None) -> dict:
    """Totals over the caller's groups. "plus" lists the fields that may be higher ("1+ trapped"):
    a group marked at_least, e.g. voices heard under rubble, is a minimum, not a count."""
    counts = {**dict.fromkeys(PEOPLE_FIELDS, 0), "plus": []}
    for group in people or []:
        n = group.get("count") or 0
        counts["total"] += n
        counts["trapped"] += n if group.get("trapped") else 0
        counts["injured"] += group.get("injured") or 0
        counts["cannot_walk"] += group.get("cannot_walk") or 0
        counts["unresponsive"] += group.get("unresponsive") or 0
        counts["dead"] += group.get("dead") or 0
        if group.get("at_least"):
            counts["plus"] += ["total"] + (["trapped"] if group.get("trapped") else [])
    counts["plus"] = sorted(set(counts["plus"]))
    return counts


def group_label(group: dict) -> str | None:
    """One tag per person or group, so one person never reads as several (a test call showed
    "1 trapped", "1 injured", "1 can't leave" for one man under a tree).

    {"count": 1, "trapped": True, "injured": 1} -> "1 trapped, injured"; 3 trapped of whom 1 is
    injured -> "3 trapped (1 injured)"; at_least -> "1+ trapped". None if nobody is at risk.
    """
    n = group.get("count") or 0
    found = [(name, k) for name, k in (
        ("trapped", n or 1 if group.get("trapped") else 0),
        ("not breathing / unconscious", group.get("unresponsive") or 0),
        ("injured", group.get("injured") or 0),
        ("can't leave", group.get("cannot_walk") or 0),
    ) if k]
    if not found:
        return None
    head_name, head = found[0]  # "1 injured" of a group of 3, not "3 injured"
    rest = found[1:]
    label = f"{head}{'+' if group.get('at_least') and head >= n else ''} {head_name}"
    if rest and all(k >= head for _, k in rest):
        label += ", " + ", ".join(name for name, _ in rest)  # all of them
    elif rest:
        label += " (" + ", ".join(name if k >= head else f"{k} {name}" for name, k in rest) + ")"  # some of them
    note = group.get("note") or ""
    return label + (f" · {note}" if note and len(note) <= 30 else "")


def group_labels(group: dict) -> list[str]:
    """Tags for one group: the dead always on their own ("5 dead"), never mixed with the living."""
    dead = group.get("dead") or 0
    living = {**group, "count": max((group.get("count") or 0) - dead, 0)} if dead else group
    label = group_label(living)
    return ([f"{dead} dead"] if dead else []) + ([label] if label else [])


def priority(incident: dict) -> tuple[tuple, list[str]]:
    """Order within one urgency level, highest first, and the reasons shown on the card.

    Not breathing or unconscious first (MPDS puts arrest, Echo, above every other top-level
    call), then the number of people at risk (SALT: the most good for the most people), then
    the number of calls (many callers about one place is a signal). Waiting time breaks ties
    in the queue sort. Our combination, not a published algorithm (dashboard/README.md).
    """
    p = incident["people"]
    critical = max(p["unresponsive"], sum(1 for c in incident["calls"] if c.get("handoff_reason") == "not_breathing"))
    at_risk = p["trapped"] + max(p["injured"], p["cannot_walk"]) + p["dead"]  # deaths: a mass-casualty sign
    if p["total"]:
        at_risk = min(at_risk, p["total"])
    reasons = []
    # Tags from the caller's own groups (the call with the most people at risk), one per group.
    top = max(incident["calls"], key=lambda c: sum(c["people"][k] for k in ("trapped", "injured", "unresponsive", "dead")))
    reasons += [label for g in top.get("people_groups") or [] for label in group_labels(g)]
    if critical and not any("not breathing" in r for r in reasons):
        reasons.insert(0, f"{critical} not breathing / unconscious")  # e.g. a handoff for CPR
    if incident["call_count"] > 1:
        reasons.append(f"{incident['call_count']} calls")
    return (critical, at_risk, incident["call_count"]), reasons


def call_view(report: dict, decision: dict | None, shift: timedelta = timedelta(0)) -> dict:
    urgency = report.get("urgency") or {}
    ai_level = urgency.get("suggested") if urgency.get("suggested") in RANK else None
    # An operator's level wins; escalating after confirming keeps the confirmed level (store.decisions).
    confirmed = bool(decision and (decision["action"] in ("confirm", "change") or decision.get("confirmed_level")))
    level = decision["level"] if confirmed and decision.get("level") in RANK else ai_level
    created, updated = parse_time(report.get("created_at")), parse_time(report.get("updated_at"))
    location = report.get("location") or {}
    return {
        "call_id": report["call_id"],
        "created_at": iso(created + shift) if created else None,
        "updated_at": iso(updated + shift) if updated else None,
        "status": report.get("status"),
        "lang": report.get("caller_language"),
        "source": (report.get("source") or "voice_agent").removesuffix("_agent"),
        "trigger": (report.get("trigger") or {}).get("type"),
        "caller": report.get("caller") or {},
        "location": {
            "spoken_address": location.get("spoken_address"),
            # The street the model recorded: without it the map never looked for the house number, and every
            # live call showed "no house number said" (a demo call to "Orlov 12", 2026-10-30).
            "street": location.get("street"),
            "area": location.get("area"),
            "aml": location.get("aml"),
            "confirmed_with_caller": location.get("confirmed_with_caller"),
            "on_map": location.get("on_map"),  # the brain's map check: False = maybe misheard
            "landmark": location.get("landmark"),  # in the caller's own words, as heard
            "map_suggestion": location.get("map_suggestion"),  # the real place the map check thinks was meant
            "street_matches": location.get("street_matches"),  # where the brain found the street, per neighbourhood
        },
        "hazard": hazard_of(report)[0],  # the category; old reports' wildfire/building_fire too
        "hazard_subtype": hazard_of(report)[1],
        "animals": report.get("animals") or [],
        "animal_tags": [animal_label(a) for a in report.get("animals") or []],
        "situation": report.get("situation"),
        "summary": report.get("summary_for_operator"),
        "summary_en": report.get("summary_en"),
        "people": people_counts(report.get("people")),
        "handoff_reason": report.get("handoff_reason"),
        "people_notes": [g.get("note") for g in report.get("people") or [] if g.get("note")],
        "people_groups": report.get("people") or [],
        "people_tags": [label for g in report.get("people") or [] for label in group_labels(g)],
        "advice": [{"key": k, "title": advice_title(k)} for k in report.get("advice_given") or []],
        "ai": {"level": ai_level, "confidence": urgency.get("confidence"), "reasons": urgency.get("reasons") or []},
        "decision": decision,
        "level": level,
        "confirmed": confirmed,
        "escalated": bool(decision and decision["action"] == "escalate"),
        "new_event": bool(report.get("new_event_suggested")),
        "event_id": report.get("event_id"),
    }


def build_incidents(reports: list[dict], decisions: dict, claims: dict, locate, now: datetime,
                    demo: bool = False, resolutions: dict | None = None, notes: dict | None = None) -> list[dict]:
    """Group calls into incidents and sort the queue. locate(incident) -> location dict or None.

    A resolved incident goes to the end of the queue. If a call came in after it was resolved,
    it counts as open again ("reopened"): new information must never stay hidden.
    """
    resolutions, notes = resolutions or {}, notes or {}
    if demo:
        reports = latest_per_case(reports)
    shifts = demo_times(reports, now) if demo else {}
    groups: dict[str, list[dict]] = {}
    for report in reports:
        if not report.get("call_id"):
            continue
        call = call_view(report, decisions.get(report["call_id"]), shifts.get(report["call_id"], timedelta(0)))
        updated = parse_time(call["updated_at"] or call["created_at"])
        call["live"] = call["status"] == "in_progress" and updated is not None and now - updated <= LIVE_WINDOW
        groups.setdefault(call["event_id"] or f"call:{call['call_id']}", []).append(call)

    incidents = []
    for incident_id, calls in groups.items():
        calls.sort(key=lambda c: c["created_at"] or "")
        top = min(calls, key=lambda c: RANK.get(c["level"], UNKNOWN_RANK))
        top_level = top["level"]
        areas = [c["location"]["area"] for c in calls if c["location"]["area"]]
        people = {k: max(c["people"][k] for c in calls) for k in PEOPLE_FIELDS}
        people["plus"] = sorted({f for c in calls for f in c["people"]["plus"]})
        incident = {
            "id": incident_id,
            "hazard": next((c["hazard"] for c in calls if c["hazard"]), None),
            "hazard_subtype": next((c["hazard_subtype"] for c in calls if c["hazard_subtype"]), None),
            "animals": any(c["animals"] for c in calls),
            "area": max(set(areas), key=areas.count) if areas else None,
            "calls": calls,
            "call_count": len(calls),
            "level": top_level,
            # Solid badge only when every call at the top level was confirmed by an operator.
            "confirmed": all(c["confirmed"] for c in calls if c["level"] == top_level) if top_level else False,
            "escalated": any(c["escalated"] for c in calls),
            "ai_confidence": top["ai"]["confidence"],
            "people": people,
            "first_at": calls[0]["created_at"],
            "last_at": max(c["updated_at"] or c["created_at"] or "" for c in calls),
            "new_event": calls[0]["new_event"],
            "claim": claims.get(incident_id),
            "notes": notes.get(incident_id, []),
            "open": any(c["status"] == "in_progress" for c in calls),
            "live": any(c["live"] for c in calls),
            "dropped_life_threat": any(c["status"] == "dropped" and c["level"] == "life_threat" for c in calls),
        }
        resolution = resolutions.get(incident_id)
        latest_call = max(c["created_at"] or "" for c in calls)
        incident["resolved"] = resolution if resolution and resolution["at"] >= latest_call else None
        incident["reopened"] = bool(resolution) and not incident["resolved"]
        incident["location"] = locate(incident)
        rank, incident["priority_reasons"] = priority(incident)
        incident["_rank"] = tuple(-x for x in rank)
        incidents.append(incident)

    # Re-sorted on every refresh, so new facts move an incident at once (dynamic priority).
    incidents.sort(key=lambda i: (i["resolved"] is not None, RANK.get(i["level"], UNKNOWN_RANK),
                                  i["claim"] is not None, i["_rank"], i["first_at"] or ""))
    for incident in incidents:
        del incident["_rank"]
    return incidents


def counts(incidents: list[dict]) -> dict:
    """Counts of open incidents; resolved ones are counted apart."""
    open_ = [i for i in incidents if not i["resolved"]]
    by_level = {level: 0 for level in LEVELS}
    for incident in open_:
        if incident["level"] in by_level:
            by_level[incident["level"]] += 1
    unclaimed = sum(1 for i in open_ if i["level"] == "life_threat" and not i["claim"])
    live = sum(1 for i in incidents for c in i["calls"] if c["live"])
    return {"by_level": by_level, "unclaimed_life_threat": unclaimed, "resolved": len(incidents) - len(open_), "live_calls": live,
            "calls": sum(i["call_count"] for i in incidents)}
