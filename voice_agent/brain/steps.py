"""Which question comes next in a call, decided by code, not by the model.

Docs/Research/09_Location_Questioning.md. In test calls the model ran the conversation itself and
its own labels were unreliable: it asked for the caller's name but marked the question "other"
(so the name reached it unmasked), read the location back after one question, skipped the
read-back, and asked for a house number the caller had already given. Now the brain works out the
next step from the report after every answer, and tells the model which one to ask. The model
still words the question, extracts the facts, picks advice and decides handoffs.

The order, skipping what is already known:
  what happened (the greeting asks "what happened, and where": callers lead with the problem),
  location: area, "did you mean <the real street>?" when the map has no street of that name but
            one that sounds like it, street (or a named landmark), the street spelled when the map finds nothing like
            it, which neighbourhood when the street is in several,
            house number, nearest corner when there is no number, where exactly at a landmark
  location read-back, how many people, anyone injured or trapped,
  the floor (building fire), the caller's name, the final read-back.
A step is skipped after two unanswered asks, or at once when the caller says they don't know.

By text (WhatsApp, SMS) there is no step by step: every reply ends with one list of everything
still missing (form_items), at most FORMS times, then the final read-back. A test by WhatsApp took
a dozen messages for one report.
"""
import re
import unicodedata
from dataclasses import dataclass, field

from . import places
from .report import hazard_of

LOCATION = ["area", "confirm_street", "street", "spell_street", "neighbourhood", "house_number", "cross_street", "exact_spot"]
ALL_STEPS = [*LOCATION, "location_readback", "what_happened", "people", "danger", "floor", "name", "final_readback"]
LOCATION_MAX_ASKS = 8  # location questions in one call, so a confused caller is never stuck
LOCATION_TRIES = 3  # read-backs of the location before going on without a yes
# An area this big is a whole city: street names repeat, so the neighbourhood is asked. Koukaki
# is 2.8 km on OpenStreetMap, Athens 45 km. The model asked it on its own in tests while the
# code's step said "read back", so the two disagreed.
WHOLE_CITY_KM = 12.0
ASKED_ONCE = {"exact_spot", "spell_street", "danger", "floor"}  # the report can't show whether these were answered
MAX_ASKS = {"location_readback": LOCATION_TRIES, "final_readback": 2}
FORMS = 2  # by text: the first list of what is missing, and one reminder of what is still missing

QUESTIONS = {
    "area": "ask which town, village or neighbourhood",
    "confirm_street": "the map has no street of the name the caller gave in that area, and it was probably misheard. "
                      "The real street that sounds closest is {street}. Ask ONLY this, in the caller's language: "
                      "'Did you mean {street}?' Do not read anything else back. Do not change street or "
                      "spoken_address: the code changes them when the caller says yes, and keeps the caller's "
                      "street when they say no. Never say the two street names one after the other",
    "street": "ask for the street, or the name of the nearest landmark if they don't know the street",
    "spell_street": "the map found no street like that in the area and nothing that sounds close: ask the caller "
                    "to spell the street name letter by letter, e.g. 'Could you spell the street for me, letter by "
                    "letter?'",
    "neighbourhood": "ask which neighbourhood it is in; if a map check note lists places, offer those",
    "house_number": "ask for the house number on that street, e.g. 'What number on that street?'",
    "cross_street": "the caller has no house number: ask for the nearest corner or cross street, or a shop or "
                    "sign they can see",
    "exact_spot": "ask where exactly at that landmark: which side, which entrance, or what is opposite",
    "location_readback": "read back ONLY the location, word for word with every name and number exactly as you "
                         "have it, and ask if it is right; fix anything the map check flagged first",
    "what_happened": "ask what happened: 'Tell me exactly what happened.'",
    "people": "ask how many people are with the caller or affected",
    "danger": "ask whether anyone is injured, trapped, unconscious, or cannot leave on their own",
    "floor": "ask which floor they are on and whether everyone can get out",
    "name": "ask for the caller's full name, so operators can call back",
    "final_readback": "read the key facts back in one or two sentences (the location word for word, what "
                      "happened, the people and any animals) and ask if everything is correct; on a clear yes, set action end",
}
TEXT_FINAL = ("read everything back in one message (the location word for word, what happened, the people, any "
              "animals, the name) and ask them to reply YES if it is right or to correct it; on a clear yes, set action end")
LABELS = {"confirm_street": "the street the map suggests, confirmed or refused", "spell_street": "the street spelled letter by letter", "house_number": "house number (or the nearest corner if there is none)", "location_readback":
          "location read-back", "what_happened": "what happened", "final_readback": "final read-back"}
