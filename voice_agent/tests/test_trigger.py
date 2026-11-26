"""Failed-112-call trigger (channels/trigger.py): the first message, no Twilio and no model."""
import pytest
from fastapi.testclient import TestClient

import brain.core as core
import channels.messaging as messaging
import channels.trigger as trigger
from brain import control


@pytest.fixture
def sent(tmp_path, monkeypatch):
    """The messages the trigger would send, instead of sending them."""
    monkeypatch.setattr(core, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(trigger, "TRIGGER_TOKEN", "secret")
    monkeypatch.setattr(trigger, "_last_sent", {})
    control.set_paused(False, "test")
    out = []
    monkeypatch.setattr(trigger, "_send", lambda channel, phone, body: out.append((channel, phone, body)) or "SM1")
    yield out
    for key in [k for k in messaging.conversations if k[1].startswith("+3069000001")]:
        del messaging.conversations[key]


def _fire(**body):
    return TestClient(messaging.app).post("/112/call-failed", json=body, headers={"X-Trigger-Token": "secret"})


def test_the_first_message_is_in_the_country_codes_language(sent):
    r = _fire(phone="+306900000101", channel="whatsapp")
    assert r.json()["lang"] == "el" and sent[0][2] == r.json()["message"]
    assert any(ch in sent[0][2] for ch in "αεηιουω")  # Greek


def test_a_known_language_beats_the_country_code(sent):
    # Demo 2026-10-31: a Greek SIM, an English-speaking audience.
    r = _fire(phone="+306900000102", channel="whatsapp", lang="en")
    assert r.json()["lang"] == "en" and "112" in sent[0][2]
    assert not any(ch in sent[0][2] for ch in "αεηιουω")  # no Greek letters
    assert messaging.conversations[("whatsapp", "+306900000102")].lang == "en"  # the replies go on in English


def test_an_unknown_language_is_refused(sent):
    assert _fire(phone="+306900000103", lang="de").status_code == 422 and sent == []
