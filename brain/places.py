"""Check during the call that the place the caller gave exists on the map.

Landmarks too: a later call heard "Τζάνειο Νοσοκομείο" as "τζάμι ο νοσοκομείο" (glass hospital).
The landmark, kept in the caller's own words, is looked up; if it isn't found, the real places of
the same kind in the area are listed ("hospitals in Piraeus") and the one that sounds closest is
suggested ("Did you mean Τζάνειο Γενικό Νοσοκομείο Πειραιά?"). If the caller only named a kind of
place ("the hospital"), the note lists the real ones so the agent can ask which.

A test call put "Belokipos" in the report: speech-to-text had misheard Ampelokipoi, the
dashboard couldn't place the incident, and nobody noticed. So after each turn that changes the
location, the brain looks the area up on OpenStreetMap (Nominatim) in the background. If it
isn't found, it also looks up the street name, which can show the real area ("Michail Mela is
in Ampelokipoi"), or compares it with the known place names the speech-to-text is primed with
(voice/keywords.json: "Belokipos" is close to Ampelokipoi). The result reaches the model as a note on the next turn, so the agent asks
the caller to repeat, spell or confirm, and the report says whether the place was found.

Privacy (the user decided on 2026-10-22): only the area, the street NAME and a landmark are sent
to OpenStreetMap, never a house number or the caller's name (core.py skips a landmark that
contains a masked personal detail). The note to the model names areas
only, never the street, so the model still sees no addresses (masking).

Street lists: when a street isn't found, the area's real street names (OpenStreetMap Overpass,
fetched in the background with only the area's box, kept 30 days) give the closest-sounding one,
and the agent asks "Did you mean ...?"; the name reaches the model only as a placeholder.
BRAIN_STREET_LIST=off turns it off.

Fair use: Nominatim allows 1 request per second with an identifying User-Agent and asks for
caching: requests are spaced, and every answer is cached in output/places.sqlite.
BRAIN_PLACE_CHECK=off turns it off. Failures are logged and the call goes on without a check.
"""
import difflib
import json
import logging
import math
import os
import re
import sqlite3
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

from . import gazetteer, osm_index
from .events import _norm  # accents off, Greek in Latin letters: compares how names sound

log = logging.getLogger("brain")

ENABLED = os.getenv("BRAIN_PLACE_CHECK", "on") != "off"
SEARCH_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "112-overflow-hackathon-brain/0.1 (+https://github.com/pro56john/Voice_Agents_Hackathon)"
COUNTRIES = "gr,tr,cy"
MIN_INTERVAL_S = 1.1
_AREA_KEYS = ("neighbourhood", "quarter", "suburb", "village", "town", "city_district", "city", "municipality")
_HOUSE_NUMBER = re.compile(r"\b\d+\s*[A-Za-zΑ-Ωα-ω]?\b")
# "οδό Ορλώφ" is searched as "Ορλώφ": the street word isn't part of the name on the map.
_STREET_WORD = re.compile(r"^\s*(?:οδός|οδού|οδό|οδος|οδου|οδο|λεωφόρος|λεωφόρου|λεωφόρο|λεωφ\.)\s+", re.IGNORECASE)

# Kinds of landmark, as callers say them (compared after _norm), and the English phrase that lists
# them on Nominatim ("hospitals in Piraeus"). First match wins: "τζάμι ο νοσοκομείο" is a hospital,
# not a mosque (τζαμί), even though both words are in the list.
_KINDS = [
    ("hospitals", {"nosokomeio", "nosokomeiou", "hospital", "hastane", "hastanesi", "hopital", "kliniki", "clinic"}),
    ("schools", {"scholeio", "scholeiou", "school", "okul", "okulu", "ecole", "lykeio", "gymnasio"}),
    ("churches", {"ekklisia", "ekklisias", "church", "kilise", "eglise"}),
    ("squares", {"plateia", "plateias", "square", "meydan", "meydani"}),
    ("railway stations", {"stathmos", "stathmou", "station", "istasyon", "gare"}),
    ("pharmacies", {"farmakeio", "pharmacy", "eczane", "pharmacie"}),
    ("police", {"astynomia", "astynomiko", "police", "karakol"}),
    ("universities", {"panepistimio", "university", "universite", "universitesi"}),
    ("hotels", {"xenodocheio", "hotel", "otel"}),
    ("parks", {"parko", "park", "parc"}),
    ("supermarkets", {"supermarket", "souper", "market"}),
    ("mosques", {"tzami", "mosque", "cami", "camii", "mosquee"}),
]
# Words that say nothing about which one it is.
_FILLER_WORDS = {"geniko", "genikou", "general", "near", "konta", "sto", "stin", "ston", "stis", "tou", "tis",
                 "to", "ta", "o", "i", "the", "of", "a", "an", "kentro", "yakin", "yaninda", "pres", "du", "de"}

