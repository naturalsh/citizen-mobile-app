"""Keyword boosting: the words Soniox should expect (Docs/Research/03).

Disaster terms in each language and the demo's place names go to Soniox as context, so
it favours them when the audio is unclear. A boosted word is more likely, not forced.
Soniox rejects context over about 10,000 characters, so the list is checked against that.

The room left is filled in this order:
  1. the caller's area streets, once the brain has them (mid-call, StreetHintSTT below): a test
     call heard "Βασιλίσσης Φρειδερίκης …" as "Σφαιρική …";
  2. every town, village and neighbourhood of the demo regions (brain/gazetteer.py, biggest
     first): the same call heard Παιανία as "Πυρανία".
"""
import json
import logging
import os
import weakref
from pathlib import Path

from livekit.plugins import soniox

from brain import gazetteer

log = logging.getLogger("voice.keywords")

ENABLED = os.getenv("VOICE_KEYWORDS", "on") != "off"
STREET_HINTS = os.getenv("VOICE_STREET_HINTS", "on") != "off"
MAX_CHARS = 10_000  # Soniox: 8,000 tokens, about 10,000 characters
MARGIN = 300  # Greek letters may cost more tokens than the character count suggests
STREETS_MAX_CHARS = 4_500  # a busy area has more streets than fit; the biggest region places stay
_FILE = Path(__file__).parent / "keywords.json"


def load(path: Path = _FILE) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def all_terms(data: dict) -> list[str]:
    """Every term and place, each once, in file order."""
    terms = [t for lang_terms in data["terms"].values() for t in lang_terms] + data["places"] + data.get("landmarks", [])
    return list(dict.fromkeys(terms))


def _fill(terms: list[str], extra: list[str], room: int) -> list[str]:
    """terms plus as many of extra as fit in room characters (as JSON: quotes, comma, space)."""
    seen = set(terms)
    for term in extra:
        cost = len(term) + 4
        if term in seen or not term.strip():
            continue
        if cost > room:
            break
        terms.append(term)
        seen.add(term)
        room -= cost
    return terms


def region_places(data: dict, budget: int) -> list[str]:
    """Places of the demo regions, the same share of budget for each region."""
    regions = data.get("regions", [])
    return [name for r in regions for name in gazetteer.names_in(tuple(r["box"]), budget // len(regions))]


def hinted_terms(data: dict, streets: list[str] = ()) -> list[str]:
    """Fixed terms, then the area streets, then the region places, within MAX_CHARS."""
    terms = all_terms(data)
    room = MAX_CHARS - MARGIN - size_chars(data, terms)
    terms = _fill(terms, list(streets), min(room, STREETS_MAX_CHARS))
    room = MAX_CHARS - MARGIN - size_chars(data, terms)
    return _fill(terms, region_places(data, room), room)


def context(path: Path = _FILE, streets: list[str] = ()) -> soniox.ContextObject | None:
    if not ENABLED:
        return None
    data = load(path)
    return soniox.ContextObject(
        general=[soniox.ContextGeneralItem(key=g["key"], value=g["value"]) for g in data["general"]],
        terms=hinted_terms(data, streets),
    )


def size_chars(data: dict, terms: list[str] | None = None) -> int:
    terms = all_terms(data) if terms is None else terms
    return len(json.dumps({"general": data["general"], "terms": terms}, ensure_ascii=False))


class StreetHintSTT(soniox.STT):
    """Soniox speech-to-text whose hints can change during a call.

    Soniox reads the context only when the connection opens, so a new context means a new
    connection. Done between turns (the caller has just finished and the agent is answering);
    audio that comes in meanwhile waits in the stream's queue. The plugin has no public way to
    do this: it uses the stream's _request_reconnect, checked against livekit-plugins-soniox 1.x."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._live = weakref.WeakSet()
        self.streets: tuple[str, ...] = ()

    def stream(self, **kwargs):
        stream = super().stream(**kwargs)
        self._live.add(stream)
        return stream

    def use_streets(self, streets: list[str]) -> bool:
        """Hint these streets from the next connection on; False if they are hinted already."""
        if not ENABLED or not STREET_HINTS or tuple(streets) == self.streets:
            return False
        self.streets = tuple(streets)
        self._params.context = context(streets=list(streets))
        for stream in list(self._live):
            reconnect = getattr(stream, "_request_reconnect", None)
            if reconnect:
                reconnect("street hints changed")
        return True
