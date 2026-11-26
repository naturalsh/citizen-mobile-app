"""Play a caller in the terminal.

    python -m brain.cli --lang el
    python -m brain.cli --lang tr --phone "+90 532 000 0000"

Type /lang xx to switch the caller's language, /report to print the report, /quit to hang up.
"""
import argparse
import json
import uuid

from dotenv import load_dotenv

load_dotenv()

from brain import CallInfo, end_call, start_call, turn  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang", default="el", choices=["el", "tr", "en", "fr"])
    parser.add_argument("--phone", default="+30 690 000 0000")
    args = parser.parse_args()

    call_id = f"call-{uuid.uuid4().hex[:6]}"
    lang = args.lang
    result = start_call(CallInfo(call_id=call_id, channel="voice", phone=args.phone, lang_guess=lang))
    print(f"\nAGENT: {result.reply_text}\n")

    reason = "completed"
    while True:
        try:
            text = input("YOU: ").strip()
        except (EOFError, KeyboardInterrupt):
            reason = "hung_up"
            break
        if not text:
            continue
        if text == "/quit":
            reason = "hung_up"
            break
        if text.startswith("/lang "):
            lang = text.split()[1]
            print(f"(caller language is now {lang})")
            continue
        if text == "/report":
            print(json.dumps(result.report, ensure_ascii=False, indent=2))
            continue

        result = turn(call_id, text, lang)
        urgency = result.report["urgency"]
        print(f"\nAGENT: {result.reply_text}")
        print(f"       [action={result.action} urgency={urgency['suggested']} reasons={urgency['reasons']}]\n")
        if result.action == "handoff":
            reason = "handed_off"
            break
        if result.action == "end":
            break

    report = end_call(call_id, reason)
    print("\nFINAL REPORT:")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
