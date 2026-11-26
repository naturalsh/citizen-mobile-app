"""Every named road and numbered building of Greece and Türkiye, kept on this machine.

The street lists (places.street_names) and the dashboard's building pins came from the public
Overpass servers. On 2026-10-28 the main one answered our requests with a notice that it is for
browser use and automated users should run their own, and both mirrors timed out. This index is
built once from Geofabrik's country extracts (OpenStreetMap, ODbL: "© OpenStreetMap contributors")
and answers in milliseconds, for any area size, without sending anything. One command does it all:

    .venv/bin/python -m brain.osm_index setup

It installs osmium (requirements-build.txt) if it is missing, downloads the latest Greece and Türkiye
extracts into output/osm/ (about 1 GB; checked against Geofabrik's MD5, and skipped when the copy there
is already the latest), and builds OSM_INDEX (output/osm/index.sqlite, not in git; about 4 minutes and
2 GB of memory). Run it again monthly to stay current. To build from files you already have:

    .venv/bin/python -m brain.osm_index build output/osm/greece-*.osm.pbf output/osm/turkey-*.osm.pbf

Reading needs nothing beyond Python's sqlite3. BRAIN_LOCAL_OSM=off goes back to the servers.

Only what the call needs is kept: road names with the box they cover (pieces of one road whose
middles fall in the same ~500 m cell merged), and numbered addresses (street, number, position). OpenStreetMap has few
house numbers here (about 172,000 in Greece and 247,000 in Türkiye in October 2026), so most
addresses still pin to the street.
"""
import hashlib
import importlib
import os
import sqlite3
import subprocess
import sys
import urllib.request
from contextlib import closing
from pathlib import Path

ENABLED = os.getenv("BRAIN_LOCAL_OSM", "on") != "off"
PATH = Path(os.getenv("OSM_INDEX", "output/osm/index.sqlite"))
CELL = 0.005  # degrees: segments of one road in the same ~500 m cell become one entry
GEOFABRIK = "https://download.geofabrik.de"
REGIONS = ("europe/greece", "europe/turkey")  # Geofabrik lists Türkiye under Europe
BUILD_REQUIREMENTS = Path(__file__).resolve().parent.parent / "requirements-build.txt"


def available(path: Path | None = None) -> bool:
    return ENABLED and (path or PATH).exists()


def _query(sql: str, box, path: Path | None = None) -> list:
    """Rows for the boxes overlapping box [south, north, west, east]. Read-only; a connection per call,
    since calls come from several threads (a rebuild swaps the file underneath)."""
    with closing(sqlite3.connect(f"file:{path or PATH}?mode=ro", uri=True)) as conn:
        return conn.execute(sql, tuple(float(x) for x in box)).fetchall()


def streets_in(box, path: Path | None = None) -> list[str]:
    """Names of the roads that cross box [south, north, west, east], sorted."""
    rows = _query("SELECT DISTINCT s.name FROM streets s JOIN streets_box b ON s.id = b.id "
                  "WHERE b.maxlat >= ? AND b.minlat <= ? AND b.maxlon >= ? AND b.minlon <= ?", box, path)
    return sorted(r[0] for r in rows)


def addresses_in(box, path: Path | None = None) -> list[dict]:
    """Numbered buildings and address points in box: [{"street", "number", "lat", "lon"}]."""
    rows = _query("SELECT a.street, a.number, a.lat, a.lon FROM addresses a JOIN addresses_box b ON a.id = b.id "
                  "WHERE b.maxlat >= ? AND b.minlat <= ? AND b.maxlon >= ? AND b.minlon <= ?", box, path)
    return [{"street": s, "number": n, "lat": lat, "lon": lon} for s, n, lat, lon in rows]


