"""The shared dashboard at the messaging server's fixed ngrok address (dashboard/README.md).

Cloudflare's free quick tunnels gave the shared dashboard a new address every few hours
(2026-10-28/29), while the free ngrok plan gives this server one address that never changes. So
every path this server doesn't answer itself (/whatsapp, /sms, /call, /health, /112/...) is forwarded
to the shared copy of the dashboard (`python -m dashboard --share`, port 8003):

    https://<ngrok-address>/?key=<the share key>

The key is checked here as well as in the dashboard, so a copy started without a key (the operator's
own, on 8002) is never reachable from the internet, even if MESSAGING_DASHBOARD points at it.
MESSAGING_DASHBOARD=off stops forwarding. Texting never waits on it: a dashboard that is down
answers 502 here and nothing else changes.
"""
import os
import secrets
from pathlib import Path

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

URL = os.getenv("MESSAGING_DASHBOARD", "http://127.0.0.1:8003").rstrip("/")
KEY_FILE = Path("output") / "dashboard_share_key"  # written by `python -m dashboard --share`
TIMEOUT_S = 15.0
# Only what the page needs crosses, both ways: cookies (the key), caching and compression.
REQUEST_HEADERS = ("accept", "accept-encoding", "content-type", "cookie", "if-none-match", "if-modified-since")
RESPONSE_HEADERS = ("content-type", "content-encoding", "cache-control", "etag", "last-modified")

router = APIRouter()
_client: httpx.AsyncClient | None = None


def share_key() -> str:
    """The shared dashboard's key, read on every request since --share may start after this server."""
    try:
        return os.getenv("DASHBOARD_ACCESS_KEY") or KEY_FILE.read_text().strip()
    except OSError:
        return ""


def _page(text: str, status: int) -> HTMLResponse:
    return HTMLResponse(f"<h1>112 dashboard</h1><p>{text}</p>", status_code=status)


@router.api_route("/{path:path}", methods=["GET", "POST"], include_in_schema=False)
async def dashboard(path: str, request: Request) -> Response:
    global _client
    if URL == "off":
        return Response(status_code=404)
    key = share_key()
    given = request.query_params.get("key") or request.cookies.get("dashboard_key") or ""
    if not key or not secrets.compare_digest(given, key):
        return _page("This view needs the full link, with its key.", 401)
    _client = _client or httpx.AsyncClient(timeout=TIMEOUT_S)
    upstream = _client.build_request(
        request.method, f"{URL}/{path}", params=request.url.query or None, content=await request.body(),
        headers={h: v for h in REQUEST_HEADERS if (v := request.headers.get(h))})
    try:
        answer = await _client.send(upstream, stream=True)
        body = b"".join([chunk async for chunk in answer.aiter_raw()])  # still compressed: passed on as is
        await answer.aclose()
    except httpx.HTTPError:
        return _page("The dashboard isn't running on this computer right now.", 502)
    response = Response(body, status_code=answer.status_code,
                        headers={h: v for h in RESPONSE_HEADERS if (v := answer.headers.get(h))})
    for cookie in answer.headers.get_list("set-cookie"):
        response.headers.append("set-cookie", cookie)
    return response
