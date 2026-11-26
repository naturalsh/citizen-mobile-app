"""The code picks the next location question, and unclear answers are confirmed before advice
(brain/core.py, Docs/Research/09_Location_Questioning.md). A fake model, no API calls."""
import json
from types import SimpleNamespace

import brain.core as core
from brain import CallInfo, places, start_call, steps, turn


def fake_model(monkeypatch, tmp_path, answers):
    """Each turn answers with the next (report_updates, expecting, advice_topic); returns what the model was sent."""
    monkeypatch.setattr(core, "OUTPUT_DIR", tmp_path)
    sent = []

    class Models:
        def generate_content(self, **kw):
            sent.append(kw["contents"][-1].parts[0].text)
            updates, expecting, advice = answers.pop(0)
            return SimpleNamespace(text=json.dumps({
                "action": "continue", "handoff_reason": "none", "advice_topic": advice, "reply": "OK?",
                "expecting": expecting, "caller_en": "x", "reply_en": "OK?", "report_updates": updates}))

    monkeypatch.setattr(core, "_client", SimpleNamespace(models=Models()))
    return sent


def test_a_street_without_a_number_is_asked_for_the_number_then_the_corner(tmp_path, monkeypatch):
    # Test call 2026-10-24: "Athens" then "Ορλώφ", read back at once, no number asked.
    sent = fake_model(monkeypatch, tmp_path, [
        ({"area": "Athens", "spoken_address": "Αθήνα", "hazard_type": "building_fire", "situation": "Smoke in the flat."}, "location", "none"),
        ({"street": "Ορλώφ", "spoken_address": "Ορλώφ, Αθήνα"}, "location", "none"),
        ({}, "location", "none"),
        ({"cross_street": "Φιλοπάππου"}, "location", "none"),
        ({}, "location", "none"),
    ])
    start_call(CallInfo(call_id="l1", channel="voice", phone="+30 690", lang_guess="el"))
    for line in ("Βγαίνει καπνός από το διαμέρισμα, στην Αθήνα.", "Ορλώφ.", "Δεν ξέρω τον αριθμό.",
                 "Στη γωνία με Φιλοπάππου.", "Ναι."):
        turn("l1", line, "el")
    assert "ask for the street" in sent[1]  # after "Athens": a town alone is not enough
    assert "house number" in sent[2]  # after "Ορλώφ": the number, not the read-back
    assert "corner or cross street" in sent[3]  # "I don't know the number": straight to the corner
    assert "read back ONLY the location" in sent[4]  # complete: read back now


def test_a_number_asked_twice_without_an_answer_moves_on(tmp_path, monkeypatch):
    sent = fake_model(monkeypatch, tmp_path, [
        ({"area": "Athens", "street": "Ορλώφ", "spoken_address": "Ορλώφ, Αθήνα"}, "location", "none"),
        *[({}, "location", "none")] * 5,
    ])
    start_call(CallInfo(call_id="l2", channel="voice", phone="+30 690", lang_guess="el"))
    for line in ("Ορλώφ, στην Αθήνα.", "Εεε.", "Μμμ.", "Τίποτα.", "Εντάξει.", "Ναι."):
        turn("l2", line, "el")
    assert "house number" in sent[1] and "asked once already" in sent[2]  # asked again, with help
    assert "corner or cross street" in sent[3] and "asked once already" in sent[4]  # two misses: the corner
    assert "read back ONLY the location" in sent[5]  # then the read-back


def test_the_street_in_two_neighbourhoods_asks_which_until_the_area_changes(monkeypatch):
    s = core._Session(info=CallInfo(call_id="l3", channel="voice", phone="+30 690", lang_guess="el"), lang="el",
                      report={"location": {"area": "Athens", "street": "Ορλώφ", "spoken_address": "Ορλώφ 12, Αθήνα",
                                           "landmark": None, "confirmed_with_caller": False,
                                           "street_matches": [{"name": "Akropoli"}, {"name": "Glyfada"}]}})
    s.steps.matches_area = "Athens"
    assert steps._location_pieces(s.report, s.steps) == ["neighbourhood"]
    s.report["location"]["area"] = "Koukaki, Athens"  # the caller named it; the map checks it again
    assert steps._location_pieces(s.report, s.steps) == []


