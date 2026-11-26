# How to work in this repo (Voice_Agents_Hackathon)

## Project context
- Disaster-emergency voice agent for Greece and Türkiye (112 overflow), part of After Chaos (Greece–Türkiye Hackathon). Two-person team.
- Two halves, each developed on its own branch:
  - **Brain** (`brain/conversation`, Aigeus): conversation, report, advice, WhatsApp/SMS, failed-112-call trigger, event grouping, masking, tests. See `brain/README.md` and `channels/README.md`.
  - **Voice** (`voice/livekit`, Ioannis): phone, LiveKit, speech-to-text, text-to-speech. See `voice/README.md`.
- The contract between them is `brain/contract.py`: `start_call` / `turn` / `end_call`. Never change it without saying so clearly; both people must agree.
- **Dashboard** (`dashboard/`): the operator web page over the brain's reports, with Pause AI. See `dashboard/README.md`.
- Research and decisions live in `Docs/` (flow diagram, `Docs/Research/01–07`). Read the relevant doc before building a part.
- Safety advice is only ever read from `brain/advice/*.json`. Sources and decisions are in `brain/advice/SOURCES.md`. Never let a model write advice.

## Plan before code
1. Read what exists first: the package READMEs, `brain/contract.py`, and the research doc for the part being built.
2. Write a short plan: what will be built, how it connects to what exists, the list of commits, and the decisions only the owner can make. Wait for the go-ahead.
3. If what you find contradicts the plan, say so before working around it.

## Before committing
1. Work on your own branch, never directly on `main`. Pull first (`git pull`) so you don't overwrite the other person's work. Rebase or merge `main` before opening a pull request.
2. Run the tests that exist and say whether they passed:
   - `.venv/bin/python -m pytest -q tests`: unit tests, no API calls.
   - `.venv/bin/python -m eval.run`: 55 scripted calls against live Gemini. It uses about 300 of the free tier's ~500 daily requests, so run it only when the conversation behaviour changed; see `eval/README.md`.
   - If something can't be tested (no API key, no phone), say so plainly. Never claim it works.
3. Check `git status` and `git diff --cached` before every commit:
   - Never commit `.env`, API keys, tokens, `output/`, `.venv/`, recordings or caller data.
   - Make sure `.gitignore` covers them.
4. One commit = one logical change, and the project still works after it. Don't mix a feature, a refactor and a formatting change. A feature commit also updates its README, `.env.example`, requirements and tests.
5. Commit only when asked, and push only when asked. Show what's going in first.

## Commit message format
```
<Imperative summary, max ~60 chars, no full stop>

<Why this change exists and what it does, in plain sentences. 2–6 lines.>

- <Notable detail or decision>
- <Anything deliberately left out, or a known limitation>
- <How it was tested, and results if there are numbers>

Co-Authored-By: <attribution line, when the session asks for one>
```

Rules:
- The summary says what the commit *does*: "Add Soniox speech-to-text for Greek and Turkish", not "updates" or "fix stuff".
- The body explains *why* and any decision the other person would otherwise have to guess, e.g. "Deepgram's multi-language mode has no Greek, so we use Soniox".
- Name files or areas only when it helps someone find things.
- Be honest about what is not done or not verified.
- Wrap lines at about 72 characters.

Example:
```
Add LiveKit voice worker connected to the brain

Calls arrive through Twilio SIP into LiveKit; each caller utterance
is transcribed by Soniox and passed to brain.turn(), and the reply is
spoken with Cartesia.

- Language from the phone country code, switched if Soniox detects
  another language in the first sentence
- On handoff, the call is transferred to OPERATOR_NUMBER
- end_call() runs on hang-up and on dropped calls
- Tested with 3 live calls in Greek and 2 in Turkish; median reply
  1.8 s. Not tested: interruptions while the agent is speaking
```

## Testing: two layers

| | Unit tests (`tests/`) | Test set (`eval/`) |
|---|---|---|
| What it checks | Code that should always behave the same: masking, grouping calls into events, the voice call flow, and any new deterministic code | The whole agent having real conversations |
| Calls paid APIs | Never | Yes, live Gemini (~250 of ~500 free daily requests per full run) |
| When | Before every commit | When the prompt, model, advice or anything that changes what the agent says has changed |
| Reported as | Pass/fail | **life_threat_recall** (the safety number), over-triage, checks passed, latency |

New deterministic code gets unit tests. Anything that depends on a model's answer belongs in the test set, not in `tests/`.

## Code conventions
- **Python**, one package per area (`brain/`, `channels/`, `voice/`, `eval/`), each with a `README.md`: what it is, setup, how to try it, how it behaves, limits, tests, and a **Files** table.
- Every module starts with a docstring saying what it does and which research doc it follows. Comments explain *why*, short.
- Settings come from `.env` (`python-dotenv`), read once at the top of the module as constants with safe defaults. Risky or costly features get an off switch (e.g. `BRAIN_MASKING=off`).
- **Never break a call.** Failures in side features are logged and the conversation continues. Retries are short because a caller is waiting.
- **Dry run without credentials**: if a service is not configured, log what would have happened instead of crashing. Keep a visible checklist of missing keys (`python -m voice.check`).
- Fixed texts that people hear (phrases, advice) live in JSON. Mark anything unverified `"_status": "DRAFT: ..."`.
- Test data uses invented names, numbers and addresses.

## Safety rules (Docs/Research/05 and 07)
- The AI only **suggests** urgency, always with reasons; only a human operator confirms.
- The agent says it is automated (EU AI Act Article 50).
- Hand off to a human when unsure, when asked, on an unsupported language, and at once if someone is not breathing.
- The model never sees names, street addresses or numbers (brain masking). Speech-to-text and text-to-speech providers still do.

## Issues (GitHub)
Use this structure:
```
Title: <specific problem or task, e.g. "Agent misses Turkish street names on 8 kHz audio">

## What
One or two sentences on the problem or the task.

## Why it matters
Effect on the caller, the operator or the demo.

## Details
- Steps to reproduce / example call / log excerpt (no real caller data)
- What was expected vs. what happened
- Relevant files and docs (e.g. Docs/Research/04_STT_and_TTS.md)

## Done when
- [ ] Concrete, checkable conditions
```
Label it with the area: `voice`, `brain`, `channels`, `docs` or `eval`.

## Pull requests
- Title like a commit summary.
- Body: what changed, why, how it was tested (with numbers), what's not done, and anything the other person must do (e.g. "add SONIOX_API_KEY to .env").
- Mention any change to `brain/contract.py` at the top.

## General
- Plain, short sentences. No marketing language.
- Never invent results. Mark guesses and vendor claims as such.
- Ask before anything hard to undo: force-push, deleting branches, rewriting history.
- When a change alters something this file describes, update this file in the same pull request.
- Every Gemini request goes through `brain/budget.py` (hour and day limits; the project has a €5 spending cap). New code that calls Gemini must call `budget.spend()` first.
