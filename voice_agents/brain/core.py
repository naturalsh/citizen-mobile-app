"""The brain: start_call, turn / turn_stream, end_call (see contract.py)."""
import json
import logging
import os
import queue
import re
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as WaitedTooLong
from typing import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from google import genai
from google.genai import types

from . import budget, control, gazetteer, places, spelling, steps, translit
from .budget import LimitReached
from .contract import CallInfo, EndReason, TurnResult
from .events import _norm, suggest_event
from .langs import script_language
from .masking import Masker
from .prompts import system_prompt
from .report import apply_update, new_report
from .steps import Steps
from .streaming import ReplyStream, salvage
from .tools import ADVICE, PHRASES, TURN_SCHEMA

log = logging.getLogger("brain")

SUPPORTED_LANGS = ["el", "tr", "en", "fr"]
SCRIPT_MIN_LETTERS = 4  # a caller line needs this many letters before its alphabet can switch the language
LIVE_MODEL = os.getenv("BRAIN_LIVE_MODEL", "gemini-3.5-flash-lite")
# Asked when the live model is slow or busy. A different model has its own quota (issue #4).
BACKUP_MODEL = os.getenv("BRAIN_BACKUP_MODEL", "gemini-3.5-flash")
# How long a caller waits for the live model before we ask the backup instead.
MODEL_TIMEOUT_S = float(os.getenv("BRAIN_MODEL_TIMEOUT_S", "4"))
REPORT_MODEL = os.getenv("BRAIN_REPORT_MODEL", "gemini-3.5-flash-lite")
THINKING_LEVEL = os.getenv("BRAIN_THINKING_LEVEL", "minimal")
# Language of the 112 operators. "auto": Turkish for +90 numbers, otherwise Greek.
OPERATOR_LANG = os.getenv("BRAIN_OPERATOR_LANG", "auto")
OUTPUT_DIR = Path(os.getenv("BRAIN_OUTPUT_DIR", "output"))
# Hide names, street addresses and numbers from the model (brain/masking.py). "off" to compare.
MASKING = os.getenv("BRAIN_MASKING", "on") != "off"
SUMMARY_TIMEOUT_MS = 20_000
# Once a streamed reply has started, give up if no new text arrives for this long.
STREAM_STALL_S = 6.0
# Gemini refuses requests with a deadline under 10 s, so requests get this one and the
# shorter waits above are enforced on our side: a slow request is abandoned, not cancelled.
SERVER_DEADLINE_MS = 15_000
_requests = ThreadPoolExecutor(max_workers=8, thread_name_prefix="gemini")
_place_checks = ThreadPoolExecutor(max_workers=2, thread_name_prefix="places")  # map checks (places.py)

_LANG_TAG = re.compile(r"\((caller language|channel): \w+\)|\((report problems|context): [^)]*\)|\[lang: \w+\]")

_client: genai.Client | None = None


def _gemini() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client()  # reads GEMINI_API_KEY
    return _client


@dataclass
class _Session:
    info: CallInfo
    lang: str
    report: dict
    history: list[types.Content] = field(default_factory=list)
    transcript: list[dict] = field(default_factory=list)
    advice_given: set[str] = field(default_factory=set)
    report_problems: list[str] = field(default_factory=list)  # told to the model next turn
    masker: Masker = field(default_factory=Masker)
    expecting: str | None = None  # what the agent's last question asked for, e.g. "name"
    place_check: object | None = None  # running map check of the location (places.py), a Future
    place_checked: tuple | None = None  # the (area, spoken_address, landmark, street) it was started for
    steps: Steps = field(default_factory=Steps)  # which question comes next (steps.py), decided by code
    turn_streets: list[str] = field(default_factory=list)  # streets with a house number in this turn's message
    hold_advice: bool = False  # this turn's caller message was unclear: no advice until confirmed
    hazard_unclear: bool = False  # the hazard so far rests on an unclear message ("Φωτιά;")
    end_holds: int = 0  # times an "end" was turned into "is everything correct?" (_clear_yes)


_sessions: dict[str, _Session] = {}
# The last error a model gave, e.g. a rate limit, so a stopped eval run can say why (2026-10-25:
# Gemini refused every request mid-run, and the reason was lost).
last_model_error: str | None = None


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _phrase(s: _Session, name: str) -> str:
    return _phrase_for(name, s.lang, s.info.channel)


def _phrase_for(name: str, lang: str, channel: str) -> str:
    """Fixed phrase in a language.

    Prefers a "<name>_<channel>" variant (e.g. greeting_sms), then "<name>_text" for any text channel.
    """
    for variant in (f"{name}_{channel}", f"{name}_text" if channel != "voice" else None):
        if variant in PHRASES:
            name = variant
            break
    return PHRASES[name].get(lang) or PHRASES[name]["en"]


def _greeting(lang: str, channel: str, missed_call: bool) -> str:
    # No "for Turkish, continue in Turkish" line: it sounded odd to Greek callers, and the call
    # switches language by itself when the caller speaks another supported one.
    return _phrase_for("greeting_missed_call" if missed_call else "greeting", lang, channel)


def _form(items: list[str], lang: str, channel: str, again: bool) -> str:
    """One list of everything still missing, so a texted report takes two or three messages, not a
    dozen (steps.form_items). WhatsApp gets one item per line; SMS one line, since every part is billed."""
    lines = [_phrase_for(f"form_{item}", lang, channel) for item in items]
    intro = _phrase_for("form_again" if again else "form_intro", lang, channel)
    if channel == "whatsapp":
        return intro + "\n" + "\n".join(f"{i}. {line}" for i, line in enumerate(lines, 1))
    return intro + " " + " ".join(f"{i}) {line}." for i, line in enumerate(lines, 1))


# The model's own request for details, when the list that follows asks for them anyway: on a WhatsApp
# test (2026-10-31) it wrote "Please tell me your exact address and details." right after the caller
# had sent them, despite the prompt, and the list came under it. Questions go too: the list asks.
_ASKS = re.compile(r"(?i)\b(?:tell|give|send|share)\s+(?:me|us)\b|\bplease\s+provide\b|πείτε\s+μου|δώστε\s+μου|"
                   r"στείλτε\s+μου|söyleyin|yazın|bildirin|dites[- ]moi|donnez[- ]moi|envoyez[- ]moi")


def _no_requests(text: str) -> str:
    """The text before a list, without its questions or requests for details (advice has neither)."""
    sentences = re.split(r"(?<=[.!?;\u037e…])\s+", text)
    kept = [x for x in sentences if not (_ASKS.search(x) or x.rstrip().endswith(("?", ";", "\u037e")))]
    return " ".join(kept)


def _add_form(s: _Session, text: str, text_en: str | None) -> tuple[str, str | None]:
    """By text: the reply, then the list of what is still missing (once, plus one reminder)."""
    items = steps.form_items(s.report, s.steps) if s.steps.text else []
    s.steps.form_asked = items
    if not items:
        return text, text_en
    again = s.steps.forms > 0
    s.steps.forms += 1
    text, text_en = _no_requests(text), _no_requests(text_en) if text_en else text_en
    s.steps.asked = None  # a list, not one step: the answer is masked as a form ("form" in masking.py)
    sep = "\n\n" if s.info.channel == "whatsapp" else " "
    form, form_en = _form(items, s.lang, s.info.channel, again), _form(items, "en", s.info.channel, again)
    return sep.join(p for p in (text, form) if p), sep.join(p for p in (text_en, form_en) if p) if text_en else None


