"""Failed-112-call trigger: when a call to 112 does not get through, message the caller first.

Only the phone network or the 112 call centre knows a call failed, so in a real deployment
they would call this endpoint. For the demo we call it ourselves (see channels/README.md).

    POST /112/call-failed
    X-Trigger-Token: <TRIGGER_TOKEN>
    {"phone": "+306900000000", "reason": "busy", "channel": "sms"}

"lang" ("el", "tr", "en", "fr") is optional: the person's language when the caller knows it, e.g. a
tourist's phone set to English. Without it, the first message is in the language of the country code.

The first message is sent through Twilio. The person's replies then arrive on the normal
/sms or /whatsapp webhook and continue the same conversation.
"""
import hmac
import logging
import os
import re
import time
import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from twilio.rest import Client

from brain import CallInfo, control, end_call, start_call
from brain.langs import lang_from_phone

from .conversations import Conversation, conversations, has_open, locks

log = logging.getLogger("trigger")

TRIGGER_TOKEN = os.getenv("TRIGGER_TOKEN")  # shared secret with whoever reports failed calls
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_SMS_FROM = os.getenv("TWILIO_SMS_FROM")  # your Twilio number, e.g. +1555...
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM")  # the sandbox number, e.g. +14155238886
DEDUPE_WINDOW_S = 15 * 60  # one first message per number per 15 minutes, however often 112 fails

_E164 = re.compile(r"^\+[1-9]\d{7,14}$")
_last_sent: dict[str, float] = {}

router = APIRouter()


class FailedCall(BaseModel):
    phone: str
    reason: Literal["busy", "no_answer", "dropped", "network"] = "busy"
    attempted_at: Optional[str] = None
    aml: Optional[dict] = None
    channel: Literal["sms", "whatsapp"] = "sms"  # SMS works without mobile data
    # The person's language when known (a tourist with a Greek SIM, or the demo for English-speaking judges);
    # otherwise the country code decides, so a +30 number got its first message in Greek.
    lang: Optional[Literal["el", "tr", "en", "fr"]] = None


def _sender(channel: str) -> Optional[str]:
    return TWILIO_WHATSAPP_FROM if channel == "whatsapp" else TWILIO_SMS_FROM


def _send(channel: str, phone: str, body: str) -> Optional[str]:
    """Sends through Twilio and returns the message SID, or None in dry-run mode."""
    sender = _sender(channel)
    if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and sender):
        log.info("DRY RUN, not sent (%s to %s): %s", channel, phone, body)
        return None
    prefix = "whatsapp:" if channel == "whatsapp" else ""
    message = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN).messages.create(
        to=f"{prefix}{phone}", from_=f"{prefix}{sender}", body=body
    )
    return message.sid


@router.post("/112/call-failed")
def call_failed(event: FailedCall, x_trigger_token: Optional[str] = Header(default=None)) -> dict:
    # Anyone who can call this can make us text strangers, so it is closed unless a token is set.
    if not TRIGGER_TOKEN:
        raise HTTPException(status_code=503, detail="TRIGGER_TOKEN is not configured")
    if not hmac.compare_digest(x_trigger_token or "", TRIGGER_TOKEN):
        raise HTTPException(status_code=401, detail="bad trigger token")

    phone = event.phone.replace(" ", "").removeprefix("whatsapp:")
    if not _E164.match(phone):
        raise HTTPException(status_code=422, detail="phone must be in +<country><number> format")

    if control.is_paused():
        return {"sent": False, "skipped": "AI paused by an operator"}

    key = (event.channel, phone)
    with locks[key]:
        if has_open(phone):
            return {"sent": False, "skipped": "conversation already open"}
        if time.time() - _last_sent.get(phone, 0) < DEDUPE_WINDOW_S:
            return {"sent": False, "skipped": "already messaged recently"}

        lang = event.lang or lang_from_phone(phone)
        call_id = f"{event.channel[:2]}-{uuid.uuid4().hex[:8]}"
        trigger = {"type": "failed_112_call", "reason": event.reason, "attempted_at": event.attempted_at}
        greeting = start_call(
            CallInfo(call_id=call_id, channel=event.channel, phone=phone, lang_guess=lang, aml=event.aml, trigger=trigger)
        )

        try:
            sid = _send(event.channel, phone, greeting.reply_text)
        except Exception as exc:
            log.exception("sending first message to %s failed", phone)
            end_call(call_id, "dropped")
            raise HTTPException(status_code=502, detail=f"sending failed: {exc}") from exc

        conversations[key] = Conversation(call_id=call_id, lang=lang, last_seen=time.time())
        _last_sent[phone] = time.time()

    return {
        "sent": sid is not None,
        "dry_run": sid is None,
        "sid": sid,
        "call_id": call_id,
        "channel": event.channel,
        "lang": lang,
        "message": greeting.reply_text,
    }
