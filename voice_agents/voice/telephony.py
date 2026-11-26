"""Phone-call details: where a handoff is transferred, and noise cancellation per caller.

Docs/Research/01 (handoff to a human) and 02 (signal cleanup). Calls arrive from a SIP
trunk into LiveKit; browser and console calls take the same path without a phone line.
"""
import re

from livekit import rtc
from livekit.agents.voice.room_io.types import NoiseCancellationParams
from livekit.plugins import noise_cancellation

from .config import LANGS

_E164 = re.compile(r"^\+[1-9]\d{7,14}$")


def is_phone_call(participant: rtc.RemoteParticipant) -> bool:
    return participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP


def link_language(participant: rtc.RemoteParticipant) -> str | None:
    """The language a browser test link was made for (`python -m voice.link --lang tr`), or None.

    A browser call has no phone number, so it started in Greek: a Turkish tester's call stayed
    Greek (2026-10-26). Phone calls keep their country code; console attributes aren't strings."""
    if is_phone_call(participant):
        return None
    lang = participant.attributes.get("lang")
    return lang if isinstance(lang, str) and lang in LANGS else None


def caller_number(participant: rtc.RemoteParticipant) -> str | None:
    """The caller's number on a phone call; None for browser and console calls.

    Console mode uses a stand-in participant whose attributes are not real strings,
    so only a SIP participant's text attribute counts.
    """
    if not is_phone_call(participant):
        return None
    number = participant.attributes.get("sip.phoneNumber")
    return number if isinstance(number, str) and number.strip() else None


def transfer_target(operator_number: str) -> str | None:
    """'+30 690 000 0000' -> 'tel:+306900000000'; None if empty or not a full international number."""
    number = re.sub(r"[\s\-()]", "", operator_number or "")
    return f"tel:{number}" if _E164.match(number) else None


def noise_filter(params: NoiseCancellationParams):
    """LiveKit Cloud noise cancellation: the telephony model for phone lines, the general one otherwise."""
    if is_phone_call(params.participant):
        return noise_cancellation.BVCTelephony()
    return noise_cancellation.BVC()
