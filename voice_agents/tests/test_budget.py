"""The Gemini request limit (brain/budget.py). No API calls."""
import time

import pytest

from brain import budget


@pytest.fixture
def limits(monkeypatch):
    def set_limits(per_hour, per_day=1000):
        monkeypatch.setattr(budget, "MAX_PER_HOUR", per_hour)
        monkeypatch.setattr(budget, "MAX_PER_DAY", per_day)

    return set_limits


@pytest.fixture
def announced(monkeypatch):
    seen = []
    monkeypatch.setattr(budget, "_notify", lambda title, message, sound: seen.append(title))
    monkeypatch.setattr(budget, "NOTIFY", True)
    return seen


def test_counts_requests_under_the_limit(limits):
    limits(5)
    for _ in range(3):
        budget.spend("turn")
    s = budget.status()
    assert (s["hour"], s["day"], s["limit_on"]) == (3, 3, False)


def test_limit_raises_announces_once_and_writes_the_flag_file(limits, announced):
    limits(2)
    budget.spend("turn")
    budget.spend("turn")
    for _ in range(3):
        with pytest.raises(budget.LimitReached):
            budget.spend("turn")
    assert announced == ["Gemini usage at 80%", "Gemini limit reached"]  # each once, not every request
    assert budget.status()["limit_on"]
    assert budget.status()["hour"] == 2  # refused requests are not counted
    assert "stopped calling Gemini" in budget._flag_file().read_text()


def test_day_limit_also_applies(limits):
    limits(per_hour=100, per_day=1)
    budget.spend("turn")
    with pytest.raises(budget.LimitReached):
        budget.spend("turn")


def test_resumes_after_the_hour_and_says_so(limits, announced, monkeypatch):
    limits(1)
    budget.spend("turn")
    with pytest.raises(budget.LimitReached):
        budget.spend("turn")
    assert budget._flag_file().exists()

    later = time.time() + 3601  # an hour later the first request has left the window
    monkeypatch.setattr(budget.time, "time", lambda: later)
    budget.spend("turn")
    assert "Gemini calls resumed" in announced
    assert not budget._flag_file().exists()
    assert not budget.status()["limit_on"]


def test_a_failing_notification_never_breaks_counting(limits, monkeypatch):
    limits(1)
    monkeypatch.setattr(budget, "NOTIFY", True)
    monkeypatch.setattr(budget.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError("no osascript")))
    budget.spend("turn")
    with pytest.raises(budget.LimitReached):
        budget.spend("turn")
