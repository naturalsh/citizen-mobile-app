# Operator dashboard

A live web page for 112 operators: every call and message the agent handles appears as an incident, sorted by urgency, on a map, with the AI's suggested urgency and its reasons for an operator to **confirm, change or escalate**. It reads what the brain already writes (`output/reports/`), so voice, WhatsApp and SMS calls all show up, from any process.

## Run it

```bash
.venv/bin/python -m dashboard --demo            # the 34 eval test calls, replayed as the last 40 minutes
.venv/bin/python -m dashboard --demo --reset    # same, forgetting earlier claims and decisions (before a demo)
.venv/bin/python -m dashboard                   # live calls from output/reports
```

Open http://127.0.0.1:8001. Start the shift with your name: it goes on every claim and decision, and the click lets the browser play alert sounds.

It listens on 127.0.0.1 only and has **no login**, while it shows callers' names, numbers and addresses: never expose it to a network as is.

**Sharing with a friend on the same Wi-Fi** (for testing): `.venv/bin/python -m dashboard --share` starts a second copy on port 8003 and prints a link like `http://192.168.1.20:8003/?key=…`. It is the full dashboard (every button works, Pause AI too), but every request needs the key from the link; opening the link once stores it in a cookie. The key stays the same across restarts (kept in `output/dashboard_share_key`, never committed; `DASHBOARD_ACCESS_KEY` overrides it): a new key on every start locked out a page opened with the old link, and its transcripts didn't load. A page whose key no longer works now says so. It works only on the same network, only while it runs (Ctrl+C stops it), and anyone with the link sees callers' details: send it only to the person testing with you. macOS may ask once whether Python may accept incoming connections.

**Outside the Wi-Fi** (e.g. a friend elsewhere): the messaging server's fixed ngrok address shows that copy, behind the same key: `https://<ngrok-address>/?key=…` (channels/README.md, "The shared dashboard at the same address"). The address never changes, but ngrok's free monthly allowance is shared with texting and call links, so the page there updates every 10 s. Before that, we ran a Cloudflare quick tunnel to that copy, `cloudflared tunnel --protocol http2 --edge-ip-version 4 --url http://localhost:8003` (TCP and IPv4: the default UDP connection dropped on this network), and send its `https://….trycloudflare.com` address with the same `?key=…`. Without the key the page answers 401. The address changes every time the tunnel starts, and Cloudflare dropped it after a few hours (2026-10-29), which is why it moved to ngrok.

## What's on the screen

```
┌──────────────────────────────────────────────────────────────────────────┐
│ 112 Overflow operator dashboard        Live · AI requests · Sound · Pause AI │
│ ● 2 on the line ▲ 3 LIFE THREAT ▲ 1 not taken ◆ 5 URGENT … ✓ 6 resolved   │
├────────────────────────┬──────────────────────────┬──────────────────────┤
│ QUEUE (incidents)      │ MAP                      │ SELECTED INCIDENT    │
│ on the line now,       │ one shape per incident,  │ steps: take, check,  │
│ urgency badge, AI %,   │ size = number of calls,  │ resolve; notes;      │
│ NEW EVENT, timer,      │ colour/shape = urgency,  │ per call: summary,   │
│ place, calls, people,  │ older ones fade,         │ caller, address, GPS,│
│ status, claim,         │ resolved ones faint      │ advice, Agree /      │
│ resolved (collapsed)   │                          │ Change / Supervisor, │
│                        │                          │ call back, transcript│
└────────────────────────┴──────────────────────────┴──────────────────────┘
```

