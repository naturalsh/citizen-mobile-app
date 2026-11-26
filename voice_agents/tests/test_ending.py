"""A call ends only on a clear yes (a test call ended on the caller's name correction). No API calls."""
import json
from types import SimpleNamespace

import pytest

import brain.core as core
from brain import CallInfo, start_call, turn


@pytest.mark.parametrize("text, yes", [
    ("Ναι, σωστά.", True), ("Σωστό είναι.", True), ("Εντάξει.", True), ("Yes, that's right.", True),
    ("Evet, doğru.", True), ("Oui.", True),
    ("Αιγέας Πολιτόπουλος.", False), ("Όχι.", False), ("Ναι, αλλά το όνομά μου είναι Αιγέας", False),
    ("No, there is also a building where I hear people", False), ("", False),
])
def test_clear_yes(text, yes):
    assert core.clear_yes(text) is yes


def run(tmp_path, monkeypatch, caller_lines, urgency="urgent"):
    monkeypatch.setattr(core, "OUTPUT_DIR", tmp_path)
    answer = {"action": "end", "handoff_reason": "none", "advice_topic": "none", "reply": "Η αναφορά σας διαβιβάστηκε.",
              "expecting": "other", "caller_en": "x", "reply_en": "Your report was passed on.",
              "report_updates": {"urgency_suggested": urgency, "urgency_reasons": ["test"]}}
    models = SimpleNamespace(generate_content=lambda **kw: SimpleNamespace(text=json.dumps(answer)))
    monkeypatch.setattr(core, "_client", SimpleNamespace(models=models))
    start_call(CallInfo(call_id="e1", channel="voice", phone="+30 690", lang_guess="el"))
    return [turn("e1", line, "el") for line in caller_lines]


def test_a_correction_never_ends_the_call(tmp_path, monkeypatch):
    r = run(tmp_path, monkeypatch, ["Αιγέας Πολιτόπουλος."])[0]
    assert (r.action, r.reply_text) == ("continue", core.PHRASES["confirm_again"]["el"])


def test_a_clear_yes_ends_it(tmp_path, monkeypatch):
    assert run(tmp_path, monkeypatch, ["Ναι, σωστά."])[0].action == "end"


def test_never_a_loop_and_info_calls_end_without_a_yes(tmp_path, monkeypatch):
    results = run(tmp_path, monkeypatch, ["Αιγέας.", "Μμ.", "Τίποτα."])
    assert [r.action for r in results] == ["continue", "continue", "end"]  # held twice at most
    core._sessions.clear()
    assert run(tmp_path, monkeypatch, ["Τίποτα, λάθος κλήση."], urgency="information")[0].action == "end"


def test_streamed_calls_never_speak_the_goodbye_first(tmp_path, monkeypatch):
    run(tmp_path, monkeypatch, [])
    core._log_line(core._sessions["e1"], "caller", "Αιγέας Πολιτόπουλος.")
    core._sessions["e1"].report["urgency"]["suggested"] = "urgent"
    assert core._prefix(core._sessions["e1"], "end", None) == (core.PHRASES["confirm_again"]["el"], True)