def test_a_caller_who_cant_say_where_is_not_asked_forever(tmp_path, monkeypatch):
    sent = fake_model(monkeypatch, tmp_path, [({"hazard_type": "building_fire", "situation": "Smoke in the flat."}, "location", "none")] +
                      [({}, "location", "none")] * (steps.LOCATION_MAX_ASKS + 2))
    start_call(CallInfo(call_id="l4", channel="voice", phone="+30 690", lang_guess="el"))
    for _ in range(steps.LOCATION_MAX_ASKS + 2):
        turn("l4", "Βοήθεια, σας παρακαλώ.", "el")
    # What happened first; then each place piece twice (area, then street), then the call goes on:
    # a caller who can't say is never stuck.
    assert "what happened" in sent[0]
    assert sum("ask which town" in m for m in sent) == 2 and sum("ask for the street" in m for m in sent) == 2
    assert "how many people" in sent[5]


def test_a_fire_heard_as_a_question_is_confirmed_before_any_advice(tmp_path, monkeypatch):
    # Test call 2026-10-24: speech-to-text heard «Φωτιά;» where nobody said fire; wildfire advice followed.
    full = {"area": "Athens", "street": "Ορλώφ", "spoken_address": "Ορλώφ 12, Αθήνα", "location_confirmed": True}
    sent = fake_model(monkeypatch, tmp_path, [
        (full, "other", "none"),
        ({"hazard_type": "wildfire"}, "other", "wildfire.approaching"),
        ({}, "other", "wildfire.approaching"),
    ])
    start_call(CallInfo(call_id="l5", channel="voice", phone="+30 690", lang_guess="el"))
    turn("l5", "Ορλώφ 12, Αθήνα, ναι σωστά.", "el")
    held = turn("l5", "Φωτιά;", "el")
    assert "unclear" in sent[1] and held.report["advice_given"] == []
    assert "Φύγετε" not in held.reply_text  # no evacuation advice on a misheard word
    confirmed = turn("l5", "Ναι.", "el")  # "Did you say fire?" - "Yes."
    assert confirmed.report["advice_given"] == ["wildfire.approaching"]


def test_a_clear_hazard_gets_its_advice_at_once(tmp_path, monkeypatch):
    full = {"area": "Athens", "street": "Ορλώφ", "spoken_address": "Ορλώφ 12, Αθήνα", "location_confirmed": True}
    fake_model(monkeypatch, tmp_path, [(full, "other", "none"),
                                       ({"hazard_type": "wildfire"}, "other", "wildfire.approaching")])
    start_call(CallInfo(call_id="l6", channel="voice", phone="+30 690", lang_guess="el"))
    turn("l6", "Ορλώφ 12, Αθήνα.", "el")
    result = turn("l6", "Έρχεται φωτιά από το βουνό προς τα σπίτια μας.", "el")
    assert result.report["advice_given"] == ["wildfire.approaching"]


def test_cannot_say_and_unclear():
    assert steps.cannot_say("Δεν ξέρω τον αριθμό") and steps.cannot_say("I don't know") and steps.cannot_say("Bilmiyorum")
    assert not steps.cannot_say("Ορλώφ 12")
    assert core._unclear("Φωτιά;") and core._unclear("Fire?") and core._unclear("Φωτιά.")
    assert not core._unclear("Καίγεται το διαμέρισμα δίπλα")


def test_a_street_without_a_number_is_searched_on_the_map():
    assert places.the_street("Ορλώφ", "Αθήνα, Ορλώφ") == "Ορλώφ"
    assert places.the_street("Θεμιστοκλέους 5", None) == "Θεμιστοκλέους"  # a masked address comes back whole
    assert places.the_street(None, "100. Yıl Mahallesi, Görken Sitesi") is None  # a neighbourhood, not a street
    assert places.the_street("1593 Sokak No: 5", None) == "1593 Sokak"  # a numbered Turkish street keeps its number
    searched = []

    def search(query, limit=3, box=None):
        searched.append(query)
        if query == "Athens":
            return [{"label": "Athens", "name": "Αθήνα", "areas": [], "district": "Athens", "lat": 37.976,
                     "lon": 23.735, "bbox": [37.85, 38.10, 23.60, 23.90]}]
        return [{"label": query, "name": query, "areas": [d], "district": d, "lat": lat, "lon": lon, "bbox": None}
                for d, (lat, lon) in {"Akropoli": (37.966, 23.726), "Glyfada": (37.866, 23.754)}.items()] if box else []

    result = places.check("Athens", "Αθήνα, Ορλώφ", street="Ορλώφ", search=search)
    assert [m["name"] for m in result["street_matches"]] == ["Akropoli", "Glyfada"] and "Ορλώφ" in searched


