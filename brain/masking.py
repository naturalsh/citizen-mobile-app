"""Reversible masking of personal details (Docs/Research/07_Privacy_and_Encryption.md).

Before a caller's words go to Gemini, names, street addresses, phone numbers, e-mails and
ID numbers are swapped for placeholders like <PERSON_1> or <ADDRESS_1>. The model answers
with the placeholders, and we swap the real values back before the caller hears the reply
and before the report is saved. The model never sees the real details.

Detection is rule-based (no Greek/Turkish NER model with a usable licence was found):
- e-mails, phone and ID numbers: patterns
- street addresses: a street word or a Greek genitive street name, followed by a number
- names: after "my name is" style phrases in each language, or the whole answer when the
  agent has just asked for the caller's name
- anything already masked is masked again wherever it reappears
Village and town names are left visible on purpose: the model needs them for the area
field and to group calls. Names said in passing ("my mother Eleni") are not caught.
"""
import re

from . import gazetteer

from .steps import cannot_say  # "I don't know" in four languages
from .events import _norm  # accents off, Greek in Latin letters: compares names however they are written

_PLACEHOLDER = re.compile(r"<\s*(PERSON|ADDRESS|PHONE|EMAIL|ID)[\s_]*(\d+)\s*>", re.IGNORECASE)

_UPPER = "A-ZΑ-ΩΆΈΉΊΌΎΏÇĞİÖŞÜÀ-Ý"
_WORD = r"[\w'’\-]+"
_CAP_WORD = rf"[{_UPPER}][\w'’\-]*"
_NUM = r"\d{1,4}[A-Za-zΑ-Ωα-ω]?"

_HOUSE_NUMBER_END = re.compile(r"\s+\d{1,4}\s*[A-Za-zΑ-Ωα-ω]?$")  # "Φραγκιαδών 16" -> "Φραγκιαδών"
_STREET_WORD_START = re.compile(r"^\s*(?:οδός|οδού|οδό|οδος|οδου|οδο|λεωφόρος|λεωφόρου|λεωφόρο|λεωφ\.)\s+", re.IGNORECASE)
# Words that come before a number without being a street ("Παιδιά 3", "Bina 3 katlı", "Person 2"):
# never remembered as a street name, or they would be masked for the rest of the call.
_NOT_A_STREET_NAME = {_norm(w) for w in (
    "παιδιά", "παιδί", "γιαγιά", "παππούς", "άτομα", "άνθρωποι", "περίπου", "συνολικά", "πολυκατοικία", "κτίριο",
    "σπίτι", "αριθμός", "όροφος", "τραυματίες", "bina", "kişi", "çocuk", "sokak", "caddesi", "cadde", "bulvarı",
    "numara", "person", "people", "persons", "children", "building", "house", "street", "road", "avenue", "number",
    "immeuble", "maison", "personnes", "enfants")} - {""}  # _norm drops street words ("sokak", and "οδός"):
# with "" in the set every "οδός Αγίου Νικολάου 12" was skipped as a count and masked in two halves (test set 2026-11-15)
_CAPITALISED = re.compile(rf"(?<![<\w])[{_UPPER}][\w'’\-]*(?![\w>])")  # one capitalised word, not inside a placeholder
_EMAIL = re.compile(r"[\w.+\-]+@[\w\-]+\.[\w.\-]+")
_LONG_NUMBER = re.compile(r"(?<![\w+])(?:\+|00)?\d(?:[\s\-]?\d){8,14}(?!\w)")