def fixed_voice_texts(lang: str) -> list[str]:
    """Every line the brain says word for word on a voice call in `lang`.

    The voice side pre-records these (voice/prerecord.py) and plays the recording whenever
    the brain says one of them. Built with the same code as the real replies, so they match.
    """
    lines = [_greeting(lang, "voice", missed) for missed in (False, True)]
    lines += [_phrase_for(name, lang, "voice") for name in ("hold", "handoff", "error_fallback")]
    lines += [entry.get(lang) or entry["en"] for entry in ADVICE.values()]
    return list(dict.fromkeys(lines))  # no duplicates, order kept


def _advice(s: _Session, topic: str) -> str:
    entry = ADVICE[topic]
    if s.info.channel == "sms" and "sms" in entry:
        entry = entry["sms"]
    return entry.get(s.lang) or entry["en"]


def _english_fixed() -> dict[str, str]:
    """Every fixed phrase and advice text, in any language, mapped to its English version."""
    english = {}
    for entry in [*PHRASES.values(), *ADVICE.values(), *(e["sms"] for e in ADVICE.values() if "sms" in e)]:
        if isinstance(entry, dict) and isinstance(entry.get("en"), str):
            english.update({text: entry["en"] for text in entry.values() if isinstance(text, str)})
    return english


_FIXED_EN = _english_fixed()


def _log_line(s: _Session, role: str, text: str, text_en: str | None = None, lang: str | None = None) -> None:
    # text_en: what operators read on the dashboard. Known when the line is English or a fixed
    # phrase; the caller's own words get theirs when the model answers (_finish_turn). A line whose
    # letters prove another language is never its own English copy (Turkish was once saved so).
    lang = lang or s.lang
    if text_en is None:
        text_en = text if lang == "en" and not script_language(text) else _FIXED_EN.get(text)
    s.transcript.append({"role": role, "text": text, "lang": lang, "at": _now(), "text_en": text_en})


_save_lock = threading.Lock()  # a finished map check saves from its own thread (_store_map_result)


def _save(s: _Session) -> None:
    """Report sink. For now writes JSON files; the dashboard will read from here."""
    with _save_lock:
        _write(s)


def _write(s: _Session) -> None:
    for kind, data in (("reports", s.report), ("transcripts", s.transcript)):
        folder = OUTPUT_DIR / kind
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{s.info.call_id}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _result(s: _Session, text: str, action="continue", handoff_reason=None, text_en: str | None = None) -> TurnResult:
    _log_line(s, "agent", text, text_en)
    _save(s)
    return TurnResult(reply_text=text, lang=s.lang, action=action, handoff_reason=handoff_reason, report=s.report)


def start_call(info: CallInfo) -> TurnResult:
    lang = info.lang_guess if info.lang_guess in SUPPORTED_LANGS else "en"
    report = new_report(info.call_id, info.phone, lang, info.aml, info.channel, info.trigger)
    s = _Session(info=info, lang=lang, report=report)
    s.steps.text = info.channel != "voice"
    _sessions[info.call_id] = s

    if control.is_paused():
        return _paused_handoff(s)
    missed_call = (info.trigger or {}).get("type") == "failed_112_call"
    greeting, greeting_en = _greeting(lang, info.channel, missed_call), _greeting("en", info.channel, missed_call)
    if missed_call and s.steps.text:  # we write first: the list comes with the greeting
        greeting, greeting_en = _add_form(s, greeting, greeting_en)
    # The model needs to know what the caller already heard.
    s.history.append(types.Content(role="model", parts=[types.Part(text=greeting)]))
    s.expecting = s.steps.expecting()  # the greeting asks what happened, and where
    return _result(s, greeting, text_en=greeting_en)


def hold_phrase(call_id: str) -> str:
    """Short "one moment" line in the caller's language, for the voice side to say while a reply is slow."""
    s = _sessions[call_id]
    return _phrase(s, "hold")


def turn(call_id: str, caller_text: str, lang: str, interrupted: bool = False) -> TurnResult:
    s, early = _prepare_turn(call_id, caller_text, lang, interrupted)
    if early:
        return early
    try:
        return _finish_turn(s, _ask(s))
    except LimitReached:
        return _limit_handoff(s)
    except Exception:
        log.exception("no model answered for %s", call_id)
        return _give_up(s)


def turn_stream(call_id: str, caller_text: str, lang: str, interrupted: bool = False) -> Iterator[tuple[str, object]]:
    """Like turn(), but hands out the reply while the model is still writing it.

    Yields ("start", {"action", "handoff_reason", "lang"}) once, then ("text", piece) events to
    speak in order, then ("result", TurnResult). The pieces joined are what the caller hears;
    the result is the same as turn() would return. Blocking: run it in a thread.
    """
    s, early = _prepare_turn(call_id, caller_text, lang, interrupted)
    if early:
        yield from _whole(early)
        return

    try:
        budget.spend("turn-stream")
    except LimitReached:
        yield from _whole(_limit_handoff(s))
        return

    reader = ReplyStream(clean=lambda text: _speakable(s, s.masker.unmask(text)),
                         prefix=lambda a, t: _prefix(s, a, t),
                         allow_handoff=lambda reason: _handoff_allowed(s, reason),
                         broken=s.masker.invented, fallback=_phrase(s, "error_fallback"))
    events: queue.Queue = queue.Queue()
    threading.Thread(target=_pump, args=(list(s.history), events), daemon=True).start()
    raw, deadline, failure = "", time.monotonic() + MODEL_TIMEOUT_S, None
    while True:
        wait = STREAM_STALL_S if raw else deadline - time.monotonic()
        try:
            kind, value = events.get(timeout=max(wait, 0.01))
        except queue.Empty:
            kind, value = "slow", None
        if kind == "chunk":
            raw += value
            for event in reader.feed(raw):
                if event[0] == "start" and event[1]["action"] == "end" and _would_hold(s):
                    event = ("start", {**event[1], "action": "continue"})  # "is everything correct?" instead
                yield event[0], ({**event[1], "lang": s.lang} if event[0] == "start" else event[1])
            continue
        if kind != "done":
            failure = value or "no answer in time"
        break

    if failure and not reader.spoke:
        # Nothing said yet: ask the other models the normal way and say the whole reply at once.
        log.warning("streamed answer failed for %s (%s); trying the backup", call_id, failure)
        try:
            result = _finish_turn(s, _ask(s, skip_first=True))
        except LimitReached:
            result = _limit_handoff(s)
        except Exception:
            log.exception("no model answered for %s", call_id)
            result = _give_up(s)
        yield from _whole(result, started=reader.started)
        return

    if reader.broke:
        yield "result", _made_up(s, raw, "".join(reader.said).strip())
        return
    if failure:
        # Part of the reply was already spoken when the model stopped: keep that much.
        log.warning("streamed answer cut off for %s (%s)", call_id, failure)
        raw = salvage(raw, reader)
    try:
        result = _finish_turn(s, raw)
    except ValueError:
        log.exception("unreadable streamed answer for %s", call_id)
        result = _finish_turn(s, salvage(raw, reader))
    yield "result", result


def _whole(result: TurnResult, started: bool = False) -> Iterator[tuple[str, object]]:
    if not started:
        yield "start", {"action": result.action, "handoff_reason": result.handoff_reason, "lang": result.lang}
    yield "text", result.reply_text
    yield "result", result