def orlof_map(landmark_at=None):
    """A fake map: Athens, Koukaki inside it, Orlof Street in Akropoli (Koukaki) and in Glyfada."""
    searched = []
    athens = {"label": "Athens", "name": "Αθήνα", "areas": [], "district": "Athens", "lat": 37.976, "lon": 23.735,
              "bbox": [37.85, 38.10, 23.60, 23.90]}
    koukaki = {"label": "Koukaki", "name": "Κουκάκι", "areas": [], "district": "Koukaki", "lat": 37.964, "lon": 23.723,
               "bbox": [37.958, 37.970, 23.715, 23.731]}
    streets = {"Akropoli": (37.9645, 23.7214), "Glyfada": (37.866, 23.754)}

    def search(query, limit=3, box=None):
        searched.append(query)
        if box:
            return [{"label": query, "name": query, "areas": [d], "district": d, "lat": lat, "lon": lon, "bbox": None,
                     "lines": [[[lat, lon], [lat + 0.002, lon]]]}
                    for d, (lat, lon) in streets.items() if box[0] <= lat <= box[1] and box[2] <= lon <= box[3]]
        if query == "Athens":
            return [athens]
        if query == "Κουκάκι, Athens":
            return [koukaki]
        if landmark_at and query.startswith("Ακρόπολη"):
            return [{"label": "Acropolis", "name": "Ακρόπολη", "areas": [], "district": "Akropoli",
                     "lat": landmark_at[0], "lon": landmark_at[1], "bbox": None}]
        return []
    return search, searched


def test_a_street_in_two_places_is_narrowed_by_the_neighbourhood_the_caller_said():
    # Test call 2026-10-24: "Ορλώφ, Κουκάκι, Αθήνα" but area "Athens": Koukaki and Glyfada came back.
    search, _ = orlof_map()
    result = places.check("Athens", "Ορλώφ, Κουκάκι, Αθήνα", None, "Ορλώφ", search=search)
    assert [m["name"] for m in result["street_matches"]] == ["Akropoli"]
    assert "Κουκάκι" in result["note"] and "Koukaki, Athens" in result["note"]


def test_a_street_in_two_places_is_narrowed_by_a_landmark_next_to_it():
    search, _ = orlof_map(landmark_at=(37.9715, 23.7257))  # the Acropolis: 0.9 km from one, 12 km from the other
    result = places.check("Athens", "Ορλώφ, κοντά στην Ακρόπολη, Αθήνα", "Ακρόπολη", "Ορλώφ", search=search)
    assert [m["name"] for m in result["street_matches"]] == ["Akropoli"] and "Near Ακρόπολη" in result["note"]


def test_a_landmark_between_the_two_doesnt_pick_one():
    search, _ = orlof_map(landmark_at=(37.915, 23.74))  # halfway: no guess
    result = places.check("Athens", "Ορλώφ, Αθήνα", "Ακρόπολη", "Ορλώφ", search=search)
    assert len(result["street_matches"]) == 2 and "Ask which neighbourhood" in result["note"]


def test_a_map_check_is_saved_at_once_and_a_doubt_undoes_the_yes(tmp_path, monkeypatch):
    from concurrent.futures import Future
    monkeypatch.setattr(core, "OUTPUT_DIR", tmp_path)
    s = core._Session(info=CallInfo(call_id="l7", channel="voice", phone="+30 690", lang_guess="el"), lang="el",
                      report=core.new_report("l7", "+30 690", "el", None))
    s.report["location"].update({"area": "Athens", "street": "Ορλώφ", "spoken_address": "Ορλώφ, Αθήνα",
                                 "confirmed_with_caller": True})
    check = Future()
    monkeypatch.setattr(places, "ENABLED", True)
    monkeypatch.setattr(core._place_checks, "submit", lambda fn, *args: check)
    core._start_map_check(s)
    check.set_result({"on_map": True, "note": "several", "street_matches": [{"name": "Akropoli"}, {"name": "Glyfada"}]})
    saved = json.loads((tmp_path / "reports" / "l7.json").read_text())  # no caller turn needed
    assert [m["name"] for m in saved["location"]["street_matches"]] == ["Akropoli", "Glyfada"]
    assert saved["location"]["confirmed_with_caller"] is False and s.steps.matches_area == "Athens"


def test_the_note_says_a_house_number_comes_after_the_street(tmp_path, monkeypatch):
    sent = fake_model(monkeypatch, tmp_path, [({"area": "Athens", "spoken_address": "Αθήνα", "hazard_type": "building_fire", "situation": "Smoke in the flat."}, "location", "none")] * 2)
    start_call(CallInfo(call_id="l8", channel="voice", phone="+30 690", lang_guess="el"))
    turn("l8", "Βγαίνει καπνός από το διαμέρισμα, στην Αθήνα.", "el")
    turn("l8", "Ορλώφ.", "el")
    assert "ask for the street" in sent[1] and "house number" in sent[1]


