"""Map check of the caller's location during the call (brain/places.py). A fake map, no network."""
import json
from concurrent.futures import Future
from types import SimpleNamespace

import brain.core as core
from brain import CallInfo, places, start_call, turn

# A fake OpenStreetMap: what exists, and where.
MAP = {
    "ampelokipoi": [{"label": "Ampelokipoi, Athens", "areas": ["Ampelokipoi", "Athens"]}],
    "michail mela": [{"label": "Michail Mela, Ampelokipoi", "areas": ["Ampelokipoi", "Athens"]}],
}


def fake_search(query):
    fake_search.sent.append(query)
    return MAP.get(query.strip().lower(), [])


def setup_function():
    fake_search.sent = []


def test_street_name_never_keeps_the_house_number():
    assert places.street_name("Michail Melá 13, Belokipos") == "Michail Melá"
    assert places.street_name("Οδός Θεμιστοκλέους 5Α, Βαθύ") == "Οδός Θεμιστοκλέους"
    assert places.street_name("near the port") is None


def test_a_found_area_needs_nothing_else():
    assert places.check("Ampelokipoi", "Michail Mela 13", street="Michail Mela", search=fake_search) == {
        "on_map": True, "note": None, "suggestion": None, "street_matches": None}  # no box: the street isn't searched
    assert fake_search.sent == ["Ampelokipoi"]  # the street isn't looked up when the area is found


def test_a_misheard_area_is_caught_by_the_street():
    # From a test call: speech-to-text wrote "Belokipos" for Ampelokipoi.
    result = places.check("Belokipos", "Michail Mela 13, Belokipos", street="Michail Mela", search=fake_search)
    assert result["on_map"] is False and "Did you mean Ampelokipoi?" in result["note"]
    assert all("13" not in q for q in fake_search.sent)  # never the house number
    assert "Michail" not in result["note"]  # the model never sees the street


def test_a_misheard_area_close_to_a_known_name_is_suggested():
    result = places.check("Belokipos", None, search=fake_search)  # no street to help
    assert result["on_map"] is False and "Did you mean Ampelokipoi?" in result["note"]
    assert places.closest_known("Kifisya") == "Kifisia" and places.closest_known("Nowhereville") is None


def test_nothing_found_asks_to_repeat_or_spell():
    result = places.check("Nowhereville", None, search=fake_search)
    assert result["on_map"] is False and "spell" in result["note"]


def test_answers_are_cached():
    places.check("Belokipos", "Michail Mela 13", street="Michail Mela", search=fake_search)
    places.check("Belokipos", "Michail Mela 13", street="Michail Mela", search=fake_search)
    assert fake_search.sent == ["Belokipos", "Michail Mela"]


