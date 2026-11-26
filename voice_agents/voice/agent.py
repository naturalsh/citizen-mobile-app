"""LiveKit voice worker: caller audio -> Soniox -> brain.turn() -> Cartesia or Azure -> caller.

    .venv/bin/python -m voice.agent console   # talk through your laptop mic, no LiveKit server
    .venv/bin/python -m voice.agent start     # join LiveKit Cloud; call from the Agent Console or a phone

There is no LLM in the LiveKit session on purpose: the brain is the LLM. Soniox's endpoint
detection decides when the caller has finished (VOICE_TURN_DETECTION); a turn that is only
"εε…" is ignored and fillers are stripped (voice/fillers.py). Then on_user_turn_completed
sends the text to brain.turn_stream() and speaks the reply as it arrives; if the caller would hear silence for VOICE_HOLD_AFTER_S, it says the
brain's "one moment" line first (issues #2 and #4). Follows Docs/Voice_Agent_Flow.md and
Docs/Research/04_STT_and_TTS.md.
"""
import asyncio
import logging
import time
from typing import AsyncIterable

from livekit.agents import Agent, AgentServer, AgentSession, JobContext, JobProcess, cli, get_job_context
from livekit.agents.llm import ChatContext, ChatMessage
from livekit.agents.voice import (
    AgentStateChangedEvent,
    CloseEvent,
    SpeechHandle,
    UserInputTranscribedEvent,
    UserStateChangedEvent,
)
from livekit import api, rtc
from livekit.agents.voice import room_io
from livekit.agents.voice.events import CloseReason
from livekit.plugins import silero, soniox

from . import config, fillers, keywords, load, recordings, telephony, voices
from .call import CallFlow, in_thread
from .language import LanguageTracker
from .timing import ReplyTimes

log = logging.getLogger("voice")


