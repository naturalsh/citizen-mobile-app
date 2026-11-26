"""Voice settings from .env, and the checklist of keys still missing.

The checklist is printed every time the worker starts (and by `python -m voice.check`),
so it is always clear which keys are needed for a real call. Only names are printed,
never values.
"""
import os

from dotenv import load_dotenv

load_dotenv()

LANGS = ["el", "tr", "en", "fr"]

# Phone number used for browser and console calls, which have no caller ID.
# Its country code sets the first language guess (+30 Greek, +90 Turkish).
TEST_PHONE = os.getenv("VOICE_TEST_PHONE", "+30 690 000 0000")

SONIOX_MODEL = os.getenv("SONIOX_MODEL", "stt-rt-v5")
# Empty = Soniox's default (US) server. An EU-region project needs wss://stt-rt.eu.soniox.com/transcribe-websocket
SONIOX_BASE_URL = os.getenv("SONIOX_BASE_URL", "")
# When the caller's turn ends. "stt" (default): Soniox's endpoint detection, which listens for
# hesitation and intonation, so "εε…" plus a pause doesn't end the turn. "vad": silence only
# (Silero VAD + LiveKit's 0.5 s delay). "livekit": LiveKit's own audio turn detector, the
# setting used before; it has no Greek.
TURN_DETECTION = os.getenv("VOICE_TURN_DETECTION", "stt").lower()
# Soniox endpoint settings, used when VOICE_TURN_DETECTION=stt
# (https://soniox.com/docs/stt/rt/endpoint-detection).
# Longest wait after speech before the turn ends, 500-3000 ms (Soniox's default 2000).
SONIOX_MAX_ENDPOINT_DELAY_MS = int(os.getenv("SONIOX_MAX_ENDPOINT_DELAY_MS", "1500"))
# -1.0..1.0, Soniox's default 0.0. Lower = fewer, later endpoints: Soniox suggests it for
# frequent pauses and slow speech, as with a frightened caller. -0.2 with 2000 ms made callers
# wait 2.8 s for each reply in a test call (2026-10-24), so back to the default with 1500 ms.
SONIOX_ENDPOINT_SENSITIVITY = float(os.getenv("SONIOX_ENDPOINT_SENSITIVITY", "0.0"))
# 0-3, Soniox's default 0. Higher = earlier endpoints; Soniox advises against it with a
# negative sensitivity.
SONIOX_ENDPOINT_LATENCY_LEVEL = int(os.getenv("SONIOX_ENDPOINT_LATENCY_LEVEL", "0"))
# Ignore turns that are only "εε", "um", "ıı"... and strip fillers before the brain (voice/fillers.py).
FILLER_FILTER = os.getenv("VOICE_FILLER_FILTER", "on") != "off"
# Log every final sentence speech-to-text hears, before the brain sees it: a test call lost the
# caller's swearing somewhere between Soniox and the transcript, with no way to tell where.
# The log holds what callers say (it stays on this machine); "off" for real callers.
LOG_HEARD = os.getenv("VOICE_LOG_HEARD", "on") != "off"
# Handoffs on phone calls are transferred here, e.g. "+30 690 000 0000". Empty = hang up instead.
OPERATOR_NUMBER = os.getenv("OPERATOR_NUMBER", "")
# LiveKit Cloud noise cancellation (telephony model on phone lines). "off" on a self-hosted server.
NOISE_CANCELLATION = os.getenv("VOICE_NOISE_CANCELLATION", "on") != "off"
# Speak the brain's reply while it is still being written (brain.turn_stream). "off" waits for
# the whole reply as before (issue #4).
STREAM_REPLIES = os.getenv("VOICE_STREAM_REPLIES", "on") != "off"
# If the caller has heard nothing this many seconds after they stopped, say the brain's
# "one moment" line (issue #2). 0 = never. 1.5 s played it 3 times in one test call, and the
# real reply then waited for it to finish.
HOLD_AFTER_S = float(os.getenv("VOICE_HOLD_AFTER_S", "2.5"))
# When this computer takes no new calls (voice/load.py): at this many calls at once, or when the
# CPU stays above this share. LiveKit's own rule (CPU over 70%) turned calls away while the laptop
# was only busy with other apps, e.g. recording the screen.
MAX_CALLS = int(os.getenv("VOICE_MAX_CALLS", "3"))
CPU_LIMIT = float(os.getenv("VOICE_CPU_LIMIT", "0.95"))

# Text-to-speech provider: "cartesia" (default), "azure" or "elevenlabs".
TTS_PROVIDER = os.getenv("VOICE_TTS", "cartesia").lower()
CARTESIA_MODEL = os.getenv("CARTESIA_MODEL", "sonic-3")  # sonic-3 is the first with Greek
# One Cartesia voice per language, picked in the Cartesia dashboard. Empty = Cartesia's default voice.
CARTESIA_VOICES = {lang: os.getenv(f"CARTESIA_VOICE_{lang.upper()}", "") for lang in LANGS}
# Azure: named neural voices per language, overridable with AZURE_VOICE_EL etc.
_AZURE_DEFAULTS = {
    "el": "el-GR-AthinaNeural",
    "tr": "tr-TR-EmelNeural",
    "en": "en-GB-SoniaNeural",
    "fr": "fr-FR-DeniseNeural",
}
AZURE_VOICES = {lang: os.getenv(f"AZURE_VOICE_{lang.upper()}") or voice for lang, voice in _AZURE_DEFAULTS.items()}
# ElevenLabs key: set by `npx @elevenlabs/cli onboard` as ELEVENLABS_API_KEY (the SDK's name).
# ELEVEN_API_KEY (the LiveKit plugin's name) still works.
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY") or os.getenv("ELEVEN_API_KEY", "")
# ElevenLabs: Flash v2.5 is their fastest model and has Greek and Turkish.
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_flash_v2_5")
# One voice per language, e.g. your own clone for Greek. Empty = ElevenLabs' default voice.
ELEVENLABS_VOICES = {lang: os.getenv(f"ELEVENLABS_VOICE_{lang.upper()}", "") for lang in LANGS}
# A little slower than normal, for a noisy phone line. 0.95 sounded rushed in the first console
# calls; 0.6 stability / 0.85 speed then sounded flat and slow in a friend's test call; 0.45 /
# 0.9 sounded angry at the end of sentences (2026-10-24), so 0.6 again at 0.9. Speed
# range 0.7-1.2. Changing either makes the pre-recorded lines play live until
# `python -m voice.prerecord` records them again.
ELEVENLABS_STABILITY = float(os.getenv("ELEVENLABS_STABILITY", "0.6"))
ELEVENLABS_SPEED = float(os.getenv("ELEVENLABS_SPEED", "0.9"))

