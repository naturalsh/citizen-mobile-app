"""Language guesses that need no model: from the phone number, and from written text."""
import re

_PREFIXES = {"+30": "el", "+357": "el", "+90": "tr", "+33": "fr", "+32": "fr"}

_GREEK = re.compile(r"[Ͱ-Ͽἀ-῿]")
_LETTER = re.compile(r"[^\W\d_]")
_TURKISH_ONLY = re.compile(r"[ğĞşŞıİ]")
_FRENCH_ONLY = re.compile(r"[éèêëàâùûœ]", re.IGNORECASE)


def lang_from_phone(phone: str) -> str:
    """First guess from the country code. The caller can still switch later."""
    number = phone.replace(" ", "").removeprefix("whatsapp:")
    for prefix in sorted(_PREFIXES, key=len, reverse=True):
        if number.startswith(prefix):
            return _PREFIXES[prefix]
    return "en"


def script_language(text: str) -> str | None:
    """The language the letters prove, or None: Greek letters, or a Turkish- or French-only letter.

    Speech-to-text labelled a Turkish caller's "İzmir'deyim", "Evet, doğru" and "Evim yıkıldı" as
    English in a test call (2026-10-26), and the call went on in English. Letters like ı, ğ, ş
    can't be English."""
    letters = _LETTER.findall(text)
    if not letters:
        return None
    if len(_GREEK.findall(text)) / len(letters) > 0.3:
        return "el"
    if _TURKISH_ONLY.search(text):
        return "tr"
    if _FRENCH_ONLY.search(text):
        return "fr"
    return None


def lang_from_text(text: str, current: str) -> str:
    """Language of a written message, falling back to the current one when unclear.

    Good enough for el/tr/en/fr. Latin text with no telltale letters keeps the current
    language, unless that is Greek (a Greek speaker would write in Greek letters).
    """
    if not _LETTER.findall(text):
        return current
    if proven := script_language(text):
        return proven
    return "en" if current == "el" else current