def _pump(history: list, events: queue.Queue) -> None:
    """Runs in a thread: streams the live model's answer into the queue."""
    try:
        stream = _gemini().models.generate_content_stream(
            model=LIVE_MODEL, contents=history, config=_turn_config()
        )
        for chunk in stream:
            if chunk.text:
                events.put(("chunk", chunk.text))
        events.put(("done", None))
    except Exception as exc:
        events.put(("error", exc))


def _prepare_turn(call_id: str, caller_text: str, lang: str, interrupted: bool) -> tuple[_Session, TurnResult | None]:
    s = _sessions[call_id]
    # The letters beat the language the voice side passed: speech-to-text labelled Turkish as English.
    # But a letter or two prove nothing: an English caller's "uh" was written "η.", and the next reply
    # was in Greek (demo call, 2026-10-30).
    letters = len(re.findall(r"[^\W\d_]", caller_text))
    lang = (script_language(caller_text) if letters >= SCRIPT_MIN_LETTERS else None) or lang
    _log_line(s, "caller", caller_text, lang=lang)  # in the language it was said in, for the dashboard
    s.steps.floor_said = s.steps.floor_said or steps.floor_said(caller_text)  # before the next question is chosen
    if control.is_paused():
        return s, _paused_handoff(s)

    if lang != s.lang:
        if lang not in SUPPORTED_LANGS:
            return s, _hand_off(s, "unsupported_language")
        s.lang = lang
        s.report["caller_language"] = lang

    if _goodbye(caller_text) and (s.report.get("situation") or any(s.report["location"].get(k) for k in ("area", "spoken_address", "landmark"))):
        # The caller is leaving: say that the report is passed on, and ask nothing more. A live test
        # (2026-11-15) answered "Αντίο" with the neighbourhood question again. The line is not closed
        # by us: speech-to-text can write "Bye." from noise, and a caller who speaks again is heard.
        return s, _result(s, _phrase(s, "passed_on"))

    asked_for = _asked_for(s)  # before this turn's note: what the last reply asked, for masking
    # Masked before the next step is chosen: a street in this message changes what is asked (steps.py).
    said = s.masker.mask(caller_text, *asked_for, _area_streets(s)) if MASKING else caller_text
    # A street with its house number in this message (the real values behind the placeholders it holds).
    # Only in an answer about the place, and only a name the masker took for a street: "Συνολικά 5 άτομα"
    # after the people question is a count.
    known = {_norm(name) for name in s.masker.street_names()}
    s.steps.street_in_message = MASKING and asked_for[0] in ("location", "street", "opening") and any(
        _norm(re.sub(r"\s+\d{1,4}\s*[A-Za-zΑ-Ωα-ω]?$", "", re.sub(r"^\s*(?i:οδός|οδού|οδό|λεωφόρος|λεωφόρου|λεωφόρο)\s+", "", s.masker.unmask(found.group(0))))) in known
        and any(ch.isdigit() for ch in s.masker.unmask(found.group(0)))
        for found in re.finditer(r"<ADDRESS_\d+>", said))
    # Every "street number" this message holds, in an answer about the place or to a texted list: the
    # street the code falls back on when the model records none (_street_from_address).
    s.turn_streets = [value for value in (s.masker.unmask(found.group(0)) for found in re.finditer(r"<ADDRESS_\d+>", said))
                      if any(ch.isdigit() for ch in value)] if MASKING and asked_for[0] in (
                          "location", "street", "opening", "form") else []
    s.steps.map_pending = places.ENABLED and s.place_check is not None and not s.place_check.done()
    note = f"(caller language: {s.lang})"
    if s.info.channel != "voice":
        note += f" (channel: {s.info.channel})"
    if interrupted:
        note += " (the caller interrupted your last reply before it finished)"
    if (s.info.trigger or {}).get("type") == "failed_112_call":
        note += " (context: we contacted this person first because their call to 112 did not get through)"
    if s.report_problems:
        note += f" (report problems: {'; '.join(s.report_problems)})"
    if map_note := _map_check_result(s):
        note += f" (map check: {map_note})"
    # Before the next step is chosen: a yes changes the report, and so does a yes taken back.
    answered = _answer_to_suggestion(s, caller_text) or _take_back_the_suggestion(s, caller_text)
    pending = s.steps.suggested_street
    if step := steps.note(s.report, s.steps, s.hazard_unclear,
                          (s.masker.hide("ADDRESS", pending) if MASKING else pending) if pending else None):
        note += f" ({step})"
    if answered:
        note += f" {answered}"
    if s.steps.street_in_message and not s.report["location"].get("street"):
        # The model sees one placeholder and cannot tell it holds a number: in a replay it asked
        # "what number on that street?" right after the caller had said it.
        note += (" (the caller's message holds the street and its house number together, as one placeholder: record "
                 "that placeholder in street and spoken_address, and do not ask for the street or the house number)")
    confirms = s.hazard_unclear and clear_yes(caller_text)  # "Ναι" to "Did you say fire?"
    s.hold_advice = _unclear(caller_text) and not confirms and (not s.report["hazard_type"] or s.hazard_unclear)
    # One-word places and yeses are normal answers to location questions and read-backs.
    if s.hold_advice and s.expecting != "location" and not clear_yes(caller_text):
        note += (" (unclear: the caller's message is one word or sounds like a question, and speech-to-text "
                 "may have misheard it. If it is about what happened, confirm it before anything else with one "
                 "short question, e.g. 'Did you say fire? What is burning?'. No advice this turn.)")
    if asked_for[0] == "form" and "name" in s.steps.form_asked and s.masker.form_name and MASKING:
        # The model saw the name masked in a list and, in an eval run, left caller_name empty.
        s.report["caller"]["name"] = s.masker.form_name
    if s.steps.asked == "spell_street" and (word := spelling.spelled(caller_text, s.lang)):
        said = _take_spelled(s, word)
    s.history.append(types.Content(role="user", parts=[types.Part(text=f"{note} {said}")]))
    return s, None


# A name question the code didn't schedule (the model asked on its own): its words still mark the
# answer as a name, so the name is masked.
_NAME_QUESTION = re.compile(r"όνομ|ονοματεπώνυμ|λένε|\bname\b|\badın|\bisminiz|\bisim|\bnom\b|appelez", re.IGNORECASE)


def _street_from_address(s: _Session) -> None:
    """The model put a masked street into spoken_address but left street empty (it can't tell
    <ADDRESS_1> is a street), so the map never searched it: in eval runs on 2026-10-27, "στην Ορλώφ"
    and "Ορλώφ 12" in an opening. The code knows which masked values are in the address."""
    location = s.report["location"]
    spoken = location.get("spoken_address") or ""
    if location.get("street"):
        return

    def name_of(value: str) -> str:  # "Gazi Caddesi No 18" -> "Gazi Caddesi"
        street = re.sub(r"\s*\b\d+\s*[A-Za-zΑ-Ωα-ω]?\b", "", value).strip(" .,-:")
        return re.sub(r"(?i)\s+(?:no|numara|αριθμός|αρ)[.:]?$", "", street).strip(" .,-:")

    for value in sorted(s.masker.values("ADDRESS"), key=len, reverse=True):
        street = name_of(value)
        # A masked town or neighbourhood ("Ορλώφ 12 Κουκάκι" in a text) is not the street.
        if spoken and value in spoken and len(street) >= 3 and not gazetteer.is_place(street, inflected=True):
            location["street"] = street
            s.masker.hide("ADDRESS", street)  # known to the masker, so the summary request masks it too
            return
    # The model left the street out of the address altogether: a texted "İzmir Buca, Şirinyer, Gazi
    # Caddesi No 18. …" was recorded as its area only, and the next list asked for the street name
    # (test set 2026-11-15). The street with a number in this very message is the street.
    elsewhere = " ".join(filter(None, (location.get("cross_street"), location.get("landmark"))))
    for value in s.turn_streets:
        street = name_of(value)
        if len(street) >= 3 and value not in elsewhere and not gazetteer.is_place(street, inflected=True):
            location["street"] = street
            location["spoken_address"] = f"{value}, {spoken}" if spoken else value
            s.masker.hide("ADDRESS", street)
            return


