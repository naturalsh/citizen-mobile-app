# 09 Location questioning

**Summary.** Human call-takers don't move on until they have an address a crew can find: street and house number, plus the apartment or floor in a building. When there is no number, they ask for the nearest corner or cross street, then landmarks and signs. They read the address back, and when several places match they check which one. For "what happened" they ask an open question and clarify unclear answers instead of assuming. In a test call on 2026-10-24 our agent did none of this: it accepted "Athens, Orlof" (no number; Orlof Street is in two neighbourhoods of Athens), read it back after one question, and treated a misheard «Φωτιά;» ("Fire?") as a wildfire.

## What call-takers do

- **The full address first, always read back.** One police department's policy: the address is repeated back to the caller every time, even when it matches the phone system's record ([Mesquite PD](https://apps.cityofmesquite.com/police_web/go/docs/219.pdf)). Lithuania's 112 asks for the town, street, house number, apartment number and the stairwell code ([112.lt](https://112.lt/en/calling-number-112/call-takers-questions/)).
- **What a full address includes.** Maine's call-transfer template lists house number, apartment number, business name, intersection, landmarks and GPS ([Maine 911](https://www.maine.gov/maine911/sites/maine.gov.maine911/files/inline-files/CALLXFERTEMPLATE_FINAL_20220524.docx)). NENA's "dispatchable location" includes the suite, apartment or floor ([NENA knowledge base](https://kb.nena.org/wiki/Location?oldid=3569)).
- **No address: corner, then landmarks.** Call-takers ask for the street, the closest intersection and nearby landmarks, and are told that cross-street checks are critical when several matches are possible ([Anchorage PD](https://public.powerdms.com/ANDPD/documents/1664371)). Public advice says the same: landmarks, cross streets, signs, large buildings ([NJ 911](https://www.nj.gov/911/home/where.html), [Prince William County](https://pwcva.gov/department/public-safety-communications/general-questions)).
- **Don't lead the caller.** EMD guidance for transferred calls says not to ask "Is your address X?": the caller gives the address ([Santa Barbara Sheriff](https://www.sbsheriff.org/wp-content/uploads/2019/11/EMD-Transferred-Calls.pdf)). Our map check's "Do you mean X?" is the exception, used only when the name heard isn't a real place.
- **What happened comes first in the caller's mind.** In conversation analysis of emergency calls, the caller's first turn is where they give the reason for the call, often as a full story (Zimmerman 1992; [Raymond & Zimmerman 2007](https://blog.linguisten.de/post/176008021505/raymond-and-zimmerman-2007-research-on-language)). In one ambulance study, in half of the call openings the caller tried to give the reason during the call-taker's first scripted questions ([UWE](https://uwe-repository.worktribe.com/index.php/output/12112588/a-conversation-analytical-study-of-call-openings-in-emergency-medical-service-calls-where-the-patient-is-at-imminent-risk-of-out-of-hospital-cardiac-arrest)), and callers who pre-empt a location-first protocol cause friction ([Monash](https://research.monash.edu/en/publications/hijacking-the-dispatch-protocol-when-callers-pre-empt-their-reaso/)). Many services still take the location first, so it is known if the line drops ([SECAmb](https://www.secamb.nhs.uk/wp-content/uploads/2026/05/EOC-Call-Handling-Procedure-website-ready.docx), [San Jose PD](https://www2.sjpd.org/records/pc-13650_library/Other%20Training%20Materials/Communications/Call%20Taking%20Procedures%20Lesson%20Plan.pdf)); UK ambulance services now ask the nature of the call at the start. There is no single standard.
- **What happened: open, then clarify.** Ask "What happened?"; if the answer doesn't allow a chief complaint to be chosen, clarify it ([Germantown EMD](https://germantown-tn.gov/home/showpublisheddocument/9995/636142025228870000)).
- **How often it goes wrong.** In 1,830 UK ambulance calls, 26% had a communication problem that could delay dispatch, most often the caller's emotional state ([BMJ 2001](https://www.bmj.com/content/323/7316/781.full.pdf)). No study found measures how often callers can't give their address.

## What the agent does now

- **What happened first, then where** (since 2026-10-26). The greeting asks "Tell me what happened, and where.", so the caller tells it in their own order, and the location comes right after, before people and names, so a dropped call still has it early (we also have the phone number to call or text back).
- **The code picks the next question** (`brain/steps.py`; for the whole call since 2026-10-26, not only the location), in this order: what happened, area, street (or a named landmark), which neighbourhood when the map finds the street in several, house number, and the nearest corner when there is no number. A note on the caller's message tells the model which one to ask. Prompt rules alone didn't hold: the model read the location back after one question.
- **It keeps asking.** Each piece is asked up to twice, the second time with help ("a street sign, the number on a door"). A clear "I don't know" skips it at once. At most 8 location questions per call, then the read-back, as before.
- **A street without a number is searched on the map** (`places.the_street`), so the agent can ask "Orlof Street in Koukaki or in Glyfada?".
- **A misheard place or street is caught in three layers** (test call 2026-10-26: Παιανία heard as "Πυρανία", "Βασιλίσσης Φρειδερίκης …" as "Σφαιρική …"): an unknown area is compared by sound with every town and village of Greece and Türkiye (GeoNames) near the city named, and the agent asks "Did you mean Παιανία?"; once the area is known, its real streets are added to the speech-to-text hints mid-call; and when the street still isn't on the map with nothing close, the agent asks the caller to spell it, letter by letter, once (`spell_street`). Spelling is what call-takers do with a name they can't place; how speech-to-text writes spelled letters is not yet tested on a live call.
- **Unclear answers are confirmed.** A one-word answer, or one heard as a question, gets "Did you say fire? What is burning?", and no advice until it is clear (`_unclear`).
- **In a building it asks the floor** and whether everyone can get out (prompt). A fire in a building is `building_fire`, not `wildfire`.

## Open questions

- The floor is asked in the prompt only, not tracked by the code. Apartment numbers and door codes (Lithuania asks for them) are not asked.
- The NENA call-processing standard (NENA-STA-020.2-2026) wasn't readable as text here, so its exact location rules aren't checked.

## Sources

- Mesquite PD, communications general order: https://apps.cityofmesquite.com/police_web/go/docs/219.pdf
- 112 Lithuania, call-taker's questions: https://112.lt/en/calling-number-112/call-takers-questions/
- Maine 911 call-transfer template: https://www.maine.gov/maine911/sites/maine.gov.maine911/files/inline-files/CALLXFERTEMPLATE_FINAL_20220524.docx
- NENA knowledge base, Location: https://kb.nena.org/wiki/Location?oldid=3569
- Anchorage PD dispatch policy: https://public.powerdms.com/ANDPD/documents/1664371
- NJ 911, Where is the emergency?: https://www.nj.gov/911/home/where.html
- Prince William County 911, general questions: https://pwcva.gov/department/public-safety-communications/general-questions
- Santa Barbara Sheriff, EMD transferred calls: https://www.sbsheriff.org/wp-content/uploads/2019/11/EMD-Transferred-Calls.pdf
- Germantown TN, emergency medical dispatch procedure: https://germantown-tn.gov/home/showpublisheddocument/9995/636142025228870000
- Bradley et al., communication problems in ambulance calls, BMJ 2001: https://www.bmj.com/content/323/7316/781.full.pdf
- Raymond & Zimmerman 2007, summary: https://blog.linguisten.de/post/176008021505/raymond-and-zimmerman-2007-research-on-language
- Call openings in ambulance calls at risk of cardiac arrest (UWE): https://uwe-repository.worktribe.com/index.php/output/12112588/a-conversation-analytical-study-of-call-openings-in-emergency-medical-service-calls-where-the-patient-is-at-imminent-risk-of-out-of-hospital-cardiac-arrest
- Callers pre-empting the dispatch protocol (Monash): https://research.monash.edu/en/publications/hijacking-the-dispatch-protocol-when-callers-pre-empt-their-reaso/
- SECAmb call handling procedure: https://www.secamb.nhs.uk/wp-content/uploads/2026/05/EOC-Call-Handling-Procedure-website-ready.docx
- San Jose PD call-taking lesson plan: https://www2.sjpd.org/records/pc-13650_library/Other%20Training%20Materials/Communications/Call%20Taking%20Procedures%20Lesson%20Plan.pdf
