"""Operator dashboard: a small web app over the brain's reports (see dashboard/README.md).

    .venv/bin/python -m dashboard            # live: output/reports
    .venv/bin/python -m dashboard --demo     # the eval test calls, replayed as the last 40 minutes

The page (static/) polls /api/state every 2 seconds (10 over the internet), compressed. Operators claim incidents and confirm,
change or escalate the AI's urgency per call; those decisions are stored apart from the
reports (store.py). The "Pause AI" switch stops the agent on every channel, and "Surge mode"
sets how readily it hands callers to a person (brain/control.py).
It listens on 127.0.0.1 only: there is no login, so it must not be exposed to a network.
A copy can be shared with someone on the same Wi-Fi (--share): the full dashboard, but every
request needs the access key from its link.
"""
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from brain import budget, control

from . import data
from .geocode import Geocoder, locate
from .store import OperatorStore

STATIC = Path(__file__).parent / "static"

Operator = Field(min_length=1, max_length=40)


class ClaimRequest(BaseModel):
    incident_id: str
    operator: str = Operator
    claim: bool = True


class DecisionRequest(BaseModel):
    call_id: str
    action: Literal["confirm", "change", "escalate"]
    level: Optional[Literal["life_threat", "urgent", "needs_help", "information"]] = None
    operator: str = Operator


class ResolveRequest(BaseModel):
    incident_id: str
    operator: str = Operator
    resolved: bool = True


class NoteRequest(BaseModel):
    incident_id: str
    operator: str = Operator
    text: str = Field(min_length=1, max_length=300)


class NoteUndoRequest(BaseModel):
    note_id: int
    operator: str = Operator


class UndoRequest(BaseModel):
    call_id: str
    operator: str = Operator


class HandoffModeRequest(BaseModel):
    mode: str
    operator: str = Operator


class PauseRequest(BaseModel):
    paused: bool
    operator: str = Operator


