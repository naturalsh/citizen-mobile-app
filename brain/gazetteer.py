"""Every town, village and neighbourhood of Greece and Türkiye, to tell what a misheard place was.

In a test call speech-to-text heard Παιανία (Peania) as "Πυρανία", and the map check, which knew
only the 77 places in voice/keywords.json, suggested Πετράλωνα, a different neighbourhood. The
list here comes from GeoNames (https://www.geonames.org, CC BY 4.0): populated places only,
without abandoned or historical ones, with the Greek name for Greece and the Turkish name for
Türkiye, and the name in Latin letters. It is built once and kept in brain/data:

    .venv/bin/python -m brain.gazetteer build <folder with GR.txt and TR.txt from download.geonames.org/export/dump>

It is used by the map check (places.closest_known) and for the speech-to-text hints of the
demo regions (voice/keywords.py). No network at run time.
"""
import csv
import gzip
import math
import re
import sys
from functools import lru_cache
from pathlib import Path

from .events import _norm  # accents off, Greek in Latin letters: compares names however they are written

FILE = Path(__file__).parent / "data" / "places_gr_tr.tsv.gz"
_GREEK = re.compile(r"[Ͱ-Ͽἀ-῿]")
_SKIP = {"PPLQ", "PPLH", "PPLW"}  # abandoned, historical, destroyed
# How Greek is pronounced, so names compare by sound: Παιανία is said "peania" (αι = e), and
# speech-to-text wrote it "Πυρανία". Spelling alone matched a different village, Πέρανι.
_SOUNDS = [("ου", "u"), ("αι", "e"), ("ει", "i"), ("οι", "i"), ("υι", "i"), ("μπ", "b"), ("ντ", "d"), ("γκ", "g"),
           ("γγ", "g"), ("τσ", "ts"), ("τζ", "dz"), ("ψ", "ps"), ("ξ", "ks"), ("θ", "th"), ("χ", "h"), ("φ", "f"),
           ("β", "v"), ("γ", "g"), ("δ", "d"), ("ζ", "z"), ("κ", "k"), ("λ", "l"), ("μ", "m"), ("ν", "n"),
           ("π", "p"), ("ρ", "r"), ("σ", "s"), ("ς", "s"), ("τ", "t"), ("α", "a"), ("ε", "e"), ("η", "i"),
           ("ι", "i"), ("ο", "o"), ("υ", "i"), ("ω", "o")]
_LATIN_SOUNDS = [("ou", "u"), ("ai", "e"), ("ei", "i"), ("oi", "i"), ("mp", "b"), ("nt", "d"), ("y", "i"), ("ph", "f")]


def sound(text: str) -> str:
    """A rough spoken form in Latin letters: 'Παιανία' and 'Peania' both -> 'peania'."""
    import unicodedata

    plain = "".join(c for c in unicodedata.normalize("NFD", text.lower()) if not unicodedata.combining(c))
    if _GREEK.search(plain):
        for greek, latin in _SOUNDS:
            plain = plain.replace(greek, latin)
    else:
        plain = _norm(plain)
        for spelled, said in _LATIN_SOUNDS:
            plain = plain.replace(spelled, said)
    plain = re.sub(r"[^a-z]", "", plain)
    return re.sub(r"(.)\1", r"\1", plain)  # double letters sound single


def build(geonames_dir: Path, out: Path = FILE) -> int:
    """GeoNames country files -> one small file: country, name, name in Latin letters, lat, lon, population."""
    rows = []
    for country in ("GR", "TR"):
        with open(geonames_dir / f"{country}.txt", encoding="utf-8") as f:
            for g in csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
                if g[6] != "P" or g[7] in _SKIP:
                    continue
                name = g[1]
                if country == "GR":  # GeoNames' main name is in Latin letters; callers say the Greek one
                    name = next((a for a in g[3].split(",") if _GREEK.search(a)), g[1])
                rows.append((country, name, g[2], g[4], g[5], g[14] or "0"))
    out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out, "wt", encoding="utf-8") as f:
        f.write("# GeoNames (https://www.geonames.org), CC BY 4.0: populated places of Greece and Türkiye\n")
        for row in rows:
            f.write("\t".join(row) + "\n")
    return len(rows)


