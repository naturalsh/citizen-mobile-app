"""Filler filter (voice/fillers.py) and turn-end settings (voice/config.py). No API calls."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from voice import config, fillers


@pytest.mark.parametrize("text", [
    "Εε.", "εεε…", "Μμ", "Εμμ,", "Χμμ.",  # Greek
    "Iıı...", "ııı", "Eee", "Şey...",  # Turkish
    "Um.", "Uhh, umm", "Hmm", "Erm",  # English
    "Euh...", "Heu",  # French
    "Εε, εε... μμ.", "...",
])
def test_only_fillers_leaves_nothing(text):
    assert fillers.clean(text) == ""


@pytest.mark.parametrize("text, expected", [
    ("Εε, Πολιτόπουλος", "Πολιτόπουλος"),
    ("Το σπίτι, εε, έπεσε", "Το σπίτι, έπεσε"),
    ("Είμαι στο Βαθύ, εε", "Είμαι στο Βαθύ"),
    ("Uh, my name is Ava Stone, um.", "my name is Ava Stone"),
    ("Iıı evim yıkıldı", "evim yıkıldı"),
    ("Şey, enkaz altında biri var", "enkaz altında biri var"),
    ("Euh, il y a un incendie", "il y a un incendie"),
])
def test_fillers_are_stripped_from_real_words(text, expected):
    assert fillers.clean(text) == expected


@pytest.mark.parametrize("text", [
    "Ναι", "Όχι", "Evet", "Hayır", "OK", "Oui", "I", "I am trapped",
    "Έπεσε το σπίτι", "Ε-λένη", "Εμμανουήλ", "Μαμά", "εεμ-τέλος",
    "Bir şey oldu",  # "şey" is a real word ("something") after the first word
    "Mhm", "uh-huh", "hı hı",  # mean yes
])
def test_real_words_are_never_stripped(text):
    assert fillers.clean(text) == text


@pytest.mark.parametrize("text", ["Φ Ρ Ε Ι Δ Ε Ρ Ι Κ Η Σ", "Ε, Μ, Π, Ο, Ρ, Ι, Ο, Υ"])
def test_a_spelled_street_keeps_letters_that_look_like_fillers(text):
    """"Ε" and "Μ" are letters when the caller spells a street (brain/spelling.py)."""
    assert fillers.clean(text) == text


@pytest.mark.parametrize("text", ["Ε;", "Hm?", "Euh ?"])
def test_a_filler_asked_as_a_question_is_kept(text):
    """"Ε;" means "what?": the caller wants the last line again."""
    assert fillers.clean(text) != ""


def test_normalize_ignores_case_accents_and_repeats():
    assert fillers.normalize("Εεέ") == "ε"
    assert fillers.normalize("UMMM") == "um"
    assert fillers.normalize("Şey") == "sey"
    assert fillers.normalize("Iıı") == "ı"
    assert fillers.normalize("I") == "i"  # English "I" is not the Turkish filler "ı"


def test_list_has_every_language():
    data = __import__("json").loads(fillers._FILE.read_text(encoding="utf-8"))
    assert set(data["anywhere"]) == set(config.LANGS) == set(data["leading"])


@pytest.mark.parametrize("value, expected", [("stt", "stt"), ("vad", "vad"), ("livekit", None), ("typo", "stt")])
def test_turn_detection_setting(monkeypatch, value, expected):
    monkeypatch.setattr(config, "TURN_DETECTION", value)
    assert config.turn_detection() == expected


def test_soniox_endpoint_options_default_and_clamped(monkeypatch):
    monkeypatch.setattr(config, "TURN_DETECTION", "stt")
    monkeypatch.setattr(config, "SONIOX_MAX_ENDPOINT_DELAY_MS", 2000)
    monkeypatch.setattr(config, "SONIOX_ENDPOINT_SENSITIVITY", -0.2)
    monkeypatch.setattr(config, "SONIOX_ENDPOINT_LATENCY_LEVEL", 0)
    assert config.soniox_endpoint_options() == {"max_endpoint_delay_ms": 2000, "endpoint_sensitivity": -0.2}

    monkeypatch.setattr(config, "SONIOX_MAX_ENDPOINT_DELAY_MS", 9000)
    monkeypatch.setattr(config, "SONIOX_ENDPOINT_SENSITIVITY", -5.0)
    monkeypatch.setattr(config, "SONIOX_ENDPOINT_LATENCY_LEVEL", 7)
    from livekit.plugins import soniox

    options = config.soniox_endpoint_options()
    assert options == {"max_endpoint_delay_ms": 3000, "endpoint_sensitivity": -1.0,
                       "endpoint_latency_adjustment_level": 3}
    soniox.STTOptions(**options)  # the plugin accepts them (it raises outside its ranges)


def test_soniox_defaults_when_turns_end_on_vad(monkeypatch):
    for value in ("vad", "livekit"):
        monkeypatch.setattr(config, "TURN_DETECTION", value)
        assert config.soniox_endpoint_options() == {}


def _agent(monkeypatch):
    """IntakeAgent without LiveKit: the brain and the speaking are fakes."""
    from voice import agent
    from voice.language import LanguageTracker

    monkeypatch.setattr(config, "STREAM_REPLIES", False)
    monkeypatch.setattr(config, "HOLD_AFTER_S", 0)
    intake = agent.IntakeAgent.__new__(agent.IntakeAgent)
    intake.flow = MagicMock(outcome=None, call_id="test")
    intake.flow.reply.return_value = SimpleNamespace(lang="el")
    intake.languages = LanguageTracker("el")
    intake.times = MagicMock()
    intake._last_reply = []
    intake._speak = AsyncMock()
    return intake


def _turn(intake, text):
    asyncio.run(intake.on_user_turn_completed(None, SimpleNamespace(text_content=text)))


def test_filler_only_turn_is_not_sent_to_the_brain(monkeypatch):
    intake = _agent(monkeypatch)
    monkeypatch.setattr(config, "FILLER_FILTER", True)
    _turn(intake, "Εε...")
    intake.flow.reply.assert_not_called()
    intake._speak.assert_not_called()


def test_brain_gets_the_words_without_fillers(monkeypatch):
    intake = _agent(monkeypatch)
    monkeypatch.setattr(config, "FILLER_FILTER", True)
    _turn(intake, "Εε, Πολιτόπουλος")
    assert intake.flow.reply.call_args.args[0] == "Πολιτόπουλος"


def test_filter_off_sends_everything(monkeypatch):
    intake = _agent(monkeypatch)
    monkeypatch.setattr(config, "FILLER_FILTER", False)
    _turn(intake, "Εε, Πολιτόπουλος")
    assert intake.flow.reply.call_args.args[0] == "Εε, Πολιτόπουλος"
