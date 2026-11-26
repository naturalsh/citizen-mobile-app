"""FastAPI bridge for the embedded Voice_Agents brain (brain/contract.py).

Replaces LiveKit telephony with a JSON HTTP API for the mobile 112 chat + voice-readout UI:
    GET  /api/voice/health
    POST /api/voice/start   -> brain.start_call(CallInfo(channel="voice", ...))
    POST /api/voice/turn    -> brain.turn(call_id, text, lang)
    POST /api/voice/end     -> brain.end_call(call_id, reason)

Run:
    ../Voice_Agents/.venv/bin/uvicorn voice_api:app --host 127.0.0.1 --port 8001
"""

import logging
import os
import uuid
from typing import Literal, Optional

from dotenv import load_dotenv

load_dotenv()

from fastapi import BackgroundTasks, FastAPI, HTTPException  # noqa: E402
from fastapi.concurrency import run_in_threadpool  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from brain import CallInfo, end_call, start_call, turn  # noqa: E402
from brain.contract import EndReason  # noqa: E402
from brain.langs import lang_from_text  # noqa: E402

log = logging.getLogger("voice_api")

app = FastAPI(title="Nature Shield 112 Voice Agent API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

_active_calls: dict[str, str] = {}  # call_id -> current lang


class AmlLocation(BaseModel):
    lat: float
    lon: float
    accuracy_m: Optional[float] = None


class StartRequest(BaseModel):
    lang: Literal["en", "tr", "el", "fr"] = "en"
    phone: str = "web-mobile-112"
    aml: Optional[AmlLocation] = None


class TurnRequest(BaseModel):
    call_id: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=2000)
    lang: Optional[str] = None


class EndRequest(BaseModel):
    call_id: str = Field(min_length=1)
    reason: EndReason = "hung_up"


def _safe_end(call_id: str, reason: EndReason) -> Optional[dict]:
    _active_calls.pop(call_id, None)
    try:
        return end_call(call_id, reason)
    except KeyError:
        return None
    except Exception:
        log.exception("end_call failed for %s", call_id)
        return None


def _summarize_report(report: dict) -> dict:
    """Return non-PII summary fields safe for the citizen chat UI."""
    urgency = report.get("urgency") or {}
    loc = report.get("location") or {}
    return {
        "hazard": report.get("hazard"),
        "urgency": urgency.get("suggested"),
        "reasons": urgency.get("reasons") or [],
        "area": loc.get("area"),
        "address": loc.get("spoken_address") or loc.get("landmark"),
    }


@app.get("/api/voice/health")
def health() -> dict:
    return {
        "ok": True,
        "configured": bool(os.getenv("GEMINI_API_KEY")),
        "active_calls": len(_active_calls),
    }


@app.post("/api/voice/start")
async def api_start(req: StartRequest, background: BackgroundTasks) -> dict:
    call_id = f"mob-{uuid.uuid4().hex[:8]}"
    aml = req.aml.model_dump(exclude_none=True) if req.aml else None
    info = CallInfo(
        call_id=call_id,
        channel="voice",
        phone=req.phone,
        lang_guess=req.lang,
        aml=aml,
    )
    result = await run_in_threadpool(start_call, info)
    if result.action == "handoff":
        background.add_task(_safe_end, call_id, "handed_off")
    else:
        _active_calls[call_id] = result.lang

    return {
        "call_id": call_id,
        "reply_text": result.reply_text,
        "lang": result.lang,
        "action": result.action,
        "handoff_reason": result.handoff_reason,
        "summary": _summarize_report(result.report),
    }


@app.post("/api/voice/turn")
async def api_turn(req: TurnRequest, background: BackgroundTasks) -> dict:
    if req.call_id not in _active_calls:
        raise HTTPException(status_code=404, detail="Call session not found or already ended")

    prev_lang = req.lang or _active_calls[req.call_id]
    detected_lang = lang_from_text(req.text, prev_lang)

    try:
        result = await run_in_threadpool(turn, req.call_id, req.text.strip(), detected_lang)
    except KeyError:
        _active_calls.pop(req.call_id, None)
        raise HTTPException(status_code=404, detail="Call session expired")

    if result.action in ("handoff", "end"):
        reason: EndReason = "handed_off" if result.action == "handoff" else "completed"
        background.add_task(_safe_end, req.call_id, reason)
        _active_calls.pop(req.call_id, None)
    else:
        _active_calls[req.call_id] = result.lang

    return {
        "call_id": req.call_id,
        "reply_text": result.reply_text,
        "lang": result.lang,
        "action": result.action,
        "handoff_reason": result.handoff_reason,
        "summary": _summarize_report(result.report),
    }


@app.post("/api/voice/end")
async def api_end(req: EndRequest) -> dict:
    report = await run_in_threadpool(_safe_end, req.call_id, req.reason)
    return {"ok": True, "summary": _summarize_report(report) if report else None}
