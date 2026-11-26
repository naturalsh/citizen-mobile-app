"""Run the scripted test calls in eval/cases/ against the real brain and score them.

    .venv/bin/python -m eval.run                      # every case
    .venv/bin/python -m eval.run --lang el,tr         # only these languages
    .venv/bin/python -m eval.run --case el-flood-car  # one case (or several, comma-separated)
    .venv/bin/python -m eval.run --sleep 2            # pause between turns (free-tier rate limits)

Each case is a scripted caller: its lines are sent in order until the agent ends or hands
off the call. Results are printed and saved to output/eval/<time>.json.

The headline number is life-threat recall: of the calls that really are life-threatening,
how many the agent suggested as life_threat. Missing one is the worst failure.
"""
import argparse
import json
import os
import re
import statistics
import time
import uuid
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(".env")
# Keep eval reports and events away from the real ones.
os.environ.setdefault("BRAIN_OUTPUT_DIR", str(Path("output") / "eval" / "brain"))

import brain.core as core  # noqa: E402
from brain import budget, control  # noqa: E402
from brain import CallInfo, end_call, start_call, turn  # noqa: E402
from brain.events import _norm  # noqa: E402
from brain.tools import ADVICE, PHRASES  # noqa: E402

CASES_DIR = Path(__file__).parent / "cases"
RESULTS_DIR = Path("output") / "eval"
ERROR_REPLIES = {text for text in PHRASES["error_fallback"].values() if isinstance(text, str)}
MAX_RETRIES = 3

# Everything sent to the model, to check that masking kept personal details out.
_sent_to_model: list[str] = []


def _spy_on_model() -> None:
    client = core._gemini()
    original = client.models.generate_content

    def spy(**kw):
        contents = kw["contents"]
        items = [contents] if isinstance(contents, str) else [p.text for c in contents for p in c.parts or [] if p.text]
        _sent_to_model.extend(items)
        return original(**kw)

    client.models.generate_content = spy


def load_cases(langs: set[str] | None, case_id: str | None) -> list[dict]:
    cases = []
    for path in sorted(CASES_DIR.glob("*.json")):
        cases += json.loads(path.read_text(encoding="utf-8"))
    if case_id:
        wanted = set(case_id.split(","))
        cases = [c for c in cases if c["id"] in wanted]
    if langs:
        cases = [c for c in cases if c["lang"] in langs]
    return cases


MAX_TURNS = 14  # an answering caller (case "answers") stops here if the call never ends
YES = {"el": "Ναι, σωστά.", "tr": "Evet, doğru.", "en": "Yes, that's right.", "fr": "Oui, c'est ça."}
DONT_KNOW = {"el": "Δεν ξέρω.", "tr": "Bilmiyorum.", "en": "I don't know.", "fr": "Je ne sais pas."}


def next_line(case: dict, script: list[str], asked: str | None, used: set[str]) -> str | None:
    """What the caller says next. Fixed scripts said their lines in order whatever the agent
    asked, so a correct but different question made a case drift and fail. A case with "answers"
    ({step: line}, steps as in brain/steps.py) answers the step the brain says it asked; its
    "turns" are said when no answer fits (the opening, and scripted moments like a correction).
    By text, "form" answers the first list of what is missing and "form_again" the reminder."""
    answers = case.get("answers")
    if answers is not None and asked in answers and asked not in used:
        used.add(asked)
        return answers[asked]
    if answers is not None and asked in ("location_readback", "final_readback"):
        return answers.get("yes", YES[case["lang"]])  # before scripted lines, meant for other moments
    if script:
        return script.pop(0)
    if answers is None:
        return None  # a fixed script that ran out: the caller hangs up
    if asked is None:
        return answers.get("yes", YES[case["lang"]])
    return answers.get(asked, DONT_KNOW[case["lang"]])


def run_case(case: dict, sleep: float) -> dict:
    _sent_to_model.clear()
    # Each case fixes its handoff mode, so the dashboard's live surge switch can't change results.
    mode = case.get("handoff_mode", "surge")
    control.handoff_mode = lambda: mode
    call_id = f"eval-{case['id']}-{uuid.uuid4().hex[:4]}"
    info = CallInfo(
        call_id=call_id, channel=case.get("channel", "voice"), phone=case["phone"],
        lang_guess=case["lang"], trigger=case.get("trigger"),
    )
    start_call(info)
    transcript, latencies, errors, gave_up = [], [], 0, False
    result = None
    script, used = list(case["turns"]), set()
    line = script.pop(0)
    while line is not None and len(transcript) < MAX_TURNS:
        for attempt in range(MAX_RETRIES):
            t0 = time.perf_counter()
            result = turn(call_id, line, case["lang"])
            latencies.append((time.perf_counter() - t0) * 1000)
            if result.reply_text not in ERROR_REPLIES:
                break
            errors += 1
            time.sleep(5 * (attempt + 1))  # usually a rate limit; the brain dropped the turn, so resend it
        session = core._sessions.get(call_id)
        if session and session.place_check:  # a real caller takes seconds to answer: let the map check finish
            try:
                session.place_check.result(timeout=6)
            except Exception:
                pass
        transcript.append({"caller": line, "agent": result.reply_text, "action": result.action,
                           "expecting": session.expecting if session else None})
        if result.reply_text in ERROR_REPLIES:
            gave_up = True  # model still unavailable after retries: most likely the daily quota
            break
        if result.action in ("end", "handoff"):
            break
        asked = session.steps.asked if session else None
        if session and session.steps.form_asked:  # a texted list: the caller answers all of it at once
            asked = "form" if session.steps.forms == 1 else "form_again"
        line = next_line(case, script, asked, used)
        time.sleep(sleep)

    action = result.action if result else "continue"
    reason = {"end": "completed", "handoff": "handed_off"}.get(action, "hung_up")
    report = end_call(call_id, reason)
    return {
        "case": case, "action": action, "handoff_reason": result.handoff_reason if result else None,
        "report": report, "transcript": transcript, "latencies_ms": latencies, "errors": errors, "gave_up": gave_up,
        "sent_to_model": list(_sent_to_model),
    }


