"""CallFlow against a fake brain: no LiveKit, no API keys."""
import asyncio
import threading

from brain.contract import CallInfo, TurnResult
from voice.call import CallFlow, in_thread


class FakeBrain:
    def __init__(self, actions=("continue",), lang=None):
        self.actions = list(actions)
        self.lang = lang
        self.calls = []

    def start_call(self, info: CallInfo) -> TurnResult:
        self.calls.append(("start", info))
        return TurnResult("hello", info.lang_guess, "continue", None, {})

    def turn(self, call_id, text, lang, interrupted=False) -> TurnResult:
        self.calls.append(("turn", call_id, text, lang, interrupted))
        action = self.actions.pop(0) if self.actions else "continue"
        reason = "caller_request" if action == "handoff" else None
        return TurnResult("ok", self.lang or lang, action, reason, {})

    def end_call(self, call_id, reason):
        self.calls.append(("end", call_id, reason))
        return {"status": reason}


def test_first_language_from_country_code():
    assert CallFlow("+30 690 000 0000", brain_api=FakeBrain()).lang == "el"
    assert CallFlow("+90 532 000 0000", brain_api=FakeBrain()).lang == "tr"
    assert CallFlow("+44 7700 900000", brain_api=FakeBrain()).lang == "en"


def test_start_sends_voice_call_info():
    fake = FakeBrain()
    flow = CallFlow("+90 532 000 0000", call_id="vo-1", brain_api=fake)
    flow.start()
    info = fake.calls[0][1]
    assert (info.call_id, info.channel, info.phone, info.lang_guess) == ("vo-1", "voice", "+90 532 000 0000", "tr")


def test_reply_passes_language_and_interruption():
    fake = FakeBrain()
    flow = CallFlow("+30 690 000 0000", call_id="vo-1", brain_api=fake)
    flow.reply("Σεισμός", interrupted=True)
    assert fake.calls[-1] == ("turn", "vo-1", "Σεισμός", "el", True)


def test_reply_passes_the_spoken_language():
    fake = FakeBrain()
    flow = CallFlow("+30 690 000 0000", call_id="vo-1", brain_api=fake)
    flow.reply("Merhaba, bina çöktü", lang="tr")
    assert fake.calls[-1] == ("turn", "vo-1", "Merhaba, bina çöktü", "tr", False)
    assert flow.lang == "tr"


def test_language_follows_the_brain():
    flow = CallFlow("+30 690 000 0000", brain_api=FakeBrain(lang="tr"))
    flow.reply("Merhaba")
    assert flow.lang == "tr"


def test_end_reason_prefers_the_brains_decision():
    flow = CallFlow("+30", brain_api=FakeBrain(actions=["end"]))
    assert flow.end_reason(caller_left=False) == "dropped"
    assert flow.end_reason(caller_left=True) == "hung_up"
    flow.reply("ναι, σωστά")
    assert flow.end_reason(caller_left=True) == "completed"

    handoff = CallFlow("+30", brain_api=FakeBrain(actions=["handoff"]))
    handoff.reply("θέλω άνθρωπο")
    assert handoff.end_reason(caller_left=True) == "handed_off"


def test_finish_runs_once():
    fake = FakeBrain()
    flow = CallFlow("+30", call_id="vo-1", brain_api=fake)
    assert flow.finish("hung_up") == {"status": "hung_up"}
    assert flow.finish("dropped") is None
    assert [c for c in fake.calls if c[0] == "end"] == [("end", "vo-1", "hung_up")]


def test_finish_survives_brain_errors():
    class Broken(FakeBrain):
        def end_call(self, call_id, reason):
            raise RuntimeError("summary timed out")

    assert CallFlow("+30", brain_api=Broken()).finish("completed") is None


# --- streamed replies and the hold line (issues #2 and #4) ---


class StreamingBrain(FakeBrain):
    def turn_stream(self, call_id, text, lang, interrupted=False):
        result = self.turn(call_id, text, lang, interrupted)
        yield "start", {"action": result.action, "handoff_reason": result.handoff_reason, "lang": result.lang}
        yield "text", "o"
        yield "text", "k"
        yield "result", result

    def hold_phrase(self, call_id):
        return f"hold {call_id}"


def test_reply_stream_passes_events_and_tracks_the_outcome():
    flow = CallFlow("+30 690", call_id="vo-1", brain_api=StreamingBrain(actions=["handoff"]))
    events = list(flow.reply_stream("θέλω άνθρωπο", lang="el"))
    assert [k for k, _ in events] == ["start", "text", "text", "result"]
    assert events[0][1]["action"] == "handoff"
    assert "".join(v for k, v in events if k == "text") == "ok"
    assert flow.outcome == "handed_off"


def test_hold_line_comes_from_the_brain():
    assert CallFlow("+30 690", call_id="vo-9", brain_api=StreamingBrain()).hold_line() == "hold vo-9"


def test_in_thread_hands_items_to_async_code():
    async def read():
        return [item async for item in in_thread(lambda: iter([1, 2, 3]))]

    assert asyncio.run(read()) == [1, 2, 3]


def test_in_thread_finishes_the_generator_even_if_reading_stops():
    finished = threading.Event()

    def turn():
        yield "start"
        yield "text"
        finished.set()  # the brain records the turn only at the end

    async def read_first_only():
        events = in_thread(turn)
        first = await anext(events)
        await asyncio.to_thread(finished.wait, 2)
        return first

    assert asyncio.run(read_first_only()) == "start"
    assert finished.is_set()


def test_in_thread_raises_errors_from_the_thread():
    def broken():
        yield 1
        raise ValueError("brain failed")

    async def read():
        return [item async for item in in_thread(broken)]

    try:
        asyncio.run(read())
    except ValueError as exc:
        assert str(exc) == "brain failed"
    else:
        raise AssertionError("expected the error")


def test_a_link_language_beats_the_test_phone_number():
    from voice.call import CallFlow
    assert CallFlow("+30 690 000 0000").lang == "el"
    assert CallFlow("+30 690 000 0000", lang="tr").lang == "tr"


def test_street_hints_come_from_the_brain_when_it_has_them():
    class WithStreets(FakeBrain):
        def street_hints(self, call_id):
            return ["Βασιλίσσης Φρειδερίκης"]

    assert CallFlow("+30 690 000 0000", brain_api=WithStreets()).street_hints() == ["Βασιλίσσης Φρειδερίκης"]
    assert CallFlow("+30 690 000 0000", brain_api=FakeBrain()).street_hints() == []
