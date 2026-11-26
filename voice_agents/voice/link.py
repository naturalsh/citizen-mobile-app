"""A link anyone can open in a browser to call the agent, for testing without a phone line.

    .venv/bin/python -m voice.link                 # Greek, valid 12 hours
    .venv/bin/python -m voice.link --lang tr --hours 3

With PUBLIC_BASE_URL set (the messaging server's tunnel, channels/README.md) it prints a short
link to that server instead: every click makes a pass for a NEW room. LiveKit sends the agent
only into a new room, and reopening a fixed room soon after a call joined it without an agent
("Disconnected", 2026-10-26). The short link is signed with LIVEKIT_API_SECRET, so only links
made here work, and it stops working after --hours.

It opens LiveKit Meet with a pass for one room, signed locally with LIVEKIT_API_KEY and
LIVEKIT_API_SECRET (nothing is sent anywhere). The agent joins by itself. The pass carries the
language the call starts in: a browser call has no phone number, and a Turkish tester's call
stayed in Greek (2026-10-26). One room per link, so one call at a time; it can be reopened.

LiveKit sends the agent only when a room is created. An empty room used to stay open for a
while after a call, so reopening the link joined it without an agent ("Disconnected"); the
pass now closes the room as soon as the caller leaves.
"""
import argparse
import hashlib
import hmac
import os
import secrets
import time
import urllib.parse
from datetime import timedelta

from dotenv import load_dotenv

from .config import LANGS


def make_link(lang: str = "el", hours: float = 12) -> tuple[str, str]:
    """(room, link)."""
    from livekit import api

    room = f"test-call-{secrets.token_hex(3)}"
    token = (
        api.AccessToken()
        .with_identity(f"tester-{secrets.token_hex(2)}")
        .with_name("Tester")
        .with_attributes({"lang": lang})  # read by telephony.link_language
        # Close the room right after the call, so the next opening creates it again with an agent.
        .with_room_config(api.RoomConfiguration(departure_timeout=1, empty_timeout=60))
        .with_ttl(timedelta(hours=hours))
        .with_grants(api.VideoGrants(room_join=True, room=room, can_publish=True, can_subscribe=True))
        .to_jwt()
    )
    query = urllib.parse.urlencode({"liveKitUrl": os.environ["LIVEKIT_URL"], "token": token})
    return room, f"https://meet.livekit.io/custom?{query}"


def _signature(lang: str, expires: int) -> str:
    secret = os.environ["LIVEKIT_API_SECRET"].encode()
    return hmac.new(secret, f"call|{lang}|{expires}".encode(), hashlib.sha256).hexdigest()[:32]


def short_link(base_url: str, lang: str = "el", hours: float = 12) -> str:
    """A link to the messaging server's /call: a fresh room on every click (see above)."""
    expires = int(time.time() + hours * 3600)
    query = urllib.parse.urlencode({"lang": lang, "expires": expires, "sig": _signature(lang, expires)})
    return f"{base_url.rstrip('/')}/call?{query}"


def check_short_link(lang: str, expires: int, sig: str) -> bool:
    """True if a /call link was made with our secret, for a supported language, and hasn't expired."""
    if lang not in LANGS or expires < time.time() or not os.getenv("LIVEKIT_API_SECRET"):
        return False
    return hmac.compare_digest(sig, _signature(lang, expires))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lang", default="el", choices=LANGS, help="the language the call starts in")
    parser.add_argument("--hours", type=float, default=12, help="how long the link works")
    args = parser.parse_args()
    load_dotenv(".env")
    if base := os.getenv("PUBLIC_BASE_URL"):
        print(f"Starts in {args.lang}, a new room on every click, works for {args.hours:g} hours "
              "(needs the messaging server and its tunnel running):")
        print(short_link(base, args.lang, args.hours))
        return
    room, link = make_link(args.lang, args.hours)
    print(f"Room {room}, starts in {args.lang}, works for {args.hours:g} hours "
          "(one room: wait a few seconds after a call before reopening):")
    print(link)


if __name__ == "__main__":
    main()
