"""Mint a fresh LiveKit room token for a citizen 112 browser call.

Invoked by server.mjs (`POST /api/voice/token`) so the mobile citizen app
connects directly to the running LiveKit voice_agent worker.
"""
import argparse
import json
import os
import secrets
import sys
from datetime import timedelta

from dotenv import load_dotenv

from .config import LANGS


def mint(lang: str = "en", minutes: int = 30) -> dict:
    from livekit import api

    url = os.getenv("LIVEKIT_URL", "").strip()
    key = os.getenv("LIVEKIT_API_KEY", "").strip()
    secret = os.getenv("LIVEKIT_API_SECRET", "").strip()
    if not (url and key and secret):
        raise RuntimeError("Missing LIVEKIT_URL, LIVEKIT_API_KEY or LIVEKIT_API_SECRET in voice_agent/.env")

    room = f"citizen-112-{secrets.token_hex(4)}"
    identity = f"citizen-{secrets.token_hex(3)}"
    token = (
        api.AccessToken(key, secret)
        .with_identity(identity)
        .with_name("Citizen 112")
        .with_attributes({"lang": lang})  # read by telephony.link_language
        .with_room_config(api.RoomConfiguration(departure_timeout=1, empty_timeout=60))
        .with_ttl(timedelta(minutes=minutes))
        .with_grants(api.VideoGrants(room_join=True, room=room, can_publish=True, can_subscribe=True))
        .to_jwt()
    )
    return {"url": url, "token": token, "room": room, "identity": identity, "lang": lang}


def main() -> None:
    parser = argparse.ArgumentParser(description="Mint a LiveKit token for a citizen 112 call.")
    parser.add_argument("--lang", default="en", choices=LANGS)
    args = parser.parse_args()
    load_dotenv(".env")
    try:
        print(json.dumps(mint(args.lang)))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
