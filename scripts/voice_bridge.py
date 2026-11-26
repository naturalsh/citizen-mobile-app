#!/usr/bin/env python3
"""Optional HTTP bridge connecting citizen-mobile-app's /voice-api/* to Voice_Agents/brain/contract.py.

Run from the Voice_Agents venv:
    /Users/efe/Projects/Greek-Turkish/Voice_Agents/.venv/bin/python scripts/voice_bridge.py

Then start citizen-mobile-app with:
    node server.mjs --voice-api http://127.0.0.1:8010
"""
import os
import sys
import uuid
from typing import Optional

VOICE_REPO = os.environ.get(
    "VOICE_AGENTS_REPO",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "Voice_Agents")),
)
if VOICE_REPO not in sys.path:
    sys.path.insert(0, VOICE_REPO)

from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn

from brain.contract import CallInfo
from brain.core import start_call, turn, end_call

app = FastAPI(title="Nature Shield 112 Voice Bridge")


class StartReq(BaseModel):
    lang: str = "en"
    channel: str = "voice"
    phone: str = "web-mobile"
    aml: Optional[dict] = None


class TurnReq(BaseModel):
    call_id: str
    text: str
    lang: str = "en"


class EndReq(BaseModel):
    call_id: str
    reason: str = "hung_up"


@app.get("/voice-api/health")
def health():
    return {"ok": True}


@app.post("/voice-api/start")
def api_start(req: StartReq):
    call_id = f"web-{uuid.uuid4().hex[:10]}"
    res = start_call(CallInfo(call_id=call_id, channel="voice", phone=req.phone, lang_guess=req.lang, aml=req.aml))
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


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("VOICE_BRIDGE_PORT", "8010")))