def test_confidence_is_never_100_percent():
    report = core.new_report("l9", "+30 690", "el", None)
    core.apply_update(report, {"urgency_suggested": "life_threat", "urgency_reasons": ["fire"], "urgency_confidence": 1.0})
    assert report["urgency"]["confidence"] == 0.95


def test_a_street_that_doesnt_exist_gets_the_closest_real_one(monkeypatch):
    # Speech-to-text often writes Greek streets that don't exist; then nothing reached the map.
    search, _ = orlof_map()
    monkeypatch.setattr(places, "ENABLED", True)
    monkeypatch.setattr(places, "STREET_LIST", True)
    monkeypatch.setattr(places, "street_names", lambda area, search: ["Ορλώφ", "Ζίννη", "Βεΐκου"])
    result = places.check("Koukaki, Athens", "Ορλόβ 12", None, "Ορλόβ", search=lambda q, limit=3, box=None: (
        [{"label": "Koukaki", "name": "Κουκάκι", "areas": [], "district": "Koukaki", "lat": 37.964, "lon": 23.723,
          "bbox": [37.958, 37.970, 23.715, 23.731], "size_km": 1.8}] if not box else []))
    assert result["street_suggestion"] == "Ορλώφ" and "Did you mean Ορλώφ?" in result["note"]
    nothing = places.check("Koukaki, Athens", "Δοκιμής 4", None, "Δοκιμής", search=lambda q, limit=3, box=None: (
        [{"label": "Koukaki", "name": "Κουκάκι", "areas": [], "lat": 37.964, "lon": 23.723,
          "bbox": [37.958, 37.970, 23.715, 23.731], "size_km": 1.8}] if not box else []))
    assert "street_suggestion" not in nothing and "repeat or spell" in nothing["note"]


def test_the_suggested_street_reaches_the_model_only_as_a_placeholder():
    from concurrent.futures import Future
    s = core._Session(info=CallInfo(call_id="l10", channel="voice", phone="+30 690", lang_guess="el"), lang="el",
                      report=core.new_report("l10", "+30 690", "el", None))
    check = Future()
    check.set_result({"on_map": True, "street_matches": [], "street_suggestion": "Ορλώφ",
                      "note": "... sounds closest is Ορλώφ. Ask the caller: 'Did you mean Ορλώφ?' ..."})
    s.place_check = check
    note = core._map_check_result(s)
    assert "Ορλώφ" not in note and "<ADDRESS_1>" in note and s.masker.unmask("<ADDRESS_1>") == "Ορλώφ"


def test_street_lists_are_fetched_once_in_the_background_and_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(places, "STREET_LIST", True)
    monkeypatch.setattr(places, "_street_lists_wanted", set())
    fetched = []
    area = [{"label": "Koukaki", "name": "Κουκάκι", "areas": [], "lat": 37.964, "lon": 23.723,
             "bbox": [37.958, 37.970, 23.715, 23.731], "size_km": 1.8}]
    def fetch(box):
        fetched.append(box)
        return ["Ορλώφ", "Ζίννη"]
    assert places.street_names("Koukaki, Athens", lambda q: area, fetch) is None  # not there yet: fetching
    places._street_lists.submit(lambda: None).result()  # wait for the background fetch
    assert places.street_names("Koukaki, Athens", lambda q: area, fetch) == ["Ορλώφ", "Ζίννη"]
    assert len(fetched) == 1
    big = [{**area[0], "size_km": 45}]  # a whole city: too many streets, ask the neighbourhood instead
    assert places.street_names("Attica", lambda q: big, fetch) is None and len(fetched) == 1


def test_a_name_question_marked_other_still_masks_the_answer(tmp_path, monkeypatch):
    # Eval 2026-10-26: the model asked "Ποιο είναι το ονοματεπώνυμό σας;" with expecting "other".
    s = core._Session(info=CallInfo(call_id="l11", channel="voice", phone="+30 690", lang_guess="el"), lang="el",
                      report=core.new_report("l11", "+30 690", "el", None))
    s.expecting = "other"
    s.transcript = [{"role": "agent", "text": "Ποιο είναι το ονοματεπώνυμό σας;"}, {"role": "caller", "text": "Κώστας Δοκιμάκης."}]
    assert core._asked_for(s)[0] == "name"
    assert "Δοκιμάκης" not in s.masker.mask("Κώστας Δοκιμάκης.", *core._asked_for(s))