class IntakeAgent(Agent):
    def __init__(self, flow: CallFlow, caller: rtc.RemoteParticipant, times: ReplyTimes) -> None:
        super().__init__(instructions="Replies come from brain.turn(); this agent has no LLM.")
        self.flow = flow
        self.caller = caller
        self.times = times
        self.languages = LanguageTracker(flow.lang)
        self._hints: asyncio.Task | None = None  # looking for the area's streets (_street_hints)
        self._last_reply: list[SpeechHandle] = []  # one reply can be several parts (recorded + live)
        self._fixed = {lang: flow.fixed_lines(lang) for lang in config.LANGS}  # lines that may be pre-recorded

    async def on_enter(self) -> None:
        @self.session.on("user_input_transcribed")
        def _heard(ev: UserInputTranscribedEvent) -> None:
            if ev.is_final:
                self.languages.heard(ev.transcript, ev.language)
                if config.LOG_HEARD:
                    log.info("call %s heard (%s, agent %s): %s", self.flow.call_id, ev.language,
                             self.session.agent_state, ev.transcript)

        @self.session.on("user_state_changed")
        def _caller_state(ev: UserStateChangedEvent) -> None:
            if ev.old_state == "speaking" and ev.new_state == "listening":
                self.times.caller_stopped(ev.created_at)

        @self.session.on("agent_state_changed")
        def _agent_state(ev: AgentStateChangedEvent) -> None:
            if ev.new_state == "speaking" and (silence := self.times.agent_started(ev.created_at)) is not None:
                log.info("call %s: %.2f s of silence before the reply", self.flow.call_id, silence)

        await self._speak(self.flow.start())

    async def on_user_turn_completed(self, turn_ctx: ChatContext, new_message: ChatMessage) -> None:
        heard = (new_message.text_content or "").strip()
        lang = self.languages.decide()
        text = fillers.clean(heard) if config.FILLER_FILTER else heard
        if heard and not text:
            # Only "εε…": the caller is thinking. Stay silent and keep listening.
            log.info("call %s: only fillers, still listening", self.flow.call_id)
            return
        if not text or self.flow.outcome:
            return
        if (waited := self.times.turn_ended(time.time())) is not None:
            log.info("call %s: end of turn detected %.2f s after the caller stopped", self.flow.call_id, waited)
        interrupted = any(handle.interrupted for handle in self._last_reply)
        started = time.perf_counter()
        hold = asyncio.create_task(self._hold_after(config.HOLD_AFTER_S))
        try:
            if config.STREAM_REPLIES:
                await self._stream_reply(text, interrupted, lang, started, hold)
            else:
                # turn() blocks for 1-3 s on the model; keep the audio loop running meanwhile.
                result = await asyncio.to_thread(self.flow.reply, text, interrupted, lang)
                hold.cancel()
                self.times.brain_took(time.perf_counter() - started)
                self.languages.current = result.lang
                await self._speak(result)
        finally:
            hold.cancel()
            hints = getattr(self, "_hints", None)  # tests build the agent without __init__
            if not (hints and not hints.done()):
                self._hints = asyncio.create_task(self._street_hints())

    async def _street_hints(self, tries: int = 4, gap_s: float = 2.5) -> None:
        """Hint the caller's area streets to speech-to-text once the brain has them (voice/keywords.py).
        The map check fetches them in the background, so look a few times after each turn. Never
        while the caller speaks: the reconnect would cut their words."""
        try:
            stt = self.session.stt
        except (AttributeError, RuntimeError):
            return  # no session (a test) or the call is closing
        if not isinstance(stt, keywords.StreetHintSTT):
            return
        for attempt in range(tries):
            if attempt:
                await asyncio.sleep(gap_s)
            try:
                streets = await asyncio.to_thread(self.flow.street_hints)
            except Exception:
                log.exception("call %s: street hints failed", self.flow.call_id)
                return
            if not streets:
                continue
            while self.session.user_state == "speaking":
                await asyncio.sleep(0.3)
            if stt.use_streets(streets):
                log.info("call %s: %d area streets hinted to speech-to-text", self.flow.call_id, len(streets))
            return

    async def _stream_reply(self, text: str, interrupted: bool, lang: str, started: float, hold: asyncio.Task) -> None:
        """Speak the brain's reply while it is still being written (brain.turn_stream)."""
        events = in_thread(lambda: self.flow.reply_stream(text, interrupted, lang))
        try:
            _, start = await anext(events)  # ("start", ...): the action is known before any text
        except Exception:
            log.exception("call %s: no reply from the brain", self.flow.call_id)
            return
        hold.cancel()
        # Time until the brain's answer started arriving (the rest streams while it is spoken).
        self.times.brain_took(time.perf_counter() - started)
        self.languages.current = start["lang"]

        async def pieces() -> AsyncIterable[str]:
            async for kind, value in events:
                if kind == "text":
                    yield value

        await self._say(pieces(), start["lang"], start["action"], start["handoff_reason"])

    async def _hold_after(self, delay_s: float) -> None:
        """Say the brain's "one moment" line if the reply hasn't started after delay_s (issue #2)."""
        if delay_s <= 0:
            return
        await asyncio.sleep(delay_s)
        try:
            line, lang = self.flow.hold_line(), self.languages.current
            for part, recording in recordings.split(line, lang, self._fixed.get(lang, [])):
                self._say_part(part, recording, interruptible=True, add_to_chat_ctx=False)
        except RuntimeError:
            return  # the caller already hung up
        log.info("call %s: reply slow, said the hold line", self.flow.call_id)

    async def _speak(self, result) -> None:
        await self._say(result.reply_text, result.lang, result.action, result.handoff_reason)

    async def _say(self, text: str | AsyncIterable[str], lang: str, action: str, handoff_reason: str | None) -> None:
        voices.switch(self.session.tts, lang)

        final = action in ("end", "handoff")
        try:
            # The last line (read-back confirmation, handoff notice) must be heard in full.
            if isinstance(text, str):
                fixed = self._fixed.get(lang, [])
                handles = [self._say_part(part, rec, not final) for part, rec in recordings.split(text, lang, fixed)]
            else:
                handles = await self._say_pieces(text, lang, interruptible=not final)
        except RuntimeError:
            # The caller hung up while the brain was still answering; the reply is in the
            # transcript but nobody is left to hear it.
            log.info("call %s closed before the reply could be spoken", self.flow.call_id)
            return
        self._last_reply = handles
        if not final or not handles:
            return
        await handles[-1].wait_for_playout()
        if action == "handoff" and await self._transfer(handoff_reason):
            return  # the caller leaves the room for the operator's phone; the session then closes
        await _hang_up()

    def _say_part(self, text: str, recording, interruptible: bool, add_to_chat_ctx: bool = True) -> SpeechHandle:
        """Play a pre-recorded line (voice/recordings.py) or speak the text live."""
        if recording is not None:
            return self.session.say(text, audio=recordings.frames(recording), allow_interruptions=interruptible,
                                    add_to_chat_ctx=add_to_chat_ctx)
        return self.session.say(text, allow_interruptions=interruptible, add_to_chat_ctx=add_to_chat_ctx)

    async def _say_pieces(self, pieces: AsyncIterable[str], lang: str, interruptible: bool) -> list[SpeechHandle]:
        """Speak a streamed reply: recorded lines from disk, the rest live as it arrives, in order."""
        fixed = self._fixed.get(lang, [])
        handles: list[SpeechHandle] = []
        live: asyncio.Queue | None = None  # feeds the live part currently being spoken
        async for piece in pieces:
            for part, recording in recordings.split(piece, lang, fixed):
                if recording is not None:
                    if live is not None:
                        live.put_nowait(None)
                        live = None
                    handles.append(self._say_part(part, recording, interruptible))
                    continue
                if live is None:
                    if not part.strip():
                        continue  # e.g. the space after a recorded line
                    live = asyncio.Queue()
                    handles.append(self.session.say(_drain(live), allow_interruptions=interruptible))
                live.put_nowait(part)
        if live is not None:
            live.put_nowait(None)
        return handles

    async def _transfer(self, reason: str | None) -> bool:
        """Transfer a phone caller to OPERATOR_NUMBER. False (then we hang up) if that isn't possible."""
        target = telephony.transfer_target(config.OPERATOR_NUMBER)
        if not target or not telephony.is_phone_call(self.caller):
            log.info("handoff for %s (%s): no transfer (no OPERATOR_NUMBER or not a phone call), hanging up",
                     self.flow.call_id, reason)
            return False
        ctx = get_job_context()
        try:
            await ctx.api.sip.transfer_sip_participant(
                api.TransferSIPParticipantRequest(
                    room_name=ctx.room.name, participant_identity=self.caller.identity, transfer_to=target,
                    play_dialtone=True,
                )
            )
        except Exception:
            log.exception("transfer failed for %s, hanging up", self.flow.call_id)
            return False
        log.info("call %s transferred to the operator (%s)", self.flow.call_id, reason)
        return True