# The place names speech-to-text is primed with; a misheard area is usually close to one of them.
_KNOWN_PLACES_FILE = Path(__file__).parent.parent / "voice" / "keywords.json"

_lock = threading.Lock()
_last = 0.0

# The real street names of an area, from OpenStreetMap's Overpass service, to tell what a misheard
# street was: speech-to-text often writes Greek street names that don't exist, and then nothing
# reaches the map. Only the area's box is sent. The public server took 33 s for one neighbourhood
# in a test, so lists are fetched in the background as soon as the area is known, and kept.
STREET_LIST = os.getenv("BRAIN_STREET_LIST", "on") != "off"
# The public servers are often busy (502/504 in an eval run): try the next one before giving up.
OVERPASS_URLS = [u for u in os.getenv("OVERPASS_URL", "").split(",") if u] or [
    "https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter"]
# A neighbourhood or town. Whole Athens (45 km on the map) timed out on the public servers in an
# eval run; there the agent asks the neighbourhood first, and that one gets a list.
STREET_LIST_MAX_KM = 20.0
LOCAL_LIST_MAX_KM = 80.0  # with the local index (osm_index.py) a whole city has a list too: Athens is 45 km
STREET_LIST_DAYS = 30
STREET_SOUNDS_LIKE = 0.75  # how close a heard street must sound to a real one to be suggested
# This close, it is the same name in other letters ("Orlof" for Ορλώφ, texted in Latin letters):
# used at once, no "did you mean". OpenStreetMap has Greek street names only in Greek.
SAME_STREET = 0.9
_street_lists = ThreadPoolExecutor(max_workers=1, thread_name_prefix="streets")
_street_lists_wanted: set[str] = set()


def _cache_path() -> Path:
    return Path(os.getenv("BRAIN_OUTPUT_DIR", "output")) / "places.sqlite"


_DISTRICT_KEYS = ("suburb", "neighbourhood", "quarter", "village", "town", "city_district", "city")


def nominatim(query: str, limit: int = 3, box: list | None = None) -> list[dict]:
    """Places for a query, each {"label", "name" (as written locally), "areas": [neighbourhood, city...],
    "district" (the neighbourhood a caller would name), "lat", "lon", "bbox", "size_km"}.
    box [south, north, west, east]: only results inside it, e.g. a street within the caller's city. Those
    hits also carry "lines": the street's own line on the map, [[lat, lon], ...] per stretch."""
    global _last
    params = {"q": query, "format": "jsonv2", "limit": limit, "addressdetails": 1, "namedetails": 1,
              "countrycodes": COUNTRIES, "accept-language": "en"}
    if box:  # simplified to about 5 m: enough to draw the street, small enough to keep in the report
        params |= {"viewbox": f"{box[2]},{box[1]},{box[3]},{box[0]}", "bounded": 1,
                   "polygon_geojson": 1, "polygon_threshold": 0.00005}
    params = urllib.parse.urlencode(params)
    with _lock:  # one request at a time, at most one a second
        time.sleep(max(0.0, _last + MIN_INTERVAL_S - time.monotonic()))
        _last = time.monotonic()
        request = urllib.request.Request(f"{SEARCH_URL}?{params}", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=4) as response:
            hits = json.loads(response.read())
    return [{"label": h.get("display_name", ""), "name": (h.get("namedetails") or {}).get("name") or h.get("name"),
             "areas": [h["address"][k] for k in _AREA_KEYS if k in h.get("address", {})],
             "district": next((h["address"][k] for k in _DISTRICT_KEYS if k in h.get("address", {})), None),
             "lat": float(h["lat"]), "lon": float(h["lon"]), "kind": h.get("category"),
             "bbox": [float(x) for x in h["boundingbox"]] if h.get("boundingbox") else None,
             "size_km": _size_km(h.get("boundingbox")), "lines": _lines(h.get("geojson"))} for h in hits]


def _lines(geojson: dict | None) -> list:
    """A street's GeoJSON line(s) as [[[lat, lon], ...], ...]; nothing for points and areas."""
    kind, coords = (geojson or {}).get("type"), (geojson or {}).get("coordinates")
    if kind == "LineString":
        coords = [coords]
    elif kind != "MultiLineString":
        return []
    return [[[round(lat, 6), round(lon, 6)] for lon, lat in line] for line in coords]


def _size_km(bbox) -> float | None:
    """The diagonal of Nominatim's bounding box [south, north, west, east], in km."""
    try:
        south, north, west, east = (float(x) for x in bbox)
    except (TypeError, ValueError):
        return None
    lat = (south + north) / 2
    return 111.2 * ((north - south) ** 2 + ((east - west) * math.cos(math.radians(lat))) ** 2) ** 0.5


