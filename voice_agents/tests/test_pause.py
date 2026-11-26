"""Pause AI (brain/control.py): every channel hands callers to a human. No API calls."""
import pytest
from fastapi.testclient import TestClient

import brain.core as core
from brain import CallInfo, control, start_call, turn, turn_stream


@pytest.fixture
def no_model(tmp_path, monkeypatch):
    """Fail loudly if anything tries to call Gemini while paused."""
    monkeypatch.setattr(core, "OUTPUT_DIR", tmp_path)

    class NoModels:
        def __getattr__(self, name):
            raise AssertionError("Gemini was called while the AI is paused")

    monkeypatch.setattr(core, "_client", type("C", (), {"models": NoModels()})())


def test_pause_info_records_who_and_when():
    assert not control.is_paused()
    control.set_paused(True, "Maria")
    info = control.pause_info()
    assert info["by"] == "Maria" and info["at"]
    control.set_paused(False, "Maria")
    assert control.pause_info() is None


def test_new_call_while_paused_goes_straight_to_a_human(no_model):
    control.set_paused(True, "Maria")
    r = start_call(CallInfo(call_id="p1", channel="voice", phone="+30 690", lang_guess="el"))
    assert (r.action, r.handoff_reason) == ("handoff", "operator_paused")
    assert r.reply_text == core.PHRASES["handoff"]["el"]
    assert r.report["status"] == "handed_to_human"


def test_turn_and_stream_while_paused_never_call_the_model(no_model):
    start_call(CallInfo(call_id="p2", channel="voice", phone="+30 690", lang_guess="el"))  # before the pause
    control.set_paused(True, "Maria")
    assert turn("p2", "Σεισμός", "el").handoff_reason == "operator_paused"
    events = list(turn_stream("p2", "Βοήθεια", "el"))
    assert events[-1][1].handoff_reason == "operator_paused"


def test_end_call_while_paused_skips_the_model_summary(no_model):
    start_call(CallInfo(call_id="p3", channel="voice", phone="+30 690", lang_guess="el"))
    control.set_paused(True, "Maria")
    report = core.end_call("p3", "hung_up")
    assert report["summary_for_operator"] == report["situation"]  # English fallback, no model call


def test_whatsapp_and_failed_call_trigger_while_paused(no_model, monkeypatch):
    import channels.messaging as messaging
    import channels.trigger as trigger

    monkeypatch.setattr(messaging, "TWILIO_AUTH_TOKEN", None)  # a real token in .env would demand Twilio's signature
    control.set_paused(True, "Maria")
    client = TestClient(messaging.app)
    r = client.post("/whatsapp", data={"From": "whatsapp:+306900000099", "Body": "Σεισμός!"})
    assert core.PHRASES["handoff_text"]["el"] in r.text
    assert ("whatsapp", "+306900000099") not in messaging.conversations  # nothing left open

    monkeypatch.setattr(trigger, "TRIGGER_TOKEN", "secret")
    r = client.post("/112/call-failed", json={"phone": "+306900000098"}, headers={"X-Trigger-Token": "secret"})
    assert r.json() == {"sent": False, "skipped": "AI paused by an operator"}
