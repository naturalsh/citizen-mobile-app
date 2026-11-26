"""Call report, following Docs/Research/06_Report_Structure.md."""
from datetime import datetime, timezone

# Category, then what kind (2026-10-26: a car fire went in as "other", and operators asked to
# filter by kind). Not only natural hazards: gas leaks, explosions and road accidents happen in them.
HAZARD_SUBTYPES = {
    "earthquake": ["collapse", "damage"],
    "fire": ["wildfire", "building", "vehicle", "other"],
    "flood": ["building", "street", "vehicle", "river"],
    "storm": ["wind", "fallen_tree", "power_line", "lightning"],
    "landslide": [],
    "other": ["gas_leak", "explosion", "road_accident", "other"],
}
HAZARD_TYPES = list(HAZARD_SUBTYPES)
SUBTYPES = list(dict.fromkeys(s for kinds in HAZARD_SUBTYPES.values() for s in kinds))
# Reports from before the categories: wildfire and building_fire were top-level types.
LEGACY_HAZARDS = {"wildfire": ("fire", "wildfire"), "building_fire": ("fire", "building")}


def hazard_of(report: dict) -> tuple[str | None, str | None]:
    """(category, subtype) of a report, also for reports written before the categories."""
    kind = report.get("hazard_type")
    if kind in LEGACY_HAZARDS:
        return LEGACY_HAZARDS[kind]
    return kind, report.get("hazard_subtype")
URGENCY_LEVELS = ["life_threat", "urgent", "needs_help", "information"]
STATUSES = ["in_progress", "complete", "handed_to_human", "dropped"]
MAX_CONFIDENCE = 0.95


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_report(
    call_id: str, phone: str, lang: str, aml: dict | None, channel: str = "voice", trigger: dict | None = None
) -> dict:
    now = _now()
    return {
        "call_id": call_id,
        "event_id": None,
        "created_at": now,
        "updated_at": now,
        "status": "in_progress",
        "handoff_reason": None,  # why a person took over, e.g. not_breathing, caller_request
        "caller_language": lang,
        "caller": {"name": None, "phone": phone, "relation": None},
        "location": {
            "aml": aml,
            "spoken_address": None,
            "street": None,  # the street name alone, as the caller said it (looked up on the map, no number)
            "cross_street": None,  # the nearest corner or cross street, when there is no house number
            "area": None,  # municipality / neighbourhood / village, kept by the PHI stripper
            "landmark": None,  # the named landmark in the caller's own words, as heard ("τζάμι ο νοσοκομείο")
            "map_suggestion": None,  # the real place the map check thinks was meant (places.py)
            "confirmed_with_caller": False,
            "on_map": None,  # the brain's map check (places.py): True found, False not found, None not checked
        },
        "hazard_type": None,  # a category: earthquake, fire, flood, storm, landslide, other
        "hazard_subtype": None,  # what kind, e.g. fire: vehicle (HAZARD_SUBTYPES)
        "situation": None,
        "people": [],
        "animals": [],  # animals at risk, never in people: a trapped cat was dropped in a test call
        "urgency": {
            "suggested": None,
            "confidence": None,
            "reasons": [],
            "confirmed_by_operator": None,  # only a human operator sets this
        },
        "new_event_suggested": None,
        "summary_for_operator": None,  # in the operators' language (Greek or Turkish)
        "summary_en": None,  # the same summary in English, for the dashboard
        "transcript_ref": f"transcripts/{call_id}",
        "source": f"{channel}_agent",  # voice_agent, whatsapp_agent, sms_agent
        "trigger": trigger,  # e.g. {"type": "failed_112_call", ...} when we contacted them first
        "advice_given": [],  # advice topics read to the caller, in order
        "observed_at": now,
    }


def apply_update(report: dict, fields: dict) -> list[str]:
    """Apply the model's report_updates to the report. Returns validation errors, if any."""
    errors = []
    caller = report["caller"]
    location = report["location"]
    urgency = report["urgency"]

    if "caller_name" in fields:
        caller["name"] = fields["caller_name"]
    if "caller_relation" in fields:
        caller["relation"] = fields["caller_relation"]
    before = (location["spoken_address"], location["area"], location.get("landmark"))
    if "spoken_address" in fields:
        location["spoken_address"] = fields["spoken_address"]
    for key in ("street", "cross_street"):
        if key in fields:
            location[key] = fields[key]
    if "area" in fields:
        location["area"] = fields["area"]
    if "landmark" in fields:
        location["landmark"] = fields["landmark"]
    if "location_confirmed" in fields:
        location["confirmed_with_caller"] = bool(fields["location_confirmed"])
    elif (location["spoken_address"], location["area"], location.get("landmark")) != before:
        location["confirmed_with_caller"] = False  # a changed location must be confirmed again
    if "hazard_type" in fields:
        kind, legacy_subtype = LEGACY_HAZARDS.get(fields["hazard_type"], (fields["hazard_type"], None))
        if kind in HAZARD_TYPES:
            if kind != report["hazard_type"]:
                report["hazard_subtype"] = None  # a subtype belongs to its category
            report["hazard_type"] = kind
            report["hazard_subtype"] = legacy_subtype or report["hazard_subtype"]
        else:
            errors.append(f"hazard_type must be one of {HAZARD_TYPES}")
    if fields.get("hazard_subtype") not in (None, "", "none"):
        if fields["hazard_subtype"] in HAZARD_SUBTYPES.get(report["hazard_type"], []):
            report["hazard_subtype"] = fields["hazard_subtype"]
        else:
            errors.append(f"hazard_subtype for {report['hazard_type']} must be one of "
                          f"{HAZARD_SUBTYPES.get(report['hazard_type'], [])}")
    if "animals" in fields:
        report["animals"] = fields["animals"]
    if "situation" in fields:
        report["situation"] = fields["situation"]
    if "people" in fields:
        report["people"] = fields["people"]
    if "urgency_suggested" in fields:
        if fields["urgency_suggested"] in URGENCY_LEVELS:
            urgency["suggested"] = fields["urgency_suggested"]
        else:
            errors.append(f"urgency_suggested must be one of {URGENCY_LEVELS}")
    if "urgency_confidence" in fields:
        # Never "100% sure": the model gave 1.0 in tests, from one caller on a phone line.
        try:
            urgency["confidence"] = min(max(float(fields["urgency_confidence"]), 0.0), MAX_CONFIDENCE)
        except (TypeError, ValueError):
            errors.append("urgency_confidence must be a number from 0 to 0.95")
    if "urgency_reasons" in fields:
        urgency["reasons"] = fields["urgency_reasons"]
    if "summary_for_operator" in fields:
        report["summary_for_operator"] = fields["summary_for_operator"]

    if urgency["suggested"] and not urgency["reasons"]:
        errors.append("urgency_reasons is required whenever urgency_suggested is set")
    if location["confirmed_with_caller"] and not location["spoken_address"]:
        errors.append("spoken_address is empty but the location was confirmed; fill spoken_address")
    elif report["situation"] and not location["spoken_address"] and not location["aml"]:
        errors.append("no spoken_address yet; if the caller gave any location, put it in spoken_address")

    report["updated_at"] = _now()
    return errors
