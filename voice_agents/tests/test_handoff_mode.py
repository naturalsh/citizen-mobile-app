"""Surge mode (brain/control.py) and why a call was handed off. No API calls."""
import json

import brain.core as core
from brain import CallInfo, control, start_call
from brain.prompts import system_prompt


def test_surge_is_the_default_and_the_switch_records_who(monkeypatch):
    monkeypatch.setattr(control, "DEFAULT_HANDOFF_MODE", "surge")
    assert control.handoff_info() == {"mode": "surge", "by": None, "at": None}
    info = control.set_handoff_mode("normal", "Maria")
    assert control.handoff_mode() == "normal" and info["by"] == "Maria" and info["at"]


def test_bad_mode_is_refused_and_a_damaged_file_hands_off_more_readily(tmp_path):
    try:
        control.set_handoff_mode("relaxed", "Maria")
        raise AssertionError("an unknown mode was accepted")
    except ValueError:
        pass
    path = control._mode_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json")
    assert control.handoff_mode() == "normal"
    path.write_text(json.dumps({"mode": "party"}))
    assert control.handoff_mode() == "normal"


def test_each_mode_has_its_own_handoff_rules():
    surge, normal = system_prompt("surge"), system_prompt("normal")
    assert "SURGE" in surge and "SURGE" not in normal
    assert "animal stuck" in surge and "animal rescue" in normal  # deferred in a surge, a person otherwise
    assert "not_breathing" in surge and "not_breathing" in normal  # always a person at once
    assert system_prompt("unknown") == normal


def test_the_report_keeps_why_a_person_took_over(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "OUTPUT_DIR", tmp_path)
    control.set_paused(True, "Maria")
    r = start_call(CallInfo(call_id="h1", channel="voice", phone="+30 690", lang_guess="el"))
    assert r.report["handoff_reason"] == "operator_paused"
    saved = json.loads((tmp_path / "reports" / "h1.json").read_text())
    assert saved["handoff_reason"] == "operator_paused"


def test_a_supported_language_is_never_handed_off_as_unsupported(tmp_path, monkeypatch):
    # Test call 2026-10-26: a Turkish caller mixing in English was handed to a person by the model.
    from types import SimpleNamespace
    from brain import turn
    monkeypatch.setattr(core, "OUTPUT_DIR", tmp_path)

    class Models:
        def generate_content(self, **kw):
            return SimpleNamespace(text=json.dumps({
                "action": "handoff", "handoff_reason": "unsupported_language", "advice_topic": "none",
                "reply": "Where are you?", "expecting": "location", "caller_en": "x", "reply_en": "Where are you?",
                "report_updates": {}}))

    monkeypatch.setattr(core, "_client", SimpleNamespace(models=Models()))
    start_call(CallInfo(call_id="h2", channel="voice", phone="+30 690", lang_guess="el"))
    result = turn("h2", "This is speaking Greek. Merhaba, nasılsın?", "en")
    assert result.action == "continue" and result.reply_text == "Where are you?"
    assert turn("h2", "Hallo, wo bin ich hier?", "de").action == "handoff"  # really unsupported: a person


def test_turkish_letters_keep_the_call_in_turkish_whatever_the_label(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from brain import turn
    monkeypatch.setattr(core, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(core, "_client", SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kw: SimpleNamespace(
        text=json.dumps({"action": "continue", "handoff_reason": "none", "advice_topic": "none", "reply": "Ne oldu?",
                         "expecting": "what_happened", "caller_en": "x", "reply_en": "x", "report_updates": {}})))))
    start_call(CallInfo(call_id="h3", channel="voice", phone="+30 690", lang_guess="tr"))
    assert turn("h3", "Evim yıkıldı.", "en").lang == "tr"


def test_the_agent_never_promises_that_help_is_coming(tmp_path, monkeypatch):
    # Test call 2026-10-26: "Biliyorum, yardım yolda." (I know, help is on the way): nobody had been sent.
    monkeypatch.setattr(core, "OUTPUT_DIR", tmp_path)  # never the real output/: it showed on the dashboard
    start_call(CallInfo(call_id="h4", channel="voice", phone="+30 690", lang_guess="tr"))
    s = core._sessions["h4"]
    said = core._no_promises(s, "Biliyorum, yardım yolda. Hangi mahalledesiniz?")
    assert "yolda" not in said and said == "Bildiriminiz hemen operatörlere iletiliyor. Hangi mahalledesiniz?"
    assert "geliyor" not in core._no_promises(s, "Ekipler size doğru geliyor, lütfen bekleyin.")
    assert "on the way" not in core._no_promises(s, "Help is on the way. Where are you?")
    assert core._no_promises(s, "Hangi mahalledesiniz?") == "Hangi mahalledesiniz?"  # nothing to remove
