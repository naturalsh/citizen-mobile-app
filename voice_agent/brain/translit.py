"""No Greek letters in a reply to a caller who isn't speaking Greek.

On an English demo call (2026-10-30) the agent said "Εντάξει, Orlov 12, Κουκάκι" and "Did you mean
Ορλώφ?". The model wrote the Greek "okay" itself, despite the prompt's rule, and the street came from
the map in Greek letters, as the code fills a placeholder with the real name. An English or Turkish
voice can't read Greek letters, and a texter may not either. So, sentence by sentence before it is
said or sent (core.py): a Greek acknowledgement becomes the caller's language (greek_words.json),
and any other Greek word is written in Latin letters (ELOT 743, the Greek standard used on street
signs: Ορλώφ -> Orlof, Ερμού -> Ermou). Reports keep the Greek names; Greek calls are untouched.
"""
import json
import re
import unicodedata
from pathlib import Path

_ACKS = json.loads((Path(__file__).parent / "greek_words.json").read_text(encoding="utf-8"))["acknowledgements"]
_GREEK = "Ͱ-ͽͿ-Ͽἀ-῿"  # Greek letters, without the Greek question mark (U+037E)
_GREEK_WORD = re.compile(f"[{_GREEK}][{_GREEK}̀-ͯ]*")

_SINGLE = dict(zip("αβγδεζηθικλμνξοπρσςτυφχψω",
                   ["a", "v", "g", "d", "e", "z", "i", "th", "i", "k", "l", "m", "n", "x", "o", "p", "r",
                    "s", "s", "t", "y", "f", "ch", "ps", "o"]))
_PAIRS = {"ου": "ou", "αι": "ai", "ει": "ei", "οι": "oi", "γγ": "ng", "γξ": "nx", "γχ": "nch"}
_AT_START = {"μπ": "b", "ντ": "d", "γκ": "g"}
_INSIDE = {"μπ": "mp", "ντ": "nt", "γκ": "gk"}
_VOICED = set("αεηιοωυβγδζλμνρ")  # αυ/ευ/ηυ are av/ev/iv before these, af/ef/if otherwise


def _plain(word: str) -> tuple[str, set[int]]:
    """Lower case without accents, and the positions that had a diaeresis (ϊ pairs with nothing)."""
    out, apart = [], set()
    for ch in unicodedata.normalize("NFD", word.lower()):
        if ch == "̈":
            apart.add(len(out) - 1)
        elif not unicodedata.combining(ch):
            out.append(ch)
    return "".join(out), apart


def to_latin(word: str) -> str:
    """One Greek word in Latin letters, keeping a capital first letter, or all capitals."""
    w, apart = _plain(word)
    out, i = [], 0
    while i < len(w):
        pair, after = w[i:i + 2], w[i + 2:i + 3]
        if len(pair) == 2 and i + 1 not in apart:
            if pair[0] in "αεη" and pair[1] == "υ":
                out.append({"α": "a", "ε": "e", "η": "i"}[pair[0]] + ("v" if after in _VOICED and after else "f"))
                i += 2
                continue
            if pair in _AT_START:
                out.append(_AT_START[pair] if i == 0 else _INSIDE[pair])
                i += 2
                continue
            if pair in _PAIRS:
                out.append(_PAIRS[pair])
                i += 2
                continue
        out.append(_SINGLE.get(w[i], w[i]))
        i += 1
    latin = "".join(out)
    letters = [c for c in word if c.isalpha()]
    if len(letters) > 1 and all(c.isupper() for c in letters):
        return latin.upper()
    return latin[:1].upper() + latin[1:] if word[:1].isupper() else latin


def _accent_free(greek: str) -> str:
    """A pattern that matches the Greek words with or without accents, any case."""
    variants: dict[str, set[str]] = {}
    for code in [*range(0x370, 0x400), *range(0x1F00, 0x2000)]:
        ch = chr(code)
        base = _plain(ch)[0]
        if len(base) == 1:
            variants.setdefault(base, set()).update({ch, ch.lower(), ch.upper()})
    return "".join(f"[{''.join(sorted(variants.get(c, {c})))}]" if c != " " else r"\s+" for c in _plain(greek)[0])


_ACK_PATTERNS = [(re.compile(rf"(?<!\w){_accent_free(greek)}(?!\w)"), words) for greek, words in _ACKS.items()]


def _like(said: str, word: str) -> str:
    """The replacement with the capital letter where the Greek word had one ("I" stays "I")."""
    if said[:1].isupper() or word.split()[0] in ("I", "I'm"):
        return word
    return word[:1].lower() + word[1:]


_LATIN = re.compile(r"[A-Za-zÀ-ɏ]")


def for_caller(text: str, lang: str) -> str:
    """The reply as a caller speaking `lang` should hear or read it.

    Only Greek words inside a sentence in the caller's language are written in Latin letters: a
    sentence wholly in Greek (the model answered in the wrong language) would become gibberish
    ("Pou vriskeste"), and would pass for English on the operator's copy, so it stays as it was."""
    if lang == "el" or not _GREEK_WORD.search(text):
        return text
    for pattern, words in _ACK_PATTERNS:
        if lang in words:
            text = pattern.sub(lambda m: _like(m.group(0), words[lang]), text)
    sentences = re.split(r"(?<=[.!?…;])(\s+)", text)
    return "".join(_GREEK_WORD.sub(lambda m: to_latin(m.group(0)), s.replace(";", "?")) if _LATIN.search(s) else s
                   for s in sentences)