def _search(query: str, search=nominatim, limit: int = 3, box: list | None = None) -> list[dict]:
    """Cached search: each query is sent once ("not found" is cached too)."""
    key = query.strip().lower() if limit == 3 else f"{limit}|{query.strip().lower()}"
    if box:  # "geo": answers with the street's line (older cached answers had none)
        key = f"geo in {','.join(f'{x:.3f}' for x in box)}|{key}"
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as conn:
        # v3: answers now say what kind of thing each one is (v2 had no "kind": an area could be a holiday flat).
        conn.execute("CREATE TABLE IF NOT EXISTS places_v3 (query TEXT PRIMARY KEY, hits TEXT NOT NULL)")
        row = conn.execute("SELECT hits FROM places_v3 WHERE query = ?", (key,)).fetchone()
        if row:
            return json.loads(row[0])
        if box:
            hits = search(query, limit=limit, box=box)
        else:
            hits = search(query) if limit == 3 else search(query, limit=limit)
        conn.execute("INSERT OR REPLACE INTO places_v3 VALUES (?, ?)", (key, json.dumps(hits, ensure_ascii=False)))
        conn.commit()
        return hits


_PLACE_KINDS = {"place", "boundary"}  # a neighbourhood, town, island or district; not a shop or a flat


def _places(hits: list[dict], need_box: bool = False) -> list[dict]:
    """Only the hits that are places (with a box, if need_box). Hits without a kind count as places."""
    return [h for h in hits if (h.get("bbox") or not need_box) and h.get("kind", "place") in _PLACE_KINDS]


def area_hit(area: str, search=nominatim, cached_only: bool = False, need_box: bool = True,
             keep: int = 1) -> dict | None:
    """The caller's area as a place on the map, or None.

    The first search answer was taken whatever it was: on a demo call (2026-10-30) the model wrote
    the area as "Acropolis, Koukaki, Athens", the first answer was a holiday flat named "Spacious apt
    in Koukaki FIX 500 meter to Acropolis", and the street was searched only inside that flat's few
    metres, so Ορλώφ wasn't found. Now only a place counts (a neighbourhood, town, island or
    district), and if the area as said isn't one, its most local parts are dropped one by one
    ("Koukaki, Athens", then "Athens"), down to `keep` parts. cached_only: never a request (used during
    a turn)."""
    parts = [p.strip() for p in area.split(",") if p.strip()]
    for i in range(max(1, len(parts) - keep + 1)):
        query = ", ".join(parts[i:])
        hits = json.loads(_cached(query) or "[]") if cached_only else _search(query, search)
        if found := _places(hits, need_box):
            return found[0]
    return None


_DOUBLE = re.compile(r"(\w)\1")


def spellings(street: str) -> list[str]:
    """'Καλλιρρόης' -> ['Καλλιρρόης', 'Καλιρρόης', 'Καλλιρόης', 'Καλιρόης']: OpenStreetMap matches
    spelling exactly, and Greek street names are written with or without doubled letters (a test
    call's Καλλιρρόης 33 is Καλλιρόης on the map: only the ρρ is single). At most 4, each cached."""
    doubles = list(_DOUBLE.finditer(street))
    one_each = [street[:m.start()] + m.group(1) + street[m.end():] for m in doubles]
    return list(dict.fromkeys([street, *one_each, _DOUBLE.sub(r"\1", street)]))[:4]


GROUP_KM = 2.0  # stretches of one street this close together are one place to the caller


def _km(a: dict, b: dict) -> float:
    lat = math.radians((a["lat"] + b["lat"]) / 2)
    return 111.2 * math.hypot(a["lat"] - b["lat"], (a["lon"] - b["lon"]) * math.cos(lat))


def street_matches(street: str, area: str, search=nominatim) -> list[dict] | None:
    """Where the street is inside the area: [{"name", "also", "lat", "lon", "km", "lines"}], closest
    to the area's centre first, stretches under GROUP_KM apart as one ("Neos Kosmos / Petralona").

    Every spelling is tried, not just until the first hit: in a test call the spelling as heard
    (Καλλιρρόης) found only a different street near Piraeus, the real one being Καλλιρόης in central
    Athens. "Athens" on the map is greater Athens, so that street came back in 8 neighbourhoods.
    None when the area has no box on the map (nothing to search inside)."""
    centre = area_hit(area, search)
    if not centre:
        return None
    hits = []
    for spelling in spellings(street):
        hits += _search(spelling, search, limit=10, box=centre["bbox"])
    # Only the street itself: the search also returns streets that merely contain the name
    # ("Yuvarlak Kaya Sokak" for Kaya Sokak). Exact names first; a hit without a name stays.
    hits = [h for h in hits if not h.get("name") or same_street(street, h["name"])]
    said = [_street_words(s) for s in spellings(street)]  # Καλλιρόης is as exact as Καλλιρρόης
    exact = [h for h in hits if h.get("name") and _street_words(h["name"]) in said]
    hits = exact or hits
    groups: list[dict] = []
    for hit in sorted(hits, key=lambda h: _km(h, centre)):
        name = hit.get("district") or (hit["areas"][0] if hit.get("areas") else area)
        # any point of the group, so a long avenue chains into one place instead of three
        near = next((g for g in groups if any(_km({"lat": a, "lon": o}, hit) < GROUP_KM for a, o in g["points"])), None)
        if near:
            near["points"].append([hit["lat"], hit["lon"]])
            near["lines"] += [line for line in hit.get("lines") or [] if line not in near["lines"]]
            if name not in (near["name"], *near["also"]):
                near["also"].append(name)
        else:
            groups.append({"name": name, "also": [], "lat": hit["lat"], "lon": hit["lon"],
                           "km": round(_km(hit, centre), 1), "points": [[hit["lat"], hit["lon"]]],
                           "lines": list(hit.get("lines") or [])})
    return [{k: v for k, v in g.items() if k != "points"} for g in groups]