def _contains_all(value: str | None, parts: list[str]) -> bool:
    return bool(value) and all(_norm(p) in _norm(value) for p in parts)


def score(run: dict) -> dict:
    """One check per expectation in the case. True = pass, False = fail."""
    e, r = run["case"]["expect"], run["report"]
    urgency = r["urgency"]["suggested"]
    given = r.get("advice_given", [])
    checks = {}

    if e.get("action", "any") != "any":
        checks["action"] = run["action"] == e["action"]
    if "handoff_reason" in e:
        checks["handoff_reason"] = run["handoff_reason"] in e["handoff_reason"]
    if "urgency" in e:
        checks["urgency"] = urgency in e["urgency"]
    if "hazard_type" in e:
        checks["hazard"] = r["hazard_type"] == e["hazard_type"]
    if "hazard_subtype" in e:
        checks["hazard_subtype"] = r.get("hazard_subtype") == e["hazard_subtype"]
    if "animals_min" in e:  # animals at risk are recorded, never dropped or counted as people
        checks["animals"] = sum(a.get("count") or 1 for a in r.get("animals") or []) >= e["animals_min"]
    if "max_messages" in e:  # by text: a list per reply, not a question per message
        checks["messages"] = len(run["transcript"]) <= e["max_messages"]
    if "address_contains" in e:
        checks["address"] = _contains_all(r["location"]["spoken_address"], e["address_contains"])
    if "area_contains" in e:
        where = f"{r['location'].get('area') or ''} {r['location']['spoken_address'] or ''}"
        checks["area"] = _contains_all(where, e["area_contains"])
    if "caller_name" in e:
        checks["name"] = _contains_all(r["caller"]["name"], [e["caller_name"]])
    if "name_excludes" in e:  # e.g. hesitation sounds that must not end up in the name
        checks["name_clean"] = not any(_norm(x) in _norm(r["caller"]["name"] or "").split() for x in e["name_excludes"])
    asks = [t.get("expecting") for t in run["transcript"]]
    if "first_reply_expects" in e:  # e.g. only a neighbourhood given: ask for the street first
        checks["first_question"] = bool(asks) and asks[0] == e["first_reply_expects"]
    if "location_asks_max" in e:
        checks["location_asks"] = asks.count("location") <= e["location_asks_max"]
    if "location_asks_min" in e:  # a vague place must be probed, not accepted
        checks["location_probed"] = asks.count("location") >= e["location_asks_min"]
    groups = r.get("people") or []
    for turn_no, words in e.get("reply_contains", {}).items():  # e.g. the agent suggests the real place
        reply = run["transcript"][int(turn_no) - 1]["agent"] if len(run["transcript"]) >= int(turn_no) else ""
        checks[f"reply {turn_no} says {'/'.join(words)}"] = any(_norm(w) in _norm(reply) for w in words)
    for turn_no, words in e.get("reply_not_contains", {}).items():  # e.g. a wrong guess
        reply = run["transcript"][int(turn_no) - 1]["agent"] if len(run["transcript"]) >= int(turn_no) else ""
        checks[f"reply {turn_no} avoids {'/'.join(words)}"] = not any(_norm(w) in _norm(reply) for w in words)
    if "location_confirmed" in e:
        checks["location_confirmed"] = bool(r["location"].get("confirmed_with_caller")) == e["location_confirmed"]
    if "location_on_map" in e:
        checks["location_on_map"] = r["location"].get("on_map") == e["location_on_map"]
    if "street_found" in e:  # the street in the report exists in the caller's area on OpenStreetMap
        checks["street_found"] = bool(r["location"].get("street_matches")) == e["street_found"]
    if "people_groups_min" in e:  # separate places (a tree, a building) stay separate entries
        checks["people_groups"] = len(groups) >= e["people_groups_min"]
    if "people_injured_max" in e:  # injuries the caller never mentioned must not be invented
        checks["no_guessed_injuries"] = sum(g.get("injured") or 0 for g in groups) <= e["people_injured_max"]
    if "people_dead_min" in e:  # deaths the caller reported must reach the report
        checks["people_dead"] = sum(g.get("dead") or 0 for g in groups) >= e["people_dead_min"]
    if "people_at_least" in e:  # "voices under the rubble" is a minimum, not an exact count
        checks["people_at_least"] = any(g.get("at_least") for g in r.get("people") or []) == e["people_at_least"]
    for topic in e.get("advice_required", []):
        if topic in ADVICE:  # skip topics that don't exist in the advice files yet
            checks[f"advice+ {topic}"] = topic in given
    for topic in e.get("advice_forbidden", []):
        checks[f"advice- {topic}"] = topic not in given

    # Masking: the caller's name and street must never reach the model.
    secrets = [s for s in [r["caller"]["name"]] if s]
    if not e.get("address_not_personal"):  # e.g. a port gate number is not a home address
        secrets += e.get("address_contains", [])[:1]
    # Whole words only: "Gül" (a street) must not match inside "meşgul" (busy).
    leaked = [
        s for s in secrets
        if any(re.search(rf"\b{re.escape(_norm(s))}\b", _norm(t)) for t in run["sent_to_model"])
    ]
    if secrets:
        checks["no_pii_to_model"] = not leaked

    return {"checks": checks, "urgency": urgency, "leaked": leaked}