def _area_from_address(s: _Session) -> None:
    """The model left area empty although the address names a town: a WhatsApp test on 2026-10-27
    wrote "fragiadon 16 Piraeus" twice and the map check, with no area, found nothing. The last
    real place in the address (gazetteer.py) is the area, as addresses end with the town."""
    location = s.report["location"]
    spoken = location.get("spoken_address") or ""
    if location.get("area") or not spoken:
        return
    found = []  # "Ορλώφ 12, Κουκάκι, Αθήνα" -> "Κουκάκι, Αθήνα": every place piece at the end
    for piece in reversed([p.strip(" .") for p in re.split(r"[,\n;]", spoken) if p.strip(" .")]):
        if not any(ch.isdigit() for ch in piece) and gazetteer.is_place(piece, inflected=True):
            found.insert(0, piece)
            continue
        words = piece.split()
        for size in (2, 1):  # the end of "fragiadon 16 Piraeus"
            tail = " ".join(words[-size:])
            if len(words) > size and not any(ch.isdigit() for ch in tail) and gazetteer.is_place(tail, inflected=True):
                found.insert(0, tail)
                break
        break
    if not found:
        # Town first: "Piraeus, fragiadon 16", and "Σάμο, Βαθύ, Θεμιστοκλέους 5": every place piece at the
        # start. In the test set (2026-11-15) only the first piece was looked at, "Σάμο" was not known as
        # Σάμος, and the caller was asked for the area three times after saying it.
        for piece in [p.strip(" .") for p in re.split(r"[,\n;]", spoken) if p.strip(" .")]:
            if any(ch.isdigit() for ch in piece) or not gazetteer.is_place(piece, inflected=True):
                break
            found.append(piece)
    if found:
        location["area"] = ", ".join(found)


def _take_spelled(s: _Session, word: str) -> str:
    """The street the caller just spelled goes into the report by code (the model never sees street
    names) and is checked on the map; the model gets a placeholder for it."""
    location = s.report["location"]
    old = places.the_street(location.get("street"), location.get("spoken_address"))
    location["street"] = word
    spoken = location.get("spoken_address") or ""
    location["spoken_address"] = spoken.replace(old, word) if old and old in spoken else word
    location["confirmed_with_caller"] = False
    name = s.masker.hide("ADDRESS", word) if MASKING else word
    return (f"(the caller spelled the street letter by letter: {name}. Street and spoken_address are set to it; "
            "do not change them) " + name)


MAX_STREET_HINTS = 600  # Παιανία has 495; the hints keep as many as fit (voice/keywords.py)


def street_hints(call_id: str) -> list[str]:
    """The real street names of the caller's area once the map check has them, for the voice side's
    speech-to-text hints (voice/keywords.py); empty until then. Never waits on the network: a test
    call heard "Βασιλίσσης Φρειδερίκης …" as "Σφαιρική …"."""
    s = _sessions.get(call_id)
    area = s and s.report["location"].get("area")
    if not (area and places.ENABLED and places.STREET_LIST):
        return []
    try:
        names = (places.street_names(area) or []) if places.has_street_list(area) else []
    except Exception:
        log.exception("street hints unavailable for %s", call_id)
        return []
    # A whole city (Piraeus: 8,515 streets in the local index) is far more than the ~4,500 characters
    # of hints: an alphabetical slice would only bias speech-to-text, so hint a neighbourhood's list only.
    return names if len(names) <= MAX_STREET_HINTS else []


def _asked_for(s: _Session) -> tuple[str | None, str]:
    """What the last question asked for, for masking: (expecting, places already given). It comes
    from the step the code scheduled (steps.py), not from the model's label: the model once asked
    for the name but marked the question "other", and the name reached it unmasked."""
    last = next((t["text"] for t in reversed(s.transcript[:-1]) if t["role"] == "agent"), "")
    location = s.report["location"]
    given = " ".join(filter(None, (location.get("area"), location.get("landmark"))))
    if s.steps.form_asked:  # a texted list: any piece may be a name, a street or a number
        return "form", given
    if s.expecting == "name" or s.steps.told == "name" or _NAME_QUESTION.search(last):
        return "name", ""  # scheduled, labelled, or worded as a name question: mask it either way
    street = places.the_street(location.get("street"), location.get("spoken_address")) or ""
    # Places already given stay visible: the area, the landmark and the rest of the address.
    given = " ".join(filter(None, (location.get("area"), location.get("landmark"),
                                   (location.get("spoken_address") or "").replace(street, " ") if street else
                                   location.get("spoken_address"))))
    if s.steps.asked == "what_happened":
        return "opening", given  # "my house burned down, at …": what happened often comes with where
    return ("street" if s.steps.asked in ("street", "cross_street") else s.expecting), given


def _area_streets(s: _Session) -> frozenset:
    """The real street names of the caller's area (places.street_names), for masking: a street
    said anywhere in the call is masked, however it is phrased. Empty until the list is in."""
    area = s.report["location"].get("area")
    if not (area and places.ENABLED and places.STREET_LIST):
        return frozenset()
    try:
        names = places.street_names(area) or []
    except Exception:
        log.exception("street list unavailable for masking in %s", s.info.call_id)
        return frozenset()
    words = {_norm(n) for n in names} | {_norm(n.split()[-1]) for n in names if len(n.split()[-1]) >= 5}
    return frozenset(w for w in words if w)


def _turn_config() -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        system_instruction=system_prompt(control.handoff_mode()),
        response_mime_type="application/json",
        response_json_schema=TURN_SCHEMA,
        thinking_config=types.ThinkingConfig(thinking_level=THINKING_LEVEL),
        temperature=0.3,
        http_options=types.HttpOptions(timeout=SERVER_DEADLINE_MS),
    )


def _ask(s: _Session, skip_first: bool = False) -> str:
    """The model's raw JSON answer. Live model first, then the backup, then the live model once more.

    We stop waiting for each attempt after its time limit, so a slow model costs the caller
    seconds, not minutes. Raises the last error if none of them answers.
    """
    attempts = [(LIVE_MODEL, MODEL_TIMEOUT_S), (BACKUP_MODEL, MODEL_TIMEOUT_S + 2), (LIVE_MODEL, MODEL_TIMEOUT_S + 2)]
    last_error: Exception | None = None
    for i, (model, timeout_s) in enumerate(attempts[1:] if skip_first else attempts):
        budget.spend(f"turn:{model}")  # raises LimitReached: stop, don't try other models
        request = _requests.submit(_gemini().models.generate_content, model=model, contents=list(s.history),
                                   config=_turn_config())
        try:
            response = request.result(timeout=timeout_s)
            json.loads(response.text)  # unreadable answers count as failures
            if i or skip_first:
                log.info("answered by %s for %s", model, s.info.call_id)
            return response.text
        except WaitedTooLong:
            log.warning("%s took over %.0f s for %s", model, timeout_s, s.info.call_id)
            last_error = TimeoutError(f"{model} took over {timeout_s} s")
        except Exception as exc:  # rate limit, outage, bad JSON: try the next one
            log.warning("%s failed for %s: %s", model, s.info.call_id, str(exc)[:120])
            last_error = exc
        global last_model_error
        last_model_error = f"{model}: {str(last_error)[:300]}"
    raise last_error


