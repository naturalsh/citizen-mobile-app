"""Start the operator dashboard.

    .venv/bin/python -m dashboard            # live calls from output/reports
    .venv/bin/python -m dashboard --demo     # replay the eval test calls (output/eval/brain)
    .venv/bin/python -m dashboard --demo --reset   # ...and forget earlier claims and decisions
    .venv/bin/python -m dashboard --share    # the same, for a friend on the same Wi-Fi (link with a key)
"""
import argparse
import os
import secrets
import socket
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # before importing the brain, so .env settings apply

import uvicorn  # noqa: E402

from .app import create_app  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--demo", action="store_true", help="show the eval test calls instead of live calls")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--reset", action="store_true",
                        help="forget all claims and operator decisions first (e.g. before a demo)")
    parser.add_argument("--share", action="store_true",
                        help="the full dashboard for someone on the same Wi-Fi, behind a key in the link")
    args = parser.parse_args()
    if args.share:
        return share(args)

    output_dir = Path("output") / "eval" / "brain" if args.demo else Path("output")
    if args.reset:
        (output_dir / "operator.sqlite").unlink(missing_ok=True)
        print("Claims and operator decisions cleared.")
    print(f"Operator dashboard: http://127.0.0.1:{args.port}  ({'demo: eval test calls' if args.demo else 'live calls'})")
    # 127.0.0.1 only: the dashboard has no login and shows callers' personal details.
    uvicorn.run(create_app(output_dir, demo=args.demo), host="127.0.0.1", port=args.port, log_level="warning")


def _lan_address() -> str:
    """This computer's address on the local network (no packet is sent)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def _kept_key(output_dir: Path) -> str:
    """The same key after a restart: a new key on every start locked out a page opened with the old
    link, and its transcripts wouldn't load (2026-10-26). Kept in output/, which is never committed."""
    path = Path("output") / "dashboard_share_key"
    try:
        if key := path.read_text().strip():
            return key
    except OSError:
        pass
    key = secrets.token_urlsafe(12)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(key)
    return key


def share(args) -> None:
    """The full dashboard on the local network, behind a key that is part of the link.

    For testing with a friend on the same Wi-Fi. It shows callers' details and every button
    works (Pause AI too), so the key is never optional, and it runs only while this does."""
    output_dir = Path("output") / "eval" / "brain" if args.demo else Path("output")
    port = args.port if args.port != 8001 else 8003  # beside the operator's own dashboard on 8002
    key = os.getenv("DASHBOARD_ACCESS_KEY") or _kept_key(output_dir)
    print("Dashboard for someone on the same Wi-Fi. Send them this link:")
    print(f"    http://{_lan_address()}:{port}/?key={key}")
    print("Anyone with the link can see callers' details and use every button until you stop this (Ctrl+C).",
          flush=True)  # shown at once even when the output is a log, not a terminal
    uvicorn.run(create_app(output_dir, demo=args.demo, access_key=key), host="0.0.0.0", port=port,
                log_level="warning")


if __name__ == "__main__":
    main()