async def _drain(queue: asyncio.Queue) -> AsyncIterable[str]:
    while (piece := await queue.get()) is not None:
        yield piece


async def _hang_up() -> None:
    """Deleting the room disconnects the caller (also on a phone line) and closes the session."""
    try:
        await get_job_context().delete_room()
    except Exception:
        log.exception("could not delete the room")  # e.g. console mode has no server room
    get_job_context().shutdown("call over")


def prewarm(proc: JobProcess) -> None:
    proc.userdata["vad"] = silero.VAD.load()


# end_call() writes the operator summary (up to ~20 s), so give shutdown time to finish it.
# Full by the number of calls, not LiveKit's CPU rule (load.py).
server = AgentServer(setup_fnc=prewarm, shutdown_process_timeout=30,
                     load_fnc=load.current, load_threshold=load.THRESHOLD)


@server.rtc_session()
async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect()
    participant = await ctx.wait_for_participant()
    phone = telephony.caller_number(participant) or config.TEST_PHONE
    flow = CallFlow(phone, lang=telephony.link_language(participant))
    times = ReplyTimes()
    log.info("call %s from %s, first language guess %s", flow.call_id, phone[:4] + "…", flow.lang)

    # The VAD stays for interruptions; the end of the caller's turn comes from Soniox
    # (VOICE_TURN_DETECTION, voice/config.py).
    turn_detection = config.turn_detection()
    session = AgentSession(
        vad=ctx.proc.userdata["vad"],
        stt=keywords.StreetHintSTT(
            **({"base_url": config.SONIOX_BASE_URL} if config.SONIOX_BASE_URL else {}),
            params=soniox.STTOptions(
                model=config.SONIOX_MODEL,
                language_hints=[flow.lang] + [lang for lang in config.LANGS if lang != flow.lang],
                enable_language_identification=True,
                context=keywords.context(),
                **config.soniox_endpoint_options(),
            )
        ),
        tts=voices.make_tts(flow.lang),
        **({"turn_handling": {"turn_detection": turn_detection}} if turn_detection else {}),
    )
    log.info("call %s: turn end from %s %s", flow.call_id, turn_detection or "LiveKit's default",
             config.soniox_endpoint_options() or "")

    caller_left = False

    @session.on("close")
    def _on_close(ev: CloseEvent) -> None:
        nonlocal caller_left
        caller_left = ev.reason == CloseReason.PARTICIPANT_DISCONNECTED
        ctx.shutdown("call over")  # caller hung up, line dropped, or the agent hung up

    async def _finish(_shutdown_reason: str) -> None:
        if caller_left:
            # Close the room first, then write the summary. LiveKit sends the agent only into a new
            # room: a room left open ~40 s after a call made a reopened test link join without an
            # agent ("Disconnected", 2026-10-26).
            try:
                await ctx.delete_room()
            except Exception:
                log.exception("could not close the room of %s", flow.call_id)
        reason = flow.end_reason(caller_left)
        await asyncio.to_thread(flow.finish, reason)
        log.info("call %s ended (%s); %s", flow.call_id, reason, times.summary())

    # Shutdown callbacks run however the job ends, so end_call() always runs exactly once.
    ctx.add_shutdown_callback(_finish)
    room_options = room_io.RoomOptions(
        # LiveKit Cloud only; VOICE_NOISE_CANCELLATION=off for a self-hosted server.
        audio_input=room_io.AudioInputOptions(noise_cancellation=telephony.noise_filter)
        if config.NOISE_CANCELLATION else True,
    )
    await session.start(IntakeAgent(flow, participant, times), room=ctx.room, room_options=room_options)


if __name__ == "__main__":
    print(config.checklist())
    cli.run_app(server)
