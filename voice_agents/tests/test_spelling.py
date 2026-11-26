"""A street spelled letter by letter (brain/spelling.py) and the step that asks for it
(brain/steps.py, brain/core.py). A fake model, no API calls."""
from concurrent.futures import Future

import brain.core as core
from brain import CallInfo, places, steps
from brain.spelling import spelled


def test_letters_letter_names_and_syllables_become_one_word():
    assert spelled("Φ Ρ Ε Ι Δ Ε Ρ Ι Κ Η Σ", "el") == "Φρειδερικης"
    assert spelled("φι, ρο, έψιλον, γιώτα", "el") == "Φρει"
    assert spelled("Φρει-δε-ρί-κης", "el") == "Φρειδερίκης"
    assert spelled("Φ όπως Φώτης, Ρ, Ε", "el") == "Φρε"
    assert spelled("A, T, A, T, Ü, R, K", "tr") == "Atatürk"
    assert spelled("be, a, yumuşak ge", "tr") == "Bağ"
    assert spelled("İ, N, Ö, N, Ü", "tr") == "İnönü"


def test_words_around_the_letters_are_dropped():
    assert spelled("Ναι, το λέω: Φ Ρ Ε Ι Δ Ε Ρ Ι Κ Η Σ.", "el") == "Φρειδερικης"


def test_ordinary_answers_are_not_spelling():
    for text in ("Βασιλίσσης Φρειδερίκης δώδεκα", "Δεν ξέρω", "Ναι", "Στην Παιανία είναι", "Φ Ρ"):
        assert spelled(text, "el") is None, text


def _session(call_id):
    s = core._Session(info=CallInfo(call_id=call_id, channel="voice", phone="+30 690", lang_guess="el"), lang="el",
                      report=core.new_report(call_id, "+30 690", "el", None))
    s.report.update({"hazard_type": "building_fire", "situation": "Smoke in the flat."})
    s.report["location"].update({"area": "Παιανία", "street": "Σφαιρική", "spoken_address": "Σφαιρική 4, Παιανία"})
    return s


def _map_says(s, monkeypatch, tmp_path, result, street_list=True):
    monkeypatch.setattr(core, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(places, "ENABLED", True)
    monkeypatch.setattr(places, "has_street_list", lambda area: street_list)
    check = Future()
    monkeypatch.setattr(core._place_checks, "submit", lambda fn, *args: check)
    core._start_map_check(s)
    check.set_result(result)


def test_a_street_with_nothing_close_on_the_map_is_spelled(tmp_path, monkeypatch):
    # Test call 2026-10-26: "Βασιλίσσης Φρειδερίκης …" was heard as "Σφαιρική …".
    s = _session("sp1")
    _map_says(s, monkeypatch, tmp_path, {"on_map": True, "street_matches": [], "note": "not found"})
    assert steps.remaining(s.report, s.steps)[0] == "spell_street"
    assert "letter by letter" in steps.note(s.report, s.steps)


def test_a_close_real_street_is_offered_instead_of_spelling(tmp_path, monkeypatch):
    s = _session("sp2")
    _map_says(s, monkeypatch, tmp_path, {"on_map": True, "street_matches": [], "street_suggestion": "Σφακίων",
                                         "note": "Did you mean Σφακίων?"})
    assert "spell_street" not in steps.remaining(s.report, s.steps)


def test_no_spelling_before_the_area_street_list_is_in(tmp_path, monkeypatch):
    s = _session("sp3")
    _map_says(s, monkeypatch, tmp_path, {"on_map": True, "street_matches": [], "note": "not found"}, street_list=False)
    assert "spell_street" not in steps.remaining(s.report, s.steps)


def test_the_spelled_street_goes_into_the_report_and_only_masked_to_the_model(tmp_path, monkeypatch):
    s = _session("sp4")
    said = core._take_spelled(s, "Φρειδερικης")
    location = s.report["location"]
    assert location["street"] == "Φρειδερικης" and location["spoken_address"] == "Φρειδερικης 4, Παιανία"
    assert "Φρειδερικης" not in said and s.masker.unmask("<ADDRESS_1>") == "Φρειδερικης"
    assert steps.remaining(s.report, s.steps)[0] != "spell_street"  # a new street: checked on the map again
