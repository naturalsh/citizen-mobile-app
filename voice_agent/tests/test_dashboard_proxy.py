"""The shared dashboard at the messaging server's address (channels/dashboard_proxy.py). No network:
the dashboard is a fake behind httpx's MockTransport, streaming its answers like a real server."""
import gzip

import httpx
import pytest
from fastapi.testclient import TestClient

from channels import dashboard_proxy
from channels.messaging import app

KEY = "invented-key-123"


@pytest.fixture
def seen(monkeypatch):
    """Requests that reached the (fake) dashboard."""
    requests = []

    def dashboard(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/state":
            return httpx.Response(200, stream=httpx.ByteStream(gzip.compress(b'{"incidents": []}')),
                                  headers={"content-type": "application/json", "content-encoding": "gzip"})
        return httpx.Response(200, stream=httpx.ByteStream(b"<html>page</html>"), headers={
            "content-type": "text/html", "set-cookie": f"dashboard_key={KEY}; HttpOnly; SameSite=strict"})

    monkeypatch.setenv("DASHBOARD_ACCESS_KEY", KEY)
    monkeypatch.setattr(dashboard_proxy, "URL", "http://dashboard.test")
    monkeypatch.setattr(dashboard_proxy, "_client", httpx.AsyncClient(transport=httpx.MockTransport(dashboard)))
    return requests


def test_without_the_key_nothing_reaches_the_dashboard(seen):
    client = TestClient(app)
    assert client.get("/").status_code == 401
    assert client.get("/api/state?key=wrong").status_code == 401
    assert seen == []


def test_with_the_key_the_page_and_its_updates_come_through(seen):
    client = TestClient(app)
    page = client.get(f"/?key={KEY}")
    assert page.status_code == 200 and "page" in page.text
    assert client.cookies.get("dashboard_key") == KEY  # the dashboard's cookie reaches the browser
    state = client.get("/api/state")  # later requests carry the key as that cookie
    assert state.json() == {"incidents": []}  # still compressed on the way: the client unpacked it
    assert [r.url.path for r in seen] == ["/", "/api/state"]
    assert seen[0].url.params["key"] == KEY


def test_texting_and_call_links_are_not_forwarded(seen):
    assert TestClient(app).get("/health").json()["ok"] is True
    assert seen == []


def test_a_dashboard_that_is_down_is_a_502_and_never_breaks_the_server(monkeypatch):
    def down(request):
        raise httpx.ConnectError("refused")
    monkeypatch.setenv("DASHBOARD_ACCESS_KEY", KEY)
    monkeypatch.setattr(dashboard_proxy, "_client", httpx.AsyncClient(transport=httpx.MockTransport(down)))
    client = TestClient(app)
    assert client.get(f"/?key={KEY}").status_code == 502
    assert client.get("/health").status_code == 200


def test_off_switch(seen, monkeypatch):
    monkeypatch.setattr(dashboard_proxy, "URL", "off")
    assert TestClient(app).get(f"/?key={KEY}").status_code == 404 and seen == []


def test_no_key_set_means_no_dashboard(seen, monkeypatch, tmp_path):
    # A dashboard started without --share has no key: it must never be reachable from the internet.
    monkeypatch.delenv("DASHBOARD_ACCESS_KEY")
    monkeypatch.setattr(dashboard_proxy, "KEY_FILE", tmp_path / "missing")
    assert TestClient(app).get("/?key=").status_code == 401 and seen == []
