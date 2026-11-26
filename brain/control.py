"""Operator control of the AI: the "Pause AI" and "Surge mode" switches on the dashboard.

The EU AI Act (Article 14(4)(e), Docs/Research/05) asks that the people overseeing a
high-risk system can stop it. While paused, the brain does not call Gemini: every new call,
message and turn is handed to a human operator with handoff_reason "operator_paused".

Surge mode decides how readily the AI hands a caller to a person. In a surge every operator
is needed for life-threats, so a cat in a tree is recorded and the call ends instead of
waiting for a person; outside a surge anything that isn't a disaster call goes to a person.
The default is BRAIN_HANDOFF_MODE (surge: the service only runs when 112 is overloaded).

Each switch is a small file in output/ (BRAIN_CONTROL_DIR), so the dashboard, the voice
worker and the messaging server, which run as separate processes, all see the same state.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def _file() -> Path:
    return Path(os.getenv("BRAIN_CONTROL_DIR", "output")) / "AI_PAUSED.json"


def pause_info() -> dict | None:
    """{"by": operator, "at": time} while paused, else None."""
    try:
        return json.loads(_file().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return {"by": "unknown", "at": None}  # a damaged file still means paused: fail safe


def is_paused() -> bool:
    return pause_info() is not None


def set_paused(paused: bool, by: str) -> None:
    path = _file()
    if not paused:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    path.write_text(json.dumps({"by": by, "at": at}), encoding="utf-8")


HANDOFF_MODES = ("surge", "normal")
DEFAULT_HANDOFF_MODE = os.getenv("BRAIN_HANDOFF_MODE", "surge")


def _mode_file() -> Path:
    return Path(os.getenv("BRAIN_CONTROL_DIR", "output")) / "HANDOFF_MODE.json"


def handoff_info() -> dict:
    """{"mode": "surge" | "normal", "by": operator or None, "at": time or None}."""
    try:
        info = json.loads(_mode_file().read_text(encoding="utf-8"))
        if info.get("mode") in HANDOFF_MODES:
            return info
    except FileNotFoundError:
        return {"mode": DEFAULT_HANDOFF_MODE if DEFAULT_HANDOFF_MODE in HANDOFF_MODES else "surge", "by": None, "at": None}
    except (OSError, ValueError):
        pass
    return {"mode": "normal", "by": "unknown", "at": None}  # damaged file: hand off more readily, the safe side


def handoff_mode() -> str:
    return handoff_info()["mode"]


def set_handoff_mode(mode: str, by: str) -> dict:
    if mode not in HANDOFF_MODES:
        raise ValueError(f"mode must be one of {HANDOFF_MODES}")
    path = _mode_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    info = {"mode": mode, "by": by, "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    path.write_text(json.dumps(info), encoding="utf-8")
    return info
