"""Voice choice per provider and language, no API calls."""
from voice import config, voices


def test_azure_has_a_named_voice_and_locale_for_every_language():
    for lang in config.LANGS:
        opts = voices.options("azure", lang)
        assert opts["language"].startswith(lang + "-")
        assert opts["voice"].startswith(opts["language"])  # e.g. el-GR-AthinaNeural in el-GR


def test_azure_greek_and_turkish_defaults():
    assert voices.options("azure", "el")["voice"] == "el-GR-AthinaNeural"
    assert voices.options("azure", "tr")["voice"] == "tr-TR-EmelNeural"


def test_cartesia_sends_language_and_voice_only_when_set(monkeypatch):
    monkeypatch.setitem(config.CARTESIA_VOICES, "el", "")
    assert voices.options("cartesia", "el") == {"language": "el"}
    monkeypatch.setitem(config.CARTESIA_VOICES, "tr", "voice-id-123")
    assert voices.options("cartesia", "tr") == {"language": "tr", "voice": "voice-id-123"}


def test_elevenlabs_uses_the_voice_set_for_each_language(monkeypatch):
    monkeypatch.setitem(config.ELEVENLABS_VOICES, "el", "my-greek-clone")
    monkeypatch.setitem(config.ELEVENLABS_VOICES, "tr", "turkish-voice")
    assert voices.options("elevenlabs", "el") == {"voice_id": "my-greek-clone", "language": "el"}
    assert voices.options("elevenlabs", "tr") == {"voice_id": "turkish-voice", "language": "tr"}


def test_elevenlabs_falls_back_to_the_default_voice_instead_of_keeping_the_last(monkeypatch):
    monkeypatch.setitem(config.ELEVENLABS_VOICES, "fr", "")
    assert voices.options("elevenlabs", "fr")["voice_id"] == voices.ELEVENLABS_DEFAULT_VOICE


def test_elevenlabs_switches_voice_with_the_language(monkeypatch):
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "not-a-real-key")  # building the client makes no request
    monkeypatch.setitem(config.ELEVENLABS_VOICES, "el", "my-greek-clone")
    monkeypatch.setitem(config.ELEVENLABS_VOICES, "tr", "turkish-voice")
    tts = voices.make_tts("el", "elevenlabs")
    assert voices.provider_of(tts) == "elevenlabs"
    assert (tts._opts.model, tts._opts.voice_id) == (config.ELEVENLABS_MODEL, "my-greek-clone")
    voices.switch(tts, "tr")
    assert (tts._opts.voice_id, tts._opts.language) == ("turkish-voice", "tr")


def test_elevenlabs_key_from_the_sdk_name_reaches_the_plugin(monkeypatch):
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "key-from-elevenlabs-cli")
    assert voices.make_tts("el", "elevenlabs")._opts.api_key == "key-from-elevenlabs-cli"