def summarize(runs: list[dict]) -> dict:
    def pct(n, d):
        return f"{n}/{d} ({100 * n / d:.0f}%)" if d else "n/a"

    real = [r for r in runs if r["case"]["expect"].get("life_threat") is True]
    not_real = [r for r in runs if r["case"]["expect"].get("life_threat") is False]
    caught = [r for r in real if r["score"]["urgency"] == "life_threat"]
    over = [r for r in not_real if r["score"]["urgency"] == "life_threat"]
    all_checks = [v for r in runs for v in r["score"]["checks"].values()]
    by_kind: dict[str, list[bool]] = {}
    for r in runs:
        for k, v in r["score"]["checks"].items():
            by_kind.setdefault(k.split(" ")[0], []).append(v)
    lat = [ms for r in runs for ms in r["latencies_ms"]]
    return {
        "cases": len(runs),
        "life_threat_recall": pct(len(caught), len(real)),
        "missed_life_threats": [r["case"]["id"] for r in real if r not in caught],
        "over_triage": pct(len(over), len(not_real)),
        "checks_passed": pct(sum(all_checks), len(all_checks)),
        "by_check": {k: pct(sum(v), len(v)) for k, v in sorted(by_kind.items())},
        "latency_ms": {
            "median": round(statistics.median(lat)) if lat else None,
            "p90": round(statistics.quantiles(lat, n=10)[-1]) if len(lat) >= 10 else None,
        },
        "model_errors_retried": sum(r["errors"] for r in runs),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lang", help="comma-separated, e.g. el,tr")
    parser.add_argument("--case", help="case ids, comma-separated")
    parser.add_argument("--sleep", type=float, default=0.5, help="seconds between turns")
    args = parser.parse_args()

    cases = load_cases(set(args.lang.split(",")) if args.lang else None, args.case)
    if not cases:
        raise SystemExit("no matching cases")
    _spy_on_model()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}.json"
    runs, not_run = [], []
    usage = budget.status()
    print(f"Gemini requests so far: {usage['hour']}/{usage['max_per_hour']} this hour, "
          f"{usage['day']}/{usage['max_per_day']} today. A full run uses about 250.\n")
    for i, case in enumerate(cases, 1):
        if budget.status()["limit_on"]:
            not_run = [c["id"] for c in cases[i - 1:]]
            print(f"\nStopped: the Gemini request limit is active (brain/budget.py). Not run: {', '.join(not_run)}")
            break
        run = run_case(case, args.sleep)
        run["score"] = score(run)
        run.pop("sent_to_model")  # only needed for scoring
        if run["gave_up"]:
            not_run = [c["id"] for c in cases[i - 1:]]
            print(f"\nStopped at {case['id']}: the model is still unavailable after retries. "
                  f"Last error from Gemini: {core.last_model_error or 'none recorded'}. Not run: {', '.join(not_run)}")
            break
        runs.append(run)
        failed = [k for k, v in run["score"]["checks"].items() if not v]
        mark = "PASS" if not failed else "FAIL"
        print(f"[{i:2}/{len(cases)}] {mark} {case['id']:<28} urgency={run['score']['urgency']!s:<12} "
              f"action={run['action']:<8} {'failed: ' + ', '.join(failed) if failed else ''}")
        # Save after every case, so a stopped run keeps what it finished.
        _save(out, runs, not_run=[c["id"] for c in cases[i:]])

    summary = summarize(runs) if runs else {}
    print("\n" + json.dumps(summary, ensure_ascii=False, indent=2))
    _save(out, runs, not_run)
    print(f"\nFull results: {out}")


def _save(out: Path, runs: list[dict], not_run: list[str]) -> None:
    summary = summarize(runs) if runs else {}
    data = {"summary": summary, "not_run": not_run, "runs": runs}
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