def test_a_busy_street_list_server_falls_back_to_the_next(monkeypatch):
    import io
    monkeypatch.setattr(places, "OVERPASS_URLS", ["https://busy.example", "https://ok.example"])
    def urlopen(request, timeout):
        if "busy" in request.full_url:
            raise OSError("HTTP Error 504: Gateway Timeout")
        return io.BytesIO(json.dumps({"elements": [{"tags": {"name": "Ορλώφ"}}, {"tags": {"name": "Ζίννη"}}]}).encode())
    monkeypatch.setattr(places.urllib.request, "urlopen", urlopen)
    assert places.overpass_streets([37.95, 37.97, 23.71, 23.73]) == ["Ζίννη", "Ορλώφ"]


def test_a_street_texted_in_latin_letters_is_found_under_its_greek_name(monkeypatch):
    # WhatsApp test 2026-10-26: "Orlof 12A, Koukaki" was "not found"; OpenStreetMap only has Ορλώφ.
    monkeypatch.setattr(places, "ENABLED", True)
    monkeypatch.setattr(places, "STREET_LIST", True)
    monkeypatch.setattr(places, "street_names", lambda area, search: ["Ορλώφ", "Ζίννη"])
    koukaki = {"label": "Koukaki", "name": "Κουκάκι", "areas": [], "district": "Koukaki", "lat": 37.964, "lon": 23.723,
               "bbox": [37.958, 37.970, 23.715, 23.731], "size_km": 1.8}

    def search(query, limit=3, box=None):
        if not box:
            return [koukaki]
        return [{"label": query, "name": query, "areas": ["Akropoli"], "district": "Akropoli", "lat": 37.9645,
                 "lon": 23.7214, "bbox": None}] if query == "Ορλώφ" else []

    result = places.check("Koukaki, Athens", "Orlof 12A, Koukaki", None, "Orlof", search=search)
    assert [m["name"] for m in result["street_matches"]] == ["Akropoli"] and result["note"] is None  # no question


def test_street_hints_for_speech_to_text_only_once_the_list_is_kept(monkeypatch):
    s = core._Session(info=CallInfo(call_id="l13", channel="voice", phone="+30 690", lang_guess="el"), lang="el",
                      report=core.new_report("l13", "+30 690", "el", None))
    core._sessions["l13"] = s
    monkeypatch.setattr(places, "ENABLED", True)
    monkeypatch.setattr(places, "STREET_LIST", True)
    monkeypatch.setattr(places, "street_names", lambda area: ["Βασιλίσσης Φρειδερίκης"])
    monkeypatch.setattr(places, "has_street_list", lambda area: area == "Παιανία")
    assert core.street_hints("l13") == []  # no area yet
    s.report["location"]["area"] = "Αθήνα"
    assert core.street_hints("l13") == []  # no list kept: never waits on the network
    s.report["location"]["area"] = "Παιανία"
    assert core.street_hints("l13") == ["Βασιλίσσης Φρειδερίκης"]
    assert core.street_hints("no-such-call") == []
    monkeypatch.setattr(places, "street_names", lambda area: [f"Οδός {i}" for i in range(core.MAX_STREET_HINTS + 1)])
    assert core.street_hints("l13") == []  # a whole city's list is too long to hint


def test_a_masked_street_in_the_address_is_kept_as_the_street(tmp_path, monkeypatch):
    # Eval 2026-10-27: the model put <ADDRESS_1> into spoken_address only, so the map never searched it.
    sent = fake_model(monkeypatch, tmp_path, [({"area": "Athens", "spoken_address": "<ADDRESS_1>, Αθήνα",
                                                "hazard_type": "building_fire", "situation": "Smoke."}, "other", "none")])
    start_call(CallInfo(call_id="l14", channel="voice", phone="+30 690", lang_guess="el"))
    turn("l14", "Βγαίνει καπνός από μια πολυκατοικία στην Αθήνα, στην Ορλώφ, κοντά στην Ακρόπολη.", "el")
    s = core._sessions["l14"]
    assert "Ορλώφ" not in sent[0] and s.report["location"]["street"] == "Ορλώφ"
    assert "Ορλώφ" not in s.masker.mask_known('{"street": "Ορλώφ"}')  # the summary request masks it too


def test_the_opening_note_says_record_then_ask_the_next_missing_item():
    r = core.new_report("l15", "+30 690", "el", None)
    note = steps.note(r, steps.Steps())
    assert note.startswith("this message answers the question just asked") and "area, street" in note
