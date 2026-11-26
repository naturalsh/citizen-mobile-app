"""WhatsApp and SMS channels: Twilio webhook -> brain -> reply.

    .venv/bin/uvicorn channels.messaging:app --port 8000

Point Twilio's "When a message comes in" to https://<public-url>/whatsapp (WhatsApp sandbox)
or https://<public-url>/sms (a Twilio phone number). See channels/README.md.
Every other path is the shared dashboard, behind its key (dashboard_proxy.py).
"""
import logging
import os
import time
import uuid

from dotenv import load_dotenv

load_dotenv()

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request  # noqa: E402
from fastapi.concurrency import run_in_threadpool  # noqa: E402
from fastapi.responses import RedirectResponse, Response  # noqa: E402
from twilio.request_validator import RequestValidator  # noqa: E402
from twilio.twiml.messaging_response import MessagingResponse  # noqa: E402

from brain import CallInfo, end_call, start_call, turn  # noqa: E402
from brain.contract import Channel  # noqa: E402
from brain.langs import lang_from_phone, lang_from_text  # noqa: E402

from . import dashboard_proxy, trigger  # noqa: E402
from .conversations import Conversation, conversations, locks  # noqa: E402

log = logging.getLogger("messaging")

TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")  # e.g. the tunnel's https URL

app = FastAPI()
app.include_router(trigger.router)  # POST /112/call-failed


def _handle(channel: Channel, phone: str, text: str, background: BackgroundTasks) -> str:
    """One incoming message -> the one message to send back."""
    key = (channel, phone)
    with locks[key]:  # one turn at a time per sender, even if they send fast
        convo = conversations.get(key)
        if convo and convo.idle():
            background.add_task(end_call, convo.call_id, "dropped")
            convo = None

        greeting = None
        if convo is None:
            lang = lang_from_text(text, lang_from_phone(phone))
            convo = Conversation(call_id=f"{channel[:2]}-{uuid.uuid4().hex[:8]}", lang=lang, last_seen=time.time())
            conversations[key] = convo
            greeting = start_call(CallInfo(call_id=convo.call_id, channel=channel, phone=phone, lang_guess=lang))
            if greeting.action == "handoff":  # AI paused by an operator: only the handoff line
                background.add_task(end_call, convo.call_id, "handed_off")
                del conversations[key]
                return greeting.reply_text

        convo.lang = lang_from_text(text, convo.lang)
        convo.last_seen = time.time()
        result = turn(convo.call_id, text, convo.lang)

        if result.action in ("handoff", "end"):
            # The summary can take a few seconds; reply to Twilio first.
            background.add_task(end_call, convo.call_id, "handed_off" if result.action == "handoff" else "completed")
            del conversations[key]

        # One message, not two: saves a message and stays under the sandbox's 1 message / 3 s limit.
        if greeting:
            return f"{greeting.reply_text}\n\n{result.reply_text}" if channel == "whatsapp" else f"{greeting.reply_text} {result.reply_text}"
        return result.reply_text


async def _webhook(channel: Channel, request: Request, background: BackgroundTasks) -> Response:
    form = dict(await request.form())

    if TWILIO_AUTH_TOKEN:
        url = f"{PUBLIC_BASE_URL}{request.url.path}" if PUBLIC_BASE_URL else str(request.url)
        signature = request.headers.get("X-Twilio-Signature", "")
        if not RequestValidator(TWILIO_AUTH_TOKEN).validate(url, form, signature):
            raise HTTPException(status_code=403, detail="bad Twilio signature")

    phone = form.get("From", "").removeprefix("whatsapp:")
    text = form.get("Body", "").strip()
    if not phone:
        raise HTTPException(status_code=400, detail="missing From")
    if not text:
        # Voice note, photo or location without text. Let the brain ask them to write it.
        text = "(the caller sent a voice note, photo or location that cannot be read, no text)"

    reply = await run_in_threadpool(_handle, channel, phone, text, background)

    twiml = MessagingResponse()
    twiml.message(reply)
    return Response(content=str(twiml), media_type="application/xml")


@app.post("/whatsapp")
async def whatsapp(request: Request, background: BackgroundTasks) -> Response:
    return await _webhook("whatsapp", request, background)


@app.post("/sms")
async def sms(request: Request, background: BackgroundTasks) -> Response:
    return await _webhook("sms", request, background)


@app.get("/call")
def call(lang: str, expires: int, sig: str) -> RedirectResponse:
    """A browser test call in a new room (voice/link.py): a fixed room reopened soon after a call
    got no agent, since LiveKit sends the agent only into a new room. Signed links only."""
    from voice.link import check_short_link, make_link

    if not check_short_link(lang, expires, sig):
        raise HTTPException(status_code=403, detail="this call link is not valid or has expired")
    _, link = make_link(lang, hours=1)  # only for joining now
    return RedirectResponse(link, status_code=302)


@app.get("/health")
def health() -> dict:
    return {"ok": True, "open_conversations": len(conversations)}


app.include_router(dashboard_proxy.router)  # last: every other path goes to the shared dashboard