def test_the_next_turn_tells_the_model_and_the_report_says_not_on_map(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(places, "ENABLED", True)
    monkeypatch.setattr(places, "nominatim", fake_search)
    monkeypatch.setattr(places.check, "__defaults__", (None, fake_search))
    sent = []

    class Models:
        def generate_content(self, **kw):
            sent.append(kw["contents"][-1].parts[0].text)
            return SimpleNamespace(text=json.dumps({
                "action": "continue", "handoff_reason": "none", "advice_topic": "none", "reply": "OK?",
                "expecting": "other", "caller_en": "x", "reply_en": "OK?",
                "report_updates": {"area": "Belokipos", "spoken_address": "Michail Mela 13, Belokipos", "street": "Michail Mela"}}))

    monkeypatch.setattr(core, "_client", SimpleNamespace(models=Models()))
    start_call(CallInfo(call_id="p1", channel="voice", phone="+44 7700", lang_guess="en"))
    turn("p1", "I'm in Belokipos, Michail Mela 13", "en")
    core._sessions["p1"].place_check.result(timeout=5)  # the check runs in the background
    r = turn("p1", "There is a fire", "en")
    assert "(map check: 'Belokipos' was not found" in sent[-1]
    assert r.report["location"]["on_map"] is False


# --- landmarks (a test call heard "Τζάνειο Νοσοκομείο" as "τζάμι ο νοσοκομείο") ---

HOSPITALS = [{"label": n, "name": n, "areas": ["Piraeus"]} for n in (
    "Ναυτικό Νοσοκομείο Πειραιά", "Τζάνειο Γενικό Νοσοκομείο Πειραιά", "ΚΛΙΝΙΚΗ ΤΙΜΙΟΣ ΣΤΑΥΡΟΣ",
    "Γενικό Αντικαρκινικό Νοσοκομείο Πειραιά Μεταξά")]


def fake_map(query, limit=3):
    fake_map.sent.append(query)
    if query.lower() == "piraeus":
        return [{"label": "Piraeus", "name": "Πειραιάς", "areas": ["Piraeus"]}]
    if query.startswith("hospitals in"):
        return HOSPITALS
    if query.lower().startswith("τζάνειο"):
        return [HOSPITALS[1]]
    return []


def test_a_misheard_hospital_gets_the_real_one_suggested():
    fake_map.sent = []
    result = places.check("Piraeus", None, "τζάμι ο νοσοκομείο", search=fake_map)
    assert result["on_map"] is False and result["suggestion"] == "Τζάνειο Γενικό Νοσοκομείο Πειραιά"
    assert "Do you mean Τζάνειο Γενικό Νοσοκομείο Πειραιά?" in result["note"]
    assert "hospitals in Piraeus" in fake_map.sent


def test_a_real_landmark_is_on_the_map():
    fake_map.sent = []
    result = places.check("Piraeus", None, "Τζάνειο νοσοκομείο", search=fake_map)
    assert result == {"on_map": True, "note": None, "suggestion": "Τζάνειο Γενικό Νοσοκομείο Πειραιά"}


def test_only_a_kind_of_place_lists_the_real_ones_to_ask_which():
    fake_map.sent = []
    result = places.check("Piraeus", None, "το νοσοκομείο", search=fake_map)
    assert result["on_map"] is False and "Which hospital" in result["note"] and "Τζάνειο" in result["note"]


def test_a_changed_location_must_be_confirmed_again():
    from brain.report import apply_update, new_report
    r = new_report("c", "+30 690", "el", None)
    apply_update(r, {"spoken_address": "κοντά στο τζάμι ο νοσοκομείο", "location_confirmed": True})
    assert r["location"]["confirmed_with_caller"] is True
    apply_update(r, {"landmark": "Τζάνειο νοσοκομείο"})
    assert r["location"]["confirmed_with_caller"] is False


def test_the_model_is_reminded_until_the_location_is_confirmed(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "OUTPUT_DIR", tmp_path)
    sent, updates = [], [{"area": "Piraeus", "spoken_address": "Ακτή Μιαούλη 10, Πειραιάς", "street": "Ακτή Μιαούλη",
                                 "hazard_type": "building_fire", "situation": "Smoke in the flat."}, {}, {}, {}, {}, {}]

    class Models:
        def generate_content(self, **kw):
            sent.append(kw["contents"][-1].parts[0].text)
            return SimpleNamespace(text=json.dumps({
                "action": "continue", "handoff_reason": "none", "advice_topic": "none", "reply": "OK?",
                "expecting": "location_readback", "caller_en": "x", "reply_en": "OK?", "report_updates": updates.pop(0)}))

    monkeypatch.setattr(core, "_client", SimpleNamespace(models=Models()))
    start_call(CallInfo(call_id="g1", channel="voice", phone="+30 690", lang_guess="el"))
    for line in ("Βγαίνει καπνός από το διαμέρισμα, στον Πειραιά", "α", "β", "γ", "δ", "ε"):
        turn("g1", line, "el")
    reminders = [m for m in sent if "read back ONLY the location" in m]
    assert len(reminders) == 3 and all("read back ONLY" in m for m in sent[1:4])
    assert "how many people" in sent[4] and "read back ONLY" not in sent[5]  # after that the call goes on


def test_a_landmark_with_a_personal_detail_is_never_sent_to_the_map(tmp_path, monkeypatch):
    monkeypatch.setattr(places, "ENABLED", True)
    started = []
    monkeypatch.setattr(core._place_checks, "submit", lambda fn, *args: started.append(args) or Future())
    s = core._Session(info=CallInfo(call_id="m1", channel="voice", phone="+30 690", lang_guess="el"), lang="el",
                      report={"location": {"area": "Piraeus", "spoken_address": None, "landmark": "το σπίτι της Μαρίας"}})
    s.masker._swap("PERSON", "Μαρίας")  # the caller's name, known to the masker
    core._start_map_check(s)
    assert started == [("Piraeus", None, None, None)]


def test_an_area_with_the_wrong_city_is_still_found():
    # Eval: "Keratsini, Athens" isn't on the map as written (Keratsini isn't in the City of Athens),
    # and the false "not found" made the agent ask the caller to repeat a correct place.
    def search(query, limit=3):
        return [{"label": "Keratsini", "name": "Κερατσίνι", "areas": []}] if query == "Keratsini" else []
    assert places.check("Keratsini, Athens", None, search=search)["on_map"] is True


def test_a_street_and_number_need_no_landmark_check():
    sent = []
    def search(query, limit=3):
        sent.append(query)
        return [{"label": "Koukaki", "name": "Κουκάκι", "areas": []}]
    places.check("Koukaki", "Οδός Δοκιμής 4, δίπλα στον φούρνο", "δίπλα στον φούρνο", search=search)
    assert sent == ["Koukaki"]  # the bakery isn't looked up, and the number never leaves



def test_a_part_of_a_place_is_not_checked_as_a_landmark():
    # Eval: "κεντρική είσοδος" (main entrance) replaced the hospital as the landmark and was "not found".
    sent = []
    def search(query, limit=3):
        sent.append(query)
        return [{"label": "Piraeus", "name": "Πειραιάς", "areas": []}]
    assert places.check("Piraeus", None, "κεντρική είσοδος", search=search)["on_map"] is True
    assert sent == ["Piraeus"]



ATHENS = {"label": "Athens", "name": "Αθήνα", "areas": [], "district": "Athens", "lat": 37.976, "lon": 23.735,
          "bbox": [37.85, 38.10, 23.60, 23.90]}


def street_map(found):
    """A fake map: Athens, and for each spelling searched inside its box, these streets."""
    asked = []
    def search(query, limit=3, box=None):
        asked.append((query, box is not None))
        if query == "Athens":
            return [ATHENS]
        return [{"label": query, "name": query, "areas": [d], "district": d, "lat": lat, "lon": lon, "bbox": None}
                for d, (lat, lon) in found.get(query, {}).items()] if box else []
    return search, asked


def test_a_street_in_several_neighbourhoods_makes_the_agent_ask_which():
    # A test call's "Καλλιρρόης 33, Athens": that spelling is near Piraeus (Rentis), the real one is
    # Καλλιρόης in Koukaki and Neos Kosmos. Every spelling is searched, inside Athens only.
    search, asked = street_map({"Καλλιρρόης": {"Kallipoli": (37.928, 23.635), "Ekali": (38.116, 23.841)},
                                "Καλλιρόης": {"Koukaki": (37.961, 23.721), "Neos Kosmos": (37.966, 23.731)}})
    result = places.check("Athens", "Καλλιρρόης 33, Αθήνα", street="Καλλιρρόης", search=search)
    # closest to the centre first; Koukaki and Neos Kosmos, 1 km apart, are one stretch of the same street
    assert [(m["name"], m["also"]) for m in result["street_matches"]] == [
        ("Neos Kosmos", ["Koukaki"]), ("Kallipoli", []), ("Ekali", [])]
    assert "several places in Athens" in result["note"] and "Neos Kosmos (Koukaki)" in result["note"]
    assert "Καλ" not in result["note"]  # the model never sees the street
    assert all(in_box for q, in_box in asked if q != "Athens") and "33" not in str(asked)


def test_a_long_avenue_is_one_place_not_one_per_neighbourhood():
    # On the real map Kallirrois Avenue came back in Neos Kosmos, Filopappou and Petralona, each
    # stretch under 2 km from the next: the caller would not know which "neighbourhood" to pick.
    search, _ = street_map({"Καλλιρόης": {"Neos Kosmos": (37.966, 23.731), "Filopappou": (37.966, 23.715),
                                         "Petralona": (37.968, 23.700), "Vari": (37.835, 23.800)}})
    matches = places.check("Athens", "Καλλιρόης 33", street="Καλλιρόης", search=search)["street_matches"]
    assert [(m["name"], m["also"]) for m in matches] == [("Neos Kosmos", ["Filopappou", "Petralona"]), ("Vari", [])]


def test_a_street_in_one_neighbourhood_is_placed_without_a_question():
    search, _ = street_map({"Καλλιρόης": {"Koukaki": (37.961, 23.721)}})
    result = places.check("Athens", "Καλλιρόης 33", street="Καλλιρόης", search=search)
    assert result["note"] is None and [m["name"] for m in result["street_matches"]] == ["Koukaki"]


def test_a_street_not_in_the_area_asks_for_the_neighbourhood_or_spelling():
    search, _ = street_map({})
    result = places.check("Athens", "Δοκιμής 4", street="Δοκιμής", search=search)
    assert result["street_matches"] == [] and "not found in Athens" in result["note"]


def test_a_street_is_matched_by_its_own_name_not_one_containing_it():
    # Live check 2026-10-27: "Kaya Sokak" in Keçiören matched "Yuvarlak Kaya Sokak", another street.
    assert not places.same_street("Kaya Sokak", "Yuvarlak Kaya Sokak")
    assert places.same_street("Kaya Sokak", "Kaya Sokağı") and not places.same_street("Gazi Caddesi", "Gazi Bulvarı")
    assert places.same_street("Orlof", "Ορλώφ") and places.same_street("Καλλιρρόης", "Καλλιρόης")
    assert places.same_street("Διάκου", "Αθανασίου Διάκου")  # Greek callers drop the first name
    assert places.same_street("Kifisias", "Λεωφόρος Κηφισίας")


def test_street_matches_leave_out_other_streets_with_the_same_word():
    area = {"label": "Keçiören", "name": "Keçiören", "areas": [], "district": "Keçiören", "lat": 39.98, "lon": 32.86,
            "bbox": [39.9, 40.1, 32.7, 33.0], "size_km": 12}

    def search(query, limit=3, box=None):
        if not box:
            return [area]
        return [{"label": "x", "name": "Yuvarlak Kaya Sokak", "areas": ["Atapark"], "district": "Atapark",
                 "lat": 39.99, "lon": 32.87, "bbox": None},
                {"label": "x", "name": "Kaya Sokak", "areas": ["Kaya Mahallesi"], "district": "Kaya Mahallesi",
                 "lat": 39.97, "lon": 32.85, "bbox": None}]

    assert [m["name"] for m in places.street_matches("Kaya Sokak", "Keçiören", search)] == ["Kaya Mahallesi"]


def test_orlov_with_a_v_is_the_same_street_as_orlof():
    # English demo call 2026-10-30: speech-to-text wrote "Orlov 12"; it wasn't taken for Ορλώφ
    # (orlof in Latin letters) until the agent asked "Did you mean Ορλώφ?".
    for heard in ("Orlov", "Orlow", "Orloff", "Orlov Street"):
        assert places.same_street(heard, "Ορλώφ") and places._street_sound(heard, "Ορλώφ") >= places.SAME_STREET
    assert not places.same_street("Ev Sokak", "Ef Sokak")  # short words stay themselves
    assert not places.same_street("Kaya Sokak", "Yuvarlak Kaya Sokak")


def _flat_then_places(query, limit=3, box=None):
    # Demo call 2026-10-30: the first answer for this area was a holiday flat, not a place.
    if query == "Acropolis, Koukaki, Athens":
        return [{"label": "Spacious apt in Koukaki FIX 500 meter to Acropolis", "name": "Spacious apt", "areas": [],
                 "kind": "tourism", "lat": 37.9631, "lon": 23.7239, "bbox": [37.9630, 37.9632, 23.7238, 23.7240]}]
    if query == "Koukaki, Athens":
        return [{"label": "Κουκάκι", "name": "Κουκάκι", "areas": [], "kind": "place", "lat": 37.964, "lon": 23.724,
                 "bbox": [37.958, 37.970, 23.716, 23.732], "size_km": 1.6}]
    if query == "Athens":
        return [{"label": "Athens", "name": "Αθήνα", "areas": [], "kind": "boundary", "lat": 37.98, "lon": 23.73,
                 "bbox": [37.9, 38.1, 23.6, 23.9], "size_km": 30}]
    return []


def test_the_area_is_a_place_never_a_holiday_flat(tmp_path, monkeypatch):
    monkeypatch.setattr(places, "_cache_path", lambda: tmp_path / "places.sqlite")
    hit = places.area_hit("Acropolis, Koukaki, Athens", _flat_then_places)
    assert hit["name"] == "Κουκάκι"  # the flat is skipped; the street is then searched in all of Koukaki
    assert places._area_found("Acropolis, Koukaki, Athens", _flat_then_places)
    # A misheard neighbourhood still counts as not found, although its city is a place.
    assert not places._area_found("Belokipos, Athens", _flat_then_places)
    assert places.area_hit("Belokipos, Athens", _flat_then_places)["name"] == "Αθήνα"  # the street search may use the city


def test_the_neighbourhood_the_caller_named_picks_the_street():
    # Demo call 2026-10-30: Filippou 13 is in three places in Thessaloniki; the caller answered
    # "Dikitirio", but Διοικητήριο isn't a place on the map, so searching inside it found all three again.
    three = {"on_map": True, "note": "several", "street_matches": [
        {"name": "Διοικητήριο", "also": [], "lat": 40.639, "lon": 22.942},
        {"name": "Evosmos", "also": [], "lat": 40.666, "lon": 22.904},
        {"name": "Πυλαία", "also": [], "lat": 40.599, "lon": 22.981}]}
    for area in ("Dioikitirio, Thessaloniki, Greece", "Dikitirio, Thessaloniki"):
        picked = places._named(area, "Φιλίππου 13, Θεσσαλονίκη", None, three)
        assert [m["name"] for m in picked["street_matches"]] == ["Διοικητήριο"]
    assert places._named("Thessaloniki", "Filippou 13, Thessaloniki", None, three) is None  # none named yet
