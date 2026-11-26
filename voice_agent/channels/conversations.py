"""Open text conversations, shared by the incoming webhooks and the failed-call trigger."""
import threading
import time
from collections import defaultdict
from dataclasses import dataclass

IDLE_TIMEOUT_S = 30 * 60  # a new message after this long starts a new report


@dataclass
class Conversation:
    call_id: str
    lang: str
    last_seen: float

    def idle(self) -> bool:
        return time.time() - self.last_seen > IDLE_TIMEOUT_S


conversations: dict[tuple[str, str], Conversation] = {}  # keyed by (channel, sender number)
locks: defaultdict[tuple[str, str], threading.Lock] = defaultdict(threading.Lock)


def has_open(phone: str) -> bool:
    """True if this number has a live conversation on any channel."""
    return any(p == phone and not c.idle() for (_, p), c in list(conversations.items()))
