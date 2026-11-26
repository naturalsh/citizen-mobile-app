"""English copies for the operators' dashboard: transcript lines and the summary. No API calls."""
import json
from types import SimpleNamespace

import pytest

import brain.core as core
from brain import CallInfo, end_call, start_call, turn


class FakeModels:
    """Answers every request with the next prepared JSON text."""

    def __init__(self, answers):
        self.answers = list(answers)

    def generate_content(self, **kw):
        return SimpleNamespace(text=json.dumps(self.answers.pop(0), ensure_ascii=False))


@pytest.fixture
def model(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "OUTPUT_DIR", tmp_path)

    def use(*answers):
        monkeypatch.setattr(core, "_client", SimpleNamespace(models=FakeModels(answers)))
        return tmp_path

    return use


def answer(**extra):
    base = {"action": "continue", "handoff_reason": "none", "advice_topic": "none", "reply": "Πού βρίσκεστε;",
            "expecting": "location", "report_updates": {}, "caller_en": "There was an earthquake.",
            "reply_en": "Where are you?"}
    return {**base, **extra}


def test_greeting_and_fixed_lines_get_their_english_text(model):
    model()
    r = start_call(CallInfo(call_id="t1", channel="voice", phone="+30 690", lang_guess="el"))
    line = core._sessions["t1"].transcript[0]
    assert line["text"] == r.reply_text and line["text_en"].startswith("You are")  # English greeting
    assert core._FIXED_EN[core.PHRASES["handoff"]["el"]] == core.PHRASES["handoff"]["en"]


def test_caller_and_agent_lines_get_the_models_english(model):
    model(answer(advice_topic="earthquake.trapped", reply="Πόσοι είστε;", reply_en="How many are you?"))
    start_call(CallInfo(call_id="t2", channel="voice", phone="+30 690", lang_guess="el"))
    turn("t2", "Σεισμός, είμαι εγκλωβισμένη!", "el")
    caller, agent = core._sessions["t2"].transcript[-2:]
    assert caller["text_en"] == "There was an earthquake."
    assert agent["text_en"].startswith(core.ADVICE["earthquake.trapped"]["en"][:30])  # advice first, in English
    assert agent["text_en"].endswith("How many are you?")


def test_english_calls_are_copied_and_old_answers_without_english_still_work(model):
    old = answer()
    del old["caller_en"], old["reply_en"]
    model(old)
    start_call(CallInfo(call_id="t3", channel="voice", phone="+44 7700", lang_guess="en"))
    turn("t3", "There was an earthquake", "en")
    caller, agent = core._sessions["t3"].transcript[-2:]
    assert caller["text_en"] == "There was an earthquake"
    assert agent["text_en"] is None  # the fake reply is Greek: Greek letters are never their own English copy


def test_a_turkish_line_labelled_english_is_kept_as_turkish(model):
    # Test call 2026-10-26: speech-to-text labelled Turkish as English, the line was saved as its own
    # English copy, and the dashboard had no "Show original (Türkçe)".
    model(answer())
    start_call(CallInfo(call_id="t5", channel="voice", phone="+30 690", lang_guess="tr"))
    turn("t5", "Evim yıkıldı.", "en")
    caller = core._sessions["t5"].transcript[-2]
    assert caller["lang"] == "tr" and core._sessions["t5"].report["caller_language"] == "tr"
    assert core._operator_lang(core._sessions["t5"]) == "Turkish"  # the summary in the language spoken


def test_summary_comes_in_both_languages_from_one_request(model):
    out = model(answer(), {"summary": "Σεισμός στο Βαθύ.", "summary_en": "Earthquake in Vathy."})
    start_call(CallInfo(call_id="t4", channel="voice", phone="+30 690", lang_guess="el"))
    turn("t4", "Σεισμός", "el")
    report = end_call("t4", "completed")
    assert (report["summary_for_operator"], report["summary_en"]) == ("Σεισμός στο Βαθύ.", "Earthquake in Vathy.")
    saved = json.loads((out / "transcripts" / "t4.json").read_text())
    assert all("text_en" in line for line in saved)


# --- replies that use a placeholder we never made (eval: "Με λένε . Είστε η;") ---

def test_a_reply_with_a_made_up_name_is_replaced_by_please_repeat(model):
    model(answer(reply="Με λένε <PERSON_1>. Είστε η <PERSON_2>;", expecting="name"))
    start_call(CallInfo(call_id="t5", channel="voice", phone="+30 690", lang_guess="el"))
    before = len(core._sessions["t5"].history)
    r = turn("t5", "Η μητέρα μου δεν μπορεί να κουνηθεί.", "el")
    assert r.reply_text == core.PHRASES["error_fallback"]["el"]
    assert len(core._sessions["t5"].history) == before  # the caller's repeat replaces this turn


def test_a_made_up_name_never_blanks_the_report(model):
    model(answer(report_updates={"caller_name": "<PERSON_7>", "situation": "Earthquake"}))
    start_call(CallInfo(call_id="t6", channel="voice", phone="+30 690", lang_guess="el"))
    r = turn("t6", "Σεισμός", "el")
    assert r.report["caller"]["name"] is None and r.report["situation"] == "Earthquake"


def test_a_streamed_reply_stops_at_a_made_up_placeholder():
    from brain.masking import Masker
    from brain.streaming import ReplyStream

    m = Masker()
    reader = ReplyStream(clean=m.unmask, prefix=lambda a, t: ("", False), broken=m.invented, fallback="Please repeat.")
    raw = '{"action": "continue", "handoff_reason": "none", "advice_topic": "none", "reply": "Με λένε <PERSON_1>. Είστε η;"}'
    pieces = [text for kind, text in reader.feed(raw) if kind == "text"]
    assert reader.broke and pieces[-1] == " Please repeat."
    assert "<" not in "".join(pieces) and "Είστε" not in "".join(pieces)  # nothing after the hole is said


def test_an_english_caller_hears_the_greek_street_in_latin_letters(model):
    # Demo call 2026-10-30: "Εντάξει, Orlov 12, Κουκάκι." The operators' English copy is untouched.
    model(answer(reply="Εντάξει, Ορλώφ 12, Κουκάκι. What is your name?", reply_en="Okay, Ορλώφ 12. What is your name?"))
    start_call(CallInfo(call_id="t9", channel="voice", phone="+30 690", lang_guess="en"))
    r = turn("t9", "It's on Orlov 12 in Koukaki.", "en")
    assert r.reply_text == "Okay, Orlof 12, Koukaki. What is your name?"
    assert core._sessions["t9"].transcript[-1]["text"] == r.reply_text


def test_one_greek_letter_does_not_switch_an_english_call(model):
    # Demo call 2026-10-30: speech-to-text wrote an English caller's "uh" as "η.", and the reply came in Greek.
    model(answer(reply="Is there any danger right now?", reply_en="Is there any danger right now?"),
          answer(reply="Where are you?", reply_en="Where are you?"))
    start_call(CallInfo(call_id="t10", channel="voice", phone="+30 690", lang_guess="en"))
    turn("t10", "η.", "en")
    assert core._sessions["t10"].lang == "en"
    turn("t10", "Είμαι στην Αθήνα.", "en")  # a real Greek sentence still switches
    assert core._sessions["t10"].lang == "el"
