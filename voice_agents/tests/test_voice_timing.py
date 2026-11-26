"""Reply-time bookkeeping, no API calls."""
from voice.timing import ReplyTimes


def test_greeting_is_not_timed():
    t = ReplyTimes()
    assert t.agent_started(10.0) is None
    assert t.silence == []


def test_silence_from_caller_stop_to_agent_audio():
    t = ReplyTimes()
    t.caller_stopped(10.0)
    assert t.agent_started(11.5) == 1.5
    assert t.agent_started(20.0) is None  # each stop is counted once


def test_latest_stop_counts_when_the_caller_pauses_and_goes_on():
    t = ReplyTimes()
    t.caller_stopped(10.0)
    t.caller_stopped(12.0)
    assert t.agent_started(13.0) == 1.0


def test_summary():
    t = ReplyTimes()
    for stop, start in ((0, 1.0), (10, 12.0), (20, 23.0)):
        t.caller_stopped(stop)
        t.agent_started(start)
    for s in (0.8, 1.5, 2.5):
        t.brain_took(s)
    assert t.summary() == "3 replies: silence median 2.00 s, p90 2.80 s; brain median 1.50 s, p90 2.30 s"
    assert ReplyTimes().summary() == "no replies timed"


def test_how_long_end_of_turn_detection_waited():
    # A test call waited 2.8 s per reply; this shows how much of it was the turn-end wait.
    t = ReplyTimes()
    assert t.turn_ended(5.0) is None  # nothing said yet
    t.caller_stopped(10.0)
    assert t.turn_ended(11.25) == 1.25
    assert t.agent_started(12.5) == 2.5  # the silence still counts from the stop
    assert "turn end median 1.25 s" in t.summary()
