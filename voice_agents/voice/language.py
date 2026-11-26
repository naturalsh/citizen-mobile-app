"""Which language to pass to brain.turn(), from Soniox's per-sentence language labels.

Docs/Research/04: the phone's country code is the first guess, then the caller's speech
decides. Short answers ("Ναι", "OK", "Evet") are easy to mislabel, and the brain hands off
on any language it does not support, so a switch needs a sentence with enough letters,
and an unsupported language must be heard in two such sentences in a row.

Two exceptions, from a test call where a Turkish caller's "Merhaba." (7 letters) never switched
the call out of Greek: the caller's first words decide with fewer letters (they answer the
greeting in their own language), and short sentences in the same other language add up over
consecutive turns.
"""
import os

from brain.langs import script_language

from .config import LANGS

MIN_LETTERS = int(os.getenv("VOICE_LANG_MIN_LETTERS", "12"))
FIRST_TURN_MIN_LETTERS = 5  # "Merhaba", "Hello", "Bonjour"; not "OK", "Ναι", "Evet"
UNSUPPORTED_TURNS = 2


def _code(lang: str | None) -> str | None:
    """'el', 'el-GR', 'EL' -> 'el'."""
    if not lang:
        return None
    return str(lang).split("-")[0].split("_")[0].lower() or None


class LanguageTracker:
    def __init__(self, current: str) -> None:
        self.current = current
        self._letters: dict[str, int] = {}  # this turn: language -> letters heard
        self._unsupported_turns = 0
        self._carried: dict[str, int] = {}  # another supported language, heard in the last turns
        self._first_turn = True

    def heard(self, text: str, lang: str | None) -> None:
        """One final transcript from speech-to-text."""
        # The letters beat speech-to-text's label: it labelled Turkish sentences as English.
        code = script_language(text) or _code(lang)
        if code:
            self._letters[code] = self._letters.get(code, 0) + sum(ch.isalpha() for ch in text)

    def decide(self) -> str:
        """Language for this turn. Call once per caller turn; starts the next turn fresh."""
        letters, self._letters = self._letters, {}
        if not letters:
            return self.current
        first, self._first_turn = self._first_turn, False
        lang, count = max(letters.items(), key=lambda item: item[1])
        if lang == self.current:
            self._unsupported_turns = 0
            self._carried = {}
            return self.current
        if lang in LANGS:
            total = count + self._carried.get(lang, 0)
            # The first words decide early only when they are clearly one language: "No, I— I
            # connect. Merhaba" switched a Turkish caller's call to English (2026-10-26).
            clear = count >= 2 * (sum(letters.values()) - count)
            if total >= MIN_LETTERS and clear or (first and count >= FIRST_TURN_MIN_LETTERS and clear):
                self._unsupported_turns = 0
                self._carried = {}
                self.current = lang
                return lang
            self._carried = {lang: total}  # not yet: it adds up if the next turn is the same language
            return self.current
        if count < MIN_LETTERS:
            return self.current
        self._unsupported_turns += 1
        # Passing the unsupported code makes the brain hand off to a human.
        return lang if self._unsupported_turns >= UNSUPPORTED_TURNS else self.current