@lru_cache(maxsize=1)
def places() -> list[dict]:
    """[{"country", "name", "latin", "lat", "lon", "population", "key"}]; empty if the file is missing."""
    if not FILE.exists():
        return []
    found = []
    with gzip.open(FILE, "rt", encoding="utf-8") as f:
        for line in f:
            if line.startswith("#"):
                continue
            country, name, latin, lat, lon, population = line.rstrip("\n").split("\t")
            found.append({"country": country, "name": name, "latin": latin, "lat": float(lat), "lon": float(lon),
                          "population": int(population or 0), "key": sound(name)})
    return found


def _km(a: tuple, b: dict) -> float:
    lat = math.radians((a[0] + b["lat"]) / 2)
    return 111.2 * math.hypot(a[0] - b["lat"], (a[1] - b["lon"]) * math.cos(lat))


def closest(heard: str, near: tuple | None = None, within_km: float = 60, cutoff: float = 0.7,
            country: str | None = None) -> dict | None:
    """The real place that sounds closest to a heard name ("Πυρανία" -> Παιανία), or None.

    Compared by sound (sound()). With near (lat, lon), only places within_km of it, since the same
    village name repeats across the country; ties go to the bigger place. Greek letters mean Greece."""
    import difflib

    key = sound(heard)
    if len(key) < 3:
        return None
    country = country or ("GR" if _GREEK.search(heard) else None)
    best, best_score = None, cutoff
    for place in places():
        if abs(len(place["key"]) - len(key)) > 3 or (country and place["country"] != country) \
                or (near and _km(near, place) > within_km):
            continue
        # A small lead for bigger places: a caller far more often means Παιανία (14,595 people) than a
        # hamlet that happens to sound a little closer.
        score = difflib.SequenceMatcher(None, key, place["key"]).ratio() + 0.03 * math.log10(place["population"] + 1)
        if score > best_score:
            best, best_score = place, score
    return best if best and best["name"].lower() != heard.strip().lower() else None


@lru_cache(maxsize=1)
def _all_names() -> frozenset:
    return frozenset(_norm(p["name"]) for p in places()) | frozenset(_norm(p["latin"]) for p in places())


@lru_cache(maxsize=1)
def _stems() -> frozenset:
    return frozenset(n[:-k] for n in _all_names() for k in (1, 2) if len(n) - k >= 4)


def is_place(name: str, inflected: bool = False) -> bool:
    """name is a town, village or neighbourhood (any accents, Greek or Latin letters). inflected:
    also in another grammatical case, "στον Πειραιά", "της Σάμου" (the last one or two letters differ)."""
    if any(not _norm(word) for word in name.split()):
        return False  # a street word: "Gazi Caddesi" is a street, though _norm drops "caddesi" and Gazi is a town
    key = _norm(name)
    if key in _all_names():
        return True
    if not inflected:
        return False
    if len(key) >= 3 and key + "s" in _all_names():  # names are compared in Latin letters
        return True  # the accusative of a short -ος name, which the stems leave out: "στη Σάμο", "στον Βόλο"
    return any(len(key) - k >= 4 and key[:-k] in _stems() for k in (1, 2))


def names_in(box: tuple, budget: int) -> list[str]:
    """Names of the places inside box (south, north, west, east), biggest first, up to budget
    characters: hints for speech-to-text, which takes about 10,000 characters of context."""
    inside = sorted((p for p in places() if box[0] <= p["lat"] <= box[1] and box[2] <= p["lon"] <= box[3]),
                    key=lambda p: -p["population"])
    chosen, used = [], 0
    for place in inside:
        if place["name"] in chosen:
            continue
        if used + len(place["name"]) + 4 > budget:
            break
        chosen.append(place["name"])
        used += len(place["name"]) + 4
    return chosen


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "build":
        print(f"{build(Path(sys.argv[2]))} places written to {FILE}")
    else:
        print(__doc__)