_LIVEKIT = "https://cloud.livekit.io -> project -> Settings -> Keys"
_CARTESIA_VOICES = "https://play.cartesia.ai/voices (copy the voice ID)"
_AZURE = "https://portal.azure.com -> create a Speech resource -> Keys and Endpoint"
_ELEVEN_VOICES = "https://elevenlabs.io/app -> Voices -> the voice -> copy its Voice ID"

# (name, what it is for, where to get it, required for a call)
KEYS = [
    ("LIVEKIT_URL", "LiveKit Cloud project URL, wss://... (not needed for `console` mode)", _LIVEKIT, True),
    ("LIVEKIT_API_KEY", "LiveKit Cloud API key", _LIVEKIT, True),
    ("LIVEKIT_API_SECRET", "LiveKit Cloud API secret", _LIVEKIT, True),
    (
        "SONIOX_API_KEY",
        "speech-to-text; permission 'Speech-to-text, real-time' only, US-region project",
        "https://console.soniox.com -> project -> API keys",
        True,
    ),
    ("CARTESIA_API_KEY", "text-to-speech (VOICE_TTS=cartesia)", "https://play.cartesia.ai/keys", TTS_PROVIDER == "cartesia"),
    ("GEMINI_API_KEY", "the brain", "https://aistudio.google.com/app/apikey", True),
    ("CARTESIA_VOICE_EL", "Greek voice ID (else Cartesia's default voice)", _CARTESIA_VOICES, False),
    ("CARTESIA_VOICE_TR", "Turkish voice ID", _CARTESIA_VOICES, False),
    ("CARTESIA_VOICE_EN", "English voice ID", _CARTESIA_VOICES, False),
    ("CARTESIA_VOICE_FR", "French voice ID", _CARTESIA_VOICES, False),
    ("ELEVENLABS_API_KEY", "text-to-speech (VOICE_TTS=elevenlabs)",
     "npx -y @elevenlabs/cli@latest onboard init (signs in and saves the key)", TTS_PROVIDER == "elevenlabs"),
    ("ELEVENLABS_VOICE_EL", "Greek ElevenLabs voice ID, e.g. your clone (else the default voice)", _ELEVEN_VOICES, False),
    ("ELEVENLABS_VOICE_TR", "Turkish ElevenLabs voice ID", _ELEVEN_VOICES, False),
    ("AZURE_SPEECH_KEY", "text-to-speech (VOICE_TTS=azure)", _AZURE, TTS_PROVIDER == "azure"),
    ("AZURE_SPEECH_REGION", "region of that Speech resource, e.g. westeurope", _AZURE, TTS_PROVIDER == "azure"),
    ("OPERATOR_NUMBER", "phone that handoffs are transferred to, +<country><number>",
     "the phone of whoever plays the operator in the demo", False),
]


def turn_detection() -> str | None:
    """AgentSession's turn_detection: "stt" or "vad"; None leaves LiveKit's own choice."""
    if TURN_DETECTION == "livekit":
        return None
    return "vad" if TURN_DETECTION == "vad" else "stt"


def soniox_endpoint_options() -> dict:
    """Endpoint settings for soniox.STTOptions; empty (Soniox's defaults) unless turns end on Soniox.

    Values are clamped to Soniox's ranges, because the plugin raises on anything outside them
    and a typo in .env must not stop the worker. Sensitivity and latency level are only sent
    when they differ from Soniox's defaults: models before stt-rt-v5 reject them.
    """
    if turn_detection() != "stt":
        return {}
    options: dict = {"max_endpoint_delay_ms": min(max(SONIOX_MAX_ENDPOINT_DELAY_MS, 500), 3000)}
    if sensitivity := min(max(SONIOX_ENDPOINT_SENSITIVITY, -1.0), 1.0):
        options["endpoint_sensitivity"] = sensitivity
    if level := min(max(SONIOX_ENDPOINT_LATENCY_LEVEL, 0), 3):
        options["endpoint_latency_adjustment_level"] = level
    return options


def checklist() -> str:
    lines = ["Voice keys checklist (.env):"]
    for name, purpose, where, required in KEYS:
        mark = "x" if os.getenv(name) else " "
        need = "" if required else " (optional)"
        lines.append(f"  [{mark}] {name}: {purpose}{need}")
        if mark == " ":
            lines.append(f"        get it: {where}")
    return "\n".join(lines)


def missing_required() -> list[str]:
    return [name for name, _, _, required in KEYS if required and not os.getenv(name)]
