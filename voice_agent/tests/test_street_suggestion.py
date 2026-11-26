"""A street speech-to-text misheard, and the real one the map suggests (brain/core.py, steps.py,
masking.py). From the live test call of 2026-11-15: a street was heard under a wrong name every
time, the model read the map's street and the heard one back together, then the heard one twice,
and the address was never confirmed. Invented street names, a fake model, no API calls."""
from concurrent.futures import Future

import brain.core as core
from brain import CallInfo, places, steps
from brain.masking import Masker

HEARD, REAL = "Φραγγυλλιδών", "Φραγκιάδων"


def _session(call_id):
    s = core._Session(info=CallInfo(call_id=call_id, channel="voice", phone="+30 690", lang_guess="el"), lang="el",
                      report=core.new_report(call_id, "+30 690", "el", None))
    s.report.update({"hazard_type": "earthquake", "situation": "A building collapsed."})
    s.report["location"].update({"area": "Piraeus", "street": HEARD, "spoken_address": f"{HEARD} 16"})
    s.masker.mask(f"Είμαι στην {HEARD} 16.", "other", "Piraeus")
    s.transcript.append({"role": "agent", "text": "…"})
    return s


def _map_suggests(s, monkeypatch, tmp_path, suggestion=REAL):
    monkeypatch.setattr(core, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(places, "ENABLED", True)
    monkeypatch.setattr(places, "has_street_list", lambda area: True)
    monkeypatch.setattr(places, "size_km", lambda area: 45.0)  # a whole city
    check = Future()
    monkeypatch.setattr(core._place_checks, "submit", lambda fn, *args: check)
    core._start_map_check(s)
    check.set_result({"on_map": True, "street_matches": [], "street_suggestion": suggestion,
                      "note": f"... sounds closest is {suggestion}. Ask the caller: 'Did you mean {suggestion}?' ..."})


def test_a_street_with_an_accented_ending_is_masked_wherever_it_is_said():
    m = Masker()
    said = m.mask(f"Είμαι στην {HEARD} 16 και έχει πέσει ένα κτίριο πάνω σε ένα παιδί.", "opening", "Piraeus")
    assert HEARD not in said and "16" not in said and "<ADDRESS_1>" in said
    # Said again without the number, it is still masked, as a street of its own.
    alone = m.mask(f"Το κομμάτι που λες, {HEARD}, είναι σκέτο {HEARD}.", "location", "Piraeus")
    assert HEARD not in alone and alone.count("<ADDRESS_2>") == 2
    assert m.unmask("<ADDRESS_1>") == f"{HEARD} 16" and m.unmask("<ADDRESS_2>") == HEARD
    # Endings without an accent are masked as before, and words that are not streets are left alone.
    assert Masker().mask("Θεμιστοκλέους 5", "other") == "<ADDRESS_1>"
    assert Masker().mask("Είμαστε 3 άτομα.", "other") == "Είμαστε 3 άτομα."
    # The accent moved, as speech-to-text does, and a street word in front: still the same street.
    m = Masker()
    m.mask("στην οδό Φραγκιαδών 16", "location")
    assert "Φραγκιάδων" not in m.mask("Ναι, Φραγκιάδων.", "other") and "Φραγκιαδών" not in m.mask("Φραγκιαδών λέω", "other")


def test_a_word_before_a_count_is_never_taken_for_a_street():
    # Found by review: "word + number" was remembered as a street, and the word was then masked
    # for the rest of the call ("Τα <ADDRESS_2> δεν αναπνέουν").
    for first, later in (("Παιδιά 3", "Τα παιδιά δεν αναπνέουν"), ("Συνολικά 5 άτομα, ένα παιδί παγιδευμένο.", "Συνολικά δέκα"),
                         ("Bina 3 katlı, çöktü", "Bina çöktü"), ("Person 2 is trapped", "One Person is not breathing")):
        m = Masker()
        m.mask(first, "location")
        assert m.mask(later, "other") == later, first
    assert Masker().mask("Παιδιά 3", "other") == "Παιδιά 3"  # the count reaches the model
    m = Masker()
    m.mask("Ada 5", "location")
    assert m.mask("burada bir adam var", "other") == "burada bir adam var"  # never inside another word


def test_the_code_asks_did_you_mean_before_the_neighbourhood(tmp_path, monkeypatch):
    s = _session("su1")
    _map_suggests(s, monkeypatch, tmp_path)
    # A whole city: but whether the street was misheard comes first, and the neighbourhood is not
    # asked while that is open (the real street may be in one place only).
    missing = steps.remaining(s.report, s.steps)
    assert missing[0] == "confirm_street" and "neighbourhood" not in missing
    assert s.report["location"]["map_suggestion"] == f"{REAL} 16"  # for the operator, whatever the caller answers
    placeholder = s.masker.hide("ADDRESS", REAL)
    note = steps.note(s.report, s.steps, suggestion=placeholder)
    assert f"'Did you mean {placeholder}?'" in note and REAL not in note and "Do not change street" in note


def test_a_yes_puts_the_real_street_into_the_report_by_code(tmp_path, monkeypatch):
    s = _session("su2")
    _map_suggests(s, monkeypatch, tmp_path)
    s.steps.asked = "confirm_street"
    told = core._answer_to_suggestion(s, "Ναι, αυτό.")
    location = s.report["location"]
    assert (location["street"], location["spoken_address"]) == (REAL, f"{REAL} 16")
    assert location["map_suggestion"] is None and location["confirmed_with_caller"] is False
    assert REAL not in told and HEARD not in told and "16" not in told  # the model gets a placeholder only
    missing = steps.remaining(s.report, s.steps)
    assert "confirm_street" not in missing and "neighbourhood" not in missing  # the real street is looked up first
    # Whatever the model says or writes afterwards, the heard name does not come back.
    assert core._tidy_streets(s, f"Εντάξει, Πειραιάς, {HEARD} 16, είναι σωστό;") == f"Εντάξει, Πειραιάς, {REAL} 16, είναι σωστό;"
    assert core._tidy_streets(s, f"{REAL} {HEARD} 16") == f"{REAL} 16"


def test_a_no_keeps_the_callers_street_and_does_not_ask_again(tmp_path, monkeypatch):
    s = _session("su3")
    _map_suggests(s, monkeypatch, tmp_path)
    s.steps.asked = "confirm_street"
    told = core._answer_to_suggestion(s, "Όχι, δεν είναι αυτό.")
    assert "keep the street" in told and s.report["location"]["street"] == HEARD
    assert "confirm_street" not in steps.remaining(s.report, s.steps)
    # The same suggestion arriving again from a later map check is not asked again.
    s.report["location"]["spoken_address"] = f"{HEARD} 16, Πειραιάς"
    _map_suggests(s, monkeypatch, tmp_path)
    assert "confirm_street" not in steps.remaining(s.report, s.steps)


def test_the_street_said_again_is_neither_yes_nor_no(tmp_path, monkeypatch):
    s = _session("su4")
    _map_suggests(s, monkeypatch, tmp_path)
    s.steps.asked = "confirm_street"
    assert core._answer_to_suggestion(s, f"{HEARD} 16.") is None
    assert s.report["location"]["street"] == HEARD and s.steps.suggested_street == REAL
    # Asked twice without an answer, the question is dropped; the suggestion stays for the operator.
    steps.after_answer(s.report, s.steps, f"{HEARD} 16.", asked="confirm_street")
    steps.after_answer(s.report, s.steps, f"{HEARD} 16.", asked="confirm_street")
    assert "confirm_street" not in steps.remaining(s.report, s.steps)
    assert s.report["location"]["map_suggestion"] == f"{REAL} 16"


def test_a_street_is_never_read_back_twice_or_beside_the_one_it_was_mistaken_for(tmp_path, monkeypatch):
    s = _session("su5")
    assert core._tidy_streets(s, f"Εντάξει, Πειραιάς, {HEARD} {HEARD} 16, είναι σωστό;") == f"Εντάξει, Πειραιάς, {HEARD} 16, είναι σωστό;"
    _map_suggests(s, monkeypatch, tmp_path)
    # Before the caller answered: the map's street is not slipped in front of the heard one.
    assert core._tidy_streets(s, f"Εντάξει, Πειραιάς, {REAL} {HEARD} 16, είναι σωστό;") == f"Εντάξει, Πειραιάς, {HEARD} 16, είναι σωστό;"
    # The question itself is left as it is.
    assert core._tidy_streets(s, f"Εννοείτε {REAL};") == f"Εννοείτε {REAL};"
    assert core._speakable(s, f"{HEARD} {HEARD} 16") == f"{HEARD} 16"


def test_a_street_and_number_in_the_message_is_not_followed_by_the_neighbourhood_question(tmp_path, monkeypatch):
    # The live call: "Είμαι στην … 16 και έχει πέσει ένα κτίριο" in Piraeus was answered with "which neighbourhood?", twice.
    monkeypatch.setattr(places, "size_km", lambda area: 45.0)
    s = core._Session(info=CallInfo(call_id="su6", channel="voice", phone="+30 690", lang_guess="el"), lang="el",
                      report=core.new_report("su6", "+30 690", "el", None))
    s.report.update({"hazard_type": "earthquake", "situation": "A building collapsed."})
    s.report["location"].update({"area": "Piraeus", "spoken_address": "Πειραιάς"})
    assert steps.remaining(s.report, s.steps)[0] == "neighbourhood"  # no street yet: narrow the city first
    s.steps.street_in_message = True   # core saw "<street> 16" in the caller's message
    missing = steps.remaining(s.report, s.steps)
    assert "neighbourhood" not in missing and "street" not in missing and "location_readback" not in missing
    assert missing[0] == "people"  # something useful while the map looks the street up
    # The model has recorded it and the map is still looking: still no neighbourhood, no read-back.
    s.steps.street_in_message = False
    s.report["location"].update({"street": HEARD, "spoken_address": f"Πειραιάς, {HEARD} 16"})
    s.steps.map_pending = True
    assert steps.remaining(s.report, s.steps)[0] == "people"
    # The map could not be asked at all: the neighbourhood is asked as before.
    s.steps.map_pending = False
    assert steps.remaining(s.report, s.steps)[0] == "neighbourhood"


def test_only_a_goodbye_is_a_goodbye():
    for text in ("Αντίο.", "Εντάξει, αντίο σας", "Hoşça kal", "OK bye", "Au revoir, merci", "Güle güle"):
        assert core._goodbye(text), text
    # Found by review: a goodbye with something said in it must reach the model.
    for text in ("Ναι.", "Γεια σας, έχει φωτιά στο σπίτι", "Αντίο, δεν αναπνέει", "Bye, three people trapped",
                 "Μη λες αντίο", "Όχι αντίο ακόμα", "Αντίο δεν λέω, ελάτε γρήγορα σας παρακαλώ πολύ"):
        assert not core._goodbye(text), text


def test_a_goodbye_is_answered_with_the_closing_line_and_the_line_stays_open(tmp_path, monkeypatch):
    from brain import start_call, turn
    from tests.test_location_steps import fake_model
    sent = fake_model(monkeypatch, tmp_path, [({"area": "Κερατσίνι", "spoken_address": "Κερατσίνι", "hazard_type": "earthquake",
                                                "situation": "A wall fell."}, "location", "none"),
                                              ({}, "other", "none")])
    start_call(CallInfo(call_id="su8", channel="voice", phone="+30 690", lang_guess="el"))
    turn("su8", "Έπεσε ένας τοίχος στο Κερατσίνι.", "el")
    bye = turn("su8", "Αντίο.", "el")
    assert bye.reply_text == core.PHRASES["passed_on"]["el"] and bye.action == "continue" and len(sent) == 1
    # Not a goodbye: it goes to the model like any message.
    turn("su8", "Αντίο, δεν αναπνέει.", "el")
    assert len(sent) == 2 and "δεν αναπνέει" in sent[1]


def _asked(s):
    s.steps.asked = "confirm_street"


def test_only_a_plain_yes_rewrites_the_street(tmp_path, monkeypatch):
    # Found by review: each of these replaced the caller's street with the map's.
    for text in (f"Το σωστό είναι {HEARD}", f"Εντάξει, {HEARD} 16 είπα", "Δεν ξέρω, εντάξει", "Όλα καταστράφηκαν",
                 "Right next to the church", "Ναι;", "Ναι αλλά όχι ακριβώς"):
        s = _session("y" + str(abs(hash(text)) % 9999))
        _map_suggests(s, monkeypatch, tmp_path)
        _asked(s)
        core._answer_to_suggestion(s, text)
        assert s.report["location"]["street"] == HEARD, text
    # A yes, a yes with the street said again (written the wrong way again), and the real street itself.
    for text in ("Ναι.", "Ναι, σωστά.", f"Ναι, {HEARD} 16.", f"{REAL} 16.", f"Ναι, {REAL}."):
        s = _session("n" + str(abs(hash(text)) % 9999))
        _map_suggests(s, monkeypatch, tmp_path)
        _asked(s)
        assert core._answer_to_suggestion(s, text) is not None, text
        assert s.report["location"]["street"] == REAL and s.report["location"]["street_as_heard"] == HEARD, text
    # "No, <the real street>" can mean either: it is neither a yes nor a no, and the question stays open.
    s = _session("amb")
    _map_suggests(s, monkeypatch, tmp_path)
    _asked(s)
    assert core._answer_to_suggestion(s, f"Όχι, {REAL} είπα.") is None
    assert s.report["location"]["street"] == HEARD and s.steps.suggested_street == REAL


def test_the_yes_is_heard_whatever_the_model_called_its_question(tmp_path, monkeypatch):
    s = _session("su9")
    _map_suggests(s, monkeypatch, tmp_path)
    s.steps.asked = None  # the model labelled "Did you mean …?" as "other"
    s.transcript += [{"role": "agent", "text": f"Εννοείτε την οδό {REAL};"}, {"role": "caller", "text": "Ναι."}]
    assert core._answer_to_suggestion(s, "Ναι.") is not None and s.report["location"]["street"] == REAL
    # A yes to some other question changes nothing.
    other = _session("su10")
    _map_suggests(other, monkeypatch, tmp_path)
    other.steps.asked = "people"
    other.transcript += [{"role": "agent", "text": "Πόσα άτομα είναι εκεί;"}, {"role": "caller", "text": "Ναι."}]
    assert core._answer_to_suggestion(other, "Ναι.") is None and other.report["location"]["street"] == HEARD


def test_the_rest_of_the_address_and_the_right_number_survive_a_yes(tmp_path, monkeypatch):
    s = _session("su11")
    s.report["location"]["spoken_address"] = f"2ος όροφος, Φραγγυλλιδων 16, Κερατσίνι, δίπλα στο φαρμακείο"  # no accent, as the model wrote it
    _map_suggests(s, monkeypatch, tmp_path)
    assert s.report["location"]["map_suggestion"] == f"{REAL} 16"  # the number after the street, not "2"
    _asked(s)
    core._answer_to_suggestion(s, "Ναι.")
    assert s.report["location"]["spoken_address"] == f"2ος όροφος, {REAL} 16, Κερατσίνι, δίπλα στο φαρμακείο"


def test_a_yes_can_be_taken_back_with_a_no_and_the_callers_street(tmp_path, monkeypatch):
    s = _session("su12")
    _map_suggests(s, monkeypatch, tmp_path)
    _asked(s)
    core._answer_to_suggestion(s, "Ναι.")
    # The heard street alone is not a no: speech-to-text writes the real street that way every time.
    assert core._take_back_the_suggestion(s, f"{HEARD} 16.") is None and s.report["location"]["street"] == REAL
    told = core._take_back_the_suggestion(s, f"Όχι, {HEARD} 16.")
    location = s.report["location"]
    assert "took back" in told and (location["street"], location["spoken_address"]) == (HEARD, f"{HEARD} 16")
    assert location["map_suggestion"] == f"{REAL} 16" and "street_as_heard" not in location  # the operator still sees both
    assert core._tidy_streets(s, f"{HEARD} 16") == f"{HEARD} 16"  # no longer rewritten
    # And the map's street is not offered again.
    _map_suggests(s, monkeypatch, tmp_path)
    assert "confirm_street" not in steps.remaining(s.report, s.steps)


def test_after_a_no_the_map_note_asks_nothing_and_the_operator_keeps_the_suggestion(tmp_path, monkeypatch):
    s = _session("su13")
    _map_suggests(s, monkeypatch, tmp_path)
    _asked(s)
    core._answer_to_suggestion(s, "Όχι.")
    s.report["location"]["spoken_address"] = f"{HEARD} 16, Πειραιάς"  # the address changed: the map is asked again
    _map_suggests(s, monkeypatch, tmp_path)
    assert s.report["location"]["map_suggestion"] == f"{REAL} 16"
    note = core._map_check_result(s)
    assert "Did you mean" not in note and "do not ask about it again" in note


def test_a_late_answer_about_the_heard_street_changes_nothing_after_a_yes(tmp_path, monkeypatch):
    s = _session("su14")
    _map_suggests(s, monkeypatch, tmp_path)
    _asked(s)
    core._answer_to_suggestion(s, "Ναι.")
    key = ("Piraeus", f"{HEARD} 16", None, HEARD)
    s.place_checked = key
    late = Future()
    late.set_result({"on_map": True, "street_matches": [], "street_suggestion": REAL, "note": "..."})
    core._store_map_result(s, late, key)
    assert s.steps.suggested_street is None and s.report["location"]["street_matches"] is None


def test_an_unanswered_suggestion_gives_way_to_the_neighbourhood(tmp_path, monkeypatch):
    s = _session("su15")
    _map_suggests(s, monkeypatch, tmp_path)
    _asked(s)
    for _ in range(2):
        steps.after_answer(s.report, s.steps, f"{HEARD} 16.", asked="confirm_street")
    assert steps.remaining(s.report, s.steps)[0] == "neighbourhood"  # a whole city: asked once the suggestion is dropped


def test_by_text_the_list_of_missing_details_has_no_line_for_the_suggestion(tmp_path, monkeypatch):
    # Found by review: the list looked up a phrase that does not exist and the reply failed.
    s = _session("su16")
    s.steps.text = True
    _map_suggests(s, monkeypatch, tmp_path)
    assert "confirm_street" not in steps.form_items(s.report, s.steps)
    text, _ = core._add_form(s, "Εντάξει.", "OK.")
    assert text.startswith("Εντάξει.")


def test_the_code_sees_a_street_with_its_number_in_the_message_and_not_a_count(tmp_path, monkeypatch):
    from brain import start_call, turn
    from tests.test_location_steps import fake_model
    monkeypatch.setattr(places, "size_km", lambda area: 45.0)
    answers = [({"area": "Piraeus", "spoken_address": "Πειραιάς"}, "what_happened", "none"),
               ({"hazard_type": "earthquake", "situation": "A building collapsed.", "spoken_address": "<ADDRESS_1>, Πειραιάς"}, "people", "none"),
               ({}, "people", "none")]
    sent = fake_model(monkeypatch, tmp_path, answers)
    start_call(CallInfo(call_id="su17", channel="voice", phone="+30 690", lang_guess="el"))
    turn("su17", "Πειραιά.", "el")
    turn("su17", f"Είμαι στην {HEARD} 16 και έχει πέσει ένα κτίριο πάνω σε ένα παιδί.", "el")
    assert HEARD not in sent[1] and "holds the street and its house number" in sent[1] and "next (neighbourhood)" not in sent[1]
    assert core._sessions["su17"].report["location"]["street"] == HEARD
    turn("su17", "Συνολικά 5 άτομα, ένα παιδί παγιδευμένο.", "el")
    assert "holds the street" not in sent[2] and "5 άτομα" in sent[2]  # a count: it reaches the model


def test_a_street_recorded_with_its_town_is_not_asked_about(tmp_path, monkeypatch):
    # The test set: street "Σάμο, Θεμιστοκλέους 5", map suggestion "Θεμιστοκλέους", asked three times.
    s = _session("su18")
    s.report["location"].update({"street": "Σάμο, Θεμιστοκλέους 5", "spoken_address": "Σάμο, Βαθύ, οδός Θεμιστοκλέους 5"})
    _map_suggests(s, monkeypatch, tmp_path, suggestion="Θεμιστοκλέους")
    assert s.steps.suggested_street is None and "confirm_street" not in steps.remaining(s.report, s.steps)


def test_the_read_back_waits_for_the_map_only_while_people_are_still_to_ask():
    s = _session("su19")
    s.report["location"]["area"] = "Κερατσίνι"
    s.steps.map_pending = True
    assert steps.remaining(s.report, s.steps)[0] == "people"  # asked while the map looks the street up
    s.report["people"] = [{"count": 1, "trapped": True}]
    assert steps.remaining(s.report, s.steps)[0] == "location_readback"  # nothing else to ask: read back, the name after


def test_a_place_given_in_this_message_is_read_back_before_the_name():
    # The test set: area, street and number in one message, people already known: the next question was the name.
    s = core._Session(info=CallInfo(call_id="su20", channel="voice", phone="+30 690", lang_guess="el"), lang="el",
                      report=core.new_report("su20", "+30 690", "el", None))
    s.report.update({"hazard_type": "earthquake", "situation": "The ceiling fell.", "people": [{"count": 1, "trapped": True}]})
    s.steps.street_in_message = True
    note = steps.note(s.report, s.steps)
    after = note.split("After that:")[1]
    assert note.startswith("next (area)") and after.index("location read-back") < after.index("name")


def test_the_map_note_asks_nothing_when_the_street_already_holds_the_real_name(tmp_path, monkeypatch):
    s = _session("su21")
    s.report["location"].update({"street": "Σάμο, Θεμιστοκλέους 5", "spoken_address": "Σάμο, Βαθύ, οδός Θεμιστοκλέους 5"})
    _map_suggests(s, monkeypatch, tmp_path, suggestion="Θεμιστοκλέους")
    note = core._map_check_result(s)
    assert "Did you mean" not in note


def test_an_answer_about_something_else_drops_the_suggestion(tmp_path, monkeypatch):
    # Test set 2026-11-16: "Did you mean …?" was asked three times while the caller reported a person
    # under a fallen tree, and twice by text to "Bilmiyorum".
    for call_id, answer in [("su30", "Ένα δέντρο έπεσε πάνω σε έναν άνθρωπο, είναι παγιδευμένος."), ("su31", "Δεν ξέρω."),
                            ("su32", "Bilmiyorum.")]:
        s = _session(call_id)
        _map_suggests(s, monkeypatch, tmp_path)
        s.steps.asked = "confirm_street"
        told = core._answer_to_suggestion(s, answer)
        assert "do not ask about it again" in told and s.report["location"]["street"] == HEARD
        assert "confirm_street" not in steps.remaining(s.report, s.steps)
        assert s.report["location"]["map_suggestion"] == f"{REAL} 16"  # still there for the operator
        assert "do not ask about it again" in core._map_check_result(s)  # the map note asks nothing either
    # A question or one unclear word is not an answer: asked once more.
    for call_id, answer in [("su33", "Τι είπατε;"), ("su34", "Ορίστε.")]:
        s = _session(call_id)
        _map_suggests(s, monkeypatch, tmp_path)
        s.steps.asked = "confirm_street"
        assert core._answer_to_suggestion(s, answer) is None and s.steps.suggested_street == REAL
