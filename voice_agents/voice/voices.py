"""Text-to-speech: which provider and which voice for each language (Docs/Research/04).

Cartesia (sonic-3) is the default for its low latency. Azure is the alternative with named
Greek and Turkish voices (VOICE_TTS=azure). ElevenLabs (VOICE_TTS=elevenlabs) is there for
cloned voices, e.g. the team's own Greek voice, on its fastest model, Flash v2.5.
"""
from livekit.plugins import azure, cartesia, elevenlabs
from livekit.plugins.elevenlabs.tts import DEFAULT_VOICE_ID as ELEVENLABS_DEFAULT_VOICE

from . import config

AZURE_LOCALES = {"el": "el-GR", "tr": "tr-TR", "en": "en-GB", "fr": "fr-FR"}


def options(provider: str, lang: str) -> dict:
    """Settings for a reply in `lang`, as update_options() arguments."""
    if provider == "azure":
        return {"voice": config.AZURE_VOICES[lang], "language": AZURE_LOCALES[lang]}
    if provider == "elevenlabs":
        # Always name a voice: otherwise switching language would keep the last one,
        # e.g. the Greek clone speaking Turkish with a Greek accent.
        return {"voice_id": config.ELEVENLABS_VOICES.get(lang) or ELEVENLABS_DEFAULT_VOICE, "language": lang}
    voice = config.CARTESIA_VOICES.get(lang)
    return {"language": lang, **({"voice": voice} if voice else {})}


def make_tts(lang: str, provider: str = config.TTS_PROVIDER):
    if provider == "azure":
        return azure.TTS(**options("azure", lang))
    if provider == "elevenlabs":
        settings = elevenlabs.VoiceSettings(
            stability=config.ELEVENLABS_STABILITY, similarity_boost=0.75, speed=config.ELEVENLABS_SPEED
        )
        # The plugin itself only looks for ELEVEN_API_KEY; pass the key read from .env.
        key = {"api_key": config.ELEVENLABS_API_KEY} if config.ELEVENLABS_API_KEY else {}
        return elevenlabs.TTS(model=config.ELEVENLABS_MODEL, voice_settings=settings, **key, **options("elevenlabs", lang))
    # Word timestamps only exist for en/de/es/fr on sonic-3 and the call switches language,
    # so they are off for every call (they only time on-screen transcripts, not the audio).
    return cartesia.TTS(model=config.CARTESIA_MODEL, word_timestamps=False, **options("cartesia", lang))


def provider_of(tts) -> str:
    if isinstance(tts, azure.TTS):
        return "azure"
    if isinstance(tts, elevenlabs.TTS):
        return "elevenlabs"
    return "cartesia"


def switch(tts, lang: str) -> None:
    """Point the session's text-to-speech at `lang` before speaking a reply."""
    tts.update_options(**options(provider_of(tts), lang))