def street_name(spoken_address: str | None) -> str | None:
    """'Michail Melá 13, Belokipos' -> 'Michail Melá': the street without the house number."""
    if not spoken_address:
        return None
    for part in spoken_address.split(","):
        if any(ch.isdigit() for ch in part):
            name = _HOUSE_NUMBER.sub("", part).strip(" .-")
            return name if len(name) >= 3 else None
    return None


def _plain(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))


def closest_known(area: str, spoken_address: str | None = None) -> str | None:
    """The real place closest to a misheard one, e.g. "Belokipos" -> Αμπελόκηποι, "Πυρανία" -> Παιανία.
    No network.

    All towns, villages and neighbourhoods of Greece and Türkiye (gazetteer.py), compared by sound,
    near the city the caller named ("Pyrania, Athens"). The caller's own words in spoken_address go
    first: they are in Greek letters, which also rules out Turkish villages. A test call's
    "Πυρανία" got Πετράλωνα when only the 77 places in voice/keywords.json were known."""
    parts = [p.strip() for p in area.split(",")]
    near = None
    if len(parts) > 1:
        city = next((h for h in json.loads(_cached(", ".join(parts[1:])) or "[]") if h.get("lat") is not None), None)
        near = (city["lat"], city["lon"]) if city else None
    heard = [p.strip() for p in (spoken_address or "").split(",") if p.strip() and not any(c.isdigit() for c in p)]
    for words in [*heard, parts[0]]:
        # The demo places speech-to-text is primed with first, in the caller's alphabet; then all.
        if known := _closest_primed(words):
            return known
        if place := gazetteer.closest(words, near=near):
            return place["name"]
    return None


def _closest_primed(heard: str) -> str | None:
    """The place from voice/keywords.json that sounds closest to the heard name, if close enough."""
    try:
        names = json.loads(_KNOWN_PLACES_FILE.read_text(encoding="utf-8"))["places"]
    except (OSError, ValueError, KeyError):
        return None
    key, greek = gazetteer.sound(heard), bool(gazetteer._GREEK.search(heard))
    scored = [(difflib.SequenceMatcher(None, key, gazetteer.sound(n)).ratio()
               + (0.01 if bool(gazetteer._GREEK.search(n)) == greek else 0), n) for n in names]
    score, name = max(scored, default=(0, None))
    return name if score >= 0.7 and name.lower() != heard.strip().lower() else None


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", _norm(text))


def _street_words(text: str) -> list[str]:
    """_words, with a name's last v, w or ff written as f: English speech-to-text wrote "Orlov" for
    Ορλώφ (orlof in Latin letters) on a demo call (2026-10-30), and it took a second question to find
    it. Orlov, Orlow, Orloff and Orlof are one name; only the end of a word of 4 letters or more, so a
    short word ("ev", house) stays itself."""
    return [re.sub(r"(?:v|w|ff)$", "f", w) if len(w) >= 4 else w for w in _words(text)]


def kind_of(landmark: str) -> str | None:
    """'κοντά στο τζάμι ο νοσοκομείο' -> 'hospitals'."""
    words = set(_words(landmark))
    return next((kind for kind, names in _KINDS if words & names), None)


def _name_words(text: str) -> list[str]:
    """The words that tell which one it is: 'τζάμι ο νοσοκομείο' -> ['tzami']. Only the words of the
    kind found are dropped, so 'τζάμι' stays when the kind is hospital."""
    words = _words(text)
    kind_words = next((names for _, names in _KINDS if set(words) & names), set())
    return [w for w in words if w not in kind_words and w not in _FILLER_WORDS and len(w) > 1]


def sounds_like(heard: str, name: str) -> float:
    """0..1, how close the heard name sounds to a real one, word by word (after _norm)."""
    a, b = _name_words(heard), _name_words(name)
    if not a or not b:
        return 0.0
    return max(difflib.SequenceMatcher(None, x, y).ratio() for x in a for y in b)


