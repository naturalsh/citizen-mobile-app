"""Find map positions for incidents with OpenStreetMap's Nominatim search.

Most calls have no GPS (AML) position, only an area like "Vathy, Samos". The dashboard looks
that area up once on OpenStreetMap and caches the answer in output/geocode.sqlite.

Privacy and fair use:
- The `area` (village, neighbourhood, town) and the street name are sent to Nominatim, never a
  house number or the caller's name (the user's rule since 2026-10-22). To pin the building, the
  dashboard asks Overpass for every numbered building in a small box around the street the brain
  found, and picks the caller's number on this machine: only the box is sent, never the number,
  street or name. DASHBOARD_HOUSE_NUMBERS=off turns that off.
- A street position is used only if it lies within STREET_MAX_KM of the area: Greek street names
  repeat, and a test call's "Καλλιρρόης, Athens" came back as a street in Ekali, 16 km away.
  Otherwise the incident stays at the area position.
- Nominatim's usage policy allows at most 1 request per second, needs an identifying
  User-Agent, and asks for caching: lookups run one at a time in a background thread, and
  every answer (also "not found") is cached.
- DASHBOARD_GEOCODE=off turns lookups off; incidents with GPS still show on the map.
"""
import json
import logging
import math
import os
import queue
import re
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
from contextlib import closing
from pathlib import Path

from brain import osm_index
from brain.places import OVERPASS_URLS, USER_AGENT as _OVERPASS_AGENT, same_street, spellings, street_name, the_street

log = logging.getLogger("dashboard")

ENABLED = os.getenv("DASHBOARD_GEOCODE", "on") != "off"
SEARCH_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "112-overflow-hackathon-dashboard/0.1 (+https://github.com/pro56john/Voice_Agents_Hackathon)"
COUNTRIES = "gr,tr,cy"  # the deployment area; keeps "Vathy" from matching elsewhere
RETRY_MISS_S = 24 * 3600  # look a not-found area up again after a day
RETRY_ERROR_S = 300  # after a failed request (offline, rate-limited), wait before trying that area again
STREET_MAX_KM = 3.0  # a street found farther than this from the caller's area is someone else's street
# A street is placed only inside an area at most this big. In a whole city street names repeat: a
# test call's Καλλιρρόης, Athens matched one in Ekali (16 km) and then one near Piraeus (9 km).
STREET_AREA_MAX_M = 5000
# How far from the pin the caller may be, drawn as a dashed circle on the map. An area's own size
# comes from OpenStreetMap's bounding box; these are the fallbacks and limits.
AREA_RADIUS_M = 1500  # an area looked up before sizes were kept
STREET_RADIUS_M = 250  # somewhere along the street: the house number wasn't found
HOUSE_NUMBERS = os.getenv("DASHBOARD_HOUSE_NUMBERS", "on") != "off"
HOUSE_RADIUS_M = 30  # the building itself
HOUSE_MAX_M = 300  # the box around the street searched for numbered buildings
HOUSE_BOX_MAX_KM = 2.0  # a long avenue: only this much around the point the brain found
NEAR_NUMBERS = 10  # one mapped neighbour this many numbers away still places the caller roughly
ESTIMATE_MAX_M = 150  # an estimate vaguer than this is no better than the street
# Nothing mapped on the caller's side: a number this close on the facing side (12 faces 9 to 13) still
# places them, with the street's width added to the circle. Ορλώφ in Koukaki has only No. 9 mapped.
FACING_NUMBERS = 4
STREET_WIDTH_M = 15
# The house number next to the street: "Ορλώφ 12Α", "Gazi Caddesi No 18". Not "100. Yıl", an ordinal.
_NUMBER = re.compile(r"(?:\b(?:No|Nr|αρ)\.?\s*)?\b(\d{1,4})\s*([A-Za-zΑ-Ωα-ω])?(?![\w])(?!\.\s*\w)")
GPS_RADIUS_M = 50  # phone GPS without its own accuracy


def _radius_m(bbox: list | None) -> float | None:
    """Half the diagonal of Nominatim's bounding box [south, north, west, east], in metres."""
    try:
        south, north, west, east = (float(x) for x in bbox)
    except (TypeError, ValueError):
        return None
    return round(min(max(_km({"lat": south, "lon": west}, {"lat": north, "lon": east}) * 500, 100), 15000))


