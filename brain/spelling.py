"""A street spelled letter by letter, joined back into a word, without the model.

Docs/Research/09_Location_Questioning.md. When the map finds no street like the one heard and no
real street of the area sounds close, the agent asks the caller to spell it (steps.py,
"spell_street"). Speech-to-text writes a spelled word as letters ("Φ Ρ Ε Ι"), letter names
("φι ρο έψιλον γιώτα"), syllables ("Φρει-δε-ρί-κης") or "Φ όπως Φώτης"; this turns any of
them into "Φρειδερικης". The word then goes to the map check and, masked, to the model.

Not verified with real spelled speech: how Soniox writes spelled Greek and Turkish letters is a
guess from the forms above. A message that is not clearly spelling gives None, and the call
goes on as before.
"""
import re
import unicodedata

# Letter names, written without accents and in lower case.
_GREEK = {
    "αλφα": "α", "βητα": "β", "γαμμα": "γ", "γαμα": "γ", "δελτα": "δ", "εψιλον": "ε", "εψιλο": "ε",
    "ζητα": "ζ", "ητα": "η", "θητα": "θ", "γιωτα": "ι", "ιωτα": "ι", "καπα": "κ", "καππα": "κ",
    "λαμδα": "λ", "λαμβδα": "λ", "λαμντα": "λ", "μι": "μ", "μυ": "μ", "νι": "ν", "νυ": "ν", "ξι": "ξ",
    "ομικρον": "ο", "ομικρο": "ο", "πι": "π", "ρο": "ρ", "σιγμα": "σ", "ταυ": "τ", "ταφ": "τ",
    "υψιλον": "υ", "υψιλο": "υ", "φι": "φ", "χι": "χ", "ψι": "ψ", "ωμεγα": "ω",
}
_TURKISH = {
    "be": "b", "ce": "c", "çe": "ç", "de": "d", "fe": "f", "ge": "g", "yumuşak ge": "ğ", "yumusak ge": "ğ",
    "he": "h", "je": "j", "ke": "k", "le": "l", "me": "m", "ne": "n", "pe": "p", "re": "r", "se": "s",
    "şe": "ş", "te": "t", "ve": "v", "ye": "y", "ze": "z",
}
_ENGLISH = {
    "bee": "b", "see": "c", "cee": "c", "dee": "d", "ef": "f", "gee": "g", "aitch": "h", "jay": "j",
    "kay": "k", "el": "l", "em": "m", "en": "n", "pee": "p", "cue": "q", "ar": "r", "ess": "s", "tee": "t",
    "vee": "v", "double u": "w", "ex": "x", "why": "y", "zed": "z", "zee": "z",
}
_NAMES = {"el": _GREEK, "tr": _TURKISH, "en": _ENGLISH, "fr": {}}
# "Φ όπως Φώτης", "F as in Fatma", "F gibi": the letter before the cue counts, the example word not.
_AS_IN = re.compile(r"(\w+)\s+(?:όπως|οπως|σαν|as in|like|gibi|comme)\s+\w+", re.IGNORECASE)
_SPLIT = re.compile(r"[\s,.\-–—;:·]+")
MIN_LETTERS = 3
MAX_PIECE = 4  # a syllable at most ("φρει"); a longer word means the caller is talking, not spelling


def _plain(word: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", word.lower()) if not unicodedata.combining(c))


def spelled(text: str, lang: str) -> str | None:
    """The word a caller spelled, e.g. "φι ρο έψιλον" -> "Φρε", or None if text is not spelling."""
    names = _NAMES.get(lang, {})
    text = _AS_IN.sub(r"\1", text)
    for two in (n for n in names if " " in n):  # "yumuşak ge", "double u"
        text = re.sub(rf"\b{two}\b", names[two], text, flags=re.IGNORECASE)
    pieces = [p.replace("i̇", "i") for p in _SPLIT.split(text.lower()) if p]  # Turkish "İ" lowers to i + dot
    letters = [names.get(p) or names.get(_plain(p)) or (p if len(p) == 1 and p.isalpha() else None) for p in pieces]
    named = [i for i, letter in enumerate(letters) if letter]
    if named:
        # "Ναι, το λέω: Φ Ρ Ε…": words before the first letter and after the last are not spelling.
        pieces, letters = pieces[named[0]:named[-1] + 1], letters[named[0]:named[-1] + 1]
        if len(named) * 2 < len(pieces):
            return None  # mostly words: the caller is talking, not spelling
    elif "-" not in text:
        return None  # syllables only count when written "Φρει-δε-ρί-κης"
    if len(pieces) < 2:
        return None  # one word is a word said again, not spelled
    for i, piece in enumerate(pieces):
        if letters[i] is None:
            if len(piece) > MAX_PIECE or not piece.isalpha():
                return None
            letters[i] = piece
    word = "".join(letters)
    if len(word) < MIN_LETTERS:
        return None
    if lang == "el":
        word = re.sub(r"σ$", "ς", word)
    first = "İ" if lang == "tr" and word[0] == "i" else word[0].upper()  # Turkish capital i has a dot
    return first + word[1:]
