"""How long the caller waits for each reply (issue #2, Docs/Research/04 latency budget).

Two numbers per turn, logged as the call goes and summarised when it ends:
- silence: from the caller stopping speaking (voice activity detection) to the agent's
  first audio. This is what the caller hears.
- brain: how long brain.turn() took, the biggest part of the silence.
- turn end: from the caller stopping to the turn being handed to the brain, i.e. how long
  end-of-turn detection waited. The rest of the silence is text-to-speech starting.
"""
import statistics


def _p90(values: list[float]) -> float:
    return statistics.quantiles(values, n=10, method="inclusive")[8] if len(values) > 1 else values[0]


class ReplyTimes:
    def __init__(self) -> None:
        self.silence: list[float] = []
        self.brain: list[float] = []
        self.turn_end: list[float] = []
        self._stopped_at: float | None = None

    def caller_stopped(self, at: float) -> None:
        self._stopped_at = at

    def agent_started(self, at: float) -> float | None:
        """Returns this turn's silence in seconds, or None when the caller hadn't spoken (the greeting)."""
        if self._stopped_at is None:
            return None
        silence, self._stopped_at = at - self._stopped_at, None
        self.silence.append(silence)
        return silence

    def brain_took(self, seconds: float) -> None:
        self.brain.append(seconds)

    def turn_ended(self, at: float) -> float | None:
        """Seconds from the caller stopping to the end of their turn, or None if not known."""
        if self._stopped_at is None:
            return None
        waited = max(at - self._stopped_at, 0.0)
        self.turn_end.append(waited)
        return waited

    def summary(self) -> str:
        parts = []
        for name, values in (("silence", self.silence), ("turn end", self.turn_end), ("brain", self.brain)):
            if values:
                parts.append(f"{name} median {statistics.median(values):.2f} s, p90 {_p90(values):.2f} s")
        return f"{len(self.silence)} replies: " + "; ".join(parts) if parts else "no replies timed"
