"""Pre-recorded audio for the lines the brain says word for word (greeting, advice, handoff...).

With VOICE_TTS=elevenlabs, every spoken character costs ElevenLabs credits and the first
audio of a line takes a moment to arrive. The fixed lines (brain.fixed_voice_texts) make up
a large share of each call, so they are recorded once with voice/prerecord.py and played
from disk; everything else the brain says is still spoken live.

A recording is found by the exact text plus everything that changes the sound (model, voice,
stability, speed), so changing any of them simply misses the recording and the line is
spoken live until it is recorded again. Recordings are your voice: they are kept out of git
(voice/recordings/ is in .gitignore) and can be regenerated at any time.
"""
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import AsyncIterator

from . import config

log = logging.getLogger("voice")

DIR = Path(os.getenv("VOICE_RECORDINGS_DIR", Path(__file__).parent / "recordings"))
SAMPLE_RATE = 24_000  # ElevenLabs "pcm_24000": raw 16-bit mono
FRAME_MS = 20
USE = os.getenv("VOICE_RECORDINGS", "on") != "off"  # "off" speaks every line live


def _settings(lang: str) -> dict:
    """Everything that changes how a line sounds, for the current .env."""
    return {
        "provider": "elevenlabs",
        "model": config.ELEVENLABS_MODEL,
        "voice": config.ELEVENLABS_VOICES.get(lang) or "",
        "stability": config.ELEVENLABS_STABILITY,
        "speed": config.ELEVENLABS_SPEED,
        "lang": lang,
    }


def key(text: str, lang: str) -> str:
    raw = json.dumps({**_settings(lang), "text": text.strip()}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def path_for(text: str, lang: str) -> Path:
    return DIR / f"{key(text, lang)}.pcm"


def available(lang: str) -> bool:
    """Recordings only apply to ElevenLabs with a voice chosen for this language."""
    return USE and config.TTS_PROVIDER == "elevenlabs" and bool(config.ELEVENLABS_VOICES.get(lang))


def split(text: str, lang: str, fixed: list[str]) -> list[tuple[str, Path | None]]:
    """Cut a reply into (text, recording or None) parts.

    The brain says a fixed line either alone (greeting, handoff, an advice piece when
    streaming) or at the start of a reply (advice followed by the model's question).
    """
    if not available(lang):
        return [(text, None)]
    stripped = text.strip()
    for line in sorted(fixed, key=len, reverse=True):  # longest first: advice, not a shorter line inside it
        if stripped.startswith(line):
            path = path_for(line, lang)
            if not path.exists():
                break
            rest = stripped[len(line):].strip()
            return [(line, path)] + ([(rest, None)] if rest else [])
    return [(text, None)]


async def frames(path: Path) -> AsyncIterator:
    """Audio frames of a recording, for session.say(text, audio=...)."""
    from livekit import rtc  # here, so the rest of this module works without LiveKit

    samples = SAMPLE_RATE * FRAME_MS // 1000
    data = path.read_bytes()
    step = samples * 2  # 16-bit mono
    for start in range(0, len(data), step):
        chunk = data[start:start + step]
        if len(chunk) < step:
            chunk += b"\0" * (step - len(chunk))  # pad the last frame
        yield rtc.AudioFrame(chunk, SAMPLE_RATE, 1, samples)


def client():
    """The ElevenLabs SDK client, with the key from .env (ELEVENLABS_API_KEY)."""
    from elevenlabs import ElevenLabs

    return ElevenLabs(api_key=config.ELEVENLABS_API_KEY or None)


def record(text: str, lang: str, eleven=None) -> tuple[Path, int | None]:
    """Ask ElevenLabs to say `text` once and save it. One request; costs the text's characters.

    Returns the file and the characters ElevenLabs charged (from its x-character-count header).
    """
    from elevenlabs import VoiceSettings

    s = _settings(lang)
    eleven = eleven or client()
    with eleven.text_to_speech.with_raw_response.convert(
        s["voice"],
        text=text.strip(),
        model_id=s["model"],
        language_code=lang,
        voice_settings=VoiceSettings(stability=s["stability"], similarity_boost=0.75, speed=s["speed"]),
        output_format="pcm_24000",
    ) as response:
        audio = b"".join(response.data)
        charged = response.headers.get("x-character-count")
    if not audio:
        raise RuntimeError("ElevenLabs returned no audio")
    path = path_for(text, lang)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(audio)
    return path, int(charged) if charged and str(charged).isdigit() else None