# What the caller's answer to each step is, for masking (masking.py): a name, a place, or other.
EXPECTING = {**{s: "location" for s in LOCATION}, "location_readback": "location", "name": "name"}


@dataclass
class Steps:
    asked: str | None = "what_happened"  # the step the last reply asked for; the greeting asks what happened, and where
    unanswered: dict = field(default_factory=dict)  # step -> times asked and not given
    location_notes: int = 0  # notes that asked for a location piece
    notes: dict = field(default_factory=dict)  # step -> notes that asked for it (a model ignoring them isn't stuck)
    told: str | None = None  # the step the last note told the model to ask
    matches_area: str | None = None  # the area the map's street_matches were found for
    text: bool = False  # WhatsApp or SMS: one list of what is missing per reply, not one question
    forms: int = 0  # lists sent
    form_asked: list = field(default_factory=list)  # the steps the last list asked for (masking.py "form")
    unfound_street: str | None = None  # a street the map didn't find, with no real street sounding close
    floor_said: bool = False  # the caller gave a floor (the report has no field for it: floor_said())
    # A live test (2026-11-15): speech-to-text wrote "Φραγγυλλιδών" for Φραγκιάδων every time. The map
    # found the real street, the model read both names back together, and the caller's "no, Φραγκιάδων"
    # was written with the wrong name again. So the code asks "did you mean …?" as a step of its own,
    # and the code, not the model, puts the real street into the report on a yes.
    suggested_street: str | None = None  # the real street the map suggests, not yet answered
    suggestion_for: str | None = None  # the street as heard, which it would replace
    refused_streets: set = field(default_factory=set)  # streets as heard that the caller kept: not suggested again
    replaced_streets: dict = field(default_factory=dict)  # street as heard -> the real one the caller said yes to
    # The caller's message of this turn holds a street with its house number (core sees it before
    # the model has recorded it), or the map is still looking a street up. While either is so, the
    # neighbourhood is not asked and the location is not read back: in the same live test the
    # caller said the street and number and was asked the neighbourhood twice instead. Only a
    # street with a number counts: a bare capitalised word after a street question is too often
    # not a street ("Βοήθεια, σας παρακαλώ").
    street_in_message: bool = False
    map_pending: bool = False

    def expecting(self) -> str:
        return EXPECTING.get(self.asked or "", "other")


def _limit(step: str) -> int:
    return MAX_ASKS.get(step, 1 if step in ASKED_ONCE else 2)


def _location_pieces(report: dict, st: Steps) -> list[str]:
    location = report["location"]
    street = places.the_street(location.get("street"), location.get("spoken_address"))
    number = any(ch.isdigit() for ch in f"{location.get('spoken_address') or ''} {location.get('street') or ''}")
    matches = location.get("street_matches") or []
    pieces = []
    area = location.get("area")
    if not area:
        pieces.append("area")
    placed = len(matches) == 1 and st.matches_area == area  # the map found the street in one place
    if street and st.suggested_street and street == st.suggestion_for and not st.text and (
            st.unanswered.get("confirm_street", 0) < _limit("confirm_street")
            and st.notes.get("confirm_street", 0) <= _limit("confirm_street")):
        # Before the neighbourhood: the street may simply have been misheard. Not by text (the list of
        # missing details has no line for it; the map note asks), and not once it went unanswered
        # twice: then the neighbourhood is asked as usual.
        pieces.append("confirm_street")
    has_street = bool(street) or st.street_in_message
    # The map is looking the street up, or is about to (the street is in this very message), or it
    # has a real street to offer in its place: the answer may make the neighbourhood question needless.
    waiting = st.map_pending or (st.street_in_message and not street) or "confirm_street" in pieces
    if area and not placed and (places.size_km(area) or 0) > WHOLE_CITY_KM and not waiting:
        pieces.append("neighbourhood")  # a whole city: which neighbourhood, before the street
    if not has_street and not location.get("landmark"):
        pieces.append("street")
    if street and street == st.unfound_street and st.matches_area == area:
        pieces.append("spell_street")  # last resort: the area's street list had nothing close (spelling.py)
    if street and len(matches) > 1 and st.matches_area == area and "neighbourhood" not in pieces:
        pieces.append("neighbourhood")  # stale once the caller named a neighbourhood: it is checked again
    if street and not number:
        pieces.append("house_number")
        if st.unanswered.get("house_number", 0) >= 2 and not location.get("cross_street"):
            pieces.append("cross_street")
    if location.get("landmark") and not street:
        pieces.append("exact_spot")
    return pieces


