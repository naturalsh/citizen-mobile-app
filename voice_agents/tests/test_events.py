import pytest

from brain import events
from brain.report import new_report


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAIN_OUTPUT_DIR", str(tmp_path))


def call(call_id, hazard, address=None, area=None, lat=None, lon=None):
    aml = {"lat": lat, "lon": lon, "accuracy_m": 20} if lat is not None else None
    report = new_report(call_id, "+30", "el", aml)
    report["hazard_type"] = hazard
    report["location"]["spoken_address"] = address
    report["location"]["area"] = area
    events.suggest_event(report)
    return report


def test_same_building_is_one_event():
    a = call("a", "earthquake", "Themistokleous 5, Vathy, Samos")
    b = call("b", "earthquake", "Odos Themistokleous 5, Vathy Samos")
    assert a["event_id"] == b["event_id"]
    assert a["new_event_suggested"] is True
    assert b["new_event_suggested"] is False


def test_greek_and_latin_spelling_group_together():
    a = call("a", "earthquake", "Οδός Θεμιστοκλέους 5, Βαθύ")
    b = call("b", "earthquake", "Themistokleous 5, Vathy")
    assert a["event_id"] == b["event_id"]


def test_norm():
    assert events._norm("Οδός Θεμιστοκλέους 5, Βαθύ") == "themistokleous 5 vathy"
    assert events._norm("Manas Bulvarı No: 12, Bayraklı") == "manas 12 bayrakli"


def test_different_building_is_a_new_event():
    a = call("a", "earthquake", "Themistokleous 5, Vathy, Samos")
    b = call("b", "earthquake", "Logotheti 40, Vathy, Samos")
    assert a["event_id"] != b["event_id"]
    assert b["new_event_suggested"] is True


def test_coordinates_beat_text():
    a = call("a", "earthquake", "near the pharmacy", lat=37.7570, lon=26.9770)
    b = call("b", "earthquake", "the white building by the square", lat=37.7575, lon=26.9772)  # ~60 m away
    c = call("c", "earthquake", "near the pharmacy", lat=37.7700, lon=26.9770)  # ~1.4 km away
    assert a["event_id"] == b["event_id"]
    assert c["event_id"] != a["event_id"]


def test_wildfire_groups_by_area():
    a = call("a", "wildfire", "road out of the village", area="Dadia, Evros")
    b = call("b", "wildfire", "behind the school", area="Dadia, Evros")
    c = call("c", "wildfire", "by the river", area="Soufli, Evros")
    assert a["event_id"] == b["event_id"] != c["event_id"]


def test_different_hazard_never_groups():
    a = call("a", "earthquake", "Themistokleous 5, Vathy")
    b = call("b", "flood", "Themistokleous 5, Vathy", area="Vathy, Samos")
    assert a["event_id"] != b["event_id"]


def test_repeated_updates_keep_the_first_call_new():
    a = call("a", "earthquake", "Themistokleous 5, Vathy")
    call("b", "earthquake", "Themistokleous 5, Vathy")
    events.suggest_event(a)  # the first call gets another turn
    assert a["new_event_suggested"] is True
    assert events.calls_in_event(a["event_id"]) == ["a", "b"]


def test_nothing_to_compare_leaves_report_alone():
    r = call("a", "earthquake")
    assert r["event_id"] is None
    r = call("b", None, "Themistokleous 5")
    assert r["event_id"] is None
