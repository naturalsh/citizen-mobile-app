"""Hazard categories, subtypes and animals in the report (brain/report.py). No API calls."""
from brain import events
from brain.report import apply_update, hazard_of, new_report
from dashboard.data import animal_label


def test_a_car_fire_is_fire_vehicle_not_other():
    # Test call 2026-10-26: a car fire was filed as "other".
    r = new_report("h1", "+30 690", "el", None)
    assert apply_update(r, {"hazard_type": "fire", "hazard_subtype": "vehicle"}) == []
    assert hazard_of(r) == ("fire", "vehicle")


def test_a_subtype_must_belong_to_its_category():
    r = new_report("h2", "+30 690", "el", None)
    errors = apply_update(r, {"hazard_type": "flood", "hazard_subtype": "vehicle_fire"})
    assert r["hazard_subtype"] is None and errors
    apply_update(r, {"hazard_type": "fire", "hazard_subtype": "vehicle"})
    apply_update(r, {"hazard_type": "flood"})
    assert r["hazard_subtype"] is None  # a new category drops the old kind


def test_old_reports_and_old_answers_map_to_categories():
    assert hazard_of({"hazard_type": "wildfire"}) == ("fire", "wildfire")
    assert hazard_of({"hazard_type": "building_fire"}) == ("fire", "building")
    r = new_report("h3", "+30 690", "el", None)
    apply_update(r, {"hazard_type": "building_fire"})
    assert (r["hazard_type"], r["hazard_subtype"]) == ("fire", "building")


def test_animals_have_their_own_list_and_tag():
    # Test call 2026-10-26: "a cat is trapped inside the building" was dropped.
    r = new_report("h4", "+30 690", "el", None)
    apply_update(r, {"animals": [{"kind": "cat", "count": 1, "trapped": True}], "people": []})
    assert r["animals"][0]["kind"] == "cat" and r["people"] == []
    assert animal_label(r["animals"][0]) == "🐾 1 cat trapped"


def test_a_wildfire_groups_by_area_but_a_car_fire_by_site():
    assert events._rule_key({"hazard_type": "fire", "hazard_subtype": "wildfire"}) == "fire.wildfire"
    assert events._rule_key({"hazard_type": "fire", "hazard_subtype": "vehicle"}) == "fire"
    assert events.RULES["fire.wildfire"][2] == "area" and events.RULES["fire"][2] == "address"
    assert events._rule_key({"hazard_type": "wildfire"}) == "fire.wildfire"  # an old report
