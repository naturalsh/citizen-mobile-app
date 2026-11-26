"""When this computer stops taking new calls: by the number of calls, not by the CPU.

LiveKit marks a worker "full" when its load goes over a threshold, and by default the load is the
whole computer's CPU with the line at 70%. Speech-to-text, the model and the voice all run in the
cloud, so the laptop's CPU says little about whether another call fits; on 2026-10-29/30 the agent
kept marking itself full while other apps were busy, and a screen recording for the demo (OBS)
would have turned new calls away. Now it is full at VOICE_MAX_CALLS calls, or only when the CPU
stays above VOICE_CPU_LIMIT (95%) over the last 5 seconds, when the audio itself would break up.

The CPU is measured over a fixed window of time, not "since LiveKit last asked": LiveKit asks at
uneven moments, sometimes milliseconds apart, and over such short spans macOS reports 0% or 100%.
A run of those 100% readings marked the agent full for 30 s at 27% CPU (2026-10-30, a demo take),
and the caller left before it joined.
"""
import logging
import time
from collections import deque

import psutil

from . import config

log = logging.getLogger("voice.load")

THRESHOLD = 0.95  # LiveKit marks the worker full above this; in production it must stay under 1
WINDOW_S = 5.0  # the CPU is averaged over this much time
_samples: deque = deque(maxlen=200)  # (time, busy seconds, total seconds), at most one per 0.25 s
_was_full = False


def worker_load(active_calls: int, cpu: float, max_calls: int, cpu_limit: float) -> float:
    """0 to 1, over THRESHOLD only when no new call should come here."""
    if active_calls >= max_calls or cpu >= cpu_limit:
        return 1.0
    return 0.9 * active_calls / max_calls  # shown in LiveKit's dashboard; always under THRESHOLD


def cpu_share(now: float | None = None, times=None) -> float:
    """The whole computer's CPU use over the last WINDOW_S seconds, 0 to 1 (0 until there is a window)."""
    now = time.monotonic() if now is None else now
    t = times or psutil.cpu_times()
    total = sum(t)
    busy = total - t.idle
    if not _samples or now - _samples[-1][0] >= 0.25:
        _samples.append((now, busy, total))
    old = next((s for s in _samples if now - s[0] <= WINDOW_S), None)
    if old is None or total - old[2] <= 0 or now - old[0] < 1.0:
        return 0.0  # under a second of history: too short to say
    return (busy - old[1]) / (total - old[2])


def current(server=None) -> float:
    """LiveKit's load_fnc: the calls running now and the CPU over the last few seconds."""
    global _was_full
    jobs = len(server.active_jobs) if server is not None else 0
    cpu = cpu_share()
    load = worker_load(jobs, cpu, config.MAX_CALLS, config.CPU_LIMIT)
    full = load > THRESHOLD
    if full != _was_full:  # say why, once, so a refused call can be explained from the log
        _was_full = full
        log.warning("%s new calls: %d calls running, CPU %.0f%% over %.0f s", "not taking" if full else "taking",
                    jobs, cpu * 100, WINDOW_S)
    return load
