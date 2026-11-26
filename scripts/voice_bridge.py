#!/usr/bin/env python3
"""HTTP bridge connecting citizen-mobile-app's /voice-api/* directly to the embedded
naturalsh/Voice_Agents repo (voice_agent/brain/contract.py & voice_agent/voice/link.py).

Run with the Voice_Agents Python environment:
    /Users/efe/Projects/Greek-Turkish/Voice_Agents/.venv/bin/python scripts/voice_bridge.py

Then start citizen-mobile-app:
    npm start
"""
import os
import sys
import uuid
from typing import Optional

from dotenv import load_dotenv

VOICE_REPO = os.environ.get(
    "VOICE_AGENTS_REPO",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "voice_agent")),
)
if VOICE_REPO not in sys.path:
    sys.path.insert(0, VOICE_REPO)

# Load voice_agent/.env so GEMINI_API_KEY, LIVEKIT_*, SONIOX_API_KEY, CARTESIA_API_KEY are active
load_dotenv(os.path.join(VOICE_REPO, ".env"))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from brain.contract import CallInfo
from brain.core import start_call, turn, end_call

app = FastAPI(title="Nature Shield 112 Voice Agent Bridge")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


class StartReq(BaseModel):
    lang: str = "en"
    channel: str = "voice"
    phone: str = "+90 500 000 0000"
    aml: Optional[dict] = None


class TurnReq(BaseModel):
    call_id: str
    text: str
    lang: str = "en"


class EndReq(BaseModel):
    call_id: str
    reason: str = "hung_up"


class LiveKitReq(BaseModel):
    lang: str = "en"
    hours: float = 1.0


@app.get("/voice-api/health")
def health():
    return {
        "ok": True,
        "gemini_configured": bool(os.getenv("GEMINI_API_KEY")),
        "livekit_configured": bool(
            os.getenv("LIVEKIT_URL") and os.getenv("LIVEKIT_API_KEY") and os.getenv("LIVEKIT_API_SECRET")
        ),
        "soniox_configured": bool(os.getenv("SONIOX_API_KEY")),
        "tts_provider": os.getenv("VOICE_TTS", "cartesia"),
    }


@app.post("/voice-api/start")
def api_start(req: StartReq):
    call_id = f"web-{uuid.uuid4().hex[:10]}"
    phone = req.phone
    if req.lang == "el" and phone == "+90 500 000 0000":
        phone = "+30 690 000 0000"
    res = start_call(CallInfo(call_id=call_id, channel="voice", phone=phone, lang_guess=req.lang, aml=req.aml))
    return {
        "call_id": call_id,
        "reply_text": res.reply_text,
        "lang": res.lang,
        "action": res.action,
        "handoff_reason": res.handoff_reason,
        "report": res.report,
    }


@app.post("/voice-api/turn")
def api_turn(req: TurnReq):
    res = turn(req.call_id, req.text, req.lang)
    return {
        "call_id": req.call_id,
        "reply_text": res.reply_text,
        "lang": res.lang,
        "action": res.action,
        "handoff_reason": res.handoff_reason,
        "report": res.report,
    }


@app.post("/voice-api/end")
def api_end(req: EndReq):
    return end_call(req.call_id, req.reason)


@app.post("/voice-api/token")
def api_token(req: LiveKitReq):
    """Mint a fresh LiveKit room + participant JWT, identical to voice_agent/voice/link.py."""
    url = os.getenv("LIVEKIT_URL")
    if not (url and os.getenv("LIVEKIT_API_KEY") and os.getenv("LIVEKIT_API_SECRET")):
        raise HTTPException(503, "LiveKit credentials are not configured in voice_agent/.env")
    import secrets
    from datetime import timedelta
    from livekit import api as lk_api

    room = f"mobile-112-{secrets.token_hex(4)}"
    token = (
        lk_api.AccessToken()
        .with_identity(f"caller-{secrets.token_hex(3)}")
        .with_name("112 Caller")
        .with_attributes({"lang": req.lang})
        .with_room_config(lk_api.RoomConfiguration(departure_timeout=1, empty_timeout=60))
        .with_ttl(timedelta(hours=req.hours))
        .with_grants(lk_api.VideoGrants(room_join=True, room=room, can_publish=True, can_subscribe=True))
        .to_jwt()
    )
    return {"livekit_url": url, "token": token, "room": room, "lang": req.lang}


@app.post("/voice-api/livekit")
def api_livekit(req: LiveKitReq):
    if not (os.getenv("LIVEKIT_URL") and os.getenv("LIVEKIT_API_KEY") and os.getenv("LIVEKIT_API_SECRET")):
        raise HTTPException(503, "LiveKit credentials are not configured in voice_agent/.env")
    from voice.link import make_link

    room, url = make_link(lang=req.lang, hours=req.hours)
    return {"room": room, "url": url}


if __name__ == "__main__":
    os.chdir(VOICE_REPO)
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("VOICE_BRIDGE_PORT", "8010")))
