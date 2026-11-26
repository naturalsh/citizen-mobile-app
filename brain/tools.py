"""The structured answer the model returns each turn, plus the advice library.

One JSON answer per turn (instead of tool calls) means exactly one model request per turn.
"""
import json
from pathlib import Path

from .report import HAZARD_TYPES, SUBTYPES, URGENCY_LEVELS
from .steps import ALL_STEPS

_HERE = Path(__file__).parent


def _load_advice() -> dict[str, dict]:
    """Returns {"earthquake.trapped": {"when": ..., "el": ..., ...}, ...}."""
    advice = {}
    for path in sorted((_HERE / "advice").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for topic, entry in data["topics"].items():
            advice[f"{data['hazard']}.{topic}"] = entry
    return advice


ADVICE = _load_advice()
PHRASES = json.loads((_HERE / "phrases.json").read_text(encoding="utf-8"))

HANDOFF_REASONS = [
    "not_understood", "caller_request", "unsupported_language", "out_of_scope", "low_confidence", "not_breathing",
]

ADVICE_MENU = "\n".join(f"- {key}: {entry['when']}" for key, entry in ADVICE.items())

_PEOPLE_ITEM = {
    "type": "object",
    "properties": {
        "count": {"type": "integer"},
        "trapped": {"type": "boolean"},
        "injured": {"type": "integer", "description": "Number of injured people in this group."},
        "cannot_walk": {"type": "integer", "description": "Number who cannot leave on their own."},
        "unresponsive": {"type": "integer", "description": "Number unconscious or not breathing normally."},
        "dead": {"type": "integer", "description": "Number the caller says have died."},
        "at_least": {"type": "boolean", "description": "True when there may be more than count, e.g. voices "
                     "heard under rubble. The caller can't know the full number."},
        "note": {"type": "string"},
    },
}

_ANIMAL_ITEM = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "description": "e.g. cat, dog, horse, in English"},
        "count": {"type": "integer"},
        "trapped": {"type": "boolean"},
        "injured": {"type": "integer"},
        "note": {"type": "string"},
    },
}

_REPORT_UPDATES = {
    "type": "object",
    "description": "Only the facts that are new or changed this turn. Empty object if nothing changed.",
    "properties": {
        "caller_name": {"type": "string"},
        "caller_relation": {"type": "string", "description": "e.g. resident, neighbour, passer-by"},
        "spoken_address": {"type": "string", "description": "Location as the caller described it, in THEIR "
                           "language and words (it is read back to them)."},
        "street": {"type": "string", "description": "The street name alone, in the caller's words, without "
                   "the house number (or the address placeholder if that is what you have)."},
        "cross_street": {"type": "string", "description": "The nearest corner or cross street the caller gave, "
                         "in their words. Asked when there is no house number."},
        "area": {
            "type": "string",
            "description": "Village, neighbourhood or municipality, plus island or city, in English. "
            "No street or house number. e.g. 'Vathy, Samos', 'Bayrakli, Izmir'.",
        },
        "landmark": {
            "type": "string",
            "description": "The named landmark the caller gave, in THEIR words and language exactly as heard, "
            "not translated or corrected. Used to check it on the map.",
        },
        "location_confirmed": {"type": "boolean", "description": "The caller said yes to the location read back "
                               "to them word for word."},
        "hazard_type": {"type": "string", "enum": HAZARD_TYPES, "description": "The category."},
        "hazard_subtype": {"type": "string", "enum": ["none", *SUBTYPES],
                           "description": "What kind, from the list for the category in the prompt."},
        "animals": {"type": "array", "items": _ANIMAL_ITEM, "description": "Full list of animals at risk; "
                    "replaces the old one. Never people."},
        "situation": {"type": "string", "description": "One or two factual sentences in English."},
        "people": {"type": "array", "items": _PEOPLE_ITEM, "description": "Full list; replaces the old one."},
        "urgency_suggested": {"type": "string", "enum": URGENCY_LEVELS},
        "urgency_confidence": {"type": "number", "description": "0 to 0.95; never 1."},
        "urgency_reasons": {"type": "array", "items": {"type": "string"}},
    },
}

# Short fields first and the reply before the long report, so the reply can be streamed later.
TURN_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["continue", "handoff", "end"]},
        "handoff_reason": {"type": "string", "enum": ["none", *HANDOFF_REASONS]},
        "advice_topic": {"type": "string", "enum": ["none", *ADVICE]},
        "reply": {"type": "string", "description": "Exactly what to say to the caller, in their language."},
        "expecting": {
            "type": "string",
            "enum": [*ALL_STEPS, "other"],
            "description": "The item your reply asks the caller for, by its name in the (next: ...) note; "
                           "\"other\" for anything else (a clarification, an answer to their question).",
        },
        "report_updates": _REPORT_UPDATES,
        # Last, so they never delay the spoken reply: English copies for the operators' dashboard.
        "caller_en": {"type": "string", "description": "The caller's last message in English."},
        "reply_en": {"type": "string", "description": "Your reply in English."},
    },
    "required": ["action", "handoff_reason", "advice_topic", "reply", "expecting", "report_updates",
                 "caller_en", "reply_en"],
    "propertyOrdering": ["action", "handoff_reason", "advice_topic", "reply", "expecting", "report_updates",
                         "caller_en", "reply_en"],
}