def _paused_handoff(s: _Session) -> TurnResult:
    """An operator paused the AI from the dashboard (brain/control.py): hand the caller to a human."""
    log.warning("AI paused by an operator: handing %s to a human", s.info.call_id)
    return _hand_off(s, "operator_paused")


def _limit_handoff(s: _Session) -> TurnResult:
    """The Gemini request limit is used up (brain/budget.py): hand the caller to a human."""
    log.error("request limit reached: handing %s to an operator", s.info.call_id)
    if s.history and s.history[-1].role == "user":
        s.history.pop()
    return _hand_off(s, "budget_limit")


# Promises that help is coming. Nobody has been sent when the agent talks: only an operator
# dispatches. The model said "Biliyorum, yardım yolda" (I know, help is on the way) in a test call
# despite the prompt, so the code removes such a sentence. Compared without accents, lowercase.
_PROMISES = re.compile("|".join([
    r"βοηθεια (ερχεται|ειναι καθ οδον)", r"ερχονται (να|οι|τα)", r"(ερχεται|στελνουμε|στειλαμε|εστειλα) .{0,20}"
    r"(ασθενοφορο|πυροσβεστ|διασωστ|βοηθεια)", r"καθ οδον",
    r"yardim (yolda|geliyor|gonderildi)", r"(ekip|ekipler|ambulans|itfaiye)\w*( \w+){0,3} (yolda|geliyor|gelecek|gonderil)",
    r"(gonderiyoruz|gonderdik)",
    r"help (is|will be) (on (the|its) way|coming|there)", r"(on (their|its) way|we('ve| have)? sent|we are sending|"
    r"been dispatched|is being dispatched)", r"(ambulance|rescuers?|firefighters?|help)( \w+){0,3} (is|are|will be) (coming|on the way|on its way|there soon)",
    r"les secours (arrivent|sont en route|vont arriver)", r"(nous envoyons|nous avons envoye|en route)",
]))


def _speakable(s: _Session, text: str) -> str:
    """A reply sentence as the caller hears or reads it: no tags, no promise of help, and no Greek
    letters unless they speak Greek (translit.py: the map's street names are in Greek)."""
    return translit.for_caller(_no_promises(s, _LANG_TAG.sub("", _tidy_streets(s, text))), s.lang)


def _no_promises(s: _Session, text: str) -> str:
    """The reply without any sentence promising help; the first one becomes "your report is going
    to the operators right away", which is true."""
    sentences = re.split(r"(?<=[.!?;\u037e…])\s+", text)
    kept, replaced = [], False
    for sentence in sentences:
        if _PROMISES.search(" ".join(steps.plain_words(sentence))):
            log.warning("removed a promise of help from the reply for %s: %r", s.info.call_id, sentence[:80])
            if not replaced:
                kept.append(_phrase(s, "passed_on"))
                replaced = True
            continue
        kept.append(sentence)
    return " ".join(kept) if replaced else text


def _handoff_allowed(s: _Session, reason: str | None) -> bool:
    """The model may not hand off for "unsupported language" while the caller's language is one we
    support: a Turkish caller mixing in English was handed to a person this way (test call,
    2026-10-26). Which languages are supported is the code's decision, not the model's."""
    if reason == "unsupported_language" and s.lang in SUPPORTED_LANGS:
        log.warning("ignored an unsupported-language handoff for %s: %s is supported", s.info.call_id, s.lang)
        return False
    return True


def _hand_off(s: _Session, reason: str) -> TurnResult:
    """A person takes over; the report keeps why, so operators see it on the dashboard."""
    s.report["status"] = "handed_to_human"
    s.report["handoff_reason"] = reason
    return _result(s, _phrase(s, "handoff"), "handoff", reason)


def _give_up(s: _Session) -> TurnResult:
    s.history.pop()  # let the caller's repeat replace this turn
    return _result(s, _phrase(s, "error_fallback"))


def _prefix(s: _Session, action: str, topic: str | None) -> tuple[str, bool]:
    """What is said before the reply: (text, replaces the reply?). Same rules as _finish_turn."""
    if action == "handoff":
        return _phrase(s, "handoff"), True
    if action == "end" and _would_hold(s):
        return _phrase(s, "confirm_again"), True  # streamed calls: never speak the goodbye first
    if topic in ADVICE and topic not in s.advice_given and not s.hold_advice:
        return _advice(s, topic), False
    return "", False


def _made_up(s: _Session, raw: str, said: str | None = None) -> TurnResult:
    """The reply used a name or address placeholder we never made (an eval call heard "Με λένε .
    Είστε η;"). Drop the answer and ask the caller to repeat; the repeat replaces this turn."""
    log.warning("reply for %s used a made-up placeholder; asking the caller to repeat", s.info.call_id)
    topic = (_ADVICE_FIELD.search(raw) or [None, None])[1]
    if said and topic in ADVICE and topic not in s.advice_given:  # the advice was already spoken
        s.advice_given.add(topic)
        s.report["advice_given"].append(topic)
    s.history.pop()
    return _result(s, said or _phrase(s, "error_fallback"))


_ADVICE_FIELD = re.compile(r'"advice_topic"\s*:\s*"([a-z_.]+)"')