def check_landmark(landmark: str, area: str, search=nominatim) -> dict:
    """Is the landmark real? If not, the closest-sounding real place of the same kind in the area."""
    named = bool(_name_words(landmark))
    if named:
        hits = [(sounds_like(landmark, h["name"]), -len(h["name"]), h["name"])
                for h in _search(f"{landmark}, {area}", search) if h.get("name")]
        if hits and max(hits)[0] >= 0.6:
            return {"on_map": True, "note": None, "suggestion": max(hits)[2]}
    kind = kind_of(landmark)
    real = [h["name"] for h in _search(f"{kind} in {area}", search, limit=15) if h.get("name")] if kind else []
    real = list(dict.fromkeys(real))
    if not named and real:
        return {"on_map": False, "suggestion": None, "note": (
            f"The caller named only a kind of place ('{landmark}'); there are several in {area}: "
            f"{'; '.join(real[:5])}. Ask which one, e.g. 'Which {kind[:-1] if kind.endswith('s') else kind}: "
            f"{real[0]} or {real[1] if len(real) > 1 else 'another'}?'")}
    ranked = sorted(((sounds_like(landmark, r), r) for r in real), reverse=True)
    if ranked and ranked[0][0] >= 0.6 and (len(ranked) == 1 or ranked[0][0] - ranked[1][0] >= 0.08):
        guess = ranked[0][1]
        return {"on_map": False, "suggestion": guess, "note": (
            f"'{landmark}' is not a place on the map in {area}; speech-to-text probably misheard it. The "
            f"real place that sounds closest is '{guess}'. Ask the caller: 'Do you mean {guess}?', and "
            "update landmark and spoken_address only if they say yes.")}
    return {"on_map": False, "suggestion": None, "note": (
        f"'{landmark}' was not found on the map in {area}; it may have been misheard. Say it back and ask "
        "the caller to repeat or spell the name, or to give the street or another landmark.")}


# Turkish numbered streets keep their number: "1593 Sokak" in İzmir is the street's name.
_NUMBERED_STREET = re.compile(r"\b(\d+)\s*\.?\s*(Sokak|Sokağı|Sok\.|Sk\.|Caddesi|Cadde|Cd\.)", re.IGNORECASE)


def the_street(street: str | None, spoken_address: str | None = None) -> str | None:
    """The street to look up: the one the model recorded in the report, house number dropped.

    Only that field, never a guess from numbers in spoken_address: a Turkish caller's "100. Yıl
    Mahallesi" (a neighbourhood) was taken for a street with a house number, searched, and shown
    as "street not found" (2026-10-26). spoken_address is kept for callers that still pass it."""
    if not street:
        return None
    if numbered := _NUMBERED_STREET.search(street):
        return f"{numbered.group(1)} {numbered.group(2)}"
    name = _STREET_WORD.sub("", _HOUSE_NUMBER.sub("", street)).strip(" ,.-")
    return name if len(name) >= 3 else None


def check(area: str | None, spoken_address: str | None, landmark: str | None = None, street: str | None = None,
          search=nominatim) -> dict:
    """{"on_map": True/False/None, "note": text for the model or None, "suggestion": a real name or None}."""
    street = the_street(street, spoken_address)
    result = {"street_matches": None, **_check_area(area, street, search, spoken_address)}
    if len(result.get("street_matches") or []) > 1:
        result = _named(area, spoken_address, landmark, result) or _narrow(street, area, spoken_address, landmark, result,
                                                                 search) or result
    # Only landmarks of a known kind (hospital, school...): "κεντρική είσοδος" (main entrance) once
    # replaced the hospital as the landmark and raised a false "not found".
    if result["on_map"] is False or not landmark or not area or street or not kind_of(landmark):
        return {**result, "suggestion": None}  # a street pins the place better than a landmark
    return check_landmark(_HOUSE_NUMBER.sub("", landmark).strip(), area, search)


def overpass_streets(box: list) -> list[str]:
    """Every named road in box [south, north, west, east], from Overpass, trying each server."""
    query = f"[out:json][timeout:120];way[highway][name]({box[0]},{box[2]},{box[1]},{box[3]});out tags;"
    error = None
    for url in OVERPASS_URLS:
        request = urllib.request.Request(url, data=urllib.parse.urlencode({"data": query}).encode(),
                                         headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=150) as response:
                elements = json.loads(response.read()).get("elements", [])
            return sorted({e["tags"]["name"] for e in elements if e.get("tags", {}).get("name")})
        except Exception as exc:  # busy or down: the next server
            error = exc
            log.info("street list from %s failed: %s", url, str(exc)[:80])
    raise error


def size_km(area: str) -> float | None:
    """The area's size on the map, only if it was already looked up (never a request: used
    during a turn). The map check looks every area up in the background."""
    hit = area_hit(area, cached_only=True)
    return hit.get("size_km") if hit else None


