"""Phone-call helpers, no API calls."""
from types import SimpleNamespace

from livekit import rtc

from voice import telephony


def test_transfer_target_needs_a_full_international_number():
    assert telephony.transfer_target("+30 690 000 0000") == "tel:+306900000000"
    assert telephony.transfer_target("+90 (532) 000-0000") == "tel:+905320000000"
    assert telephony.transfer_target("") is None
    assert telephony.transfer_target("6900000000") is None  # no country code
    assert telephony.transfer_target("+30") is None


def test_caller_number_only_from_real_phone_calls():
    from unittest.mock import MagicMock

    sip = SimpleNamespace(kind=rtc.ParticipantKind.PARTICIPANT_KIND_SIP, attributes={"sip.phoneNumber": "+306900000000"})
    browser = SimpleNamespace(kind=rtc.ParticipantKind.PARTICIPANT_KIND_STANDARD, attributes={})
    assert telephony.caller_number(sip) == "+306900000000"
    assert telephony.caller_number(browser) is None
    # Console mode's stand-in participant: attributes return mocks, not strings.
    assert telephony.caller_number(MagicMock()) is None
    sip_mock = MagicMock(kind=rtc.ParticipantKind.PARTICIPANT_KIND_SIP)
    assert telephony.caller_number(sip_mock) is None


def test_phone_callers_are_recognised():
    sip = SimpleNamespace(kind=rtc.ParticipantKind.PARTICIPANT_KIND_SIP)
    browser = SimpleNamespace(kind=rtc.ParticipantKind.PARTICIPANT_KIND_STANDARD)
    assert telephony.is_phone_call(sip)
    assert not telephony.is_phone_call(browser)


def test_a_browser_link_sets_the_starting_language():
    # A Turkish tester's browser call (no phone number) stayed in Greek (2026-10-26).
    from types import SimpleNamespace
    from livekit import rtc
    from voice import telephony
    browser = SimpleNamespace(kind=rtc.ParticipantKind.PARTICIPANT_KIND_STANDARD, attributes={"lang": "tr"})
    assert telephony.link_language(browser) == "tr"
    assert telephony.link_language(SimpleNamespace(kind=browser.kind, attributes={"lang": "de"})) is None
    phone = SimpleNamespace(kind=rtc.ParticipantKind.PARTICIPANT_KIND_SIP, attributes={"lang": "tr"})
    assert telephony.link_language(phone) is None  # a phone call keeps its country code


def test_the_link_carries_its_language(monkeypatch):
    import base64
    import json
    monkeypatch.setenv("LIVEKIT_URL", "wss://example.livekit.cloud")
    monkeypatch.setenv("LIVEKIT_API_KEY", "test-key")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "test-secret-that-is-long-enough-for-hs256")
    from voice.link import make_link
    room, link = make_link("tr", hours=1)
    payload = link.split("token=")[1].split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    assert claims["attributes"] == {"lang": "tr"} and claims["video"]["room"] == room


def test_a_short_call_link_opens_a_new_room_on_every_click(monkeypatch):
    # Reopening a fixed room soon after a call got no agent ("Disconnected", 2026-10-26).
    import urllib.parse
    from fastapi.testclient import TestClient
    monkeypatch.setenv("LIVEKIT_URL", "wss://example.livekit.cloud")
    monkeypatch.setenv("LIVEKIT_API_KEY", "test-key")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "test-secret-that-is-long-enough-for-hs256")
    import channels.messaging as messaging
    from voice.link import short_link
    link = short_link("https://example.ngrok-free.dev", "tr", hours=1)
    client = TestClient(messaging.app)
    path = link.removeprefix("https://example.ngrok-free.dev")
    first, second = (client.get(path, follow_redirects=False) for _ in range(2))
    assert first.status_code == second.status_code == 302
    rooms = [urllib.parse.parse_qs(urllib.parse.urlparse(r.headers["location"]).query)["token"][0] for r in (first, second)]
    assert rooms[0] != rooms[1]  # a new pass, for a new room, each time
    bad = path.replace("sig=", "sig=0")
    assert client.get(bad, follow_redirects=False).status_code == 403
    expired = short_link("https://example.ngrok-free.dev", "tr", hours=-1).removeprefix("https://example.ngrok-free.dev")
    assert client.get(expired, follow_redirects=False).status_code == 403