def _finish_turn(s: _Session, raw: str) -> TurnResult:
    """Apply the model's answer: report, grouping, advice, and the text the caller hears."""
    answer = json.loads(raw)
    if s.masker.invented(answer.get("reply") or ""):
        return _made_up(s, raw)
    updates = answer.get("report_updates") or {}
    for field in ("caller_name", "spoken_address", "street", "cross_street"):  # a made-up placeholder would blank a real value
        if isinstance(updates.get(field), str) and s.masker.invented(updates[field]):
            log.warning("ignoring a made-up %s placeholder for %s", field, s.info.call_id)
            del updates[field]
    # Keep only the answer's text in the history, so any model can read it on the next turn.
    s.history.append(types.Content(role="model", parts=[types.Part(text=raw)]))
    # The model saw and answered with placeholders; put the real details back.
    answer = s.masker.unmask_obj(answer)
    _translate_caller_line(s, answer.get("caller_en"))

    hazard_before = s.report["hazard_type"]
    s.report_problems = apply_update(s.report, answer.get("report_updates") or {})
    if s.report["hazard_type"] and (s.report["hazard_type"] != hazard_before or s.hazard_unclear):
        # A hazard heard from one word or a question stays unconfirmed until a clear answer or a yes.
        caller = s.transcript[-1]["text"] if s.transcript else ""
        s.hazard_unclear = _unclear(caller) and not (s.hazard_unclear and clear_yes(caller))
    location = s.report["location"]
    for heard, real in s.steps.replaced_streets.items():
        if _norm(location.get("street") or "") == _norm(heard):
            location["street"] = real  # the model wrote the heard street back: the caller said yes to the real one
    for key in ("spoken_address", "street"):
        if isinstance(location.get(key), str):
            location[key] = _tidy_streets(s, location[key])
    if isinstance(location.get("spoken_address"), str):
        # The model wrote the caller's "I don't know" into the address, and it was read back:
        # "Deneme Sokak 5, Bilmiyorum. Doğru mu?" (test set 2026-11-16).
        kept = [p.strip() for p in location["spoken_address"].split(",") if p.strip() and not (
            len(p.split()) <= 4 and steps.cannot_say(p))]
        location["spoken_address"] = ", ".join(kept) or None
    for key in ("street", "cross_street"):
        if isinstance(location.get(key), str) and len(location[key].split()) <= 4 and steps.cannot_say(location[key]):
            location[key] = None
    _street_from_address(s)
    _area_from_address(s)
    steps.after_answer(s.report, s.steps, s.transcript[-1]["text"] if s.transcript else "", s.hazard_unclear,
                       answer.get("expecting"))
    s.expecting = s.steps.expecting()
    _start_map_check(s)
    if s.report_problems:
        log.warning("report problems for %s: %s", s.info.call_id, s.report_problems)
    _group(s)

    action = answer.get("action", "continue")
    if action == "handoff" and not _handoff_allowed(s, answer.get("handoff_reason")):
        action = "continue"
    if action == "handoff":
        reason = answer.get("handoff_reason")
        return _hand_off(s, reason if reason and reason != "none" else "low_confidence")

    if action == "end" and _hold_the_end(s):
        return _result(s, _phrase(s, "confirm_again"))

    parts, parts_en = [], []
    topic = answer.get("advice_topic")
    if topic in ADVICE and topic not in s.advice_given and not s.hold_advice:
        s.advice_given.add(topic)
        s.report["advice_given"].append(topic)
        parts.append(_advice(s, topic))
        parts_en.append(_FIXED_EN.get(parts[-1], ADVICE[topic]["en"]))
    # Advice first, so the reply's question is the last thing the caller hears.
    parts.append(_speakable(s, answer.get("reply", "")).strip())
    parts_en.append(_LANG_TAG.sub("", answer.get("reply_en") or "").strip())

    text = " ".join(p for p in parts if p)
    text_en = " ".join(p for p in parts_en if p) if answer.get("reply_en") else None
    if action != "end":
        text, text_en = _add_form(s, text, text_en)
    return _result(s, text or _phrase(s, "error_fallback"), "end" if action == "end" else "continue",
                   text_en=text_en if text else None)


def _start_map_check(s: _Session) -> None:
    """Look the location up on the map in the background; the answer is used next turn."""
    location = s.report["location"]
    landmark = location.get("landmark")
    if landmark and s.masker.mask_known(landmark) != landmark:
        landmark = None  # it contains a name or number the caller gave: never send that to the map
    key = (location.get("area"), location.get("spoken_address"), landmark, location.get("street"))
    if location.get("street_matches") == [] and places.has_street_list(location.get("area")):
        key += ("with street list",)  # the street wasn't found before the list arrived: check again
    if not places.ENABLED or not any(key) or key == s.place_checked:
        return
    s.place_checked = key
    # Only the four places: the fifth part of the key marks a second look and is not for places.check, which
    # took it for its search function and failed (seen in a replay on 2026-11-15).
    s.place_check = _place_checks.submit(places.check, *key[:4])
    # Into the report as soon as it is back, not on the caller's next sentence: the dashboard map was a turn late.
    s.place_check.add_done_callback(lambda check, s=s, key=key: _store_map_result(s, check, key))


def _store_map_result(s: _Session, check, key: tuple) -> None:
    """Put a finished map check into the report and save it. Never breaks the call."""
    if key != s.place_checked or check.cancelled() or check.exception() is not None:
        return  # the location changed since, or the check failed (logged when the note is read)
    result, location = check.result(), s.report["location"]
    if places.the_street(key[3], key[1]) in s.steps.replaced_streets:
        return  # a late answer about the street as heard: the caller has said yes to the real one since
    location["on_map"] = result["on_map"]
    location["map_suggestion"] = result.get("suggestion")
    street = places.the_street(key[3], key[1])
    # Nothing like it on the map, and the area's street list has nothing that sounds close: spell it.
    s.steps.unfound_street = street if (result.get("street_matches") == [] and not result.get("street_suggestion")
                                        and places.has_street_list(key[0])) else None
    suggestion = result.get("street_suggestion")
    # The street as recorded already holds the real name ("Σάμο, Θεμιστοκλέους" for Θεμιστοκλέους): not
    # misheard, nothing to ask. In the test set (2026-11-15) the agent asked "do you mean Θεμιστοκλέους?"
    # three times of a caller who had said exactly that.
    if suggestion and street and set(_norm(suggestion).split()) <= set(_norm(street).replace(",", " ").split()):
        suggestion = None
    if suggestion and street and _norm(suggestion) != _norm(street):
        # For the operator, whatever the caller answers: the street as heard stays in the address.
        location["map_suggestion"] = _with_number(suggestion, location.get("spoken_address"), street)
        if street not in s.steps.refused_streets:
            # The code asks "did you mean …?" next (steps.py) and writes the answer into the report itself.
            s.steps.suggested_street, s.steps.suggestion_for = suggestion, street
    if result.get("street_matches") is not None:  # where the street is: one neighbourhood, or several to ask about
        location["street_matches"] = result["street_matches"]
        s.steps.matches_area = key[0]
        if len(result["street_matches"]) > 1 and location["confirmed_with_caller"]:
            # A test caller said yes to "Orlof, Athens" before the map found Orlof in two neighbourhoods.
            location["confirmed_with_caller"] = False
    try:
        _save(s)
    except Exception:
        log.exception("could not save the map check for %s", s.info.call_id)


_NUMBER_AFTER = r"\s+(\d{1,4}\s*[A-Za-zΑ-Ωα-ω]?)\b"


_HOUSE_NUMBER_WORD = re.compile(r"^\d{1,4}[A-Za-zΑ-Ωα-ω]?$")


def _street_in(street: str, spoken_address: str | None) -> tuple[int, str | None]:
    """Where the street stands in the spoken address (the index of its word, -1 when it is not
    there) and the house number right after it. Compared without accents, as the model may have
    written it differently. Only the number after the street: "2ος όροφος" is not a house number."""
    words = (spoken_address or "").split()
    wanted = _norm(street).split()
    for i in range(len(words) - len(wanted) + 1):
        if wanted and [_norm(w.strip(",.;")) for w in words[i:i + len(wanted)]] == wanted:
            after = words[i + len(wanted)].strip(",.;") if i + len(wanted) < len(words) else ""
            return i, after if _HOUSE_NUMBER_WORD.match(after) else None
    return -1, None


def _with_number(street: str, spoken_address: str | None, heard: str | None = None) -> str:
    """The street with the house number the caller gave for it, when the address has one."""
    _, number = _street_in(heard or street, spoken_address)
    return f"{street} {number}" if number else street


def _swap_street(spoken_address: str | None, old: str, new: str) -> str:
    """The spoken address with one street in place of another, everything else as it was. When
    the old one is not in it, the new street goes in front."""
    words = (spoken_address or "").split()
    at, _ = _street_in(old, spoken_address)
    if at < 0:
        return ", ".join(filter(None, (new, spoken_address)))
    last = words[at + len(old.split()) - 1]
    tail = last[len(last.rstrip(",.;")):]  # the comma after the street stays
    return " ".join([*words[:at], new + tail, *words[at + len(old.split()):]])


