"""Read the spoken reply out of the model's JSON answer while it is still being written.

The model answers each turn with one JSON object whose fields come in a fixed order:
action, handoff_reason, advice_topic, reply, ... (tools.TURN_SCHEMA). So the action and the
advice topic are known before the reply starts, and the reply can be passed to the voice
as it arrives instead of after the whole answer (Docs/Research/04, latency budget).

ReplyStream only reads; core.py still parses the complete answer, updates the report and
decides the final text. Both use the same rules, so what was spoken matches the transcript.
"""
import json
import re
from typing import Callable, Iterator

_ACTION = re.compile(r'"action"\s*:\s*"([a-z_]+)"')
_HANDOFF_REASON = re.compile(r'"handoff_reason"\s*:\s*"([a-z_]+)"')
_ADVICE = re.compile(r'"advice_topic"\s*:\s*"([a-z_.]+)"')
_REPLY_START = re.compile(r'"reply"\s*:\s*"')
_ESCAPES = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}
_OPENERS = {"<": ">", "(": ")", "[": "]"}


def decode_partial_string(raw: str) -> tuple[str, bool]:
    """Decode a JSON string body that may be cut off. Returns (text so far, string closed?)."""
    out, i = [], 0
    while i < len(raw):
        ch = raw[i]
        if ch == '"':
            return "".join(out), True
        if ch != "\\":
            out.append(ch)
            i += 1
            continue
        if i + 1 >= len(raw):
            break  # escape cut off: wait for more
        nxt = raw[i + 1]
        if nxt == "u":
            if i + 6 > len(raw):
                break
            out.append(chr(int(raw[i + 2:i + 6], 16)))
            i += 6
        else:
            out.append(_ESCAPES.get(nxt, nxt))
            i += 2
    return "".join(out), False


_SENTENCE_END = re.compile(r"[.!?;\u037e…][\"»”)]?(?=\s)")


def _sentence_end(text: str) -> int:
    """Index after the last finished sentence (0 if none): the brain checks whole sentences before
    they are spoken (core._no_promises), so a reply is released a sentence at a time."""
    ends = [m.end() for m in _SENTENCE_END.finditer(text)]
    return ends[-1] if ends else 0


def _safe_end(text: str) -> int:
    """Index up to which text can be spoken: stop before a placeholder or tag that hasn't closed yet."""
    end = len(text)
    for opener, closer in _OPENERS.items():
        start = text.rfind(opener)
        if start != -1 and closer not in text[start:]:
            end = min(end, start)
    return end


class ReplyStream:
    """Feed it the growing raw JSON; it yields ("start", {...}) once, then ("text", piece) events.

    clean(text) turns released reply text into speakable text (unmask placeholders, drop tags).
    prefix(action, topic) returns what is said before the reply: the handoff line, or the advice.
    """

    def __init__(self, clean: Callable[[str], str], prefix: Callable[[str, str | None], tuple[str, bool]],
                 allow_handoff: Callable[[str | None], bool] = lambda reason: True,
                 broken: Callable[[str], bool] = lambda text: False, fallback: str = ""):
        self._clean = clean
        self._prefix = prefix
        self._allow_handoff = allow_handoff
        # broken(masked text): the reply uses a placeholder we never made. Stop there and say
        # fallback ("please repeat") instead of a sentence with a hole in it.
        self._broken = broken
        self._fallback = fallback
        self.broke = False
        self.said: list[str] = []  # everything sent, to log what the caller really heard
        self.action: str | None = None
        self.handoff_reason: str | None = None
        self.started = False  # "start" event sent
        self.spoke = False  # any text sent
        self._reply_only_prefix = False  # handoff: the fixed line replaces the reply
        self._released = 0  # characters of the decoded reply already sent

    def feed(self, raw: str) -> Iterator[tuple[str, object]]:
        if self.action is None:
            m = _ACTION.search(raw)
            if not m:
                return
            self.action = m.group(1)
        if self.action == "handoff" and self.handoff_reason is None:
            m = _HANDOFF_REASON.search(raw)
            if not m:
                return  # wait for the reason: the voice side needs it to transfer the call
            self.handoff_reason = m.group(1)
            if not self._allow_handoff(self.handoff_reason):
                self.action, self.handoff_reason = "continue", None  # the brain overrules it (core.py)
        if not self.started:
            topic_match = _ADVICE.search(raw)
            if self.action != "handoff" and not topic_match:
                return  # wait for the advice topic: it is spoken before the reply
            self.started = True
            yield "start", {"action": self.action, "handoff_reason": self.handoff_reason}
            text, self._reply_only_prefix = self._prefix(self.action, topic_match.group(1) if topic_match else None)
            if text:
                self.spoke = True
                self.said.append(text if self._reply_only_prefix else text + " ")
                yield "text", self.said[-1]  # space before the reply
        if self._reply_only_prefix or self.broke:
            return
        start = _REPLY_START.search(raw)
        if not start:
            return
        decoded, closed = decode_partial_string(raw[start.end():])
        end = len(decoded) if closed else min(_safe_end(decoded), _sentence_end(decoded))
        if end > self._released:
            masked = decoded[self._released:end]
            self._released = end
            if self._broken(masked):
                self.broke = True
                self.spoke = True
                self.said.append(" " + self._fallback)
                yield "text", self.said[-1]
                return
            piece = self._clean(masked)
            if piece.strip():
                self.spoke = True
                self.said.append(piece)
                yield "text", piece


def salvage(raw: str, reader: ReplyStream) -> str:
    """A valid answer from a cut-off stream: what was decided and said so far, no report changes."""
    start = _REPLY_START.search(raw)
    advice = _ADVICE.search(raw)
    return json.dumps({
        "action": reader.action or "continue",
        "handoff_reason": reader.handoff_reason or "none",
        "advice_topic": advice.group(1) if advice else "none",
        "reply": decode_partial_string(raw[start.end():])[0] if start else "",
        "expecting": "other",
        "report_updates": {},
    })