def create_app(output_dir: Path, demo: bool = False, geocoder: Geocoder | None = None,
               access_key: str | None = None) -> FastAPI:
    """output_dir holds reports/ and transcripts/ (output/, or output/eval/brain in demo mode).

    access_key: required on every request, from the shared link (?key=...) and then a cookie.
    """
    reports = data.ReportFolder(output_dir / "reports")
    store = OperatorStore(output_dir / "operator.sqlite")
    geocoder = geocoder or Geocoder(Path("output") / "geocode.sqlite")  # places are shared between modes
    app = FastAPI(title="112 operator dashboard")
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    # One update was 35 KB, 6 KB compressed: over ngrok's free plan that is the monthly data allowance.
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    if access_key:
        @app.middleware("http")
        async def need_the_key(request, call_next):
            # Added last, so it runs first. The key comes in the shared link and is kept as a cookie,
            # so the page's own requests carry it too.
            given = request.query_params.get("key") or request.cookies.get("dashboard_key") or ""
            if not secrets.compare_digest(given, access_key):
                return HTMLResponse("<h1>112 dashboard</h1><p>This view needs the full link, with its key.</p>",
                                    status_code=401)
            response = await call_next(request)
            if request.query_params.get("key"):
                response.set_cookie("dashboard_key", access_key, httponly=True, samesite="strict")
            return response

    @app.middleware("http")
    async def always_fresh(request, call_next):
        # Browsers must check for a newer page after an update (cheap: an unchanged file is a 304).
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    def current() -> tuple[list[dict], dict]:
        decisions, claims, notes = store.decisions(), store.claims(), store.notes()
        found = reports.read()
        # A call that joined an event since it was taken or noted: carry those over to the event.
        moved = [(f"call:{r['call_id']}", r["event_id"]) for r in found if r.get("event_id")]
        moved = [(old, new) for old, new in moved if old in claims or old in notes]
        for old, new in moved:
            store.move(old, new)
        if moved:
            claims, notes = store.claims(), store.notes()
        incidents = data.build_incidents(found, decisions, claims,
                                         lambda i: locate(i, geocoder), datetime.now(timezone.utc), demo,
                                         resolutions=store.resolutions(), notes=notes)
        return incidents, decisions

    @app.get("/")
    def page() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/api/state")
    def state() -> dict:
        incidents, _ = current()
        usage = budget.status()
        return {
            "now": data.iso(datetime.now(timezone.utc)),
            "demo": demo,
            "paused": control.pause_info(),
            "handoff": control.handoff_info(),
            "budget": usage,
            "geocoding": {"enabled": geocoder.enabled, "pending": geocoder.pending()},
            "counts": data.counts(incidents),
            "incidents": incidents,
        }

    @app.get("/api/calls/{call_id}/transcript")
    def transcript(call_id: str) -> dict:
        path = output_dir / "transcripts" / f"{call_id}.json"
        if not path.resolve().is_relative_to((output_dir / "transcripts").resolve()) or not path.exists():
            raise HTTPException(404, "no transcript")
        return {"call_id": call_id, "lines": json.loads(path.read_text(encoding="utf-8")),
                "decisions": store.history(call_id)}

    @app.post("/api/claims")
    def claim(req: ClaimRequest) -> dict:
        if req.claim:
            return {"incident_id": req.incident_id, "claim": store.claim(req.incident_id, req.operator.strip())}
        store.release(req.incident_id)
        return {"incident_id": req.incident_id, "claim": None}

    @app.post("/api/decisions")
    def decide(req: DecisionRequest) -> dict:
        incidents, _ = current()
        call = next((c for i in incidents for c in i["calls"] if c["call_id"] == req.call_id), None)
        if call is None:
            raise HTTPException(404, "unknown call")
        if req.action == "change" and not req.level:
            raise HTTPException(422, "a change needs a level")
        level = req.level if req.action == "change" else None
        if req.action == "confirm":  # confirming keeps the AI's level, or an earlier operator level
            level = call["level"]
            if not level:
                raise HTTPException(422, "nothing to confirm: the AI has not suggested a level yet")
        return store.decide(req.call_id, req.action, level, req.operator.strip())

    @app.post("/api/decisions/undo")
    def undo(req: UndoRequest) -> dict:
        undone = store.undo(req.call_id, req.operator.strip())
        if not undone:
            raise HTTPException(409, "nothing to undo: only your own decision from the last 5 minutes can be undone")
        return {"undone": undone}

    def known_incident(incident_id: str) -> None:
        if incident_id not in {i["id"] for i in current()[0]}:
            raise HTTPException(404, "unknown incident")

    @app.post("/api/resolve")
    def resolve(req: ResolveRequest) -> dict:
        known_incident(req.incident_id)
        if req.resolved:
            return {"incident_id": req.incident_id, "resolved": store.resolve(req.incident_id, req.operator.strip())}
        store.reopen(req.incident_id)
        return {"incident_id": req.incident_id, "resolved": None}

    @app.post("/api/notes")
    def add_note(req: NoteRequest) -> dict:
        known_incident(req.incident_id)
        text = req.text.strip()
        if not text:
            raise HTTPException(422, "the note is empty")
        return store.add_note(req.incident_id, req.operator.strip(), text)

    @app.post("/api/notes/undo")
    def undo_note(req: NoteUndoRequest) -> dict:
        if not store.delete_note(req.note_id, req.operator.strip()):
            raise HTTPException(409, "only your own note from the last 5 minutes can be undone")
        return {"deleted": req.note_id}

    @app.post("/api/pause")
    def pause(req: PauseRequest) -> dict:
        control.set_paused(req.paused, req.operator.strip())
        return {"paused": control.pause_info()}

    @app.post("/api/handoff-mode")
    def handoff_mode(req: HandoffModeRequest) -> dict:
        try:
            return control.set_handoff_mode(req.mode, req.operator.strip())
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    return app
