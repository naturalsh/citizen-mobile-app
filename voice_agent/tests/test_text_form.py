"""By text, one list of what is missing instead of one question per message (brain/steps.py
form_items, brain/core.py _add_form). A fake model, no API calls."""
import json
from types import SimpleNamespace

import brain.core as core
from brain import CallInfo, start_call, turn


def fake_model(monkeypatch, tmp_path, updates):
    monkeypatch.setattr(core, "OUTPUT_DIR", tmp_path)
    sent = []

    class Models:
        def generate_content(self, **kw):
            sent.append(kw["contents"][-1].parts[0].text)
            return SimpleNamespace(text=json.dumps({
                "action": "continue", "handoff_reason": "none", "advice_topic": "none", "reply": "Ευχαριστώ.",
                "expecting": "other", "caller_en": "x", "reply_en": "Thank you.", "report_updates": updates.pop(0)}))

    monkeypatch.setattr(core, "_client", SimpleNamespace(models=Models()))
    return sent


def test_a_whatsapp_report_takes_two_lists_then_the_read_back(tmp_path, monkeypatch):
    sent = fake_model(monkeypatch, tmp_path, [
        {"hazard_type": "building_fire", "situation": "Smoke from the kitchen."},
        {"area": "Koukaki, Athens", "street": "Ορλώφ", "spoken_address": "Ορλώφ 12, Κουκάκι",
         "people": [{"count": 2, "injured": 0}], "caller_name": "<PERSON_1>"},
        {"floor": "3"},
    ])
    start_call(CallInfo(call_id="t1", channel="whatsapp", phone="+30 690", lang_guess="el"))
    first = turn("t1", "Βγαίνει καπνός από την κουζίνα!", "el")
    assert first.reply_text.startswith("Ευχαριστώ.\n\nΑπαντήστε σε ΕΝΑ μήνυμα με:\n1. Πού:")
    assert "Το ονοματεπώνυμό σας" in first.reply_text and "Τι συνέβη" not in first.reply_text  # already said

    second = turn("t1", "1. Ορλώφ 12, Κουκάκι\n2. Δύο, κανείς τραυματίας\n3. Νίκος Δοκιμάκης", "el")
    assert "<PERSON_1>" in sent[1] and "Νίκος" not in sent[1] and "Ορλώφ" not in sent[1]  # masked as a list
    assert "Κουκάκι" in sent[1]  # a real neighbourhood stays visible
    assert second.reply_text.startswith("Ευχαριστώ.\n\nΕυχαριστώ. Λείπουν ακόμα")
    assert "όροφος" in second.reply_text and "Πού:" not in second.reply_text  # only what is still missing

    third = turn("t1", "Τρίτος, βγαίνουμε όλοι.", "el")
    assert "Λείπουν" not in third.reply_text  # two lists at most
    assert "reply YES" in sent[2] or "next (final_readback)" in sent[2]


def test_an_sms_list_is_one_line(tmp_path, monkeypatch):
    fake_model(monkeypatch, tmp_path, [{}])
    start_call(CallInfo(call_id="t2", channel="sms", phone="+30 690", lang_guess="el"))
    reply = turn("t2", "Βοήθεια", "el").reply_text
    assert "\n" not in reply and "1) Τι συνέβη." in reply and "2) Πού:" in reply


def test_a_missed_112_call_text_starts_with_the_list(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "OUTPUT_DIR", tmp_path)
    greeting = start_call(CallInfo(call_id="t3", channel="whatsapp", phone="+30 690", lang_guess="el",
                                   trigger={"type": "failed_112_call"})).reply_text
    assert "δεν ολοκληρώθηκε" in greeting and "1. Τι συνέβη\n2. Πού:" in greeting


def test_a_voice_call_gets_no_list(tmp_path, monkeypatch):
    fake_model(monkeypatch, tmp_path, [{}])
    start_call(CallInfo(call_id="t4", channel="voice", phone="+30 690", lang_guess="el"))
    assert "ΕΝΑ μήνυμα" not in turn("t4", "Βοήθεια", "el").reply_text


def test_the_name_in_a_list_answer_is_recorded_by_code(tmp_path, monkeypatch):
    # Eval 2026-10-26: the model saw <PERSON_1> in the list answer and left caller_name empty.
    fake_model(monkeypatch, tmp_path, [{"hazard_type": "building_fire", "situation": "Smoke."}, {}])
    start_call(CallInfo(call_id="t5", channel="whatsapp", phone="+30 690", lang_guess="el"))
    turn("t5", "Καίγεται το διπλανό διαμέρισμα!", "el")
    turn("t5", "Ορλώφ 12, Κουκάκι, Αθήνα\nΕίμαστε τρεις\nΜαρία Δοκιμάκη", "el")
    assert core._sessions["t5"].report["caller"]["name"] == "Μαρία Δοκιμάκη"