def remaining(report: dict, st: Steps, hazard_unclear: bool = False) -> list[str]:
    """The steps still to ask, in order, without those the caller couldn't or wouldn't answer."""
    location, people = report["location"], report.get("people") or []
    steps = []
    # What happened first: callers lead with it (Docs/Research/09), and the location comes right after.
    if not (report.get("hazard_type") and report.get("situation")) or hazard_unclear:
        steps.append("what_happened")
    steps += _location_pieces(report, st) if st.location_notes < LOCATION_MAX_ASKS else []
    # Also when the place is in the message being answered right now (the report has nothing yet):
    # otherwise the read-back is missing from "After that" and the model goes on to the name, as the
    # test set showed (2026-11-15: "Στο Καρλόβασι, οδός … 12." was answered with "what is your name?").
    said_where = any(location.get(k) for k in ("area", "spoken_address", "landmark")) or st.street_in_message
    no_people = not people
    no_danger = not any(k in g for g in people for k in ("injured", "trapped", "unresponsive", "dead", "cannot_walk"))
    # While the map is looking the street up the read-back waits: a misheard street was read back,
    # confirmed, and then questioned. But only while people and injuries are still to ask: the
    # test set (2026-11-15) showed the name asked before the read-back otherwise, and one turn more.
    waiting_for_map = (st.map_pending or (st.street_in_message and not location.get("street"))) and (no_people or no_danger)
    if said_where and not location.get("confirmed_with_caller") and not st.text and not waiting_for_map:
        steps.append("location_readback")  # by text the final read-back has the location word for word
    if no_people:
        steps.append("people")
    if no_danger:
        steps.append("danger")
    if hazard_of(report) == ("fire", "building") and not st.floor_said:
        steps.append("floor")
    if not report.get("caller", {}).get("name"):
        steps.append("name")
    steps.append("final_readback")
    if st.text:
        # Lists, not single questions: what two lists didn't get is left to the operator.
        return steps if st.forms < FORMS else ["final_readback"]
    return [s for s in steps if st.unanswered.get(s, 0) < _limit(s) and st.notes.get(s, 0) <= _limit(s)]


def form_items(report: dict, st: Steps) -> list[str]:
    """What the next text list asks for: steps, with the location in one item when area or street is
    missing ("where": town, street and number). Empty once two lists were sent or nothing is missing."""
    missing = [s for s in remaining(report, st) if s not in ("location_readback", "final_readback")]
    if not st.text or st.forms >= FORMS:
        return []
    where = [s for s in missing if s in LOCATION]
    if "area" in where or "street" in where:
        missing = [s for s in missing if s not in LOCATION]
        missing.insert(1 if missing[:1] == ["what_happened"] else 0, "where")
    return missing


def after_answer(report: dict, st: Steps, caller_text: str, hazard_unclear: bool = False,
                 asked: str | None = None) -> None:
    """After the caller's answer is in the report: was the step we asked for given? Then remember
    which step the new reply asks: the one the model says it asked (its "expecting"), since it
    sometimes asks something else (a clarification, or the step after the one in the note), else
    the first one still missing."""
    missing = remaining(report, st, hazard_unclear)
    # "Keratsini, I don't know the street": the "don't know" is about the first piece still missing.
    target = st.asked if st.asked in missing else (
        missing[0] if missing and missing[0] in LOCATION and cannot_say(caller_text) else None)
    if target:
        st.unanswered[target] = st.unanswered.get(target, 0) + (2 if cannot_say(caller_text) else 1)
        missing = remaining(report, st, hazard_unclear)
    if asked in ALL_STEPS:
        st.asked = asked
    elif asked == "other":
        st.asked = None  # "who exactly?", or an answer to the caller's question: no step was asked
    elif asked == "location":  # the older, coarse label
        st.asked = next((s for s in missing if EXPECTING.get(s) == "location"), missing[0] if missing else None)
    else:
        st.asked = missing[0] if missing else None