_STREET_YES = {"ναι", "μαλιστα", "σωστα", "ακριβως", "βεβαιως", "yes", "yeah", "yep", "correct", "exactly",
               "evet", "dogru", "aynen", "oui", "exact", "exactement"}
_STREET_NO = {"οχι", "no", "hayir", "non", "yanlis", "wrong", "faux"}
_UNSURE = {"δεν", "den", "don", "dont", "not", "degil", "bilmiyorum", "pas", "ισως", "maybe", "belki"}


def _asked_the_suggestion(s: _Session, real: str) -> bool:
    """Did the last reply ask "did you mean <the real street>?" The words of the reply decide, not
    the model's label for it: a question labelled "other" would leave a yes unheard."""
    last = next((t["text"] for t in reversed(s.transcript[:-1]) if t["role"] == "agent"), "")
    said = _norm(last)
    return bool(last) and ("?" in last or ";" in last) and (
        _norm(real) in said or _norm(translit.for_caller(real, s.lang)) in said)


def _answer_to_suggestion(s: _Session, caller_text: str) -> str | None:
    """The caller's answer to "did you mean <the real street>?", applied by code. Yes: the real
    street replaces the one heard in the report, with its house number, and the model is told which
    placeholder to use from now on. No: the caller's street stays and is not questioned again.
    "I don't know" or an answer about something else: the caller's street stays, not asked again.
    The street said again, a question or one unclear word: asked once more, then dropped (steps.py).

    A yes that rewrites the report has to be a plain one: a short answer with a yes word and no
    "no", "but" or "don't know", once the street and number are set aside ("Ναι, <street> 16"). The
    caller saying the real street itself is a yes too. "Εντάξει", "Το σωστό είναι <their street>"
    and "Ναι;" are not (found by review: each of them replaced the caller's street)."""
    heard, real = s.steps.suggestion_for, s.steps.suggested_street
    if not heard or not real or not (s.steps.asked == "confirm_street" or _asked_the_suggestion(s, real)):
        return None
    location = s.report["location"]
    plain = " ".join(_plain_words(caller_text))
    names = {w for name in (heard, real) for w in _plain_words(name)}
    rest = [w for w in plain.split() if w not in names and not w.isdigit()]
    said_real = all(w in plain.split() for w in _plain_words(real))
    question = caller_text.strip().endswith(("?", ";"))
    negative = bool(set(rest) & (_STREET_NO | _NOT_YES | _UNSURE))
    yes = not question and not negative and (
        (said_real and len(rest) <= 3) or (0 < len(rest) <= 2 and bool(set(rest) & _STREET_YES)))
    if yes:
        number = _street_in(heard, location.get("spoken_address"))[1]
        location["spoken_address"] = _swap_street(location.get("spoken_address"), heard, real)
        location["street"] = real
        location["confirmed_with_caller"] = False
        location["map_suggestion"] = None
        location["street_as_heard"] = heard  # for the operator: what speech-to-text wrote
        location["street_matches"] = None  # they were for the street as heard
        s.steps.replaced_streets[heard] = real
        s.steps.suggested_street = s.steps.suggestion_for = None
        s.steps.map_pending = places.ENABLED  # the real street is looked up after this turn: no neighbourhood question yet
        full = f"{real} {number}" if number else real
        name = s.masker.hide("ADDRESS", full) if MASKING else full
        return (f"(the caller said yes: the street is {name}. The code has set street and spoken_address to it; do not "
                f"change them. From now on say {name} for the address and never the street as it was first heard)")
    if set(rest) & _STREET_NO and not said_real:
        s.steps.refused_streets.add(heard)
        s.steps.suggested_street = s.steps.suggestion_for = None
        return ("(the caller said no to the street the map suggested: keep the street exactly as the caller said it, "
                "do not suggest that street again and never say the two names together)")
    said_heard = all(w in plain.split() for w in _plain_words(heard))
    if steps.cannot_say(caller_text) or not (said_real or said_heard or question or len(rest) <= 1):
        # "I don't know", or something else altogether: in the test set (2026-11-16) the agent asked "Did
        # you mean …?" three times while the caller reported a person under a fallen tree, and twice by
        # text to "Bilmiyorum". The caller's street stays and the question is not asked again.
        s.steps.refused_streets.add(heard)
        s.steps.suggested_street = s.steps.suggestion_for = None
        return ("(the caller did not answer the question about the street: keep the street exactly as the caller "
                "said it and do not ask about it again. Record what this message says and go on)")
    return None  # the street said again, a question or one unclear word: asked once more, then dropped (steps.py)


def _take_back_the_suggestion(s: _Session, caller_text: str) -> str | None:
    """The caller said yes to the map's street and now says no with their own street again ("Όχι,
    <the street as heard> 16", at the read-back): their street goes back into the report and the
    map's is not offered again. Without a "no" the heard name alone changes nothing: speech-to-text
    writes the real street that way every time."""
    words = _plain_words(caller_text)
    for heard, real in list(s.steps.replaced_streets.items()):
        if set(words) & _STREET_NO and all(w in words for w in _plain_words(heard)) and not all(w in words for w in _plain_words(real)):
            location = s.report["location"]
            location["spoken_address"] = _swap_street(location.get("spoken_address"), real, heard)
            location["street"] = heard
            location["confirmed_with_caller"] = False
            location["map_suggestion"] = _with_number(real, location["spoken_address"], heard)
            location.pop("street_as_heard", None)
            location["street_matches"] = None
            del s.steps.replaced_streets[heard]
            s.steps.refused_streets.add(heard)
            return ("(the caller took back their yes: the street is the one they first said. The code has put it back "
                    "into street and spoken_address; do not change them and do not suggest the other street again)")
    return None


def _tidy_streets(s: _Session, text: str) -> str:
    """A street is never said twice in a row or next to the one it was mistaken for. A live call
    (2026-11-15) heard "Φραγκιάδων Φραγγυλλιδών 16" and then "Φραγγυλλιδών Φραγγυλλιδών 16" read
    back: the model had put a street name in front of a placeholder that already held it."""
    if not text:
        return text
    for heard, real in s.steps.replaced_streets.items():  # the caller said yes: the heard name is gone
        text = re.sub(rf"(?<!\w){re.escape(heard)}(?!\w)", real, text, flags=re.IGNORECASE)
    names = set(s.masker.street_names()) | set(s.steps.replaced_streets.values())
    if street := places.the_street(s.report["location"].get("street")):
        names.add(street)
    for name in sorted(names, key=len, reverse=True):
        text = re.sub(rf"(?<!\w)({re.escape(name)})(?:[\s,]+{re.escape(name)})+(?!\w)", r"\1", text, flags=re.IGNORECASE)
    # The suggestion and the heard street side by side, before the caller answered: only the heard one.
    for real, heard in ((s.steps.suggested_street, s.steps.suggestion_for),):
        if real and heard:
            text = re.sub(rf"(?<!\w){re.escape(real)}[\s,]+(?={re.escape(heard)}(?!\w))", "", text, flags=re.IGNORECASE)
    return text