def has_street_list(area: str | None) -> bool:
    """Whether the area's street list is already kept (no request). A map check that ran before the
    list arrived runs again once it is there: the public server answered 504 the first time in a
    test, and a texted "Orlof" stayed "not found" although the list had Ορλώφ."""
    if not area:
        return False
    centre = area_hit(area, cached_only=True)
    if not centre:
        return False
    if osm_index.available():
        return (centre.get("size_km") or 99) <= LOCAL_LIST_MAX_KM
    key = ",".join(f"{x:.3f}" for x in centre["bbox"])
    try:
        with closing(sqlite3.connect(_cache_path())) as conn:
            return conn.execute("SELECT 1 FROM street_lists WHERE box = ?", (key,)).fetchone() is not None
    except sqlite3.Error:
        return False


def _cached(query: str) -> str | None:
    """A search's cached answer as stored, or None, without ever searching."""
    try:
        with closing(sqlite3.connect(_cache_path())) as conn:
            row = conn.execute("SELECT hits FROM places_v3 WHERE query = ?", (query.strip().lower(),)).fetchone()
    except sqlite3.Error:
        return None
    return row[0] if row else None


def street_names(area: str, search=nominatim, fetch=overpass_streets) -> list[str] | None:
    """The real street names in the area, or None while they are being fetched (or for a big area)."""
    centre = area_hit(area, search)
    if centre and osm_index.available() and 0.2 <= (centre.get("size_km") or 99) <= LOCAL_LIST_MAX_KM:
        try:
            return osm_index.streets_in(centre["bbox"])  # on this machine: no request, no size limit but a region's
        except Exception:
            log.exception("local street index unreadable; using Overpass")
    if not centre or not 0.2 <= (centre.get("size_km") or 99) <= STREET_LIST_MAX_KM:
        return None  # a single point has no streets; a whole region has too many
    key = ",".join(f"{x:.3f}" for x in centre["bbox"])
    with closing(sqlite3.connect(_cache_path())) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS street_lists (box TEXT PRIMARY KEY, names TEXT NOT NULL, fetched REAL)")
        row = conn.execute("SELECT names, fetched FROM street_lists WHERE box = ?", (key,)).fetchone()
    if row and time.time() - row[1] < STREET_LIST_DAYS * 86400:
        return json.loads(row[0])
    if STREET_LIST and key not in _street_lists_wanted:
        _street_lists_wanted.add(key)
        _street_lists.submit(_fetch_street_list, key, centre["bbox"], fetch)
    return None


def _fetch_street_list(key: str, box: list, fetch) -> None:
    try:
        names = fetch(box)
    except Exception as exc:  # busy or offline: try again on a later check
        log.warning("street list for %s failed: %s", key, str(exc)[:120])
        _street_lists_wanted.discard(key)
        return
    with closing(sqlite3.connect(_cache_path())) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS street_lists (box TEXT PRIMARY KEY, names TEXT NOT NULL, fetched REAL)")
        conn.execute("INSERT OR REPLACE INTO street_lists VALUES (?, ?, ?)", (key, json.dumps(names, ensure_ascii=False), time.time()))
        conn.commit()
    log.info("street list for %s: %d names", key, len(names))


def _street_sound(heard: str, name: str) -> float:
    """0..1, how close a heard street sounds to a real one, in Latin letters. Callers say the
    surname only ("Διάκου" for "Αθανασίου Διάκου"), so single words of the name count too."""
    a, b = " ".join(_street_words(heard)), " ".join(_street_words(name))
    if not a or not b:
        return 0.0
    scores = [difflib.SequenceMatcher(None, a, b).ratio()]
    if " " not in a:
        scores += [difflib.SequenceMatcher(None, a, w).ratio() for w in b.split() if len(w) >= 4]
    return max(scores)


# What kind of road a name says, for same_street: a Turkish Cadde is not a Bulvar of the same name.
_ROAD_TYPES = {"sokak": "sokak", "sokagi": "sokak", "sk": "sokak", "cadde": "cadde", "caddesi": "cadde",
               "cd": "cadde", "bulvar": "bulvar", "bulvari": "bulvar", "blv": "bulvar", "odos": "odos",
               "odou": "odos", "leoforos": "leoforos", "leoforou": "leoforos", "street": "street",
               "st": "street", "avenue": "avenue", "ave": "avenue", "road": "road", "rd": "road"}


def _road_type(name: str) -> str | None:
    from .gazetteer import sound  # Greek letters written in Latin ones, as said: "οδός" -> "odos"
    for word in name.split():
        if kind := _ROAD_TYPES.get(sound(word).replace("ğ", "g")) or _ROAD_TYPES.get(_plain(word).replace("ı", "i")):
            return kind
    return None