def note(report: dict, st: Steps, hazard_unclear: bool = False, suggestion: str | None = None) -> str | None:
    """The instruction on the caller's message: what to ask next, and what comes after it.
    suggestion: the street the map suggests as the model may see it (its placeholder)."""
    missing = remaining(report, st, hazard_unclear)
    if not missing:
        return None
    if st.text:
        if form_items(report, st):
            st.told = None
            return ("text: after your reply the code adds one numbered list of every detail still missing. Do not "
                    "ask for missing details yourself. Reply in at most two short sentences: acknowledge what they "
                    "wrote, and ask only what a map check note above asks to confirm. Set expecting to other")
        st.told = "final_readback"
        return f"next (final_readback): {TEXT_FINAL}. Set expecting to final_readback"
    first = missing[0]
    st.told = first
    st.notes[first] = st.notes.get(first, 0) + 1
    if first in LOCATION:
        st.location_notes += 1  # counted per note, so a model that ignores the notes is not stuck
    again = (" You asked once already: ask again more simply and help them, e.g. a street sign, the number on "
             "a door or bell.") if first in LOCATION and st.unanswered.get(first) else (
             " You asked once already: ask again in different, simpler words." if st.unanswered.get(first) else "")
    # Also what comes once this is given: a caller who gave the street in their answer was read back
    # at once in a test call, because the note didn't say a house number comes next.
    later = missing[1:4] + (["house_number"] if first == "street" and "house_number" not in missing else [])
    after = f" After that: {', '.join(LABELS.get(s, s) for s in later)}." if later else ""
    if first == "what_happened" and st.asked == "what_happened" and not st.unanswered.get(first) and later:
        # The greeting asked "what happened, and where"; callers usually tell both at once. Saying
        # "ask what happened" here made the model ask it again in an eval run, after the caller had said it.
        where = [s for s in missing if s in LOCATION]
        order = (f"the first location detail still missing, in this order: {', '.join(LABELS.get(s, s) for s in where)}"
                 f" (the house number after the street). People, injuries and the name come only after the location"
                 if where else f"the first of these still missing, in this order: {', '.join(LABELS.get(s, s) for s in later)}")
        return (f"this message answers the question just asked (what happened, and where): record what it says. "
                f"Then ask {order}. "
                "Only if it doesn't say what happened at all, ask that instead, e.g. 'Tell me exactly what happened.' "
                "Ask one short question. Nothing else comes first unless someone is not breathing or the handoff "
                "rules apply. Set expecting to the item your reply asks")
    question = QUESTIONS[first].format(street=suggestion or "that street") if first == "confirm_street" else QUESTIONS[first]
    return (f"next ({first}): {question}.{again}{after} Ask one short question. If the caller's message "
            "already answers it, record it and ask the first item of 'After that' still missing instead, in that "
            "order (an eval call asked about injuries before the street). Nothing else comes first unless someone is "
            "not breathing or the handoff rules apply. Set expecting to the item your reply asks")


# Said when the caller can't or won't give a piece: skip it at once instead of asking twice.
_CANNOT_SAY = ("δεν ξερω", "δεν γνωριζω", "δεν θυμαμαι", "δεν ειμαι σιγουρ", "ιδεα δεν εχω", "δεν εχω ιδεα",
               "δεν βλεπω", "δεν εχει αριθμο", "δεν θελω να", "δεν μπορω να πω",
               "bilmiyorum", "hatirlamiyorum", "emin degilim", "numara yok", "soylemek istemiyorum",
               "don t know", "dont know", "no idea", "not sure", "no number", "can t see", "rather not",
               "je ne sais pas", "sais pas", "aucune idee", "pas de numero")


def plain_words(text: str) -> list[str]:
    plain = "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))
    return re.findall(r"\w+", plain.replace("ı", "i").replace("ğ", "g").replace("ş", "s"))


# A floor in any of the four languages, compared without accents: "5th floor", "floor 3", "basement",
# "3ος όροφος", "ισόγειο", "4. kat", "zemin kat", "2e étage". A WhatsApp test (2026-10-31) said "I am in the
# 5th floor" in the first list and was asked the floor again in the reminder: the report keeps no floor.
_FLOOR = re.compile(r"\b(?:\d+\s*(?:st|nd|rd|th)?\s+floor|floor\s*(?:no\s*)?\d+|(?:ground|top|first|second|third|"
                    r"fourth|fifth|sixth|seventh|eighth|ninth|tenth|last)\s+floor|basement|"
                    r"οροφ\w*|ισογει\w*|υπογει\w*|ρετιρε|"
                    r"\d+\s*(?:inci|nci|uncu|ncu)?\s*kat\w*|(?:zemin|bodrum|cati) kat\w*|"  # not Bodrum the town
                    r"\d+\s*(?:e|eme|er)?\s*etage|etage|rez de chaussee|sous sol)\b")


def floor_said(text: str) -> bool:
    return bool(_FLOOR.search(" ".join(plain_words(text.replace("-", " ")))))


def cannot_say(text: str) -> bool:
    plain = " ".join(plain_words(text.replace("'", " ").replace("’", " ")))
    return any(phrase in plain for phrase in _CANNOT_SAY)
