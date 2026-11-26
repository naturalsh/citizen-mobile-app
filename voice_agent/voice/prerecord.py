"""Record the brain's fixed lines once with ElevenLabs, so calls play them from disk.

    .venv/bin/python -m voice.prerecord                # show what would be recorded and its cost
    .venv/bin/python -m voice.prerecord --yes          # record what is missing
    .venv/bin/python -m voice.prerecord --yes --lang el

Only languages with an ElevenLabs voice in .env (ELEVENLABS_VOICE_EL etc.) are recorded.
Lines already recorded with the same voice and settings are skipped, so running it again
only costs the lines that changed. See voice/recordings.py.
"""
import argparse
import sys
import time

from . import config, recordings

import brain  # noqa: E402  (after config, which loads .env)


def plan(langs: list[str]) -> list[tuple[str, str]]:
    """(lang, text) for every fixed line not recorded yet."""
    return [(lang, t) for lang in langs for t in brain.fixed_voice_texts(lang) if not recordings.path_for(t, lang).exists()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yes", action="store_true", help="really record (costs ElevenLabs characters)")
    parser.add_argument("--lang", help="comma-separated, e.g. el,tr (default: every language with a voice set)")
    args = parser.parse_args()

    with_voice = [lang for lang in config.LANGS if config.ELEVENLABS_VOICES.get(lang)]
    langs = args.lang.split(",") if args.lang else with_voice
    missing_voice = [lang for lang in langs if lang not in with_voice]
    if missing_voice:
        sys.exit(f"No ElevenLabs voice set for {', '.join(missing_voice)}: add ELEVENLABS_VOICE_{missing_voice[0].upper()} to .env")
    if not langs:
        sys.exit("No ElevenLabs voices in .env yet (ELEVENLABS_VOICE_EL, ELEVENLABS_VOICE_TR, ...).")

    todo = plan(langs)
    for lang in langs:
        total = brain.fixed_voice_texts(lang)
        left = [t for lg, t in todo if lg == lang]
        print(f"{lang}: {len(total)} fixed lines, {len(total) - len(left)} recorded, "
              f"{len(left)} to record ({sum(len(t) for t in left):,} characters)")
    chars = sum(len(t) for _, t in todo)
    print(f"\nTotal to record: {len(todo)} lines, {chars:,} characters of ElevenLabs credit "
          f"(model {config.ELEVENLABS_MODEL}; some plans charge half a credit per character on Flash).")
    if config.TTS_PROVIDER != "elevenlabs":
        print("Note: VOICE_TTS is not 'elevenlabs', so calls won't use these recordings until you switch it.")
    if not todo:
        print("Nothing to do.")
        return
    if not args.yes:
        print("\nNothing recorded. Run again with --yes to record.")
        return

    if not config.ELEVENLABS_API_KEY:
        sys.exit("ELEVENLABS_API_KEY is missing in .env: run `npx -y @elevenlabs/cli@latest onboard init`")
    eleven, charged = recordings.client(), 0
    for i, (lang, text) in enumerate(todo, 1):
        try:
            _, used = recordings.record(text, lang, eleven)
        except Exception as exc:
            # Stop at the first failure (wrong key, voice ID, no credits) instead of retrying in a loop.
            sys.exit(f"Stopped at line {i}/{len(todo)} ({lang}): {exc}. Lines recorded so far are kept.")
        charged += used or len(text)
        print(f"[{i}/{len(todo)}] {lang} {text[:60]}...")
        time.sleep(0.3)  # gentle on the API
    print(f"\nDone: {len(todo)} lines recorded in {recordings.DIR}; ElevenLabs charged {charged:,} characters")


if __name__ == "__main__":
    main()