def same_street(heard: str, name: str) -> bool:
    """Whether a street on the map is the one the caller named, not just one with a word in common.

    A Turkish test address "Kaya Sokak" matched "Yuvarlak Kaya Sokak", another street, because a
    name containing the heard words counted. Now: the same words (accents, letters and the road word
    aside: "Orlof" is Ορλώφ, "οδός Ορλώφ" is Ορλώφ), or the same number of words spelled a little
    differently (Καλλιρρόης / Καλλιρόης). In Greek a caller may drop the first name or title
    ("Διάκου" for "Αθανασίου Διάκου"); elsewhere the extra word makes it a different street. A
    different road word (Cadde / Bulvar) is a different street."""
    said, real = _street_words(heard), _street_words(name)
    if not said or not real:
        return False
    kinds = _road_type(heard), _road_type(name)
    if all(kinds) and kinds[0] != kinds[1] and {kinds[0], kinds[1]} != {"odos", "leoforos"}:
        return False
    if said == real:
        return True
    if re.search(r"[Ͱ-Ͽ]", name) and len(said) < len(real) and real[-len(said):] == said:
        return True
    return len(said) == len(real) and difflib.SequenceMatcher(None, " ".join(said), " ".join(real)).ratio() >= 0.85


def closest_street(heard: str, names: list[str]) -> str | None:
    """The real street that sounds closest to the one heard, if it is close enough."""
    best = max(names, key=lambda n: _street_sound(heard, n), default=None)
    return best if best and _street_sound(heard, best) >= STREET_SOUNDS_LIKE else None


LANDMARK_NEAR_KM = 2.0  # a landmark this close to one stretch of the street, and far from the others, picks it


NAMED_SOUNDS_LIKE = 0.8  # a neighbourhood the caller said, against the names of the places the street is in


def _named(area: str | None, spoken_address: str | None, landmark: str | None, result: dict) -> dict | None:
    """The street is in several places, and the caller named one of them: that one.

    Demo call 2026-10-30: "Filippou 13, Thessaloniki" is in Διοικητήριο, Evosmos and Πυλαία; the
    agent asked which, the caller said "Dikitirio", and the area became "Dioikitirio, Thessaloniki".
    _narrow then searched the street inside that area, but OpenStreetMap has no place called
    Διοικητήριο, so the search fell back to all of Thessaloniki, the three places came back, and the
    map showed the whole city. The places are already known by name: the one the caller named (in
    any alphabet, as heard: "Dikitirio" is 0.9 like Διοικητήριο) is taken, if no other comes close.
    Not a landmark ("near the Acropolis" is not the neighbourhood Akropoli): _narrow asks about those."""
    plain_landmark = _plain(landmark or "")
    said = [p.strip() for p in f"{spoken_address or ''},{area or ''}".split(",")
            if p.strip() and not any(ch.isdigit() for ch in p) and not (plain_landmark and plain_landmark in _plain(p))]
    matches = result["street_matches"]
    scores = [max((sounds_like(p, name) for p in said for name in [m["name"], *(m.get("also") or [])]), default=0.0)
              for m in matches]
    best = max(scores, default=0.0)
    if best < NAMED_SOUNDS_LIKE or sorted(scores)[-2] > best - 0.15:
        return None
    chosen = matches[scores.index(best)]
    return {**result, "street_matches": [chosen], "note": (
        f"The street is in several places in {area}; the caller named {chosen['name']}, and it is there. Set area "
        "to that neighbourhood in English with the city, and don't ask which neighbourhood again.")}


def _narrow(street: str, area: str, spoken_address: str | None, landmark: str | None, result: dict,
            search=nominatim) -> dict | None:
    """The street is in several places in the area: use what else the caller said to pick one.

    A test caller said "Ορλώφ, Κουκάκι, Αθήνα, near the Acropolis", but the area stayed "Athens", so
    Orlof Street came back in Koukaki and in Glyfada. Searched inside "Κουκάκι, Athens" it is found
    once; and the Acropolis is 0.5 km from one and 12 km from the other."""
    plain_street, plain_landmark = _plain(street), _plain(landmark or "")
    parts = [p.strip() for p in (spoken_address or "").split(",") if p.strip()]
    for part in parts[:-1][:4]:  # the last part is the town or city (street first, then neighbourhood, then city)
        plain = _plain(part)
        if (plain_street in plain or any(ch.isdigit() for ch in part)
                or (plain_landmark and plain_landmark in plain) or sounds_like(part, area) >= 0.6):
            continue  # the street, a number, the landmark, or the city itself
        inside = street_matches(street, f"{part}, {area}", search)
        if inside and len(inside) == 1:
            return {**result, "street_matches": inside, "note": (
                f"The street is in several places in {area}, but the caller said '{part}', and it is there "
                f"({inside[0]['name']}). Set area to the neighbourhood the caller said, in English, with the "
                "city (e.g. 'Koukaki, Athens' for 'Κουκάκι').")}
    if landmark:
        place = next(iter(_search(f"{_HOUSE_NUMBER.sub('', landmark).strip()}, {area}", search)), None)
        if place and place.get("lat") is not None:
            matches = sorted(result["street_matches"], key=lambda m: _km(m, place))
            near, other = _km(matches[0], place), _km(matches[1], place)
            if near <= LANDMARK_NEAR_KM and other >= 3 * max(near, 0.3):
                return {**result, "street_matches": [{**matches[0], "km": round(near, 1)}], "note": (
                    f"The street is in several places in {area}; next to the landmark the caller gave "
                    f"('{landmark}') it is in {matches[0]['name']}. Confirm with one short question, e.g. "
                    f"'Near {landmark}, in {matches[0]['name']}?', and set area to that neighbourhood "
                    "in English with the city.")}
    return None


