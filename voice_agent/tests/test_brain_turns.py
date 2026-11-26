"""turn() and turn_stream() against a stand-in model: backup model, time limits, streaming. No API calls."""
import json
import time

import pytest
from google.genai import types

import brain.core as core
from brain import CallInfo, hold_phrase, start_call, turn, turn_stream
from brain.streaming import decode_partial_string

ADDRESS = "Θεμιστοκλέους 5"


def answer(reply="Πόσα άτομα είστε;", action="continue", advice="none", **extra):
    return json.dumps({
        "action": action, "handoff_reason": extra.get("handoff_reason", "none"), "advice_topic": advice,
        "reply": reply, "expecting": "other",
        "report_updates": extra.get("report_updates", {"spoken_address": "<ADDRESS_1>, Vathy", "hazard_type": "earthquake"}),
    }, ensure_ascii=False)


class FakeModels:
    """Per model: ("ok", raw) | ("slow", seconds, raw) | ("error", exc) | ("cut", raw, chars_before_error)."""

    def __init__(self, plan: dict):
        self.plan = plan
        self.calls: list[str] = []

    def _get(self, model):
        self.calls.append(model)
        return self.plan[model]

    def generate_content(self, model, contents, config):
        kind, *rest = self._get(model)
        assert config.http_options.timeout >= 10_000  # Gemini refuses shorter deadlines
        if kind == "error":
            raise rest[0]
        if kind == "slow":
            time.sleep(rest[0])
            rest = rest[1:]
        return types.GenerateContentResponse(
            candidates=[types.Candidate(content=types.Content(role="model", parts=[types.Part(text=rest[0])]))]
        )

    def generate_content_stream(self, model, contents, config):
        kind, *rest = self._get(model)
        if kind == "error":
            raise rest[0]
        if kind == "slow":
            time.sleep(rest[0])
            rest = rest[1:]
        raw, stop = rest[0], (rest[1] if kind == "cut" else None)
        for i in range(0, len(raw) if stop is None else stop, 7):  # small chunks, splitting escapes and placeholders
            piece = raw[i:i + 7] if stop is None else raw[i:min(i + 7, stop)]
            yield types.GenerateContentResponse(
                candidates=[types.Candidate(content=types.Content(role="model", parts=[types.Part(text=piece)]))]
            )
        if stop is not None:
            raise ConnectionError("stream dropped")


