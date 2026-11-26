"""The contract between the voice side (and WhatsApp) and the brain.

Change this file only when both sides agree.

    start_call(CallInfo) -> TurnResult         greeting
    turn(call_id, text, lang) -> TurnResult    one caller utterance -> one reply
    turn_stream(call_id, text, lang)           same, but yields the reply while it is written:
        ("start", {"action", "handoff_reason", "lang"}), ("text", piece)..., ("result", TurnResult)
    hold_phrase(call_id) -> str                "one moment" line for a slow reply (voice only)
    fixed_voice_texts(lang) -> list[str]       lines said word for word on calls, for pre-recording
    end_call(call_id, reason) -> dict          final report

turn_stream and hold_phrase were added for issue #2 / #4 (slow replies); turn() is unchanged.
"""
from dataclasses import dataclass
from typing import Literal, Optional

Channel = Literal["voice", "whatsapp", "sms"]
Action = Literal["continue", "handoff", "end"]
EndReason = Literal["completed", "hung_up", "dropped", "handed_off"]


@dataclass
class CallInfo:
    call_id: str
    channel: Channel
    phone: str                    # caller number, e.g. "+30 69..."
    lang_guess: str               # from country code: "el", "tr", "en", "fr"
    aml: Optional[dict] = None    # {"lat": ..., "lon": ..., "accuracy_m": ...} if available
    # Set when we contact the person first, e.g. {"type": "failed_112_call", "reason": "busy", ...}.
    # None when the person called or wrote to us. Optional, so the voice side can ignore it.
    trigger: Optional[dict] = None


@dataclass
class TurnResult:
    reply_text: str               # exactly what to say or send, in the caller's language
    lang: str                     # language the brain is now using
    action: Action
    handoff_reason: Optional[str]
    report: dict                  # current report (Docs/Research/06 schema)
