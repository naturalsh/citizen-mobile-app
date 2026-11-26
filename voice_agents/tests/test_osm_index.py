"""The local OpenStreetMap index (brain/osm_index.py): built from a tiny invented map, no network."""
import pytest

from brain import osm_index, places

TINY_MAP = """<?xml version='1.0' encoding='UTF-8'?>
<osm version="0.6" generator="test">
  <node id="1" lat="37.9300" lon="23.6400" version="1"/>
  <node id="2" lat="37.9320" lon="23.6420" version="1"/>
  <node id="3" lat="37.9500" lon="23.7000" version="1"/>
  <node id="4" lat="37.9510" lon="23.7010" version="1"/>
  <node id="5" lat="37.9310" lon="23.6410" version="1">
    <tag k="addr:street" v="Φραγκιάδων"/><tag k="addr:housenumber" v="14"/>
  </node>
  <node id="6" lat="37.9301" lon="23.6401" version="1"/>
  <node id="7" lat="37.9302" lon="23.6402" version="1"/>
  <node id="8" lat="37.9303" lon="23.6401" version="1"/>
  <way id="10" version="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="residential"/><tag k="name" v="Φραγκιάδων"/></way>
  <way id="11" version="1"><nd ref="3"/><nd ref="4"/><tag k="highway" v="primary"/><tag k="name" v="Ορλώφ"/></way>
  <way id="12" version="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="residential"/></way>
  <way id="13" version="1"><nd ref="6"/><nd ref="7"/><nd ref="8"/><nd ref="6"/>
    <tag k="building" v="yes"/><tag k="addr:street" v="Φραγκιάδων"/><tag k="addr:housenumber" v="16"/></way>
</osm>
"""


@pytest.fixture
def index(tmp_path):
    pytest.importorskip("osmium")
    source = tmp_path / "tiny.osm"
    source.write_text(TINY_MAP, encoding="utf-8")
    out = tmp_path / "index.sqlite"
    assert osm_index.build([source], out) == (2, 2)  # 2 named roads (the unnamed one left out), 2 addresses
    return out


def test_streets_and_numbered_buildings_in_a_box(index):
    piraeus = [37.90, 37.96, 23.60, 23.66]
    assert osm_index.streets_in(piraeus, index) == ["Φραγκιάδων"]
    assert osm_index.streets_in([37.90, 37.96, 23.60, 23.75], index) == ["Ορλώφ", "Φραγκιάδων"]
    numbers = {a["number"]: a for a in osm_index.addresses_in(piraeus, index)}
    assert set(numbers) == {"14", "16"} and abs(numbers["16"]["lat"] - 37.9302) < 0.001  # a building: its middle
    assert osm_index.addresses_in([38.0, 38.1, 24.0, 24.1], index) == []


def test_a_whole_city_gets_its_street_list_from_the_index(index, monkeypatch, tmp_path):
    # WhatsApp test 2026-10-27: Piraeus is 45 km on the map, so Overpass gave it no street list
    # and "fragiadon" was not found. With the index, whole cities have one, at once.
    monkeypatch.setattr(osm_index, "ENABLED", True)
    monkeypatch.setattr(osm_index, "PATH", index)
    piraeus = {"label": "Piraeus", "name": "Πειραιάς", "areas": [], "lat": 37.94, "lon": 23.65,
               "bbox": [37.78, 38.10, 23.49, 23.81], "size_km": 45.3}
    fetched = []
    assert places.street_names("Piraeus", lambda q: [piraeus], fetch=lambda box: fetched.append(box)) == ["Ορλώφ", "Φραγκιάδων"]
    assert fetched == []  # no Overpass request
    assert places.closest_street("fragiadon", places.street_names("Piraeus", lambda q: [piraeus])) == "Φραγκιάδων"


def test_without_the_index_nothing_changes(monkeypatch, tmp_path):
    monkeypatch.setattr(osm_index, "ENABLED", True)
    monkeypatch.setattr(osm_index, "PATH", tmp_path / "missing.sqlite")
    assert not osm_index.available()


def test_the_dashboard_takes_numbered_buildings_from_the_index(index, monkeypatch, tmp_path):
    from dashboard.geocode import Geocoder, place_number
    monkeypatch.setattr(osm_index, "ENABLED", True)
    monkeypatch.setattr(osm_index, "PATH", index)
    sent = []
    g = Geocoder(tmp_path / "g.sqlite", search=lambda q, box=None: None, min_interval_s=0, addresses=sent.append)
    found = g.numbered_buildings((37.92, 37.94, 23.63, 23.65))
    assert sent == [] and place_number("Φραγκιάδων", "16", found)["precision"] == "house"  # at once, nothing sent
    across = place_number("Φραγκιάδων", "15", found)  # odd side, nothing mapped there: across from No. 14
    assert across["precision"] == "estimated" and "across from No. 14" in across["how"]
    assert place_number("Φραγκιάδων", "25", found) is None  # nothing mapped near on either side


def fake_geofabrik(files: dict[str, bytes], md5s: dict[str, str] | None = None):
    """A fetch that serves invented extracts and their MD5 files, and records what was asked."""
    import hashlib
    import io
    asked = []

    def fetch(url):
        asked.append(url)
        name = url.rsplit("/", 1)[-1]
        if name.endswith(".md5"):
            pbf = name[:-4]
            digest = (md5s or {}).get(pbf) or hashlib.md5(files[pbf]).hexdigest()
            return io.BytesIO(f"{digest}  {pbf}\n".encode())
        return io.BytesIO(files[name])
    return fetch, asked


def test_download_checks_the_md5_and_skips_a_copy_that_is_already_the_latest(tmp_path):
    fetch, asked = fake_geofabrik({"greece-latest.osm.pbf": b"invented map"})
    path = osm_index.download("europe/greece", tmp_path, fetch)
    assert path == tmp_path / "greece-latest.osm.pbf" and path.read_bytes() == b"invented map"
    assert asked == ["https://download.geofabrik.de/europe/greece-latest.osm.pbf.md5",
                     "https://download.geofabrik.de/europe/greece-latest.osm.pbf"]
    asked.clear()
    osm_index.download("europe/greece", tmp_path, fetch)
    assert asked == ["https://download.geofabrik.de/europe/greece-latest.osm.pbf.md5"]  # only the small MD5 file


def test_a_broken_download_never_replaces_the_extract(tmp_path):
    (tmp_path / "turkey-latest.osm.pbf").write_bytes(b"last month")
    fetch, _ = fake_geofabrik({"turkey-latest.osm.pbf": b"cut off"}, md5s={"turkey-latest.osm.pbf": "0" * 32})
    with pytest.raises(RuntimeError, match="MD5"):
        osm_index.download("europe/turkey", tmp_path, fetch)
    assert (tmp_path / "turkey-latest.osm.pbf").read_bytes() == b"last month"


def test_setup_downloads_both_countries_then_builds(tmp_path, monkeypatch):
    fetch, _ = fake_geofabrik({"greece-latest.osm.pbf": b"gr", "turkey-latest.osm.pbf": b"tr"})
    built = []
    monkeypatch.setattr(osm_index, "_ensure_osmium", lambda: None)
    monkeypatch.setattr(osm_index, "build", lambda files, out: built.append((files, out)) or (1, 2))
    out = tmp_path / "osm" / "index.sqlite"
    assert osm_index.setup(out=out, fetch=fetch) == (1, 2)
    assert built == [([out.parent / "greece-latest.osm.pbf", out.parent / "turkey-latest.osm.pbf"], out)]