def test_a_texted_address_without_area_gets_the_town_and_is_masked(tmp_path, monkeypatch):
    # WhatsApp test 2026-10-27: "fragiadon 16 Piraeus", area left empty, so the map found nothing;
    # the lower-case street and "John Doe name" also reached the model.
    sent = fake_model(monkeypatch, tmp_path, [{"hazard_type": "earthquake", "situation": "Building collapsed.",
                                               "spoken_address": "<ADDRESS_2> <ADDRESS_1>"}])
    start_call(CallInfo(call_id="t6", channel="whatsapp", phone="+30 690", lang_guess="en"))
    core._sessions["t6"].steps.form_asked = ["what_happened", "where", "name"]
    turn("t6", "My building got demolished, in fragiadon 16 Piraeus, 2 people injured. John Doe name", "en")
    assert "fragiadon" not in sent[0] and "John" not in sent[0]
    location = core._sessions["t6"].report["location"]
    assert location["area"] == "Piraeus" and location["street"] == "fragiadon"


def test_the_area_comes_from_the_places_in_the_address():
    s = core._Session(info=CallInfo(call_id="t7", channel="whatsapp", phone="+30", lang_guess="el"), lang="el",
                      report=core.new_report("t7", "+30", "el", None))
    for spoken, area in [("Ορλώφ 12, Κουκάκι, Αθήνα", "Κουκάκι, Αθήνα"), ("Piraeus, fragiadon 16", "Piraeus"),
                         ("Gazi Caddesi No 18, Bayraklı, İzmir", "Bayraklı, İzmir"), ("near the port", None),
                         ("Σάμο, Βαθύ, Θεμιστοκλέους 5", "Σάμο, Βαθύ"), ("Βόλο, Ιάσονος 3", "Βόλο")]:
        s.report["location"].update({"area": None, "spoken_address": spoken})
        core._area_from_address(s)
        assert s.report["location"]["area"] == area, spoken


def test_the_whatsapp_demo_chat_is_not_asked_again_for_name_or_floor(tmp_path, monkeypatch):
    # WhatsApp test 2026-10-31: the answer to the list had "5th floor" and "Name is John Doe", but the
    # model saw the name (no cue matched "Name is"), wrote "Please tell me your exact address and
    # details.", and the reminder asked for the floor and the name again.
    monkeypatch.setattr(core, "OUTPUT_DIR", tmp_path)
    sent, replies = [], ["I understand, there is a fire in your building.",
                         "I'm here with you. Please tell me your exact address and details."]
    updates = [{"hazard_type": "building_fire", "situation": "Fire in the building."},
               {"area": "Piraeus", "street": "<ADDRESS_1>", "spoken_address": "Piraeus <ADDRESS_1>",
                "people": [{"count": 5}]}]  # whether anyone is hurt not recorded: the reminder asks only that

    class Models:
        def generate_content(self, **kw):
            sent.append(kw["contents"][-1].parts[0].text)
            return SimpleNamespace(text=json.dumps({
                "action": "continue", "handoff_reason": "none", "advice_topic": "none", "reply": replies.pop(0),
                "expecting": "other", "caller_en": "x", "reply_en": "x", "report_updates": updates.pop(0)}))

    monkeypatch.setattr(core, "_client", SimpleNamespace(models=Models()))
    start_call(CallInfo(call_id="t9", channel="whatsapp", phone="+30 690", lang_guess="en"))
    first = turn("t9", "Help there is a fire in my building", "en")
    assert "Which floor" in first.reply_text and "Your full name" in first.reply_text
    second = turn("t9", "I am in Piraeus Fragiadon 16 near pasalimani. There are 5 people in the house and one has "
                        "a broken foot. I am in the 5th floor. Name is John Doe", "en")
    assert "John" not in sent[1] and "<PERSON_1>" in sent[1]  # the model never sees the name
    assert core._sessions["t9"].report["caller"]["name"] == "John Doe"  # recorded by the code
    reminder = second.reply_text.split("Still missing")[1]
    assert "floor" not in reminder.lower() and "name" not in reminder.lower() and "injured" in reminder
    assert "tell me" not in second.reply_text and second.reply_text.startswith("I'm here with you.")


def test_a_street_the_model_left_out_is_taken_from_the_message():
    # Test set 2026-11-15: "İzmir Buca, Şirinyer, Gazi Caddesi No 18. …" by text was recorded as its area
    # only, and the next list asked for the street name. The street with a number in the message is it.
    s = core._Session(info=CallInfo(call_id="t9", channel="whatsapp", phone="+90", lang_guess="tr"), lang="tr",
                      report=core.new_report("t9", "+90", "tr", None))
    s.report["location"].update({"area": "Şirinyer, İzmir", "spoken_address": "Şirinyer, İzmir"})
    s.turn_streets = ["Gazi Caddesi No 18"]
    core._street_from_address(s)
    assert s.report["location"]["street"] == "Gazi Caddesi"
    assert s.report["location"]["spoken_address"] == "Gazi Caddesi No 18, Şirinyer, İzmir"
    # not when the model put it somewhere else, and not a town with a number
    for location, streets in [({"cross_street": "Gazi Caddesi No 18"}, ["Gazi Caddesi No 18"]), ({}, ["Buca 3"])]:
        s.report["location"].update({"street": None, "cross_street": None, "spoken_address": "Şirinyer", **location})
        s.turn_streets = streets
        core._street_from_address(s)
        assert s.report["location"]["street"] is None and s.report["location"]["spoken_address"] == "Şirinyer"