def nominatim(query: str, box: tuple | None = None) -> dict | None:
    """One Nominatim search. Returns {"lat", "lon", "label", "radius_m", "shape"} or None.
    box (lat, lon, radius_m): only results inside that square, e.g. a street within the caller's area.
    shape: an area's outline (GeoJSON polygon, simplified to about 50 m), drawn instead of a circle."""
    params = {"q": query, "format": "jsonv2", "limit": 1 if box else 5, "countrycodes": COUNTRIES,
              "accept-language": "en", "addressdetails": 1}
    if not box:
        params |= {"polygon_geojson": 1, "polygon_threshold": 0.0005}
    if box:
        lat, lon, r = box
        dlat, dlon = r / 111_000, r / (111_000 * max(math.cos(math.radians(lat)), 0.1))
        params |= {"viewbox": f"{lon - dlon},{lat + dlat},{lon + dlon},{lat - dlat}", "bounded": 1}
    params = urllib.parse.urlencode(params)
    request = urllib.request.Request(f"{SEARCH_URL}?{params}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=10) as response:
        results = json.loads(response.read())
    if not box:
        # An area is a place (neighbourhood, town, district), never the shop or holiday flat that came first:
        # "Acropolis, Koukaki, Athens" was pinned on "Spacious apt in Koukaki FIX 500 meter to Acropolis".
        results = [r for r in results if r.get("category") in ("place", "boundary")]
    if not results:
        return None
    hit = results[0]
    shape = hit.get("geojson") if (hit.get("geojson") or {}).get("type") in ("Polygon", "MultiPolygon") else None
    return {"lat": float(hit["lat"]), "lon": float(hit["lon"]), "label": hit.get("display_name", query),
            "radius_m": _radius_m(hit.get("boundingbox")), "shape": shape}


def overpass_addresses(box: tuple) -> list[dict]:
    """Every numbered building or address point in box (south, north, west, east), from Overpass:
    [{"street", "number", "lat", "lon"}]. Only the box is sent: the number is picked here."""
    south, north, west, east = box
    query = (f'[out:json][timeout:60];nwr["addr:housenumber"]({south:.5f},{west:.5f},{north:.5f},{east:.5f});'
             "out center tags;")
    error = None
    for url in OVERPASS_URLS:  # the public servers are often busy: the next one
        request = urllib.request.Request(url, data=urllib.parse.urlencode({"data": query}).encode(),
                                         headers={"User-Agent": _OVERPASS_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                elements = json.loads(response.read()).get("elements", [])
        except Exception as exc:
            error = exc
            continue
        found = []
        for e in elements:
            tags, point = e.get("tags") or {}, e.get("center") or e
            if tags.get("addr:street") and point.get("lat") is not None:
                found.append({"street": tags["addr:street"], "number": tags["addr:housenumber"],
                              "lat": point["lat"], "lon": point["lon"]})
        return found
    raise error


def _number_value(number: str) -> int | None:
    m = re.match(r"\s*(\d+)", number or "")
    return int(m.group(1)) if m else None


def place_number(street: str, number: str, addresses: list[dict]) -> dict | None:
    """Where house `number` on `street` is, from the numbered buildings mapped nearby, or None.

    The building itself when it is mapped; else between the nearest mapped numbers on the same side
    (even and odd numbers face each other), e.g. No. 10 between 4 and 12; else next to one mapped
    neighbour at most NEAR_NUMBERS away; else across from a number at most FACING_NUMBERS away on the
    other side. "radius_m" says how sure: 30 m for the building."""
    mine = [a for a in addresses if same_street(street, a["street"])]
    wanted, value = _plain_number(number), _number_value(number)
    for a in mine:
        if _plain_number(a["number"]) == wanted:
            return {"lat": a["lat"], "lon": a["lon"], "precision": "house", "radius_m": HOUSE_RADIUS_M,
                    "how": "the building"}
    if value is None:
        return None
    side = sorted(((v, a) for a in mine if (v := _number_value(a["number"])) is not None and v % 2 == value % 2),
                  key=lambda va: va[0])
    below = [va for va in side if va[0] < value]
    above = [va for va in side if va[0] > value]
    if below and above:
        (lo, a), (hi, b) = below[-1], above[0]
        share = (value - lo) / (hi - lo)
        spot = {"lat": a["lat"] + share * (b["lat"] - a["lat"]), "lon": a["lon"] + share * (b["lon"] - a["lon"])}
        radius = max(HOUSE_RADIUS_M, round(_km(a, b) * 1000 / 2))
        if radius <= ESTIMATE_MAX_M:
            return {**spot, "precision": "estimated", "radius_m": radius,
                    "how": f"estimated between No. {a['number']} and No. {b['number']}"}
    near = min(below[-1:] + above[:1], key=lambda va: abs(va[0] - value), default=None)
    if near and abs(near[0] - value) <= NEAR_NUMBERS:
        radius = min(ESTIMATE_MAX_M, HOUSE_RADIUS_M + 8 * abs(near[0] - value))
        return {"lat": near[1]["lat"], "lon": near[1]["lon"], "precision": "estimated", "radius_m": radius,
                "how": f"estimated near No. {near[1]['number']}"}
    facing = min(((abs(v - value), a) for a in mine if (v := _number_value(a["number"])) is not None
                  and v % 2 != value % 2), key=lambda da: da[0], default=None)
    if facing and facing[0] <= FACING_NUMBERS:
        radius = min(ESTIMATE_MAX_M, HOUSE_RADIUS_M + 8 * facing[0] + STREET_WIDTH_M)
        return {"lat": facing[1]["lat"], "lon": facing[1]["lon"], "precision": "estimated", "radius_m": radius,
                "how": f"estimated across from No. {facing[1]['number']}"}
    return None


def _street_box(match: dict) -> tuple:
    """(south, north, west, east) around the street the brain found, at most HOUSE_BOX_MAX_KM wide."""
    points = [pt for line in match.get("lines") or [] for pt in line] or [[match["lat"], match["lon"]]]
    half = HOUSE_BOX_MAX_KM / 2 / 111.2
    lats = [min(max(lat, match["lat"] - half), match["lat"] + half) for lat, _ in points]
    lons = [min(max(lon, match["lon"] - half), match["lon"] + half) for _, lon in points]
    pad = HOUSE_MAX_M / 111_000
    return (round(min(lats) - pad, 4), round(max(lats) + pad, 4), round(min(lons) - pad, 4), round(max(lons) + pad, 4))


def _plain_number(number: str | None) -> str:
    """'12 Α', '12a', '12Α' -> '12a': compares house numbers however they are written."""
    plain = (number or "").replace(" ", "").lower()
    return plain.translate(str.maketrans("αβγδε", "abgde"))


def house_number(street: str | None, spoken_address: str | None) -> str | None:
    """The house number said with the street, or None. Only from the part of the address that has
    the street in it, so a floor, a neighbourhood number or a count elsewhere is never taken."""
    if not street:
        return None
    for part in [street, *(spoken_address or "").split(",")]:
        if street.casefold() not in part.casefold():
            continue
        rest = re.sub(re.escape(street), " ", part, flags=re.IGNORECASE)
        if m := _NUMBER.search(rest):
            return m.group(1) + (m.group(2) or "")
    return None


def _queries(area: str) -> list[str]:
    """"Vathy, Samos" -> ["Vathy, Samos", "Samos"]: drop the most local part if nothing is found."""
    parts = [p.strip() for p in area.split(",") if p.strip()]
    return [", ".join(parts[i:]) for i in range(len(parts))]


class Geocoder:
    def __init__(self, path: Path, search=nominatim, enabled: bool = ENABLED, min_interval_s: float = 1.1,
                 addresses=overpass_addresses):
        self.path = path
        self.search = search
        self.addresses = addresses
        self._boxes: queue.Queue = queue.Queue()  # numbered buildings to fetch (Overpass, its own pace)
        self._boxes_queued: set[tuple] = set()
        self.enabled = enabled
        self.min_interval_s = min_interval_s
        self._todo: queue.Queue = queue.Queue()
        self._queued: set[str] = set()
        self._failed: dict[str, float] = {}  # area -> time of the last failed request
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as conn:
            # v2: areas are places only; the first table kept a holiday flat as "Acropolis, Koukaki, Athens".
            # shape: the area's outline; "" when it has none.
            conn.execute("""CREATE TABLE IF NOT EXISTS places_v2 (
                area TEXT PRIMARY KEY, lat REAL, lon REAL, label TEXT, looked_up REAL NOT NULL, radius_m REAL,
                matched TEXT, shape TEXT)""")
            conn.execute("CREATE TABLE IF NOT EXISTS addresses (box TEXT PRIMARY KEY, items TEXT, looked_up REAL NOT NULL)")
            conn.commit()
        if enabled:
            threading.Thread(target=self._work, daemon=True, name="geocoder").start()
            threading.Thread(target=self._work_boxes, daemon=True, name="addresses").start()

    def numbered_buildings(self, box: tuple) -> list[dict] | None:
        """The numbered buildings in box, cached; None while they are fetched in the background."""
        if osm_index.available():  # on this machine, nothing sent (brain/osm_index.py)
            try:
                return osm_index.addresses_in(box)
            except Exception:
                log.exception("local address index unreadable; using Overpass")
        key = ",".join(f"{x:.4f}" for x in box)
        with closing(sqlite3.connect(self.path)) as conn:
            row = conn.execute("SELECT items, looked_up FROM addresses WHERE box = ?", (key,)).fetchone()
        if row and row[0] is not None:
            return json.loads(row[0])
        if self.enabled and (not row or time.time() - row[1] > RETRY_ERROR_S):
            with self._lock:
                if box not in self._boxes_queued:
                    self._boxes_queued.add(box)
                    self._boxes.put(box)
        return None

    def _work_boxes(self) -> None:
        while True:
            box = self._boxes.get()
            key = ",".join(f"{x:.4f}" for x in box)
            try:
                items = json.dumps(self.addresses(box), ensure_ascii=False)
            except Exception as exc:  # busy servers: tried again after RETRY_ERROR_S, the street pin stays
                log.warning("numbered buildings lookup failed: %s", str(exc)[:120])
                items = None
            with closing(sqlite3.connect(self.path)) as conn:
                conn.execute("INSERT OR REPLACE INTO addresses VALUES (?, ?, ?)", (key, items, time.time()))
                conn.commit()
            with self._lock:
                self._boxes_queued.discard(box)

    def _row(self, area: str):
        with closing(sqlite3.connect(self.path)) as conn:
            return conn.execute("SELECT lat, lon, label, looked_up, radius_m, matched, shape FROM places_v2 "
                                "WHERE area = ?", (area,)).fetchone()

    def lookup(self, area: str | None, exact: bool = False, near: tuple | None = None) -> dict | None:
        """Cached position for an area, or None (and a background lookup is queued).
        exact: look up only this text, without dropping parts ("Vathy, Samos" -> "Samos").
        near (lat, lon, radius_m): a street, searched in its spellings only inside that square."""
        if not area:
            return None
        key = ("exact:" if exact else "") + area.strip().lower()
        if near:
            key = f"near:{near[0]:.3f},{near[1]:.3f},{int(near[2])}:" + area.strip().lower()
        row = self._row(key)
        if row and row[0] is not None:
            if row[4] is None or (row[6] is None and not near):
                self._queue(key, area, exact, near)  # looked up before sizes or outlines were kept: once more
            return {"lat": row[0], "lon": row[1], "label": row[2], "source": "openstreetmap",
                    "radius_m": row[4] or AREA_RADIUS_M, "matched": row[5] or area,
                    "shape": json.loads(row[6]) if row[6] else None}
        if not row or time.time() - row[3] > RETRY_MISS_S:
            self._queue(key, area, exact, near)
        return None

    def _queue(self, key: str, area: str, exact: bool, near: tuple | None = None) -> None:
        if not self.enabled:
            return
        with self._lock:
            if key not in self._queued and time.time() - self._failed.get(key, 0) > RETRY_ERROR_S:
                self._queued.add(key)
                self._todo.put((key, area, exact, near))

    def pending(self) -> int:
        return self._todo.qsize()

    def _work(self) -> None:
        last = 0.0
        while True:
            key, area, exact, near = self._todo.get()
            hit = matched = None
            try:
                for query in spellings(area) if near else [area] if exact else _queries(area):
                    matched = query
                    time.sleep(max(0.0, self.min_interval_s - (time.time() - last)))  # at most 1 request/s
                    last = time.time()
                    hit = self.search(query, box=near) if near else self.search(query)
                    if hit:
                        break
            except Exception as exc:  # offline, rate-limited: try again later, never break the dashboard
                log.warning("OpenStreetMap lookup failed for %r: %s", area, exc)
                with self._lock:
                    self._queued.discard(key)
                    self._failed[key] = time.time()
                continue
            with closing(sqlite3.connect(self.path)) as conn:
                conn.execute("INSERT OR REPLACE INTO places_v2 (area, lat, lon, label, looked_up, radius_m, matched, "
                             "shape) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                             (key, hit and hit["lat"], hit and hit["lon"], hit and hit["label"], time.time(),
                              hit and (hit.get("radius_m") or AREA_RADIUS_M),  # never NULL: NULL means "refresh"
                              hit and matched,  # e.g. "Chania" when "Old port, Chania" wasn't found
                              json.dumps(hit["shape"]) if hit and hit.get("shape") else ""))
                conn.commit()
            with self._lock:
                self._queued.discard(key)


def _km(a: dict, b: dict) -> float:
    lat = math.radians((a["lat"] + b["lat"]) / 2)
    return 111.2 * math.hypot(a["lat"] - b["lat"], (a["lon"] - b["lon"]) * math.cos(lat))


def locate(incident: dict, geocoder: Geocoder) -> dict | None:
    """GPS (AML) if any; else the street the caller named, if it is found near the area; else the area.

    "precision" says how exact the pin is ("gps", "street" or "area") and "radius_m" how far from
    it the caller may be: the dashboard draws that as a circle, so an area centre never looks exact."""
    points = [c["location"]["aml"] for c in incident["calls"] if (c["location"]["aml"] or {}).get("lat") is not None]
    if points:
        return {
            "lat": sum(p["lat"] for p in points) / len(points),
            "lon": sum(p["lon"] for p in points) / len(points),
            "label": "caller GPS (AML)",
            "source": "aml",
            "precision": "gps",
            "radius_m": max((p.get("accuracy_m") or GPS_RADIUS_M) for p in points),
        }
    area = geocoder.lookup(incident["area"])
    street = next((s for c in incident["calls"]
                   if (s := the_street(c["location"].get("street"), c["location"].get("spoken_address")))), None)
    # The brain already searched the street in every neighbourhood of the area (brain/places.py).
    matches = next((c["location"]["street_matches"] for c in incident["calls"]
                    if c["location"].get("street_matches") is not None), None)
    if matches and len(matches) == 1:
        m = matches[0]
        number = next((n for c in incident["calls"] if (n := house_number(street, c["location"].get("spoken_address"))
                                                         or house_number(street, c["location"].get("street")))), None)
        if HOUSE_NUMBERS and street and number:
            # Every numbered building around the street comes back; the caller's number is picked here.
            buildings = geocoder.numbered_buildings(_street_box(m))
            spot = place_number(street, number, buildings) if buildings else None
            if spot:
                return {"lat": spot["lat"], "lon": spot["lon"], "source": "building", "precision": spot["precision"],
                        "radius_m": spot["radius_m"], "label": f"{street} {number}, {m['name']} ({spot['how']})"}
        why = "house number not used" if not HOUSE_NUMBERS else "no house number said" if not number else \
            "house number not on OpenStreetMap"
        return {"lat": m["lat"], "lon": m["lon"], "label": f"{street or 'street'}, {m['name']} ({why})",
                "source": "street", "precision": "street", "radius_m": STREET_RADIUS_M,
                "lines": m.get("lines") or None}  # the whole street is drawn: the house number isn't known
    if area and matches is not None:
        wider = (area.get("matched") or incident["area"] or "").strip().lower() != (incident["area"] or "").strip().lower()
        return {**area, "precision": "wider" if wider else "area", "street": street,
                "street_choices": matches,  # several: the agent asks which neighbourhood; none: maybe misheard
                "street_not_placed": None}
    big_area = area and (area.get("radius_m") or AREA_RADIUS_M) > STREET_AREA_MAX_M
    if area and street and not big_area:
        # Only inside the caller's area: a search across the country found a same-named street 16 km away.
        reach = max(area.get("radius_m") or AREA_RADIUS_M, STREET_MAX_KM * 1000)
        hit = geocoder.lookup(street, near=(area["lat"], area["lon"], reach))
        if hit and _km(hit, area) * 1000 <= reach * 1.5:
            return {**hit, "label": f"{street} (street; house number not used)", "source": "street",
                    "precision": "street", "radius_m": STREET_RADIUS_M}
    if not area:
        return None
    # "Old port, Chania" not found but "Chania" was: the whole wider place, said as such on the page.
    matched = area.get("matched") or incident["area"] or ""
    wider = matched.strip().lower() != (incident["area"] or "").strip().lower()
    return {**area, "precision": "wider" if wider else "area",
            "street_not_placed": street if street and big_area else None}  # said on the page