_ADDRESS_PATTERNS = [
    # Greek with a street word: "οδός Θεμιστοκλέους 5", "στην οδό Λογοθέτη 40", "Λεωφόρος Σοφούλη 12"
    re.compile(
        rf"(?i:οδός|οδού|οδό|οδος|οδου|οδο|λεωφόρος|λεωφόρου|λεωφόρο|λεωφ\.|πλατεία|πλατείας)\s+(?:{_WORD}\s+){{0,2}}?{_NUM}\b"
    ),
    # Greek genitive street name + number, no street word: "Θεμιστοκλέους 5", "Λογοθέτη 40", "Μελά 13".
    # Also with the accent on the ending: "Φραγκιαδών 16" reached the model unmasked in a live test
    # (2026-11-15), because only the unaccented "ων" was listed.
    re.compile(rf"\b[Α-ΩΆΈΉΊΌΎΏ][α-ωάέήίόύώϊϋΐΰ]+(?:ους|ούς|ου|ού|ας|άς|ης|ής|ων|ών|η|ή|ά)\s+{_NUM}\b"),
    # The same in Latin letters, as tourists write it: "Themistokleous 5", "Logotheti 40", "Mela 13"
    # (an eval call sent "Michail Mela 13" to the model unmasked before "a" was added)
    re.compile(rf"\b[A-Z][a-z]+(?:ous|ou|as|is|on|i|a)\s+{_NUM}\b"),
    # Turkish: one capitalised word + street word + number: "Manas Bulvarı 12", "Atatürk Caddesi No: 5".
    # Only one word before the street word, so the neighbourhood before it stays visible.
    re.compile(
        rf"{_CAP_WORD}\s+(?i:Sokak|Sokağı|Sok\.|Sk\.|Caddesi|Cadde|Cad\.|Cd\.|Bulvarı|Bulvar|Blv\.)"
        rf"\s*(?i:No[:.]?\s*)?{_NUM}\b"
    ),
    # English: "12 Main Street", "Main Street 12"
    re.compile(rf"\b{_NUM}\s+{_CAP_WORD}(?:\s+{_CAP_WORD})?\s+(?i:Street|St\.?|Road|Rd\.?|Avenue|Ave\.?)(?!\w)"),
    re.compile(rf"\b{_CAP_WORD}(?:\s+{_CAP_WORD})?\s+(?i:Street|Road|Avenue)\s+{_NUM}\b"),
    # French: "12 rue des Lilas", "5, avenue Victor Hugo"
    re.compile(rf"\b{_NUM},?\s+(?i:rue|avenue|boulevard|bd|place|chemin|allée)\s+(?:{_WORD}\s*){{1,4}}"),
]

# A street word and the name after it, even without a number: "στην οδό Ορλώφ" (eval 2026-10-25).
_STREET_WORD_NAME = re.compile(
    r"(?i:οδός|οδού|οδό|οδος|οδου|οδο|λεωφόρος|λεωφόρου|λεωφόρο|λεωφ\.)\s+[Α-ΩΆΈΉΊΌΎΏ][\w'’\-]*(?:\s+[Α-ΩΆΈΉΊΌΎΏ][\w'’\-]*)?"
)
# Only in an answer to a location question: any capitalised name and a number, whatever its
# ending. "Ορλώφ 12" (an indeclinable name) reached the model in an eval run on 2026-10-25.
_NAME_AND_NUMBER = re.compile(rf"\b([Α-ΩΆΈΉΊΌΎΏ][α-ωάέήίόύώϊϋΐΰς]+(?:\s+[Α-ΩΆΈΉΊΌΎΏ][α-ωάέήίόύώϊϋΐΰς]+)?)\s+{_NUM}\b")
# A run of 1-3 capitalised words, not inside a placeholder: candidate names.
# "στην Ορλώφ", "οδό Ορλώφ": a capitalised name after these is a street unless it is a real place.
_AFTER_IN = re.compile(r"\b(?i:στην|στη|στον|στο|στις|στους|στα|οδό|οδός)\s+([Α-ΩΆΈΉΊΌΎΏ][\w'’\-]*(?:\s+[Α-ΩΆΈΉΊΌΎΏ][\w'’\-]*)?)")
# A word in any case and letters, then a house number: "fragiadon 16" typed in lower case, which
# the capitalised-name patterns missed (WhatsApp test 2026-10-27).
_WORD_AND_NUMBER = re.compile(rf"(?<![<\w])([^\W\d_]{{3,}}(?:\s+[^\W\d_]{{3,}})?)\s+({_NUM})\b")
_NOT_BEFORE_NUMBERS = {"the", "and", "are", "we're", "floor", "number", "apartment", "flat", "people", "persons",
                       "about", "maybe", "around", "near", "kat", "numara", "daire", "kişi", "kişiyiz", "yaş",
                       "όροφο", "όροφος", "άτομα", "χρονών", "étage", "personnes", "numéro", "were", "there"}
