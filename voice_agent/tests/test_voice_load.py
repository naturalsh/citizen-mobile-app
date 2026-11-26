"""When the agent takes no new calls (voice/load.py), no LiveKit."""
from collections import namedtuple

from voice import load

Times = namedtuple("Times", "user system idle")


def test_a_busy_computer_still_takes_calls():
    # 2026-10-30: the agent marked itself full at 73% CPU with no call running.
    assert load.worker_load(active_calls=0, cpu=0.85, max_calls=3, cpu_limit=0.95) < load.THRESHOLD
    assert load.worker_load(active_calls=2, cpu=0.85, max_calls=3, cpu_limit=0.95) < load.THRESHOLD


def test_full_at_the_call_limit_or_a_saturated_cpu():
    assert load.worker_load(active_calls=3, cpu=0.1, max_calls=3, cpu_limit=0.95) > load.THRESHOLD
    assert load.worker_load(active_calls=0, cpu=0.97, max_calls=3, cpu_limit=0.95) > load.THRESHOLD


def test_cpu_is_measured_over_seconds_not_between_two_quick_asks(monkeypatch):
    # Demo take 2026-10-30: LiveKit asked milliseconds apart, the readings over such spans were 100%,
    # and the agent was "full" for 30 s at 27% CPU. Over 5 s of time the share is what it really is.
    monkeypatch.setattr(load, "_samples", load.deque(maxlen=200))
    busy = idle = 0.0
    for step in range(40):  # 10 s at 0.25 s steps, 30% busy
        busy, idle = busy + 0.3, idle + 0.7
        share = load.cpu_share(now=step * 0.25, times=Times(busy, 0.0, idle))
    assert abs(share - 0.3) < 0.01
    # Many asks within a few milliseconds, all busy: still about 30% over the window, not 100%.
    for n in range(20):
        busy += 0.001
        share = load.cpu_share(now=39 * 0.25 + n * 0.001, times=Times(busy, 0.0, idle))
    assert share < 0.4


def test_too_little_history_says_nothing(monkeypatch):
    monkeypatch.setattr(load, "_samples", load.deque(maxlen=200))
    assert load.cpu_share(now=0.0, times=Times(1.0, 0.0, 0.0)) == 0.0
    assert load.cpu_share(now=0.5, times=Times(1.5, 0.0, 0.0)) == 0.0  # half a second: too short


def test_current_reads_the_running_calls_and_says_why_it_is_full(monkeypatch, caplog):
    class Server:
        active_jobs = ["call-1", "call-2", "call-3"]
    monkeypatch.setattr(load.config, "MAX_CALLS", 3)
    monkeypatch.setattr(load, "cpu_share", lambda: 0.27)
    monkeypatch.setattr(load, "_was_full", False)
    with caplog.at_level("WARNING", logger="voice.load"):
        assert load.current(Server()) > load.THRESHOLD
        Server.active_jobs = []
        assert load.current(Server()) < load.THRESHOLD
    assert [r.getMessage() for r in caplog.records] == [
        "not taking new calls: 3 calls running, CPU 27% over 5 s", "taking new calls: 0 calls running, CPU 27% over 5 s"]
