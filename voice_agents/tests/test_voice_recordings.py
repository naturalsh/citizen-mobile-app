"""Pre-recorded fixed lines (voice/recordings.py, voice/prerecord.py). No API calls."""
import asyncio
import json

import pytest

import brain
from voice import config, prerecord, recordings

GREEK = brain.fixed_voice_texts("el")
ADVICE = brain.core.ADVICE["earthquake.trapped"]["el"]


@pytest.fixture
def eleven(tmp_path, monkeypatch):
    """ElevenLabs selected, a Greek voice set, recordings in a temporary folder."""
    monkeypatch.setattr(recordings, "DIR", tmp_path / "recordings")
    monkeypatch.setattr(recordings, "USE", True)
    monkeypatch.setattr(config, "TTS_PROVIDER", "elevenlabs")
    monkeypatch.setitem(config.ELEVENLABS_VOICES, "el", "my-greek-clone")
    monkeypatch.setitem(config.ELEVENLABS_VOICES, "tr", "")
    return tmp_path


def fake_recording(text, lang="el", samples=1000):
    path = recordings.path_for(text, lang)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x01\x00" * samples)
    return path


def test_fixed_lines_cover_greeting_phrases_and_advice(tmp_path, monkeypatch):
    monkeypatch.setattr(brain.core, "OUTPUT_DIR", tmp_path)  # start_call writes a report
    assert len(GREEK) == 28  # 2 greetings + hold, handoff, repeat + 23 advice texts
    assert brain.core.PHRASES["hold"]["el"] in GREEK
    assert ADVICE in GREEK
    call = brain.CallInfo(call_id="fx", channel="voice", phone="+30 690", lang_guess="el")
    assert brain.start_call(call).reply_text in GREEK  # the greeting really said matches the recorded one


def test_key_changes_with_anything_that_changes_the_sound(eleven, monkeypatch):
    before = recordings.key(ADVICE, "el")
    assert recordings.key(ADVICE + " ", "el") == before  # surrounding spaces don't matter
    monkeypatch.setattr(config, "ELEVENLABS_SPEED", 1.1)
    assert recordings.key(ADVICE, "el") != before
    monkeypatch.setattr(config, "ELEVENLABS_SPEED", 0.95)
    monkeypatch.setitem(config.ELEVENLABS_VOICES, "el", "another-voice")
    assert recordings.key(ADVICE, "el") != before


def test_split_plays_recorded_advice_then_live_question(eleven):
    path = fake_recording(ADVICE)
    reply = f"{ADVICE} Πόσα άτομα είστε;"
    assert recordings.split(reply, "el", GREEK) == [(ADVICE, path), ("Πόσα άτομα είστε;", None)]
    assert recordings.split(ADVICE + " ", "el", GREEK) == [(ADVICE, path)]  # streamed advice piece


def test_split_speaks_live_when_not_recorded_or_not_elevenlabs(eleven, monkeypatch):
    reply = f"{ADVICE} Πόσα άτομα είστε;"
    assert recordings.split(reply, "el", GREEK) == [(reply, None)]  # nothing recorded yet
    fake_recording(ADVICE)
    assert recordings.split("Πού βρίσκεστε;", "el", GREEK) == [("Πού βρίσκεστε;", None)]
    assert recordings.split(ADVICE, "tr", GREEK) == [(ADVICE, None)]  # no Turkish voice set
    monkeypatch.setattr(config, "TTS_PROVIDER", "cartesia")
    assert recordings.split(ADVICE, "el", GREEK) == [(ADVICE, None)]
    monkeypatch.setattr(config, "TTS_PROVIDER", "elevenlabs")
    monkeypatch.setattr(recordings, "USE", False)
    assert recordings.split(ADVICE, "el", GREEK) == [(ADVICE, None)]


def test_frames_are_20_ms_and_cover_the_whole_recording(eleven):
    path = fake_recording(ADVICE, samples=1000)  # 1000 samples = 2 full frames of 480 + a padded one

    async def read():
        return [f async for f in recordings.frames(path)]

    frames = asyncio.run(read())
    assert len(frames) == 3
    assert all(f.sample_rate == 24_000 and f.samples_per_channel == 480 for f in frames)


def test_record_asks_elevenlabs_once_and_saves(eleven):
    calls = []

    class Response:
        data = iter([b"\x00\x01" * 5, b"\x00\x01" * 5])
        headers = {"x-character-count": "266"}

    class Raw:
        @staticmethod
        def convert(voice_id, **kw):
            calls.append((voice_id, kw))
            from contextlib import nullcontext
            return nullcontext(Response())

    class FakeClient:  # stands in for elevenlabs.ElevenLabs
        class text_to_speech:
            with_raw_response = Raw

    path, charged = recordings.record(ADVICE, "el", FakeClient())
    assert path.read_bytes() == b"\x00\x01" * 10 and charged == 266
    voice_id, kw = calls[0]
    assert voice_id == "my-greek-clone"
    assert (kw["text"], kw["model_id"], kw["language_code"], kw["output_format"]) == (
        ADVICE, config.ELEVENLABS_MODEL, "el", "pcm_24000")
    assert kw["voice_settings"].speed == config.ELEVENLABS_SPEED
    assert recordings.split(ADVICE, "el", GREEK) == [(ADVICE, path)]


def test_prerecord_previews_cost_and_records_nothing_without_yes(eleven, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["prerecord"])
    monkeypatch.setattr(recordings, "record", lambda *a: pytest.fail("recorded without --yes"))
    prerecord.main()
    out = capsys.readouterr().out
    assert "el: 28 fixed lines, 0 recorded, 28 to record" in out
    assert f"{sum(len(t) for t in GREEK):,} characters" in out
    assert "Run again with --yes" in out


def test_prerecord_skips_lines_already_recorded(eleven, monkeypatch):
    for text in GREEK[:20]:
        fake_recording(text)
    assert [t for _, t in prerecord.plan(["el"])] == GREEK[20:]