_NAMES = re.compile(r"(?<![<\w])[Α-ΩΆΈΉΊΌΎΏA-Z][\w'’\-]*(?:\s+[Α-ΩΆΈΉΊΌΎΏA-Z][\w'’\-]*){0,2}")
# Capitalised words that start an answer, not a street: "Στο 12", "Είμαστε 3".
_NOT_STREETS = {"στο", "στη", "στην", "στον", "το", "τη", "την", "τον", "η", "ο", "οι", "τα", "στα", "στους",
                "είμαστε", "είμαι", "είναι", "είναι", "νούμερο", "αριθμός", "αριθμό", "ναι", "όχι", "περίπου",
                "κοντά", "δίπλα", "μετά", "πριν", "όροφος", "όροφο", "διαμέρισμα", "πόρτα", "σπίτι",
                # name cues: "Adım <PERSON_1>" is not a street
                "με", "λένε", "ονομάζομαι", "λέγομαι", "adım", "ismim", "benim", "my", "name", "je", "mon", "nom",
                # English "I" is always a capital: "I'm in Belokipos" after the street question was masked as the
                # street "I'm" and read back as "I'm, Ampelokipoi, Athens" five times (test set 2026-11-15)
                "i", "i'm", "i’m", "i've", "i’ve", "i'll", "i’ll", "i'd", "i’d", "we", "we're", "we’re", "it's", "it’s"}

_STREET_WORD_IN = re.compile(r"(?i)(?<!\w)(?:sokak|sokağı|sok\.|sk\.|caddesi|cadde|cad\.|cd\.|bulvarı|bulvar|blv\.|street|road|"
                             r"avenue|rue|boulevard|οδός|οδού|οδό|λεωφόρος|λεωφόρου|λεωφόρο|no)(?!\w)")
# Also the bare label a texter writes, "Name is John Doe" or "Name: John Doe": a WhatsApp test
# (2026-10-31) wrote it so, no cue matched, and the model saw the name. Not "street name is ...".
_NAME_CUES = [
    r"με\s+λένε|ονομάζομαι|λέγομαι|το\s+όνομά\s+μου\s+είναι|(?:ονοματεπώνυμο|όνομα)\s*[:\-–]",  # Greek
    r"benim\s+adım|adım|ismim|(?:ad\s*soyad|isim)\s*[:\-–]",  # Turkish
    r"my\s+name\s+is|my\s+name's|i\s+am\s+called|(?<!street\s)(?<!road\s)\bname\s+is|\bname\s*[:\-–]",  # English
    r"je\s+m['’]appelle|mon\s+nom\s+est|\bnom\s*[:\-–]",  # French
]
# Cue words in any case, then the first name in any case, then an optional capitalised surname.
_NAME_AFTER_CUE = re.compile(rf"(?i:{'|'.join(_NAME_CUES)})\s+({_WORD}(?:\s+{_CAP_WORD})?)")
# Short answers that are never names, even capitalised ("Ναι", "Evet", "Oui").
_NOT_NAMES = {
    "ναι", "όχι", "οχι", "εντάξει", "σωστά", "βέβαια", "ευχαριστώ", "evet", "hayır", "hayir", "tamam", "doğru",
    "teşekkürler", "yes", "no", "ok", "okay", "right", "correct", "thanks", "oui", "non", "d'accord", "merci",
}

# Hesitation sounds before an answer ("Εε, Πολιτόπουλος"): never part of a name.
_FILLERS = {"ε", "εε", "εεε", "εμ", "μμ", "χμ", "ee", "eee", "ıı", "ııı", "iı", "ii", "şey", "eh", "ehm", "em", "um", "umm",
            "uh", "hmm", "euh", "ben"}


def _without_fillers(text: str) -> str:
    words = text.strip(" .,!?…").split()
    while words and words[0].strip(".,!?…").casefold() in _FILLERS:
        words.pop(0)
    return " ".join(words)


def _looks_like_a_name(text: str) -> bool:
    """The answer to "what is your name?": one to four words, every word capitalised, no digits.

    "Μαρία Παπαδοπούλου" yes; "Είμαστε δύο", "Ναι", "Oui, c'est ça" no. A name typed in lower
    case is not caught (it would also catch "είμαστε δύο").
    """
    words = text.strip(" .,!?").split()
    if not 1 <= len(words) <= 4 or any(ch.isdigit() for ch in text):
        return False
    if words[0].strip(".,!?").casefold() in _NOT_NAMES or cannot_say(text):
        return False  # "Bilmiyorum." was thanked as a name: "Teşekkür ederim, Bilmiyorum" (test set 2026-11-16)
    return all(w[0].isupper() for w in words)




