# Voice

The phone side of the agent: a LiveKit worker that listens to the caller, sends each finished sentence to the brain, and speaks the brain's reply.

```
caller audio ──► Silero VAD + Soniox speech-to-text ──► brain.turn_stream() ──► Cartesia (or Azure) text-to-speech ──► caller
```

The brain decides everything said on the call (see [brain/README.md](../brain/README.md)). This package only moves audio and text, and ends the call when the brain says so.

## Keys checklist

Also tracked, with links, in the pinned [issue #3](https://github.com/pro56john/Voice_Agents_Hackathon/issues/3). Shown with a link for each missing key every time the worker starts, and by:

```bash
.venv/bin/python -m voice.check
```

| Key | For | Needed |
|---|---|---|
| `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` | LiveKit Cloud project | For `start` mode, not for `console` |
| `SONIOX_API_KEY` | Speech-to-text | Yes |
| `CARTESIA_API_KEY` | Text-to-speech | Yes, with `VOICE_TTS=cartesia` (default) |
| `GEMINI_API_KEY` | The brain | Yes |
| `CARTESIA_VOICE_EL` / `_TR` / `_EN` / `_FR` | One voice per language, picked in the Cartesia dashboard | No: empty uses Cartesia's default voice |
| `ELEVENLABS_API_KEY` | Text-to-speech with ElevenLabs. Easiest: `npx -y @elevenlabs/cli@latest onboard init` signs you in and saves it to `.env` (the old name `ELEVEN_API_KEY` also works) | Only with `VOICE_TTS=elevenlabs` |
| `ELEVENLABS_VOICE_EL` / `_TR` / `_EN` / `_FR` | ElevenLabs voice per language, e.g. your own cloned Greek voice | No: empty uses ElevenLabs' default voice |
| `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION` | Text-to-speech with Azure | Only with `VOICE_TTS=azure` |
| `AZURE_VOICE_EL` / `_TR` / `_EN` / `_FR` | Other Azure voices | No: defaults are Athina (el), Emel (tr), Sonia (en-GB), Denise (fr) |
| `OPERATOR_NUMBER` | Phone that handoffs are transferred to | No: without it the call hangs up after the handoff line |
| `SONIOX_BASE_URL` | Only for an EU-region Soniox project: `wss://stt-rt.eu.soniox.com/transcribe-websocket` | No: empty uses Soniox's default (US) server |

**Soniox region.** A Soniox project's region is fixed when it is created, and its keys only work on that region's server. For development with invented test calls the default US region is fine. For real callers, Docs/Research/07 asks for EU processing: create an EU project (enabled on request by Soniox, see their [data residency page](https://soniox.com/docs/stt/data-residency)) and set `SONIOX_BASE_URL`. The EU host name is from Soniox's docs; the `/transcribe-websocket` path is assumed to match the US server and is not tested.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # then fill in the keys above
```

## Try it

Run from the repository root, so voice calls write to the same `output/` folder as the messaging server and grouping sees both.

```bash
.venv/bin/python -m voice.agent console   # talk through your laptop mic and speakers
.venv/bin/python -m voice.agent start     # join LiveKit Cloud, then call it from the Agent Console
```

The Agent Console is in the LiveKit Cloud dashboard; it replaces the old Agents Playground. `dev` mode still works but LiveKit has deprecated it; for restart-on-save during development use their CLI instead: `lk agent dev` ([LiveKit CLI](https://docs.livekit.io/reference/developer-tools/livekit-cli/)).

Browser and console calls have no caller ID, so the call uses `VOICE_TEST_PHONE` (default `+30 690 000 0000`). Set it to a `+90` number to start in Turkish.

**A link for someone else to call the agent from a browser** (while `voice.agent start` runs):

```bash
.venv/bin/python -m voice.link --lang tr --hours 12
```

With `PUBLIC_BASE_URL` set (the messaging server's tunnel, see `channels/README.md`) it prints a **short link to the messaging server's `/call`**: every click makes a pass for a new room and redirects to LiveKit Meet, so several people can call at once and a link can be reopened right after a call. It is signed with `LIVEKIT_API_SECRET` (only links made here work) and stops after `--hours`; it needs the messaging server and its tunnel running. Without `PUBLIC_BASE_URL` it prints a direct LiveKit Meet link for one fixed room. The pass carries the language the call starts in (`--lang el|tr|en|fr`, default `el`), which wins over `VOICE_TEST_PHONE`; a Turkish tester's browser call stayed in Greek before (2026-10-26).

Why a new room each time: LiveKit sends the agent only into a newly created room. A fixed room stayed open for about 40 s after a call (the agent writes the summary meanwhile), and reopening the link then joined it with no agent, which LiveKit Meet shows as "Disconnected". The agent now also closes the room as soon as the caller leaves (about 8 s), but reusing a room name that soon still didn't always bring the agent.

## How a call behaves

- **Greeting**: `start_call()` gives the fixed automated-assistant greeting in the language of the phone's country code (+30 Greek, +90 Turkish, otherwise English).
- **Each caller sentence**: when the caller stops speaking, the text goes to `brain.turn_stream()` in a separate thread, and the reply is spoken **while the brain is still writing it**: speech starts as soon as the first words arrive (about 1 s in a live check) instead of after the whole answer. `VOICE_STREAM_REPLIES=off` goes back to waiting for the whole reply with `brain.turn()`.
- **Slow replies** (issues #2 and #4): if the caller has heard nothing `VOICE_HOLD_AFTER_S` (2.5 s; 1.5 s played it three times in one test call, and the real reply then waited for it) after they stopped, the agent says the brain's short "one moment" line ("Μισό λεπτό, το σημειώνω.") and the reply follows. In the brain, a live model that takes over 4 s is abandoned for a backup model (see brain/README.md), so a reply should rarely take more than about 6 s even on the free tier.
- **End of the caller's turn**: Soniox decides when the caller has finished (`VOICE_TURN_DETECTION=stt`, the default). Its endpoint detection listens to pauses, intonation and the words so far, so "Ονομάζομαι εε…" plus a pause should not end the turn the way a silence timer does. It waits at most `SONIOX_MAX_ENDPOINT_DELAY_MS` (1500) after speech stops, with `SONIOX_ENDPOINT_SENSITIVITY` at Soniox's default 0.0. Until 2026-10-24 it was 2000 ms and -0.2 (slower to decide, as Soniox suggests for frequent pauses); in a test call callers then waited a median 2.8 s for each reply, about 1.4 s of it for the model. Each call's log now says how long end-of-turn detection waited ("end of turn detected … after the caller stopped", and "turn end" in the summary when the call ends). `SONIOX_ENDPOINT_LATENCY_LEVEL` (0–3, default 0) ends turns sooner but Soniox advises against it with a negative sensitivity. The Silero VAD still runs, for interruptions. `VOICE_TURN_DETECTION=vad` ends the turn after 0.5 s of silence instead; `VOICE_TURN_DETECTION=livekit` goes back to LiveKit's own audio turn detector, which the first console calls used. From livekit-agents 1.8.8's code (not checked in a log): in console mode it is LiveKit's cloud turn model, falling back to a local model that has no Greek; for a language it doesn't support it ends the turn 0.3 s after the caller stops, which would explain fillers ending turns.
- **What was heard** (`VOICE_LOG_HEARD`, on by default): every final sentence from Soniox is logged with the language and whether the agent was speaking at that moment, e.g. `call vo-… heard (el, agent speaking): …`. Use it to see whether words were never heard or were lost later (for example said while the agent was talking). The log contains what callers say: switch it off for real callers.
- **Fillers** (`fillers.py`, lists in `fillers.json`): a turn that is only hesitation ("Εε.", "μμ", "ııı", "um", "euh") is ignored: no brain request, the agent stays silent and keeps listening. In other turns fillers are dropped before the text reaches the brain ("Εε, Πολιτόπουλος" → "Πολιτόπουλος"). They are matched as whole words ignoring case, accents and repeated letters, so "ε" inside a word, "Ναι", "Evet", English "I" and "mhm" / "hı hı" (they mean yes) stay. Turkish "şey" is a real word ("bir şey oldu") and is only dropped as the first word. "Ε;" / "Hm?" ("what?") is kept. `VOICE_FILLER_FILTER=off` sends everything as heard.
- **Interruptions**: the caller can talk over a reply. The next `turn()` is told the last reply was interrupted.
- **Language**: the call starts in the language of the phone's country code. Soniox labels every sentence with the language it heard, and when the caller speaks another supported language (Greek, Turkish, English, French) the next turn switches to it. Short answers ("Ναι", "OK", "Evet") don't switch on their own: a sentence needs at least `VOICE_LANG_MIN_LETTERS` letters (default 12), but short sentences in the same other language add up over consecutive turns, and the caller's **first** words need only 5 letters ("Merhaba", "Hello"), since callers answer the greeting in their own language, but only when they are clearly one language (twice the letters of any other: "No, I— I connect. Merhaba" switched a Turkish link's call to English). The letters themselves beat speech-to-text's label: Greek letters, or ı, ğ, ş, can't be English (`brain/langs.script_language`); Soniox labelled Turkish sentences as English in a test call. A Turkish caller's "Merhaba." kept a test call in Greek before (2026-10-26). An unsupported language must be heard in two long turns in a row; then the brain hands the call to a human. Web test calls have no phone number, so they start in the language of their link (`voice.link --lang`), Greek by default.
- **Keyword boosting**: disaster terms in each language (σεισμός, εγκλωβισμένοι, enkaz altında, …) and the demo's place names (Samos, Vathy, İzmir, Bayraklı, …) are sent to Soniox as context, so it favours them when the audio is unclear (Docs/Research/03). The list is `keywords.json`; Soniox rejects context over about 10,000 characters, and a unit test checks the size. `VOICE_KEYWORDS=off` turns it off to compare. The room left is filled with every town, village and neighbourhood of the demo regions in `keywords.json` (Attica, Samos, İzmir; from `brain/gazetteer.py`, biggest first): a test call heard Παιανία as "Πυρανία" when it wasn't in the list. **Mid-call street hints**: once the brain has the caller's area street list (`brain.street_hints`), the agent adds those streets (up to 4,500 characters, before the region places) and reconnects Soniox between turns, never while the caller speaks, since Soniox reads context only when a connection opens (`keywords.StreetHintSTT`, which uses the plugin's private `_request_reconnect`). A test call heard "Βασιλίσσης Φρειδερίκης …" as "Σφαιρική …". `VOICE_STREET_HINTS=off` turns this part off. Not yet tried on a live call. **Spelled letters** ("Φ Ρ Ε Ι…") pass the filler filter, so "Ε" and "Μ" are kept as letters.
- **Voice**: Cartesia sonic-3 by default (older Sonic models have no Greek). `VOICE_TTS=azure` switches to Azure's named neural voices, and `VOICE_TTS=elevenlabs` to ElevenLabs (Flash v2.5, its fastest model, with a voice per language, e.g. your own cloned Greek voice and a native Turkish one). Whichever provider, the voice switches language (and voice) whenever the brain's reply is in another language.
- **ElevenLabs voice clone**: clone a voice in ElevenLabs (Voices → Add a new voice → Instant Voice Clone, 1–2 minutes of calm, clear speech, with the speaker's consent) and put its Voice ID in `ELEVENLABS_VOICE_EL`. Clone a native speaker per language: a Greek clone speaking Turkish keeps a Greek accent. `ELEVENLABS_STABILITY` (0.6) and `ELEVENLABS_SPEED` (0.9; ElevenLabs allows 0.7–1.2, the LiveKit plugin's comment says 0.8–1.2). The speed was 0.95 until the first console calls, where speech sometimes sounded rushed, then 0.85 with stability 0.6, which sounded slow and flat in a friend's test call, then 0.45 at 0.9, which sounded angry at the end of sentences in a test call on 2026-10-24; now 0.6 at 0.9. Lower stability is more expressive, and swings in emotion. For a more natural voice, `ELEVENLABS_MODEL=eleven_multilingual_v2` can be tried in `.env` (no code change); it starts speaking later than Flash v2.5 (by how much is not measured here), and a Professional Voice Clone (about 30 minutes of recordings) is the bigger step. The pre-recorded lines recorded at 0.95 then measured about 3.4 words (20 characters) a second in Greek and 3.2 in English, against 1.7 words (12 characters) in Turkish.
- **Pre-recorded lines** (ElevenLabs only): the greeting, hold line, handoff line, "please repeat" and the 19 advice texts are recorded once and played from disk, so they start at once and cost no credits during calls. The model's own questions and read-backs are still spoken live. A line plays from disk only if it was recorded with the current voice, model, stability and speed; otherwise it is spoken live, so a call never depends on a recording. See "Pre-recording" below.
- **Ending**: when the brain returns `end` (read-back confirmed) or `handoff`, the last line is played in full and cannot be interrupted. After `end` the call is hung up.
- **Handoff**: on a phone call with `OPERATOR_NUMBER` set, the caller is transferred to that phone (they hear a dial tone). Without it, on browser or console calls, or if the transfer fails, the call is hung up after the handoff line; the report is marked `handed_to_human` either way.
- **Noise cancellation**: LiveKit Cloud's telephony model on phone lines, its general model on browser calls (Docs/Research/02). It only works on LiveKit Cloud: set `VOICE_NOISE_CANCELLATION=off` on a self-hosted server.
- **`end_call()`** runs exactly once however the call ends: `completed`, `handed_off`, `hung_up` (caller left) or `dropped` (anything else). It writes the operator summary, so shutdown waits up to 30 s for it.
- **Reply times** (issue #2): every reply logs the seconds of silence between the caller stopping and the agent starting to speak (the hold line counts as speaking); the end of the call logs the median and 90th percentile of that silence and of the brain's time until its answer started arriving. Logs only; the report is unchanged.
- Reports and transcripts are saved by the brain to `output/` with `"source": "voice_agent"`.
- **When it takes no new calls** (`load.py`): at `VOICE_MAX_CALLS` calls at once (3), or when the CPU stays above `VOICE_CPU_LIMIT` (95%) for about 5 seconds. LiveKit's own rule marks the agent full whenever the computer's CPU is over 70%, and on 2026-10-29/30 it did so with no call running while other apps were busy, so a call got no agent; a screen recording of the demo would have done the same. The speech-to-text, the model and the voice run in the cloud, so the number of calls is the better measure. The CPU is measured over a fixed 5 seconds of time, not "since LiveKit last asked": LiveKit asks at uneven moments, sometimes milliseconds apart, macOS reports 0% or 100% over such spans, and on a demo take that marked the agent full for 30 s at 27% CPU, so the caller left before it joined. Each time the agent stops or starts taking calls, the log says why (calls running, CPU). Not measured: how many calls at once the speech and voice plans allow.

## Testing turn-taking and speed in a console call

```bash
.venv/bin/python -m voice.agent console
```

The log shows `turn end from stt {'max_endpoint_delay_ms': 2000, 'endpoint_sensitivity': -0.2}` at the start. Then try:

1. Answer the name question with "Εε…", wait about a second, then say the name. The agent should stay silent through the pause (the log says `only fillers, still listening` if Soniox ended the turn on the filler alone) and the report's name should have no "Εε".
2. Say a sentence with a pause in the middle ("Είμαι στο… Βαθύ"). It should not answer at the pause.
3. Say a short finished answer ("Ναι."). Note how long it takes to answer; the log line `s of silence before the reply` gives the seconds (whether that count includes Soniox's wait is not checked).
4. Listen to the speed: every line is spoken live at 0.85 until the lines are recorded again.

To compare with the old behaviour, run once with `VOICE_TURN_DETECTION=livekit VOICE_FILLER_FILTER=off ELEVENLABS_SPEED=0.95`.

## Pre-recording the fixed lines

With `VOICE_TTS=elevenlabs` and an ElevenLabs voice set per language:

```bash
.venv/bin/python -m voice.prerecord          # shows what would be recorded and how many characters
.venv/bin/python -m voice.prerecord --yes    # records it (24 lines per language, about 5,000 characters each)
```

- Only languages with `ELEVENLABS_VOICE_<LANG>` set are recorded. `--lang el` limits it to one.
- Already recorded lines are skipped. Changing an advice text, the voice, the model, `ELEVENLABS_STABILITY` or `ELEVENLABS_SPEED` makes those lines play live until you run it again.
- It stops at the first error (wrong key or voice ID, no credits) rather than retrying.
- Recordings go to `voice/recordings/`, which is not in git: they are your voice, and can be regenerated any time.
- `VOICE_RECORDINGS=off` speaks every line live, e.g. to compare.

## Phone calls

Calls reach LiveKit through a SIP trunk; the worker needs no code change, only setup. The caller's number (from the call) sets the first language.

1. **Number.** Buy a number in [Twilio](https://www.twilio.com/try-twilio). Greek and Turkish numbers usually need regulatory documents first; a US number is quicker for testing. Alternative: [LiveKit Phone Numbers](https://docs.livekit.io/telephony/start/sip-trunk-setup/) bought inside LiveKit Cloud (country coverage not checked).
2. **Twilio → LiveKit.** Follow [Create and configure a Twilio SIP trunk](https://docs.livekit.io/sip/quickstarts/configuring-twilio-trunk): an Elastic SIP trunk whose origination points at your LiveKit project's SIP host, with the number attached. Allow call transfer (SIP REFER) on the trunk, or handoffs can't be transferred. The simpler [TwiML option](https://docs.livekit.io/sip/accepting-calls-twilio-voice) answers calls but cannot transfer.
3. **LiveKit inbound trunk and dispatch rule.** In LiveKit Cloud → Telephony, create an inbound trunk for the number and a dispatch rule that puts each caller in their own room ([accepting calls](https://docs.livekit.io/telephony/accepting-calls/)). The worker joins every new room, so the rule needs no agent name.
4. **Operator.** Set `OPERATOR_NUMBER` to the phone that plays the 112 operator, in `+<country><number>` form.
5. Run `.venv/bin/python -m voice.agent start` and call the number.

The exact Twilio and LiveKit screens may differ from these steps; the linked guides are the reference.

## Limits

- **Language switching** relies on Soniox's labels; how often it mislabels Greek and Turkish on phone audio is not measured yet. Words from two languages in one sentence count towards the language with more letters.
- **Keywords** are a fixed list for the demo: whether they improve Greek and Turkish transcripts is not measured, and the place names do not follow the caller's location (voice calls carry no AML yet). The terms are a draft for native speakers to check.
- **Transfer** needs Twilio Elastic SIP Trunking with call transfer allowed (below); not tested yet.
- **Streaming and the hold line are not tested on a real call yet**, only with unit tests and one live streamed brain turn (no LiveKit). Check on the first calls that the hold line doesn't overlap the start of the reply.
- **No AML location**: phone calls carry the caller's number, not their position.
- **Turn end and fillers are not tested on a call yet**, only with unit tests. The Soniox values are starting points. If the agent now waits too long after a finished sentence, raise `SONIOX_ENDPOINT_SENSITIVITY` towards 0; if fillers still end the turn, lower it towards -0.5. The filler list may miss how Soniox writes a hesitation (e.g. "ehh"): add it to `fillers.json`. An ignored filler turn that interrupted a reply leaves that reply cut off.
- **Speed 0.85 makes every pre-recorded line play live** (recordings are keyed by speed) until `python -m voice.prerecord --yes` records them again, about 15,500 ElevenLabs characters for the 72 lines. Live lines cost credits and start a little later.
- Not tested with real keys yet: only the unit tests below have run.

## Tests

```bash
.venv/bin/python -m pytest -q tests/test_voice_*.py   # call flow, language, keywords, fillers, voices, telephony, timing; no keys needed
```

## Files

| File | What |
|---|---|
| `agent.py` | The LiveKit worker: session setup, speech-to-text, text-to-speech, ending the call. |
| `call.py` | One call's link to the brain (`start_call` / `turn` or `turn_stream` / `hold_phrase` / `end_call`), without LiveKit code, so it can be tested; `in_thread()` hands a blocking generator's items to async code. |
| `fillers.json`, `fillers.py` | Hesitation fillers per language; ignoring filler-only turns and stripping fillers before the brain. |
| `language.py` | Decides each turn's language from Soniox's labels, ignoring short answers. |
| `telephony.py` | Phone-call helpers: transfer target for handoffs, noise cancellation per caller, a browser link's language. |
| `link.py` | `python -m voice.link`: a browser link to call the agent, with its starting language and how long it works. |
| `timing.py` | Reply-time bookkeeping: silence per turn and the end-of-call summary. |
| `load.py` | When this computer takes no new calls: by the number of calls, and by the CPU only when it is saturated. |
| `recordings.py`, `prerecord.py` | Pre-recorded fixed lines: finding and playing them, and recording them once with the ElevenLabs SDK (which reports the characters charged). |
| `voices.py` | Text-to-speech provider (Cartesia, Azure or ElevenLabs) and the voice for each language. |
| `keywords.json`, `keywords.py` | Disaster terms, place names, the demo regions' places and the caller's area streets, boosted in speech-to-text. |
| `config.py` | Settings from `.env` (including the turn-end and Soniox endpoint settings) and the keys checklist. |
| `check.py` | Prints the keys checklist. |