def build(pbf_files: list[Path], out: Path = PATH) -> tuple[int, int]:
    """Read the extracts and write the index; returns (road entries, addresses)."""
    import osmium  # build only: requirements-build.txt

    roads: dict[tuple, list] = {}  # (name, cell) -> [minlat, maxlat, minlon, maxlon]
    addresses: list[tuple] = []

    class Reader(osmium.SimpleHandler):
        def node(self, n):
            tags = n.tags
            if "addr:housenumber" in tags and "addr:street" in tags and n.location.valid():
                addresses.append((tags["addr:street"], tags["addr:housenumber"], n.location.lat, n.location.lon))

        def way(self, w):
            tags = w.tags
            named_road = "highway" in tags and "name" in tags
            numbered = "addr:housenumber" in tags and "addr:street" in tags
            if not (named_road or numbered):
                return
            points = [(nd.lat, nd.lon) for nd in w.nodes if nd.location.valid()]
            if not points:
                return
            if numbered:  # a building outline: its middle
                addresses.append((tags["addr:street"], tags["addr:housenumber"],
                                  sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points)))
            if named_road:  # pieces of one road whose middles share a ~500 m cell become one entry
                lats, lons = [p[0] for p in points], [p[1] for p in points]
                middle = ((min(lats) + max(lats)) / 2, (min(lons) + max(lons)) / 2)
                key = (tags["name"], round(middle[0] / CELL), round(middle[1] / CELL))
                box = roads.setdefault(key, [min(lats), max(lats), min(lons), max(lons)])
                box[0], box[1] = min(box[0], min(lats)), max(box[1], max(lats))
                box[2], box[3] = min(box[2], min(lons)), max(box[3], max(lons))

    for pbf in pbf_files:
        Reader().apply_file(str(pbf), locations=True, idx="flex_mem")

    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".building")
    tmp.unlink(missing_ok=True)
    with closing(sqlite3.connect(tmp)) as conn:
        conn.executescript("""
            CREATE TABLE streets (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
            CREATE VIRTUAL TABLE streets_box USING rtree(id, minlat, maxlat, minlon, maxlon);
            CREATE TABLE addresses (id INTEGER PRIMARY KEY, street TEXT NOT NULL, number TEXT NOT NULL,
                                    lat REAL NOT NULL, lon REAL NOT NULL);
            CREATE VIRTUAL TABLE addresses_box USING rtree(id, minlat, maxlat, minlon, maxlon);
            CREATE TABLE about (key TEXT PRIMARY KEY, value TEXT);
        """)
        for i, ((name, _, _), box) in enumerate(roads.items(), 1):
            conn.execute("INSERT INTO streets VALUES (?, ?)", (i, name))
            conn.execute("INSERT INTO streets_box VALUES (?, ?, ?, ?, ?)", (i, *box))
        for i, (street, number, lat, lon) in enumerate(addresses, 1):
            conn.execute("INSERT INTO addresses VALUES (?, ?, ?, ?, ?)", (i, street, number, lat, lon))
            conn.execute("INSERT INTO addresses_box VALUES (?, ?, ?, ?, ?)", (i, lat, lat, lon, lon))
        conn.execute("INSERT INTO about VALUES ('source', ?)",
                     ("OpenStreetMap via Geofabrik, ODbL, © OpenStreetMap contributors: "
                      + ", ".join(Path(p).name for p in pbf_files),))
        conn.commit()
    tmp.replace(out)  # running readers keep the old file until their next query
    return len(roads), len(addresses)


def _open(url: str):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "voice-agents-hackathon"}),
                                  timeout=60)


def _md5(path: Path) -> str:
    digest = hashlib.md5()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def download(region: str, folder: Path, fetch=_open) -> Path:
    """The latest extract of region ("europe/greece") in folder, checked against Geofabrik's MD5.
    A copy that is already the latest is kept; a broken download raises and leaves only a .part file."""
    name = region.rsplit("/", 1)[-1] + "-latest.osm.pbf"
    url = f"{GEOFABRIK}/{region}-latest.osm.pbf"
    with fetch(url + ".md5") as r:
        expected = r.read().decode().split()[0]
    target = folder / name
    if target.exists() and _md5(target) == expected:
        print(f"{name}: already the latest")
        return target
    folder.mkdir(parents=True, exist_ok=True)
    part = target.with_suffix(".part")
    digest, done, shown = hashlib.md5(), 0, 0
    with fetch(url) as r, open(part, "wb") as f:
        size = int(r.headers.get("Content-Length") or 0) if getattr(r, "headers", None) else 0
        while chunk := r.read(1 << 20):
            f.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            if done - shown >= 50 << 20:  # a line every 50 MB, so a slow download doesn't look stuck
                shown = done
                print(f"{name}: {done >> 20} of {size >> 20 or '?'} MB")
    if digest.hexdigest() != expected:
        raise RuntimeError(f"{name}: the download doesn't match Geofabrik's MD5; run setup again")
    part.replace(target)
    print(f"{name}: downloaded, {done / (1 << 20):.1f} MB")
    return target


def _ensure_osmium():
    try:
        importlib.import_module("osmium")
    except ImportError:
        print("Installing osmium (requirements-build.txt)")
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(BUILD_REQUIREMENTS)], check=True)
        importlib.invalidate_caches()


def setup(regions=REGIONS, folder: Path | None = None, out: Path | None = None, fetch=_open) -> tuple[int, int]:
    """Everything in one go: osmium, the latest extracts, the index. Returns (road entries, addresses)."""
    out = out or PATH
    _ensure_osmium()
    files = [download(region, folder or out.parent, fetch) for region in regions]
    print("Building the index (a few minutes)")
    return build(files, out)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "build":
        roads, numbered = build([Path(p) for p in sys.argv[2:]])
        print(f"{roads} road entries and {numbered} numbered addresses written to {PATH}")
    elif sys.argv[1:] == ["setup"]:
        roads, numbered = setup()
        print(f"{roads} road entries and {numbered} numbered addresses written to {PATH}")
    else:
        print(__doc__)