class Masker:
    """Holds one conversation's placeholder <-> real value table."""

    def __init__(self) -> None:
        self._real: dict[str, str] = {}  # "<PERSON_1>" -> "Maria Papadopoulou"
        self._placeholder: dict[str, str] = {}  # casefolded real value -> "<PERSON_1>"
        self._counts: dict[str, int] = {}
        self.form_name: str | None = None  # the name found in the last texted list answer
        self._street_names: set[str] = set()  # the name part of every masked "street number"
        self._where = False  # this message answers a question about the place

    def _shares_a_known_name(self, text: str) -> bool:
        """A word of text is part of a name given earlier (usually the surname)."""
        known = {w.casefold() for p, v in self._real.items() if p.startswith("<PERSON_") for w in v.split() if len(w) > 2}
        return any(w.strip(" .,!?…").casefold() in known for w in text.split())

    def _swap(self, kind: str, value: str) -> str:
        value = value.strip(" ,.;:!?")
        if not value:
            return value
        key = value.casefold()
        if kind == "ADDRESS" and self._where and (bare := _HOUSE_NUMBER_END.sub("", value)) != value:
            # Said again without its number, the street is masked too (mask_known). Only a name given
            # where a place was asked for, one capitalised word that is not a common word or a town.
            name = _STREET_WORD_START.sub("", bare).strip(" ,.-")
            if (len(name) >= 5 and " " not in name and name[0].isupper() and _norm(name) not in _NOT_A_STREET_NAME
                    and name.casefold() not in _NOT_STREETS and name.casefold() not in _NOT_BEFORE_NUMBERS
                    and not gazetteer.is_place(name)):
                self._street_names.add(name)
        if key not in self._placeholder:
            self._counts[kind] = self._counts.get(kind, 0) + 1
            placeholder = f"<{kind}_{self._counts[kind]}>"
            self._placeholder[key] = placeholder
            self._real[placeholder] = value
        return self._placeholder[key]

    def _sub(self, pattern: re.Pattern, kind, text: str, group: int = 0) -> str:
        def repl(m: re.Match) -> str:
            k = kind(m.group(group)) if callable(kind) else kind
            whole, part = m.group(0), m.group(group)
            return whole.replace(part, self._swap(k, part)) if group else self._swap(k, part)

        return pattern.sub(repl, text)

    def hide(self, kind: str, value: str) -> str:
        """The placeholder for a value that didn't come from the caller, e.g. the real street the map
        check suggests: the model asks "Did you mean <ADDRESS_2>?" and the caller hears the name."""
        return self._swap(kind, value)

    def mask_known(self, text: str) -> str:
        """Replace values masked earlier in this conversation, longest first.

        Matches the original spelling case-insensitively. (Not the casefolded key: Turkish "İ"
        casefolds to two characters and would never match again.)
        """
        for placeholder, value in sorted(self._real.items(), key=lambda kv: len(kv[1]), reverse=True):
            # Whole words only: a short value ("Ada") was once replaced inside other words ("burada").
            start = r"(?<![<\w])" if value[:1].isalnum() else ""
            end = r"(?![\w>])" if value[-1:].isalnum() else ""
            text = re.sub(start + re.escape(value) + end, placeholder, text, flags=re.IGNORECASE)
        # A street masked with its number ("Φραγκιαδών 16") and then said alone ("σκέτο Φραγκιαδών"):
        # the bare name went to the model as plain text in a live test (2026-11-15), and it put the
        # name in front of the placeholder: "Φραγκιαδών Φραγκιαδών 16". Compared without accents:
        # speech-to-text moves them ("Φραγκιάδων").
        if self._street_names:
            wanted = {_norm(name) for name in self._street_names}
            text = _CAPITALISED.sub(lambda m: self._swap("ADDRESS", m.group(0)) if _norm(m.group(0)) in wanted else m.group(0), text)
        return text

    def _mask_streets(self, text: str, places: str, streets: frozenset, every_name: bool) -> str:
        """Street names, found by what was asked rather than by how they are said.

        every_name (the brain just asked for the street): every name in the answer is the street,
        except places already given and a sentence's first word before lowercase words ("Έπιασε
        φωτιά"). Anywhere else: a name that is a real street of the caller's area (streets, from
        OpenStreetMap). An eval run on 2026-10-26 sent "Στην Ορλώφ." to the model."""
        known = set(_norm(places).split())

        def repl(m: re.Match) -> str:
            words = m.group(0).split()
            while words and words[0].casefold() in _NOT_STREETS:  # "Στην Ορλώφ" -> "Ορλώφ"
                words = words[1:]
            span = " ".join(words)
            if not words or all(_norm(w) in known for w in words):
                return m.group(0)
            if cannot_say(span):
                # "Bilmiyorum." to the street question is one capitalised word: it was masked, recorded as
                # the street and read back as "Şirinyer, Bilmiyorum, Gazi Caddesi" (test set 2026-11-15).
                return m.group(0)
            if every_name:
                before, after = text[:m.start()].rstrip(), text[m.end():].lstrip()
                if span == m.group(0) and (not before or before[-1] in ".!?;…") and after[:1].islower():
                    return m.group(0)  # a sentence starting with a verb or a common word
            elif not (_norm(span) in streets or (len(words[-1]) >= 5 and _norm(words[-1]) in streets)):
                return m.group(0)
            return m.group(0).replace(span, self._swap("ADDRESS", span))

        return _NAMES.sub(repl, text)

    def _street_and_number(self, m: re.Match) -> str:
        words = m.group(1).split()
        while words and (words[0].casefold() in _NOT_STREETS or words[0].casefold() in _NOT_BEFORE_NUMBERS):
            words = words[1:]  # "in fragiadon 16" -> "fragiadon 16"; "floor 3" stays
        # A place with a number is rare ("Κουκάκι 2"?); a street named like one is common, so only an exact name.
        if not words or words[-1].casefold() in _NOT_BEFORE_NUMBERS or gazetteer.is_place(" ".join(words)):
            return m.group(0)
        span = f"{' '.join(words)} {m.group(2)}"
        return m.group(0).replace(span, self._swap("ADDRESS", span))

    def _mask_form_name(self, text: str) -> str:
        """In the answer to a texted list ("1. Fire 2. Ορλώφ 4, Κουκάκι 3. Two 4. Νίκος Δοκιμάκης"), the
        name after a cue ("Adım Ayşe Deneme"), else the last piece that looks like a full name: two to
        four capitalised words, not a place."""
        self.form_name = None
        if cue := _NAME_AFTER_CUE.search(text):
            self.form_name = cue.group(1).strip(" .,;:!?")
            return text.replace(cue.group(1), self._swap("PERSON", cue.group(1)))
        pieces = [re.sub(r"^\s*(?:\d+\s*[.)]|[-•*])?\s*(?:(?i:όνομα|ονοματεπώνυμο|name|ad|isim|nom)\s*:)?\s*", "", piece)
                  for piece in re.split(r"[\n,;]|[.!?](?=\s)|(?<!\d)\s(?=\d+[.)]\s)", text)]
        pieces = [re.sub(r"\s+(?i:name|όνομα|ονοματεπώνυμο|adım|ismim|nom)\s*[.!]?\s*$", "", p) for p in pieces]
        # Not a street: "Gazi Caddesi No 18. Ben …" splits before "18." like a list number, and "Gazi
        # Caddesi No" was masked as the caller's name when no name was in the message.
        names = [p.strip(" .!?") for p in pieces if _looks_like_a_name(p) and len(p.split()) >= 2
                 and not gazetteer.is_place(p.strip(" .!?")) and not _STREET_WORD_IN.search(p)
                 and not all(gazetteer.is_place(w) for w in p.strip(" .!?").split())]  # "İzmir Buca"
        if not names:
            return text
        self.form_name = names[-1]
        return text.replace(names[-1], self._swap("PERSON", names[-1]))

    def _mask_form(self, text: str, places: str, streets: frozenset) -> str:
        """A texted list answer: the name first, then each line like the answer to the street
        question, so a list number on the next line is never read as a house number. A piece that
        is wholly a real town or neighbourhood ("Κουκάκι", "Bayraklı") stays visible."""
        text = self._mask_form_name(text)
        # Also a piece of two places, "İzmir Buca": "Buca" was masked, and the model recorded it as the
        # street in front of "Gazi Caddesi No 18" (test set 2026-11-16).
        def a_town(piece: str) -> bool:
            piece = re.sub(r"^\s*\d+\s*[.)]\s*", "", piece).strip(" .!?")
            return gazetteer.is_place(piece) or (1 < len(piece.split()) <= 3 and all(gazetteer.is_place(w) for w in piece.split()))

        towns = [p.strip(" .!?") for p in re.split(r"[\n,;]|[.!?](?=\s)", text) if p.strip(" .!?") and a_town(p)]
        places = " ".join([places, *towns])
        return "\n".join(self.mask(line, "street", places, streets) for line in text.split("\n"))

    def mask(self, text: str, expecting: str | None = None, places: str = "", streets: frozenset = frozenset()) -> str:
        """Mask one caller message. expecting="name" when the agent just asked for the name,
        "street" when it asked for the street (places: the places already given, left visible),
        "form" for the answer to a texted list of everything missing (name, street, number at once).
        streets: the real street names of the caller's area, written with events._norm."""
        if expecting == "form":
            return self._mask_form(text, places, streets)
        opening, expecting = expecting == "opening", "location" if expecting == "opening" else expecting
        self._where = expecting in ("location", "street")
        text = self._sub(_EMAIL, "EMAIL", text)
        text = self._sub(_LONG_NUMBER, lambda v: "PHONE" if re.match(r"\+|00|0|69|5", v) else "ID", text)
        for pattern in _ADDRESS_PATTERNS:
            # "Παιδιά 3", "Συνολικά 5 άτομα": a count, not an address. Masked, the model lost how many.
            text = pattern.sub(lambda m: m.group(0) if _norm(m.group(0).split()[0]) in _NOT_A_STREET_NAME
                               else self._swap("ADDRESS", m.group(0)), text)
        text = self._sub(_STREET_WORD_NAME, "ADDRESS", text)
        if expecting == "street" or (streets and expecting != "name"):
            text = self._mask_streets(text, places, streets, every_name=expecting == "street")
        if expecting in ("location", "street"):
            text = _WORD_AND_NUMBER.sub(lambda m: self._street_and_number(m), text)
            text = _NAME_AND_NUMBER.sub(
                lambda m: m.group(0) if m.group(1).split()[0].casefold() in _NOT_STREETS else self._swap("ADDRESS", m.group(0)),
                text)
        if opening:
            # The answer to "what happened, and where?": a street may come before its area's street
            # list exists ("Βγαίνει καπνός … στην Ορλώφ"): after "στην", a name that isn't a place.
            # After the street-and-number patterns, so "στη Θεμιστοκλέους 5" stays one address.
            known = set(_norm(places).split())
            text = _AFTER_IN.sub(lambda m: m.group(0) if all(  # "στο Βαθύ Σάμου": two places
                gazetteer.is_place(w, inflected=True) or _norm(w) in known for w in m.group(1).split())
                else m.group(0).replace(m.group(1), self._swap("ADDRESS", m.group(1))), text)
        text = self._sub(_NAME_AFTER_CUE, "PERSON", text, group=1)

        answer = _without_fillers(text)
        if "<PERSON_" not in text and answer and _looks_like_a_name(answer) and (
                expecting == "name" or self._shares_a_known_name(answer)):
            # Also a correction at the read-back ("Αιγέας Δοκιμάκης" after "Αγίας Δοκιμάκης"): an
            # eval call sent the corrected name to the model because nobody had just asked for it.
            name = answer.strip(" .,!?…")
            text = text.replace(name, self._swap("PERSON", name))

        return self.mask_known(text)

    def street_names(self) -> list[str]:
        """The name part of every street masked with a house number, for core._tidy_streets."""
        return sorted(self._street_names)

    def values(self, kind: str) -> list[str]:
        """The real values masked as kind ("ADDRESS", "PERSON") so far in this conversation."""
        return [v for p, v in self._real.items() if p.startswith(f"<{kind}_")]

    def invented(self, text: str) -> bool:
        """True if text uses a placeholder we never made: the model made up a name or address."""
        return any(f"<{m.group(1).upper()}_{m.group(2)}>" not in self._real for m in _PLACEHOLDER.finditer(text))

    def unmask(self, text: str) -> str:
        # A placeholder we never made (the model invented it) is dropped, never read out loud.
        invented = False

        def repl(m: re.Match) -> str:
            nonlocal invented
            real = self._real.get(f"<{m.group(1).upper()}_{m.group(2)}>")
            invented = invented or real is None
            return real if real is not None else ""

        out = _PLACEHOLDER.sub(repl, text)
        # Only where one was dropped; never trim, streamed reply pieces keep their spaces.
        return re.sub(r" {2,}", " ", out).replace(" ,", ",").replace(" ;", ";") if invented else out

    def unmask_obj(self, obj):
        """Unmask every string inside a JSON-like object."""
        if isinstance(obj, str):
            return self.unmask(obj)
        if isinstance(obj, list):
            return [self.unmask_obj(v) for v in obj]
        if isinstance(obj, dict):
            return {k: self.unmask_obj(v) for k, v in obj.items()}
        return obj