@pytest.fixture
def fake(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAIN_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(core, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(core, "MODEL_TIMEOUT_S", 0.3)
    monkeypatch.setattr(core, "STREAM_STALL_S", 0.3)

    def install(plan):
        models = FakeModels(plan)
        monkeypatch.setattr(core, "_client", type("Client", (), {"models": models})())
        return models

    return install


def new_call(call_id="c1", lang="el"):
    start_call(CallInfo(call_id=call_id, channel="voice", phone="+30 690", lang_guess=lang))
    return call_id


def collect(events):
    events = list(events)
    kinds = [k for k, _ in events]
    text = "".join(v for k, v in events if k == "text")
    result = events[-1][1]
    return kinds, text, result, events


# --- turn() ---

def test_turn_uses_live_model_and_unmasks(fake):
    models = fake({core.LIVE_MODEL: ("ok", answer("Είστε στη <ADDRESS_1>;"))})
    r = turn(new_call(), f"Είμαι στη {ADDRESS}, Βαθύ", "el")
    assert r.reply_text == f"Είστε στη {ADDRESS};"
    assert r.report["location"]["spoken_address"] == f"{ADDRESS}, Vathy"
    assert models.calls == [core.LIVE_MODEL]


def test_turn_falls_back_to_backup_when_live_is_slow(fake):
    models = fake({core.LIVE_MODEL: ("slow", 5, answer("late")), core.BACKUP_MODEL: ("ok", answer("Από backup;"))})
    started = time.perf_counter()
    r = turn(new_call(), "Σεισμός", "el")
    assert r.reply_text == "Από backup;"
    assert models.calls == [core.LIVE_MODEL, core.BACKUP_MODEL]
    assert time.perf_counter() - started < 1.5  # did not wait for the slow model


def test_turn_falls_back_on_rate_limit(fake):
    models = fake({core.LIVE_MODEL: ("error", RuntimeError("429")), core.BACKUP_MODEL: ("ok", answer())})
    assert turn(new_call(), "Σεισμός", "el").reply_text == "Πόσα άτομα είστε;"
    assert models.calls == [core.LIVE_MODEL, core.BACKUP_MODEL]


def test_turn_gives_up_cleanly_when_nothing_answers(fake):
    fake({core.LIVE_MODEL: ("error", RuntimeError("down")), core.BACKUP_MODEL: ("error", RuntimeError("down"))})
    call_id = new_call()
    history_before = len(core._sessions[call_id].history)
    r = turn(call_id, "Σεισμός", "el")
    assert r.reply_text == core.PHRASES["error_fallback"]["el"]
    assert len(core._sessions[call_id].history) == history_before  # the repeat replaces this turn


# --- turn_stream() ---

def test_stream_says_advice_then_reply_and_matches_result(fake):
    raw = answer('Ακούτε τη <ADDRESS_1>; Πείτε μου "πόσοι"\\nείστε.', advice="earthquake.others_trapped")
    fake({core.LIVE_MODEL: ("ok", raw)})
    kinds, text, result, events = collect(turn_stream(new_call(), f"Η μητέρα μου είναι στα συντρίμμια, {ADDRESS}", "el"))
    assert kinds[0] == "start" and kinds[-1] == "result" and kinds.count("text") >= 3  # really streamed
    assert events[0][1] == {"action": "continue", "handoff_reason": None, "lang": "el"}
    advice = core.ADVICE["earthquake.others_trapped"]["el"]
    assert text.startswith(advice)
    assert ADDRESS in text and "<ADDRESS" not in text  # placeholder split across chunks, still unmasked
    assert " ".join(text.split()) == " ".join(result.reply_text.split())
    assert result.report["advice_given"] == ["earthquake.others_trapped"]


def test_stream_handoff_says_only_the_fixed_line(fake):
    fake({core.LIVE_MODEL: ("ok", answer("ignored", action="handoff", handoff_reason="caller_request"))})
    kinds, text, result, events = collect(turn_stream(new_call(), "Θέλω άνθρωπο", "el"))
    assert events[0][1]["action"] == "handoff" and events[0][1]["handoff_reason"] == "caller_request"
    assert text == core.PHRASES["handoff"]["el"] == result.reply_text
    assert result.action == "handoff"


def test_stream_slow_live_model_uses_backup(fake):
    models = fake({core.LIVE_MODEL: ("slow", 2, answer("late")), core.BACKUP_MODEL: ("ok", answer("Από backup;"))})
    started = time.perf_counter()
    kinds, text, result, _ = collect(turn_stream(new_call(), "Σεισμός", "el"))
    assert kinds == ["start", "text", "result"]
    assert text == result.reply_text == "Από backup;"
    assert core.BACKUP_MODEL in models.calls
    assert time.perf_counter() - started < 1.5


def test_stream_cut_off_keeps_what_was_said(fake):
    # Replies are spoken a sentence at a time, so the first sentence was out before the cut.
    raw = answer("Κατάλαβα. Μείνετε κοντά τους και περιγράψτε μου το κτίριο.")
    fake({core.LIVE_MODEL: ("cut", raw, raw.index("περιγράψτε"))})
    call_id = new_call()
    kinds, text, result, _ = collect(turn_stream(call_id, "Σεισμός", "el"))
    assert text.strip() and result.reply_text.startswith(text.strip()[:10])
    assert result.report["hazard_type"] is None  # the cut-off answer's report updates are not applied
    assert core._sessions[call_id].history[-1].role == "model"  # history stays consistent for the next turn


def test_stream_unsupported_language_hands_off_at_once(fake):
    models = fake({})
    kinds, text, result, _ = collect(turn_stream(new_call(), "Hallo", "de"))
    assert result.action == "handoff" and result.handoff_reason == "unsupported_language"
    assert models.calls == []


def test_hold_phrase_in_callers_language(fake):
    fake({})
    assert hold_phrase(new_call("c2", "tr")) == core.PHRASES["hold"]["tr"]


# --- the partial JSON reader ---

@pytest.mark.parametrize("raw, text, closed", [
    ('abc', "abc", False),
    ('a\\"b" , "x"', 'a"b', True),
    ('line\\nnext', "line\nnext", False),
    ('cut\\', "cut", False),
    ('\\u03b1\\u03b2', "αβ", False),
    ('\\u03b', "", False),
])
def test_decode_partial_string(raw, text, closed):
    assert decode_partial_string(raw) == (text, closed)


# --- the Gemini request limit (brain/budget.py) ---

def test_turn_over_the_limit_hands_off_without_calling_the_model(fake, monkeypatch):
    from brain import budget

    monkeypatch.setattr(budget, "MAX_PER_HOUR", 1)
    models = fake({core.LIVE_MODEL: ("ok", answer())})
    call_id = new_call()
    assert turn(call_id, "Σεισμός", "el").action == "continue"  # uses the one allowed request
    r = turn(call_id, "Είμαστε τρεις", "el")
    assert (r.action, r.handoff_reason) == ("handoff", "budget_limit")
    assert r.reply_text == core.PHRASES["handoff"]["el"]
    assert r.report["status"] == "handed_to_human"
    assert models.calls == [core.LIVE_MODEL]  # the second turn never reached the model


def test_stream_over_the_limit_hands_off(fake, monkeypatch):
    from brain import budget

    monkeypatch.setattr(budget, "MAX_PER_HOUR", 0)
    models = fake({core.LIVE_MODEL: ("ok", answer())})
    kinds, text, result, _ = collect(turn_stream(new_call(), "Σεισμός", "el"))
    assert kinds == ["start", "text", "result"]
    assert (result.action, result.handoff_reason) == ("handoff", "budget_limit")
    assert models.calls == []