- **Top-bar counts are buttons:** LIFE THREAT, URGENT, NEEDS HELP and INFO jump to that section of the queue; "not taken" opens the oldest life-threat nobody has taken and zooms the map to it; "on the line" jumps to the calls in progress; "resolved" opens the resolved list. The level counts are open incidents only.
- **On the line now:** a panel at the top of the queue lists every call or message the AI is handling right now (green dot, no blinking: it isn't an alarm), with where, what's known so far and the suggested urgency. Click one to open it and follow the **live conversation**: the transcript refreshes every 2 seconds and stays scrolled to the newest line. Selecting an incident with a call in progress opens that conversation by itself. When the caller says where they are, the brain may put the call into an event, which changes its incident: the open detail, a claim, notes and a half-written note follow the call there, and the map flies to the place. A call counts as on the line while its report is "in progress" and changed in the last 10 minutes; an "in progress" call silent for longer shows "No update for … (line may have dropped)".
- **Queue:** grouped under a heading per urgency level; one card per incident (calls with the same `event_id`, e.g. 4 calls about one collapsed building). Sorted by highest urgency, then unclaimed before claimed, then **within the level**: anyone not breathing or unconscious first, then the most people at risk (trapped, injured, can't leave), then the most calls, then longest waiting. The card shows why ("1 not breathing / unconscious", "5 trapped"); "1+ trapped" means at least one, maybe more (e.g. voices heard under rubble). Deaths get their own tag ("5 dead") and count towards the priority. There is one tag per person or group the caller described ("1 trapped, injured · under a tree", "1+ trapped · voices in building"), never one per condition. A red **⚠ not found on the map** next to the address means the brain's map check (brain/places.py) couldn't find the place: it may have been misheard. **⚠ street not found** means the brain searched the street inside the caller's area and it isn't there (probably misheard): the pin is only the area. **⚠ location not confirmed** means the call ended without the caller saying yes to the location read back to them: call back to check it. Under the address, "Caller said: «…»" shows the landmark exactly as speech-to-text heard it, and "map:" the real place the map check thinks was meant. The order is recomputed every 2 seconds, so an incident moves up as soon as a call reports something worse. INFO incidents go into a collapsed **Can wait** list (the INFO count opens it). The timer turns bold and underlined when an unclaimed incident waits longer than its target (2 min life threat, 5 min urgent, 15 min needs help: demo targets, not a standard). The order holds still while the mouse is over the list.
- **Map:** we only know where someone is **once they say it**. The position is the building when OpenStreetMap has its house number, else the street the caller named, searched only inside their area and in its spellings with and without doubled letters (a test call's "Καλλιρρόης" is "Καλλιρόης" on OpenStreetMap). The brain searches the street inside the area during the call (`location.street_matches`, see `brain/README.md`). Found in one place, it is pinned there, and then **the building is placed by its house number**: the dashboard takes every numbered building in a small box around that street from the local OpenStreetMap index (`brain/osm_index.py`; nothing is sent), or, without the index, from OpenStreetMap's Overpass service (only the box is sent: never the number, the street or the name), and picks the caller's number on this machine. The building itself when it is mapped (a ±30 m mark); otherwise an **estimate** between the nearest mapped numbers on the same side of the street (even and odd numbers face each other: No. 10 between 4 and 12), or next to one mapped neighbour at most 10 numbers away, or, when nothing is mapped on the caller's side, across from a number at most 4 away on the other side (Ορλώφ in Koukaki has only No. 9: No. 12 is "≈ estimated across from No. 9", the street's width added to the circle), with a circle as big as the doubt ("≈ estimated between No. 4 and No. 12"); otherwise the street ("house number not on OpenStreetMap"). Until 2026-10-30 none of this ran on live calls: the dashboard's call data left out the report's street, so every call showed "no house number said"; the tests had built that data by hand. OpenStreetMap often has few house numbers in Greece and Türkiye: a live check found 23 on Kıbrıs Şehitleri Caddesi in Alsancak and one on Ορλώφ. `DASHBOARD_HOUSE_NUMBERS=off` turns this off. Found in several (that call's "Καλλιρρόης, Athens" is in 6 places in greater Athens), each is marked **?** on the map, the detail lists the three closest to the centre, and the agent asks the caller which neighbourhood; once they say it, the pin moves to the street. Not found in the area, the detail says it may have been misheard. The dashboard's own area search also takes only places (neighbourhood, town, district), never the shop or holiday flat OpenStreetMap may list first: "Acropolis, Koukaki, Athens" was pinned on a flat's listing on 2026-10-30; it now falls back to "Koukaki, Athens". Its cache moved to a new table for the same reason. Calls from before this check fall back to the dashboard's own lookup, which places a street only inside a neighbourhood or village (up to 5 km). If "Old port, Chania" isn't found but "Chania" is, the page says it shows the whole wider place. Otherwise it is the area, the middle of the village or town; until then the incident isn't on the map and its call shows "Location not said yet". Phone GPS (AML) doesn't reach this line: phones send it only to the official 112 centre when 112 is dialled. If 112 ever passes it on (`CallInfo.aml` in the contract), the map uses it and the call shows "Phone GPS". **How exact a pin is, is always visible:** every pin shows where the caller may be, as big as what is known: **the whole street highlighted** when only the street is known (the house number isn't on OpenStreetMap, or wasn't said; its line comes from OpenStreetMap through the brain's map check), **the neighbourhood's own outline** for an area (an area centre is never an address), a dashed circle for phone GPS (its accuracy) or for an area without an outline on OpenStreetMap. When the street is in several neighbourhoods, each candidate stretch is drawn as a thin dashed line next to its "?". An area-only pin also gets a "≈", its card says "≈ approx. location", and the detail says in words what the pin means ("only the centre of Kallithea (±1.8 km): the caller is somewhere in the dashed circle"). Selecting it zooms to the whole circle. "⚠ place not found" and "⚠ location unknown" say when there is no position at all, and a box in the map's corner lists those incidents (click one to open it; click its heading to fold it to one line), so they never vanish from the map's view. Incidents at the same spot fan out slightly. Markers older than 30 minutes fade. Selecting an incident (card or marker) zooms in on it (OpenStreetMap zoom 15.25, small roads, 20% closer than level 15; 17.25 with phone GPS) and enlarges its marker; **⤢ Show all** zooms back out.
- **Transcript in one click:** every call block has a **📄 Transcript** button in its top row (next to *📞 Call back*; "Live transcript" while the call is on), and **T** opens or closes the transcripts of the selected incident.
- **Detail, summary first:** a header that stays put while the rest scrolls, with the urgency, how sure the AI is, the waiting time, the place and street, why it ranks where it does (people at risk and the AI's first reasons), and **the next step as the only filled button on the screen**: *Take incident*, then *✓ Agree: LIFE THREAT* for the first unchecked call, then *✓ Mark resolved*. *Give back* and *Reopen* are plain links. Below: the operator summary (Greek or Turkish), one compact block per call (status, why a person took over if they did, what happened, the urgency controls, *📞 Call back*), and **details and the transcript only when asked for** (open by themselves for a call on the line). **Notes are at the bottom.** Resolving before every call is checked is set apart at the very bottom and asks first.
- **English by default:** the summary and every transcript line are shown in English (copies the brain makes in the same AI answers, see brain/README.md). **Show original (Ελληνικά / Türkçe)** next to the summary switches that incident to the caller's language. Calls made before this existed show the original, marked "not translated". On a live call the caller's newest sentence stays in the original for a second or two, until the agent's reply comes back.
- **Hazards: a category and a kind.** Cards read "🔥 Fire · vehicle", "🌊 Flood · water in a building". The **Hazard** filter has each category (all of it, or one kind), and **🐾 Animals involved**. Animals at risk show as their own tags ("🐾 1 cat trapped"), never counted as people.
- **Resolved:** the incident leaves the queue, the counts and the map. **Show: Open / Resolved / All** above the queue picks what the queue and the map show (Open by default; the "resolved" count switches to Resolved). Under All, resolved incidents sit in a collapsed **✓ RESOLVED** list at the end of the queue and fade on the map. *Reopen* brings one back. If a **new call** joins a resolved incident, it reopens by itself, marked "NEW CALL AFTER RESOLVED".
- **Notes:** free text on the incident (up to 300 characters), e.g. "Fire crew 3 sent, 14:10", saved with the operator's name and time. A half-written note is kept while the page refreshes. Undo removes only your own note from the last 5 minutes.
- **📞 Call back** on every call with a number: opens the computer's phone app (`tel:` link) and reminds you to add a note. A life-threat whose line dropped gets a red "Line dropped: call back" tag.
- **Urgency per call:** **✓ Agree** keeps the AI's level; picking another level and **Set level** sets another, and stays available after agreeing, so an operator can change their mind at any time (the latest decision counts); **⚑ Ask supervisor** flags it for a second opinion. Each decision, claim, resolution and note is saved with the operator's name and time in `operator.sqlite`, apart from the reports (the brain rewrites those every turn).
- **Feedback:** a button shows "Saving…" while it works; then a message at the bottom says what happened ("✓ You agreed: LIFE THREAT for the 13:27 call") with **Undo**, and what changed flashes once. Undo removes only your own decision from the last 5 minutes; anyone else's stays on record.
- **Surge mode** (on by default): how readily the AI hands callers to a person. On: only not breathing, crimes in progress, unsupported languages and callers who insist go to a person; the AI records the rest (a cat in a tree) as low priority and ends the call. Off: anything outside a disaster call goes to a person. Asks before switching; see brain/README.md.
- **Pause AI:** stops the agent on every channel. New calls and messages hear only the handoff line and go to a human (`handoff_reason: "operator_paused"`); the failed-112-call trigger sends nothing. A banner shows who paused it and when.
- **Alerts:** a blinking edge and a two-tone sound only for **new** life-threats (first call under 2 minutes ago) nobody has claimed; the sound repeats every 15 s until it's claimed or no longer new. Everything else updates silently.
- **Spending:** the top bar shows Gemini requests against the hour limit (brain/budget.py); a red banner appears when the limit is reached.
- **Theme:** dark grey by default (projectors, dim rooms), light switch in the top bar.

## Design rules and where they come from

Researched on 2026-10-22. Standards marked *secondary* were read through summaries, not the paywalled text.

| Rule | Source |
|---|---|
| Neutral grey screen; bright colour only for priority states | ISA-101 high-performance HMI (*secondary*: vendor summaries) |
| Few priority levels, the top one rare; no alarm floods | EEMUA 191 / ISA-18.2 (*secondary*) |
| Alerts sound/flash until acknowledged (Claim), then stay listed quietly | ISA-18.2 (*secondary*) |
| Never colour alone: shape + label for each level (▲ ◆ ● ○) | WCAG 2.2 SC 1.4.1, https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html |
| Blink at most 1/s (limit is 3 flashes/s); off with reduced motion | WCAG 2.2 SC 2.3.1 |
| Red / amber / green triage meaning; avoid black ("expectant") | START triage, https://chemm.hhs.gov/startalgotext.htm |
| Highest priority first, oldest within it; flag calls past their time target | CAD practice (*secondary*); NFPA 1225 / NENA-STA-020 targets (*secondary*) |
| Show incidents with their calls; many calls from one place is a signal | Dash et al. 2022, https://www.frontiersin.org/journals/human-dynamics/articles/10.3389/fhumd.2022.670647/full ; Ushahidi Haiti ("verification by aggregation") |
| Markers per incident sized by calls, not a heatmap, for call-taking | Esri clustering guidance (vendor), call-taker study above |
| AI suggestion visibly tentative (dashed "AI-suggested" badge) until a human confirms (solid, with name and time) | EU AI Act Art. 14(4)(b–d), https://artificialintelligenceact.eu/article/14/ ; automation-bias review, Goddard et al. 2012, https://pmc.ncbi.nlm.nih.gov/articles/PMC3240751 |
| Show reasons and confidence, not commands | Dzindolet 2003, Sarter & Schroeder 2001, McGuirl & Sarter 2006 (via the review above) |
| A way to stop the system | EU AI Act Art. 14(4)(e): the Pause AI switch |
| Record who confirmed or overrode | Accountability reduces automation bias (Mosier & Skitka, via the review above) |
| Most important first; a fixed header; details on demand, two levels at most | NN/g inverted pyramid, https://www.nngroup.com/articles/inverted-pyramid/ ; progressive disclosure, https://www.nngroup.com/articles/progressive-disclosure/ ; call-takers wanted extra media only "when needed" (Dash et al. 2022, above) |
| One primary button per screen; secondary outlined; status colours never on buttons | NHS design system, https://service-manual.nhs.uk/design-system/components/buttons ; GOV.UK, https://design-system.service.gov.uk/components/button/ ; ISA-101 grey screens (*secondary*) |
| Consequential actions (Resolve) apart from routine ones (Add note) | NN/g, https://www.nngroup.com/articles/proximity-consequential-options/ |
| Within the top level: not breathing first, then most people at risk, then waiting | MPDS Echo above Delta (*secondary*), https://iaedjournal.org/determinant-codes/ ; START, https://chemm.hhs.gov/incident-primer/triage/start-triage ; SALT "most good for most people" (*secondary*). The combination is ours, not a published algorithm. |
| In a surge, lower priorities wait (deferred list, surge mode) | Hurricane Harvey 911 practice (*secondary*, news report), https://www.pbs.org/newshour/show/this-familys-hurricane-tragedy-highlights-911-system-problems |
| Zoom 15 for an area, 17 for an address | OpenStreetMap zoom levels, https://wiki.openstreetmap.org/wiki/Zoom_levels |

**Colours** are a fixed status scale, checked with the dataviz palette validator for colour-blind separation between every pair of levels (worst ΔE 9.1 dark, 9.4 light; target ≥ 8):

| Level | Shape | Dark | Light |
|---|---|---|---|
| Life threat | ▲ | `#d03b3b` | `#d03b3b` |
| Urgent | ◆ | `#fab219` | `#fab219` |
| Needs help | ● | `#3b82d4` | `#1d5fc4` |
| Info | ○ | `#898781` | `#8a8983` |

## OpenStreetMap

Map positions for calls without GPS come from OpenStreetMap's Nominatim search (`geocode.py`):

- The **area** (village, neighbourhood, town) and the **street name** are sent, never a house number or the caller's name (decided by the user on 2026-10-22). A street position counts only within 3 km of the area.
- One request at a time, at most one per second, with an identifying User-Agent, as Nominatim's usage policy asks; every answer is cached in `output/geocode.sqlite`, so each place is looked up once.
- If it can't be reached, that area waits 5 minutes before the next try. The dashboard keeps working; those incidents are just not on the map.
- `DASHBOARD_GEOCODE=off` turns lookups off. Map tiles also come from OpenStreetMap (attribution shown on the map).

## Limits

- No login or roles: anyone who can open the page can claim, decide and pause. Fine on one laptop for a demo, not for a real control room.
- Polling every 2 seconds, not push. Fine for one operator and a few hundred incidents. Over the internet (any address that isn't this computer or the local network) the page asks every 10 seconds and not while its tab is hidden, and updates are compressed (35 KB → 6 KB), to stay inside ngrok's free monthly allowance; so the shared page is up to 10 s behind, and plays no alarm while hidden.
- Positions from area names are approximate (the middle of the village or town).
- Demo mode shifts the test calls' times to the last 40 minutes, so timers and fading look like a live surge; the test set is deliberately heavy on life-threats (19 of 33 incidents).
- "On the line" is read from the reports, which the brain rewrites after each turn, so the live conversation is one turn behind the audio, not word by word.
- Call back needs a phone app on the computer that handles `tel:` links (e.g. FaceTime with an iPhone); otherwise it does nothing.
- The live panel and transcript were checked with invented in-progress reports, not yet with a real call running at the same time. Not tested on a projector.

## Tests

```bash
.venv/bin/python -m pytest -q tests/test_dashboard.py tests/test_pause.py   # no network
```

## Files

| File | What |
|---|---|
| `app.py` | Web server and API: state, claims, decisions, resolve, notes, transcripts, Pause AI, surge mode. |
| `__main__.py` | `python -m dashboard [--demo] [--reset] [--port]`. |
| `data.py` | Reads the reports and builds incidents, the queue order (with the priority within a level), the counts and which calls are on the line. |
| `store.py` | Operator claims, decisions, resolutions and notes (SQLite), apart from the reports, and undo of your own recent decision or note. |
| `geocode.py` | OpenStreetMap lookups of area names, cached and rate-limited. |
| `static/` | The page: `index.html`, `style.css`, `app.js` (Leaflet map from cdnjs). |
