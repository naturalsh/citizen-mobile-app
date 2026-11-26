"""Hesitation fillers ("εε", "um", "ıı") in the caller's words, before they reach the brain.

Speech-to-text writes hesitations down, so a turn can be only "Εε." (the caller paused to
think) or start with a filler that ends up in the report ("Εε, Πολιτόπουλος"). The agent
ignores a turn that is only fillers and strips fillers from the others (agent.py).
Fillers are matched as whole words, so "ε" inside a word and short real answers ("Ναι",
"Evet") stay. The lists are in fillers.json, for every language at once: a Greek caller
can hesitate with "um". Follows Docs/Research/04_STT_and_TTS.md.
"""
import json
import re
import unicodedata
from pathlib import Path

_FILE = Path(__file__).parent / "fillers.json"
_EDGES = re.compile(r"^(\W*)(.*?)(\W*)$", re.DOTALL)  # a word without the punctuation around it
_QUESTION = ("?", ";", ";")  # "Ε;" or "Hm?" means "what?": the caller wants an answer


def normalize(word: str) -> str:
    """'Εεε' -> 'ε', 'Ummm' -> 'um', 'Şey' -> 'sey': no case, accents or repeated letters."""
    if word[:2] == "Iı":
        word = "ı" + word[1:]  # Turkish "Iıı" at the start of a sentence; a lone "I" stays English
    plain = "".join(ch for ch in unicodedata.normalize("NFD", word) if not unicodedata.combining(ch))
    return re.sub(r"(.)\1+", r"\1", plain.lower())


def load(path: Path = _FILE) -> tuple[set[str], set[str]]:
    """(fillers dropped anywhere, fillers dropped only at the start), normalized."""
    data = json.loads(path.read_text(encoding="utf-8"))

    def words(group: str) -> set[str]:
        return {normalize(w) for lang_words in data[group].values() for w in lang_words}

    return words("anywhere"), words("leading")


ANYWHERE, LEADING = load()


def _spelled(tokens: list[str]) -> bool:
    """Letter by letter ("Φ Ρ Ε Ι Δ…", brain/spelling.py): "Ε" and "Μ" are letters there, not fillers."""
    letters = [w for w in (normalize(_EDGES.match(t).group(2)) for t in tokens) if len(w) == 1 and w.isalpha()]
    return len(tokens) >= 3 and len(letters) * 2 > len(tokens) and sum(w not in ANYWHERE for w in letters) >= 2


def clean(text: str) -> str:
    """The caller's words without fillers; "" if nothing but fillers (or punctuation) was said."""
    if _spelled(text.split()):
        return text.strip()
    kept: list[str] = []
    for token in text.split():
        word = normalize(_EDGES.match(token).group(2))
        if word in ANYWHERE or (not kept and word in LEADING):
            continue
        kept.append(token)
    result = " ".join(kept).strip(" ,")
    if any(ch.isalnum() for ch in result):
        return result
    return text.strip() if text.rstrip().endswith(_QUESTION) else ""
