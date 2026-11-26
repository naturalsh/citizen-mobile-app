"""One phone call's link to the brain, without any LiveKit code so it can be unit-tested.

The LiveKit agent (agent.py) calls start() when the caller connects, reply() or
reply_stream() each time the caller finishes speaking, and finish() once when the call is
over, whatever the reason.
"""
import asyncio
import logging
import uuid
from typing import AsyncIterator, Callable, Iterator

from . import config  # noqa: F401  loads .env before the brain reads its settings

import brain  # noqa: E402
from brain.contract import EndReason, TurnResult  # noqa: E402
from brain.langs import lang_from_phone  # noqa: E402

log = logging.getLogger("voice")


class CallFlow:
    def __init__(self, phone: str, call_id: str | None = None, brain_api=brain, lang: str | None = None) -> None:
        """lang: a browser test link's language; otherwise the phone's country code decides."""
        self.phone = phone
        self.call_id = call_id or f"vo-{uuid.uuid4().hex[:8]}"
        self.lang = lang or lang_from_phone(phone)
        self.outcome: EndReason | None = None  # set when the brain ends or hands off the call
        self._brain = brain_api
        self._finished = False

    def start(self) -> TurnResult:
        info = brain.CallInfo(call_id=self.call_id, channel="voice", phone=self.phone, lang_guess=self.lang)
        return self._track(self._brain.start_call(info))

    def reply(self, caller_text: str, interrupted: bool = False, lang: str | None = None) -> TurnResult:
        """Blocking (one model request): run it in a thread. lang = language the caller just spoke."""
        lang = lang or self.lang
        return self._track(self._brain.turn(self.call_id, caller_text, lang, interrupted=interrupted))

    def reply_stream(self, caller_text: str, interrupted: bool = False, lang: str | None = None) -> Iterator[tuple]:
        """Like reply(), but yields the brain's turn_stream() events while the reply is written:
        ("start", {"action", "handoff_reason", "lang"}), ("text", piece)..., ("result", TurnResult).
        Blocking: run it with in_thread()."""
        lang = lang or self.lang
        for kind, value in self._brain.turn_stream(self.call_id, caller_text, lang, interrupted=interrupted):
            if kind == "result":
                self._track(value)
            yield kind, value

    def fixed_lines(self, lang: str) -> list[str]:
        """Lines the brain says word for word in `lang`, which may be pre-recorded (voice/recordings.py)."""
        return self._brain.fixed_voice_texts(lang)

    def hold_line(self) -> str:
        """The brain's "one moment" line in the call's language, for a slow reply."""
        return self._brain.hold_phrase(self.call_id)

    def street_hints(self) -> list[str]:
        """The caller's area streets once the brain has them, for speech-to-text hints."""
        hints = getattr(self._brain, "street_hints", None)  # test brains may not have it
        return hints(self.call_id) if hints else []

    def _track(self, result: TurnResult) -> TurnResult:
        self.lang = result.lang
        if result.action == "end":
            self.outcome = "completed"
        elif result.action == "handoff":
            self.outcome = "handed_off"
        return result

    def end_reason(self, caller_left: bool) -> EndReason:
        """Why the call ended: the brain's decision if it made one, else who hung up."""
        if self.outcome:
            return self.outcome
        return "hung_up" if caller_left else "dropped"

    def finish(self, reason: EndReason) -> dict | None:
        """Blocking (writes the operator summary, up to ~20 s): run it in a thread. Safe to call twice."""
        if self._finished:
            return None
        self._finished = True
        try:
            return self._brain.end_call(self.call_id, reason)
        except Exception:
            log.exception("end_call failed for %s", self.call_id)  # the per-turn report is already saved
            return None


async def in_thread(make_items: Callable[[], Iterator]) -> AsyncIterator:
    """Run a blocking generator in a thread and hand its items to async code as they arrive.

    The thread always runs the generator to the end, even if nobody reads the rest (for
    example when the caller interrupts the reply), so the brain still finishes the turn.
    """
    loop = asyncio.get_running_loop()
    items: asyncio.Queue = asyncio.Queue()
    done = object()

    def run() -> None:
        try:
            for item in make_items():
                loop.call_soon_threadsafe(items.put_nowait, item)
        except Exception as exc:
            loop.call_soon_threadsafe(items.put_nowait, exc)
        finally:
            loop.call_soon_threadsafe(items.put_nowait, done)

    worker = asyncio.create_task(asyncio.to_thread(run))
    try:
        while (item := await items.get()) is not done:
            if isinstance(item, Exception):
                raise item
            yield item
    finally:
        worker.add_done_callback(lambda _: None)  # keep a reference until the thread ends
