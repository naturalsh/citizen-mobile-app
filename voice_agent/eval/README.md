# Test set

55 scripted emergency calls that run against the real brain (live Gemini) and get scored. Use it after every change to the prompt, the model or the advice, and to show judges what the agent catches.

```bash
.venv/bin/python -m eval.run                          # all 55 cases, about 18 minutes
.venv/bin/python -m eval.run --lang el,tr             # only Greek and Turkish
.venv/bin/python -m eval.run --case el-flood-car,tr-flood-roof
.venv/bin/python -m eval.run --sleep 2                # slower, fewer free-tier rate limits
```

Each run prints PASS/FAIL per case and a summary, and saves everything (transcripts, reports, checks) to `output/eval/<time>.json` after every case. If the model stays unavailable after retries (usually the free tier's daily limit of about 500 requests, roughly two full runs), the run stops cleanly and lists the cases under `not_run`; rerun them later with `--case`. Eval calls write their reports and events to `output/eval/brain/`, apart from the real ones.

Every request counts towards the brain's spending limit (`brain/budget.py`, 300 an hour by default): the runner prints current usage when it starts and stops if the limit activates.

## The numbers that matter

| Metric | Meaning |
|---|---|
| **life_threat_recall** | Of the calls that really are life-threatening, how many the agent suggested as `life_threat`. **The safety number:** a miss means someone in danger waits in the normal queue. |
| **over_triage** | Of the calls that are clearly *not* life-threatening, how many it wrongly flagged `life_threat`. Too many and operators stop trusting the flag. |
| checks_passed | All individual checks together (below). |
| latency_ms | Time per reply (median and 90th percentile). |
| model_errors_retried | Free-tier rate limits hit during the run. |

## The cases

| File | Cases |
|---|---|
| `cases/el.json` | 34 Greek: earthquake (relative trapped, caller trapped, cracks only, info only, elderly alone, head bleeding by SMS, not breathing), wildfire (approaching, trapped in car), flood (rising water with wheelchair user, car in water), storm (power line down), asks for a human and insists, burglary (not a disaster), "called 112 by mistake" after the failed-call trigger; from live test calls: only a neighbourhood given, street unknown, cat in a tree (surge and normal mode), background speech, hesitation before the name, vague place by a port with voices under rubble, a hospital name misheard as "τζάμι ο νοσοκομείο", deaths with a garbled word and a name corrected at the read-back; from a test call on 2026-10-24: a street with no number (Ορλώφ, in two neighbourhoods of Athens), a full address in a whole city, a passer-by who can't give a street, a misheard «Φωτιά;», a flat on fire with smoke in the stairwell (building fire), a street narrowed by the neighbourhood the caller said or by a landmark next to it (Acropolis), a car fire, water inside a flat, and a cat trapped in a burning building |
| `cases/tr.json` | 13 Turkish: cat on a roof (surge mode), earthquake (building collapse, caller trapped, gas smell, info only, unconscious but breathing, broken leg by WhatsApp), wildfire (sheltering at home, on foot), flood (on the roof, shop only), storm (roof blown off), asks for a human |
| `cases/en_fr.json` | 5 English (tourist in a lift, tourist car in wildfire smoke, ferry question, a German speaker that must be handed off, and from a live test call: misheard area, building fire, a person under a tree and voices in a building, more information after the read-back) and 3 French (partner under a wall, flooded campsite, power line down) |

Places follow the demo story (2020 Samos–İzmir earthquake) and real recent disasters (Storm Daniel in Thessaly, Evros and Rhodes wildfires, Bozkurt flood, Hatay earthquake). All names, numbers and addresses are invented.

## How a case is written

```json
{
  "id": "el-flood-car",
  "description": "Car stuck in flood water near Volos.",
  "lang": "el", "phone": "+30 699 100 0009", "channel": "voice",
  "turns": ["The caller's lines, sent in order until the agent ends or hands off"],
  "answers": {"house_number": "Στο 20.", "name": "Νίκος Σταθόπουλος."},
  "expect": {
    "life_threat": true,
    "urgency": ["life_threat"],
    "hazard_type": "flood",
    "action": "end",
    "address_contains": ["Βενιζέλου", "20"],
    "caller_name": "Σταθόπουλος",
    "advice_required": ["flood.in_car"],
    "advice_forbidden": ["flood.water_rising_home"]
  }
}
```

`answers` (optional) makes the caller answer what it is asked: after each reply the runner looks at the step the brain scheduled (`brain/steps.py`: `area`, `street`, `neighbourhood`, `house_number`, `cross_street`, `exact_spot`, `what_happened`, `people`, `danger`, `floor`, `name`, `final_readback`) and says that answer, once. Read-backs get "Ναι, σωστά." (or `answers.yes`) unless the case gives its own (e.g. a name correction under `final_readback`). The `turns` then hold only the opening line and scripted moments (a correction, a clarification), said when no answer fits. Without `answers` the turns are said in order, as before: fixed scripts answered the wrong question whenever the agent asked a correct but different one, and the case drifted. 47 of the 56 cases use answers (the 31 older fixed scripts were converted on 2026-11-15, after a full run showed nearly all of them failing only because the caller's lines came in the wrong order); the 9 left as fixed scripts are one- and two-line calls (handoffs, a mistake call), `en-info-ferry` and `en-misheard-area-fire-tree`. No extra Gemini requests: it is a lookup, not a second model.

| Field | Check |
|---|---|
| `life_threat` | Ground truth for recall and over-triage. `null` = honestly ambiguous, left out of both. |
| `urgency` | Suggested urgency must be one of these. |
| `hazard_type` | Must match. |
| `action` | How the call must end: `end`, `handoff` or `any`. `handoff_reason` lists allowed reasons. |
| `address_contains`, `area_contains`, `caller_name` | Must appear in the report (accents and Greek/Latin spelling ignored). |
| `name_excludes` | Words that must not be part of the caller's name, e.g. `["εε"]`. |
| `first_reply_expects` | What the agent's first reply must ask for: `location`, `name` or `other`. |
| `location_asks_max` / `location_asks_min` | The agent asks for the location at most / at least this many times. |
| `hazard_subtype` | The kind within the category, e.g. `vehicle` for a car fire. |
| `animals_min` | At least this many animals at risk recorded in `animals` (never as people). |
| `street_found` | The street in the report was found in the caller's area on OpenStreetMap (`location.street_matches` not empty). For cases with a real street and an invented house number; 4 older Greek cases use the invented "Οδός Δοκιμής", which can't be found. |
| `address_not_personal` | `true` when `address_contains` is not personal data (e.g. a port gate), so the masking check ignores it. |
| `reply_contains` | `{"2": ["Τζάνει"]}`: the agent's reply to caller line 2 must contain one of these (accents and Greek/Latin spelling ignored). |
| `reply_not_contains` | The same, for words that must not appear (e.g. a wrong guess). |
| `location_confirmed` / `location_on_map` | The caller confirmed the location; the brain's map check found it. |
| `people_groups_min` | At least this many separate people entries (e.g. a person under a tree and voices in a building). |
| `people_injured_max` | At most this many injured in total: injuries the caller never mentioned must not be invented. |
| `people_dead_min` | At least this many deaths in the report's people. |
| `people_at_least` | Whether a people group must be marked `at_least` (the caller can't know the full number). |
| `handoff_mode` | `surge` (default) or `normal`: the dashboard's surge switch, fixed per case so the live switch can't change results. |
| `advice_required` / `advice_forbidden` | Advice topics that must / must not have been read out (from the report's `advice_given`). |
| `trigger` | Optional: starts the case as a failed-112-call follow-up. |
| (automatic) `no_pii_to_model` | The caller's name and street never appeared in anything sent to Gemini. |

The caller is scripted, not adaptive: if the agent asks in a different order, the next scripted line may answer a different question. Keep each line self-contained ("We are three: me, my mother and my son").

## Adding a case

Add an object to the right file with a new `id`, then run just that case with `--case <id>`. Good cases to add: real call transcripts (anonymised) from past disasters, people who are confused or panicking, mixed languages in one call, and calls about the same building from different people.
