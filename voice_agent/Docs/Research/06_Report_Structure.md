# 06 Report structure

**Summary.** There is an existing standard for emergency incident data called **EIDO**, a JSON format from NENA (the US emergency-number association). We should not implement all of it for a hackathon, but we should reuse its shape so a real system could map to it later. Its most useful idea for disasters is that one **incident** links many **calls**: a hundred people reporting the same fire become one incident with a hundred calls, not a hundred incidents.

## What EIDO is

- A JSON object for sharing one incident between call handling, dispatch systems and responders.
- One EIDO describes **one incident**, which can link to several calls, several responding units and several people.
- Main contents: incident ID, linked calls, location, incident type, notes, responding units, status.
- A related NENA concept, **IDX**, covers linking several EIDOs that describe the same real-world event.
- The European emergency-number association (EENA) has a paper on data exchange between European call centres and emergency services.
- The current EIDO document number is **not verified**. Sources cite NENA-STA-021 and NENA-STA-024 for it. Check NENA's standards page before quoting either.

## Our simplified report

One report per call. Each report points to an event, which groups the calls about the same fire, flood or collapse. The fields follow the After Chaos call script:

| Script question | Report fields |
|---|---|
| Where are you? | `location` |
| What happened? | `hazard_type`, `situation` |
| How many people are affected? | `people` |
| Is anyone injured or in immediate danger? | `people`, `urgency` |

The agent reads the key facts back to the caller before ending the call, and records the result in `confirmed_with_caller`.

```json
{
  "call_id": "call-8f2a",
  "event_id": "evt-fire-0007",
  "created_at": "2026-08-12T14:03:22Z",
  "updated_at": "2026-08-12T14:04:10Z",
  "status": "in_progress",
  "caller_language": "el",
  "caller": { "name": "Maria P.", "phone": "+30 69...", "relation": "resident" },
  "location": {
    "aml": { "lat": 40.8457, "lon": 25.8744, "accuracy_m": 15 },
    "spoken_address": "Road out of Dadia village, near the bridge",
    "confirmed_with_caller": true
  },
  "hazard_type": "wildfire",
  "situation": "Fire about 200 m from the house, smoke inside. Road out may be blocked.",
  "people": [
    { "count": 3, "trapped": true, "injured": 0, "cannot_walk": 1, "note": "elderly mother uses a wheelchair" }
  ],
  "urgency": {
    "suggested": "life_threat",
    "confidence": 0.82,
    "reasons": ["fire within 200 m", "person who cannot walk", "matched 'εγκλωβισμένοι' (trapped)"],
    "confirmed_by_operator": null
  },
  "new_event_suggested": false,
  "summary_for_operator": "Three people trapped near Dadia bridge, fire 200 m away, one in a wheelchair.",
  "transcript_ref": "transcripts/call-8f2a",
  "source": "voice_agent",
  "observed_at": "2026-08-12T14:03:40Z"
}
```

Allowed values (placeholders until we match what Greek 112 uses):

| Field | Values |
|---|---|
| `status` | `in_progress`, `complete`, `handed_to_human`, `dropped` |
| `hazard_type` | a category: `earthquake`, `fire`, `flood`, `storm`, `landslide`, `other` (since 2026-10-26; before, `wildfire` and `building_fire` were types of their own) |
| `hazard_subtype` | the kind within the category, e.g. fire: `wildfire`, `building`, `vehicle`, `other` (`brain/report.py` HAZARD_SUBTYPES) |
| `animals` | animals at risk: `kind`, `count`, `trapped`, `injured`, `note`; never counted as people |
| `urgency.suggested` | `life_threat`, `urgent`, `needs_help`, `information` |

Design choices:

- **`urgency.reasons`** is required. Operators must see *why* the AI suggests a level (see [05](05_Urgency_and_EU_AI_Act.md)).
- **`confirmed_by_operator`** stays empty until a human confirms. The AI never fills it, for any urgency level.
- **`location`** keeps the AML position and the spoken address separately. They can disagree, and the operator should see both.
- **`caller`** holds the name and phone number. Operators need them to call back if the line drops, which is common in disasters.
- **`summary_for_operator`** is in the operator's language (Greek for Greek 112, Turkish for Turkish 112), whatever language the caller spoke.
- **`source`** and **`observed_at`** let the After Chaos incident map show where each piece of information came from and how old it is, next to drone, beacon and field reports.
- **`updated_at`** exists because urgent reports are sent **during** the call and updated as new details come in.
- **`status: handed_to_human`** and **`dropped`**: the partial report is still sent, so the operator who picks up the call, or calls back, does not start from nothing.
- The transcript is stored separately and linked, so the report stays short.

## Grouping calls about the same event

This is the "Group calls about the same event" node in the diagram. In After Chaos the final merge happens in the incident backend, where calls are combined with drone, beacon and field reports and operators can merge, split or dismiss incidents. The voice agent only *suggests* which event a call belongs to.

- In a disaster, many people call about the same fire or flood. Telling repeat calls apart from new ones prevents duplicate dispatches and lets operators focus on new or worsening situations. UK fire service guidance makes the same point, and several call-centre patents describe ways to do it.
- A simple first version: a call is suggested as part of an existing event if its location is within a set distance of that event's calls and it arrives within a set time window, and the hazard type matches.
- **Repeat calls still matter.** A repeat call can report something new, such as people now trapped. Every call keeps its own report and urgency. Grouping only helps operators see the picture. It never hides a call.
- `new_event_suggested: true` flags a call that does not fit any known event. These deserve fast attention, as they may be a new fire front.

## Routing

- **To 112 personnel**: the full report, including caller name, phone and address.
- **To the After Chaos incident map**: the report as a timestamped event, with its source, confidence and age, for the incident backend and resource allocation.
- **To the prediction core and training data**: only after the [PHI stripper](07_Privacy_and_Encryption.md). Location is reduced to the municipality, plus the time of the call, so the prediction core can still see where calls cluster and how that moves over time.

## Open questions

- What format do the Greek and Turkish 112 systems accept? Greece contracted a €17.5 million next-generation 112 system in December 2024. Its data format would decide what we export.
- What distance and time window should group calls into one event? It differs for a fast wildfire and a slow flood. Test on past events if data is available.

## Sources

- [NENA: EIDO](https://kb.nena.org/wiki/EIDO_(Emergency_Incident_Data_Object))
- [NENA: EIDO standard announcement](https://www.nena.org/news/584569/NENA-Releases-ANSI-Approved-Emergency-Incident-Data-Object-EIDO-Standard.htm)
- [NENA: EIDO and IDX FAQ](https://kb.nena.org/wiki/EIDO_%26_IDX_FAQ_(Frequently_Asked_Questions)?oldid=3588)
- [EENA: PSAPs and emergency services data exchange](https://eena.org/wp-content/uploads/2024_01_17_PSAPs-and-EROs-data-Exchange-PDF.pdf)
- [Study guide: NG9-1-1 and EIDO](https://open-exam-prep.com/study-guides/nena-enp/ng911-location-routing/ng911-psap-eido-adr-transitional-elements)
- [NFCC: identify repeat calls during periods of multiple calls](https://nfcc.org.uk/?p=18062)
- [Patent: duplicate call handling at a PSAP (EP 4066479)](https://data.epo.org/gpi/EP4066479B1)
- [Patent: merging multiple emergency calls](https://patents.justia.com/patent/9420099)
- [Protothema: Greek 112 upgrade](https://origin01-en.protothema.gr/2024/12/18/kikilias-112-is-upgraded-advanced-geolocation-system-and-silent-button-for-emergency-situations)
