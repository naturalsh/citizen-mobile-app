"""Which question comes next, decided by code (brain/steps.py). No API calls."""
from brain import steps
from brain.report import new_report


def report(**location):
    r = new_report("s1", "+30 690", "el", None)
    r["location"].update(location)
    return r


def told_what_happened(r):
    r.update({"hazard_type": "building_fire", "situation": "Smoke from the flat below."})
    return r


def test_the_whole_order_skips_what_is_known():
    r = report()
    # What happened first: callers lead with it. Nothing said yet: no read-back.
    assert steps.remaining(r, steps.Steps())[:3] == ["what_happened", "area", "street"]
    r["location"].update({"area": "Koukaki, Athens", "street": "Ορλώφ", "spoken_address": "Ορλώφ 12, Κουκάκι",
                          "confirmed_with_caller": True})
    assert steps.remaining(r, steps.Steps()) == ["what_happened", "people", "danger", "name", "final_readback"]
    r.update({"hazard_type": "building_fire", "situation": "Fire in a flat below the caller."})
    r["people"] = [{"count": 2, "trapped": True}]
    r["caller"]["name"] = "Μαρία Δοκιμάκη"
    assert steps.remaining(r, steps.Steps()) == ["floor", "final_readback"]  # a building fire: which floor


def test_an_unclear_hazard_keeps_what_happened_open():
    r = report(area="Athens", street="Ορλώφ", spoken_address="Ορλώφ 12", confirmed_with_caller=True)
    r.update({"hazard_type": "wildfire", "situation": "Caller said 'fire?'"})
    assert steps.remaining(r, steps.Steps(), hazard_unclear=True)[0] == "what_happened"
    assert steps.remaining(r, steps.Steps())[0] == "people"


def test_the_code_knows_what_was_asked_so_masking_can_rely_on_it():
    # The model once asked for the name but labelled the question "other": the name reached it.
    r = report(area="Athens", street="Ορλώφ", spoken_address="Ορλώφ 12", confirmed_with_caller=True)
    r.update({"hazard_type": "earthquake", "situation": "A wall fell."})
    r["people"] = [{"count": 1, "injured": 0}]
    st = steps.Steps(asked="danger")
    steps.after_answer(r, st, "Όχι, κανείς.")
    assert st.asked == "name" and st.expecting() == "name"


def test_a_step_is_dropped_after_two_misses_or_one_dont_know():
    r = told_what_happened(report(area="Athens", street="Ορλώφ", spoken_address="Ορλώφ, Αθήνα"))
    st = steps.Steps(asked="house_number")
    steps.after_answer(r, st, "Εεε.")
    assert st.asked == "house_number" and st.unanswered == {"house_number": 1}
    steps.after_answer(r, st, "Μμμ.")
    assert st.asked == "cross_street"
    steps.after_answer(r, st, "Δεν ξέρω.")
    assert st.asked == "location_readback"  # the corner skipped at once on a clear "don't know"


def test_the_note_says_what_comes_next_and_after():
    r = told_what_happened(report(area="Athens"))
    note = steps.note(r, steps.Steps())
    assert note.startswith("next (street): ask for the street") and "house number" in note and "location read-back" in note


def test_a_whole_city_gets_the_neighbourhood_question_before_the_street(monkeypatch):
    # The model asked "which neighbourhood of Athens?" on its own while the code said "read back".
    monkeypatch.setattr(steps.places, "size_km", lambda area: {"Athens": 45.3, "Koukaki, Athens": 2.8}.get(area))
    r = told_what_happened(report(area="Athens", street="Ορλώφ", spoken_address="Ορλώφ 12, Αθήνα"))
    assert steps.remaining(r, steps.Steps())[0] == "neighbourhood"
    r["location"]["area"] = "Koukaki, Athens"
    assert steps.remaining(r, steps.Steps())[0] == "location_readback"
    r["location"].update({"area": "Athens", "street_matches": [{"name": "Akropoli"}]})
    assert steps.remaining(r, steps.Steps(matches_area="Athens"))[0] == "location_readback"  # placed on the map


def test_the_step_the_model_really_asked_is_used():
    # Eval 2026-10-26: the model asked "who exactly?" while the code thought it asked for the name,
    # so the eval caller (and masking) answered the wrong question.
    r = report(area="Athens", street="Ορλώφ", spoken_address="Ορλώφ 12", confirmed_with_caller=True)
    st = steps.Steps(asked="what_happened")
    steps.after_answer(r, st, "Έχουν πεθάνει 5 κολόβριες.", asked="other")
    assert st.asked is None and st.expecting() == "other"
    steps.after_answer(r, st, "Πέντε ενήλικες.", asked="name")
    assert st.asked == "name" and st.expecting() == "name"


def test_a_step_the_model_keeps_ignoring_is_dropped_after_a_few_notes():
    r = report(area="Athens", street="Ορλώφ", spoken_address="Ορλώφ 12", confirmed_with_caller=True)
    st = steps.Steps(asked=None)  # not the opening, whose note reads differently
    firsts = [steps.note(r, st).split(")")[0] for _ in range(5)]
    assert firsts[:3] == ["next (what_happened"] * 3 and firsts[3] == "next (people"


def test_the_note_for_what_happened_says_where_comes_next():
    note = steps.note(report(), steps.Steps(asked=None))
    assert note.startswith("next (what_happened)") and "After that: area, street" in note


def test_by_text_one_list_asks_for_everything_missing_twice_at_most():
    r, st = report(), steps.Steps(text=True)
    assert steps.form_items(r, st) == ["what_happened", "where", "people", "danger", "name"]
    assert "location_readback" not in steps.remaining(r, st)  # the final read-back has the location
    told_what_happened(r)
    r["location"].update({"area": "Koukaki, Athens", "street": "Ορλώφ", "spoken_address": "Ορλώφ, Κουκάκι"})
    r["caller"]["name"] = "Μαρία Δοκιμάκη"
    st.forms = 1
    assert steps.form_items(r, st) == ["house_number", "people", "danger", "floor"]  # only what is still missing
    assert steps.note(r, st).startswith("text: ")
    st.forms = 2  # two lists sent: the rest is left to the operator, read back now
    assert steps.form_items(r, st) == [] and steps.remaining(r, st) == ["final_readback"]
    assert "reply YES" in steps.note(r, st)