def _map_check_result(s: _Session) -> str | None:
    """The finished map check's note for the model, once; never waits, never breaks the call."""
    check, s.place_check = s.place_check, None
    if check is None or not check.done():
        s.place_check = check  # still running: try again next turn
        return None
    try:
        result = check.result()
    except Exception:
        log.exception("map check failed for %s", s.info.call_id)
        return None
    note = result["note"]  # the report already has it (_store_map_result)
    if note and (real := result.get("street_suggestion")):
        street = places.the_street(s.place_checked[3], s.place_checked[1]) if s.place_checked else None
        same = street and set(_norm(real).split()) <= set(_norm(street).replace(",", " ").split())  # "Σάμο, Θεμιστοκλέους" holds it
        if street and (street in s.steps.refused_streets or street in s.steps.replaced_streets or same):
            # The caller has refused or accepted it already, or it is the same name: nothing to ask.
            return "the street the caller gave was not found on the map. Keep it as the caller said it; do not ask about it again."
        note = note.replace(real, s.masker.hide("ADDRESS", real))  # a street name never reaches the model
    return note


def _unclear(text: str) -> bool:
    """One word, or heard as a question: speech-to-text heard «Φωτιά;» (fire?) in a test call where
    nobody mentioned a fire, and the agent gave wildfire advice at once."""
    stripped = text.strip()
    return len(_plain_words(stripped)) <= 1 or stripped.endswith(("?", ";", "\u037e"))


# A clear yes to the read-back: short, a yes word, no "no" or "but". A test call ended right after
# the caller corrected their name ("Αιγέας Πολιτόπουλος."), so the correction was never confirmed.
_YES = {"ναι", "σωστα", "σωστο", "ενταξει", "νταξει", "ακριβως", "μαλιστα", "βεβαιως", "ολα",
        "yes", "yeah", "yep", "correct", "right", "exactly", "ok", "okay",
        "evet", "dogru", "tamam", "aynen", "oui", "exact", "exactement", "voila"}
_NOT_YES = {"οχι", "αλλα", "ομως", "no", "not", "but", "wrong", "hayir", "ama", "yanlis", "non", "mais", "faux"}


_GOODBYES = {"αντιο", "bye", "goodbye", "adieu", "revoir", "hosca", "gule"}
_WITH_A_GOODBYE = {"σας", "ευχαριστω", "ενταξει", "καλα", "λοιπον", "γεια", "ok", "okay", "thanks", "thank", "you",
                   "merci", "au", "tesekkurler", "tesekkur", "ederim", "tamam", "kal", "kalin"}


def _goodbye(text: str) -> bool:
    """The caller's whole message is a goodbye: a goodbye word, and nothing but thanks and the like
    around it. "Αντίο, δεν αναπνέει" and "Bye, three people trapped" are not: they say something."""
    words = _plain_words(text)
    return 0 < len(words) <= 4 and bool(set(words) & _GOODBYES) and set(words) <= _GOODBYES | _WITH_A_GOODBYE


def _plain_words(text: str) -> list[str]:
    plain = "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))
    return re.findall(r"\w+", plain.replace("ı", "i").replace("ğ", "g").replace("ş", "s"))


def clear_yes(text: str) -> bool:
    words = _plain_words(text)
    return 0 < len(words) <= 8 and bool(set(words) & _YES) and not set(words) & _NOT_YES


def _would_hold(s: _Session) -> bool:
    """Don't end unless the caller's last words were a clear yes (twice at most, never a loop).
    Information-only calls (a cat, a call to 112 by mistake) may end without a read-back."""
    caller = next((t["text"] for t in reversed(s.transcript) if t["role"] == "caller"), "")
    return not (s.report["urgency"]["suggested"] == "information" or s.end_holds >= 2 or clear_yes(caller))


def _hold_the_end(s: _Session) -> bool:
    if not _would_hold(s):
        return False
    s.end_holds += 1
    log.info("call %s: end held, the caller's last words were not a clear yes", s.info.call_id)
    return True


def _translate_caller_line(s: _Session, caller_en: str | None) -> None:
    """The model's English copy of what the caller just said, for the operators' dashboard."""
    line = next((t for t in reversed(s.transcript) if t["role"] == "caller"), None)
    if line and caller_en and not line.get("text_en"):
        line["text_en"] = _LANG_TAG.sub("", caller_en).strip()


def _group(s: _Session) -> None:
    """Suggest which event this call belongs to. Never let it break the call."""
    try:
        suggest_event(s.report)
    except Exception:
        log.exception("event grouping failed for %s", s.info.call_id)


def end_call(call_id: str, reason: EndReason) -> dict:
    s = _sessions.pop(call_id)
    _group(s)
    if s.report["status"] == "in_progress":
        s.report["status"] = {"completed": "complete", "handed_off": "handed_to_human"}.get(reason, "dropped")
    try:
        if control.is_paused():
            raise RuntimeError("AI paused by an operator: no summary from the model")
        s.report["summary_for_operator"], s.report["summary_en"] = _operator_summary(s)
    except Exception:
        log.exception("summary failed for %s", call_id)
        s.report["summary_for_operator"] = s.report["summary_en"] = s.report["situation"]  # English fallback
    _save(s)
    return s.report


_LANG_NAMES = {"el": "Greek", "tr": "Turkish", "en": "English", "fr": "French"}


def _operator_lang(s: _Session) -> str:
    if OPERATOR_LANG != "auto":
        return _LANG_NAMES.get(OPERATOR_LANG, OPERATOR_LANG)
    # The caller's language when it is Greek or Turkish, so the dashboard's "original" view is the
    # language they spoke; a browser test call has a Greek test number but a Turkish caller.
    if s.lang in ("el", "tr"):
        return _LANG_NAMES[s.lang]
    return "Turkish" if s.info.phone.replace(" ", "").startswith("+90") else "Greek"


def _operator_summary(s: _Session) -> tuple[str, str]:
    """One or two sentence summary in the operators' language and in English, in one request."""
    report = {k: v for k, v in s.report.items() if k not in ("caller", "trigger")}  # no phone number
    lines = "\n".join(f"{t['role']}: {t['text']}" for t in s.transcript)
    report_json = json.dumps(report, ensure_ascii=False)
    if MASKING:
        if s.report["caller"]["name"]:
            s.masker.mask(s.report["caller"]["name"], expecting="name")  # make sure the name is known
        lines, report_json = s.masker.mask_known(lines), s.masker.mask_known(report_json)
    prompt = (
        f"Write a one or two sentence summary of this emergency call for a 112 operator. "
        f"Lead with location, then what happened, then people and injuries. Only facts from the "
        f"call. Keep placeholders like <PERSON_1> exactly as written. Answer with JSON: "
        f'"summary" in {_operator_lang(s)}, and "summary_en", the same summary in English.'
        f"\n\nREPORT:\n{report_json}"
        f"\n\nTRANSCRIPT:\n{lines}"
    )
    config = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_level=THINKING_LEVEL),
        http_options=types.HttpOptions(timeout=SUMMARY_TIMEOUT_MS),
        response_mime_type="application/json",
        response_json_schema=_SUMMARY_SCHEMA,
    )
    budget.spend("summary")  # over the limit: end_call falls back to the English situation
    response = _gemini().models.generate_content(model=REPORT_MODEL, contents=prompt, config=config)
    answer = json.loads(response.text)
    summary = s.masker.unmask(answer["summary"].strip())
    return summary, s.masker.unmask((answer.get("summary_en") or "").strip()) or summary


_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {"summary": {"type": "string"}, "summary_en": {"type": "string"}},
    "required": ["summary", "summary_en"],
}