def _area_found(area: str, search=nominatim) -> bool:
    """'Keratsini, Athens' isn't found as written (Keratsini isn't in the City of Athens), but
    'Keratsini' is: try the most local part on its own too. A false "not found" makes the agent
    ask a caller to repeat a correct place."""
    first = area.split(",")[0].strip()
    # Dropping parts only while two are left: "Acropolis, Koukaki, Athens" is found as "Koukaki, Athens",
    # but a misheard "Belokipos, Athens" must not count as found because "Athens" is.
    return bool(area_hit(area, search, need_box=False, keep=2)) or (
        first != area.strip() and bool(_places(_search(first, search))))


def _check_area(area: str | None, street: str | None, search=nominatim, spoken_address: str | None = None) -> dict:
    if not area and not street:
        return {"on_map": None, "note": None}
    if area and _area_found(area, search):
        names = street_names(area, search) if ENABLED and STREET_LIST else None  # starts the fetch early
        matches = street_matches(street, area, search) if street else None
        if matches is None:
            return {"on_map": True, "note": None}
        # The notes name neighbourhoods only, never the street: the model never sees addresses.
        if len(matches) > 1:
            names = [m["name"] + (f" ({', '.join(m['also'])})" if m["also"] else "") for m in matches[:3]]
            more = f", and {len(matches) - 3} more farther out" if len(matches) > 3 else ""
            return {"on_map": True, "street_matches": matches, "note": (
                f"The street the caller gave exists in several places in {area}, closest first: "
                f"{'; '.join(names)}{more}. Ask which neighbourhood, offering the first two or three "
                f"(e.g. 'Is that in {matches[0]['name']} or {matches[1]['name']}?'), and set area. If the caller's "
                "message already names the neighbourhood, take it and set area instead of asking.")}
        if not matches:
            real = closest_street(street, names) if names else None
            if real and _street_sound(street, real) >= SAME_STREET and same_street(street, real):
                found = street_matches(real, area, search)
                if found:
                    if len(found) > 1:
                        return {"on_map": True, "street_matches": found, "note": (
                            f"The street the caller gave exists in several places in {area}. Ask which "
                            f"neighbourhood, e.g. 'Is that in {found[0]['name']} or {found[1]['name']}?'.")}
                    return {"on_map": True, "street_matches": found, "note": None}
            if real:  # core.py masks the name before the model sees the note
                return {"on_map": True, "street_matches": [], "street_suggestion": real, "note": (
                    f"The street the caller gave was not found in {area}; it was probably misheard. The real "
                    f"street that sounds closest is {real}. Ask the caller, in the caller's language: 'Did you mean {real}?' and "
                    "nothing else. Do not change street or spoken_address yourself and never say the two names together: "
                    "the code puts the real street into the report when the caller says yes.")}
            return {"on_map": True, "street_matches": [], "note": (
                f"The street the caller gave was not found in {area}; it may have been misheard. Ask which "
                "neighbourhood it is in, or to repeat or spell the street.")}
        return {"on_map": True, "street_matches": matches, "note": None}
    elsewhere = []
    if street:
        for hit in _search(street, search):
            name = ", ".join(hit["areas"][:2]) if hit["areas"] else ""
            if name and name not in elsewhere:
                elsewhere.append(name)
    if area and elsewhere:
        return {"on_map": False, "note": (
            f"'{area}' was not found on the map; it may have been misheard. The street the caller gave "
            f"exists in: {'; '.join(elsewhere)}. Ask the caller to confirm, e.g. 'Did you mean "
            f"{elsewhere[0].split(',')[0]}?', and update area.")}
    if area and (guess := closest_known(area, spoken_address)):
        return {"on_map": False, "note": (
            f"'{area}' was not found on the map; it may have been misheard. A known place with a similar "
            f"name is {guess}. Ask the caller to confirm: 'Did you mean {guess}?', and update area.")}
    if area:
        return {"on_map": False, "note": (
            f"'{area}' was not found on the map; it may have been misheard. Say the place back to the "
            "caller and ask them to repeat it slowly or spell it, or to name a landmark nearby.")}
    if street and not elsewhere:
        return {"on_map": False, "note": (
            "The street the caller gave was not found on the map; it may have been misheard. Ask them "
            "to repeat or spell the street, and for the neighbourhood or town.")}
    return {"on_map": None, "note": None}  # street found, area not said yet: the normal questions ask for it
