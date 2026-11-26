# Advice texts: sources and decisions

The agent never writes safety advice itself. It picks one of the topics below, and the brain reads out the fixed text from `brain/advice/*.json`. This page says where each text comes from, what was decided where sources disagree, and what is still unverified.

Researched on 2026-10-21 from official Greek and Turkish pages first, then EU and international ones where those are silent. The texts are paraphrased, not copied.

**Before a real deployment:** a Civil Protection / AFAD contact should sign off every text, and native speakers should read the Greek and Turkish aloud.

## Source key

| Key | Source | Country |
|---|---|---|
| GSCP | General Secretariat for Civil Protection, self-protection guides: civilprotection.gov.gr/odigies-prostasias/{seismoi, dasikes-pyrkagies, plimmyres, kataigides, thyellodeis-anemoi}, and the tsunami leaflet on the same site | 🇬🇷 |
| OASP | Earthquake Planning and Protection Organization: https://oasp.gr/odigies-aytoprostasias, https://oasp.gr/faqs | 🇬🇷 |
| EKAB | Ministry of Health / EKAB booklet «Μαθαίνω Πρώτες Βοήθειες – Είμαι ασφαλής» (moh.gov.gr) | 🇬🇷 |
| AFAD-1 | AFAD «Deprem Anında Neler Yapmalısınız?» https://www.afad.gov.tr/deprem-aninda-neler-yapmalisiniz | 🇹🇷 |
| AFAD-2 | AFAD «Deprem Öncesi, Anı ve Sonrası» https://www.afad.gov.tr/deprem-oncesi-ani-ve-sonrasi-onlemini-al-guvende-kal | 🇹🇷 |
| AFAD-3 | İstanbul AFAD «Deprem sonrası ilk 6 saat» https://istanbul.afad.gov.tr/deprem-sonrasi-ilk-6-saate-dikkat---basin-bulteni | 🇹🇷 |
| AFAD-4 | AFAD Afet Farkındalık Eğitimi deck (2022), https://samsun.afad.gov.tr/kurumlar/samsun.afad/E-Kutuphane/Afet-Farkindalik-Egitimi/Afet-Farkindalik-Egitimi-Sunumu.pdf | 🇹🇷 |
| AFAD-5 | AFAD flood page https://www.afad.gov.tr/sel-oncesi-ani-ve-sonrasi-tedbirli-olun-guvende-kalin | 🇹🇷 |
| AFAD-6 | AFAD fire page https://www.afad.gov.tr/yanginlara-karsi-alinmasi-gereken-onlemler | 🇹🇷 |
| HFS | Hellenic Fire Service leaflet «Πρόληψη – Αντιμετώπιση Πυρκαγιών» (2009; Greek and English pages), from https://www.fireservice.gr/el_GR/phylladia | 🇬🇷 |
| KIZ-1 | Türk Kızılay «Afetler ve Korunma Bilinci» brochure (kizilayakademi.org.tr) | 🇹🇷 |
| KIZ-2 | Türk Kızılay «Yetişkinler İçin İlk Yardım» https://www.ilkyardim.org.tr/yetiskinler-icin-ilk-yardim.html (all rights reserved: paraphrase only) | 🇹🇷 |
| HARM | Harmancık district governorship storm notice https://www.harmancik.gov.tr/kuvvetli-ruzgar-ve-firtinaya-dikkat (AFAD-style wording, not found on afad.gov.tr) | 🇹🇷 |
| READY | ready.gov: /earthquakes, /wildfires, /floods, /home-fires | 🇺🇸 |
| CFA | Country Fire Authority, Victoria: cfa.vic.gov.au "Staying safe in the car", "Caught in the open" | 🇦🇺 |
| WHO-EU | WHO Europe wildfire smoke Q&A (2023) | 🌍 |
| FEMA | FEMA "Until Help Arrives" (five steps) | 🇺🇸 |
| USFA | US Fire Administration sheet "Apartment fire safety begins with a plan" https://www.usfa.fema.gov/downloads/fief/apartment_fire_safety.pdf | 🇺🇸 |
| LFB-1 | London Fire Brigade, escape plan for houses and converted flats https://www.london-fire.gov.uk/safety/the-home/escape-plan/escape-plan-houses-and-converted-flats/ | 🇬🇧 |
| LFB-2 | London Fire Brigade, escape plan for blocks of flats https://www.london-fire.gov.uk/safety/the-home/escape-plan/escape-plan-blocks-of-flats/ | 🇬🇧 |
| NHS | NHS "Burns and scalds" https://www.nhs.uk/conditions/burns-and-scalds/ | 🇬🇧 |

## Topics

### Earthquake (`earthquake.json`)

| Topic | When | Built from | Notes |
|---|---|---|---|
| `during_shaking` | Shaking now, indoors | GSCP, OASP, AFAD-1, AFAD-4, KIZ-1 | Drop, Cover, Hold On («Σκύψε, καλύψου, κρατήσου» / «Çök, Kapan, Tutun»). No balcony, stay inside until it stops. |
| `outdoors_or_car` | Shaking now, outdoors or driving | GSCP, OASP, AFAD-1, AFAD-2, READY | Away from buildings, power lines and slopes; driver stops in the open and stays in the car. |
| `trapped` | Caller trapped | AFAD-1, READY | No Greek source covers this. AFAD-1 matches: no matches or lighters, don't stir up dust, cover mouth, tap on pipes, shout last. |
| `others_trapped` | Someone else trapped, caller outside | READY, AFAD-2/3, KIZ-2 | "Don't enter damaged buildings" (READY); "make sure you are safe first" (AFAD); rescue by professional teams (KIZ-2). Telling the caller to keep talking and point rescuers to the voices is our addition: not in any source. |
| `after_shaking` | Shaking stopped and the caller is inside a building, or smells gas inside | GSCP, OASP, AFAD-2, AFAD-3 | Stairs, not lift; gas off; open area; aftershocks; don't re-enter. If gas is smelled, no flame or switch (AFAD-3). Condition narrowed on 2026-10-22 from "inside or near": a test caller standing in the street was told to leave the building by the stairs. Text unchanged. |
| `tsunami` | Near the sea after a strong quake | GSCP tsunami leaflet, AFAD-2, AFAD-4 | Inland or uphill now, don't wait for a warning (AFAD), don't watch, stay away until authorities say it's safe. |

### Wildfire (`wildfire.json`)

| Topic | When | Built from | Notes |
|---|---|---|---|
| `approaching` | Fire coming, can still leave | GSCP, READY, KIZ-1 | Leave now if safe, away from the fire, follow the authorities' route; close up and gas off; don't return until told. |
| `shelter_in_house` | Can't leave, inside a building | GSCP | Stay in unless escape is fully secured; close up, wet towels in gaps, away from windows, fill bath, one room. No Turkish official text found. |
| `trapped_in_car` | In a car, fire around | CFA | **No Greek or Turkish source.** GSCP only says not to *choose* a car as shelter. Engine off with vents shut follows CFA; some unofficial US advice says keep the engine running: not used. |
| `trapped_outdoors` | On foot, fire near | CFA | **No Greek or Turkish source.** CFA notes survival chances in the open are very low. |
| `smoke` | Smoke, fire not here | GSCP, WHO-EU, KIZ-1, AFAD-6 | Stay in, seal gaps; wet cloth over mouth and nose and stay low (Turkish sources); FFP2 if going out (WHO). |

### Building fire (`building_fire.json`)

Fire in a house, flat or apartment block, as opposed to a wildfire. All four texts are **DRAFT**, researched on 2026-10-24, not yet reviewed by the owner, a fire service contact or native speakers. The Greek Civil Protection guides (GSCP) have no building-fire topic, so the Greek source is the Hellenic Fire Service leaflet (HFS).

| Topic | When | Built from | Notes |
|---|---|---|---|
| `get_out` | Fire or smoke in the caller's building, way out not reported blocked | HFS, AFAD-6, LFB-1, LFB-2, USFA, READY | Get out at once and warn others (HFS: help children and the elderly); no belongings (HFS English page, LFB-1); check a door with the back of the hand, hot means another way (HFS, LFB-1, LFB-2, USFA, READY); stairs, never the lift (HFS, LFB-2, USFA); close doors behind you (HFS, LFB-1, LFB-2); stay low under smoke (all); never go back in (HFS «για κανένα λόγο μη γυρίσετε πίσω», LFB, USFA). Covering nose and mouth is left to `cannot_get_out` to keep this text short. |
| `cannot_get_out` | Inside, way out blocked by fire, smoke or a hot door | HFS, AFAD-6, LFB-1, LFB-2, USFA, READY | Room with a window (LFB-1), door shut (HFS: close every door between you and the fire; LFB-1, LFB-2); block gaps with towels or bedding (LFB-1, LFB-2, USFA, READY; "wet if you can" is our choice, borrowed from AFAD-6's wet cloth for breathing and from HFS's wet cloths in gaps, which is in its wildfire section); signal at the window with a light-coloured cloth or torch (HFS, USFA, READY); stay low (AFAD-6, HFS); don't hide (AFAD-6: not under beds or in cupboards). "Don't jump from an upper floor": see conflicts below. |
| `outside_building` | Building on fire, caller outside it | USFA, HFS, LFB-1, AFAD-6, READY | Move away and give fire engines space (USFA); don't go back in for any reason (USFA, LFB, HFS); don't put yourself at risk (AFAD-6); tell firefighters where anyone still inside is (USFA, HFS, READY). "Out of the smoke" is our addition, not in these pages. |
| `clothes_on_fire` | Someone's clothes on fire now | HFS, AFAD-6, LFB-1, READY, NHS | Stop, don't run, drop, cover the face with the hands, roll (HFS, AFAD-6, READY); or smother with a blanket or heavy fabric (AFAD-6, LFB-1, HFS, READY). Cool the burn 20 minutes under cool running water and don't remove anything stuck to it (NHS). See conflicts on cooling time. |

**Building-fire conflicts and decisions (DRAFT, owner to confirm):**
- **Stay put.** LFB-2 tells people in a block of flats to stay in their flat when the fire is elsewhere in the building, unless smoke or heat reaches them. HFS and AFAD-6 say get out at once and do not mention staying put. Stay put depends on fire-separated flats, which we can't assume for Greek and Turkish blocks, and the agent can't judge it. We don't use it: the caller gets out if the way is clear, and uses `cannot_get_out` if the stairs are full of smoke.
- **Fighting the fire.** AFAD-6 says use what you have to put the fire out until the fire service comes, without putting anyone at risk; HFS recommends owning extinguishers. LFB-1 says don't fight the fire. We never tell a caller to fight it: by the time someone calls 112 about it, the fire is not small.
- **Window.** HFS: open the window for fresh air but close it at once if it draws smoke in. LFB-1: open it and shout. USFA and READY: signal at the window. We say go to the window and signal, without telling them to open or close it; an operator can coach this.
- **Jumping.** LFB-1: escape through a window only from the ground or first floor, lowering yourself onto something soft rather than jumping. HFS, AFAD-6 and USFA don't mention it. We say "don't jump from an upper floor", which leaves a ground-floor window open as a way out.
- **Cooling a burn.** READY: cool water for 3 to 5 minutes. NHS: cool running water for 20 minutes. HFS only says cool it with water. We use 20 minutes (NHS).
- **Wet or dry cloth over the mouth.** AFAD-6 says wet; HFS says a towel or a piece of clothing. Wetting a cloth costs time while escaping, so `get_out` only says stay low.

**Not verified for building fire:** the İstanbul Fire Department (İBB İtfaiyesi) site and NFPA were not read; no official İBB page turned up in searches. A Turkish expert interview (CNN Türk) found in a search says keep windows closed until firefighters come; it is not an official source and was not used. The AFAD-6 page returned an error to one fetch tool but loaded with a plain download on 2026-10-24.

### Flood (`flood.json`)

| Topic | When | Built from | Notes |
|---|---|---|---|
| `water_rising_home` | Water rising at the building | GSCP, AFAD-5, AFAD-4, READY | Leave for high ground now if safe, without waiting for instructions (AFAD); otherwise highest floor, not a closed attic, roof only if needed (READY); mains off if dry. |
| `in_car` | Car in flood water | GSCP, AFAD-5, READY | **Team decision.** GSCP and AFAD say abandon a stalled car and go to high ground. READY says stay in the car if fast water surrounds it. We use both: shallow, still water → leave; fast water → stay in, roof if water enters. |
| `outdoors` | Near flood water or streams | GSCP, AFAD-5, KIZ-1, READY | Don't cross moving water on foot even if shallow (KIZ-1: ankle-deep water can sweep people away); avoid bridges over fast water, slopes and fallen cables. |

### Storm (`storm.json`)

| Topic | When | Built from | Notes |
|---|---|---|---|
| `indoors` | Storm, caller indoors | GSCP, HARM | Away from windows; don't go out to fix damage (HARM); no pipes or plugged-in devices in lightning (GSCP). "Inner room if the roof is damaged" is common international advice, not in GSCP. |
| `outdoors` | During a storm: caller outdoors, or trees or cables brought down by it | GSCP, HARM | Building or car; never under a tall tree («Μην καταφύγετε ποτέ κάτω από ένα ψηλό δέντρο»); away from lines, poles, signs, balconies; never touch fallen cables (HARM). Condition narrowed on 2026-10-22 from "…or reports fallen trees or power lines": a test call got it for a tree falling on someone during a building fire, with no storm. Text unchanged. |

### First aid (`first_aid.json`), for any hazard

| Topic | When | Built from | Notes |
|---|---|---|---|
| `bleeding` | Someone bleeding | EKAB, KIZ-2, FEMA | Direct pressure, add cloth on top, don't remove the first layer. **Left out on purpose:** tourniquets (need training) and raising the limb (KIZ-2 no longer recommends it). |
| `do_not_move` | Possible fracture, neck, back or head injury | GSCP, EKAB, KIZ-2 | Don't move unless in danger, head and neck still, limb as found, nothing to eat or drink (KIZ-2), keep warm. No splints or collars (need training). |
| `unconscious_breathing` | Unconscious but breathing | EKAB, KIZ-2 | Recovery position keeping head, neck and back in line. Turning someone with a suspected spine injury properly needs training; a human operator should coach it when possible. |

**Not breathing** is not an advice topic: the agent hands off to a human operator straight away (`handoff_reason: "not_breathing"`), because CPR must be coached by a trained dispatcher.

## Conflicts and how we resolved them

- **Triangle of life vs. Drop, Cover, Hold On.** Greek Civil Protection and OASP use only drop-cover-hold. AFAD's current page (AFAD-1) still mentions «hayat üçgeni» next to «Çök-Kapan-Tutun», but AFAD's national drills and Kızılay use only Çök-Kapan-Tutun. We use Drop, Cover, Hold On wording only.
- **Doorways.** OASP: a doorframe helps only in old stone or brick buildings, not reinforced concrete. READY: avoid doorways. We don't mention doorways.
- **Lying beside the car in a tunnel** (AFAD-1): triangle-of-life style, not used.
- **Flooded car:** see `in_car` above.
- **Gas after an earthquake.** GSCP/OASP: switch off gas before leaving. AFAD-3: turn off the electricity only if you can't smell gas. We say: gas off if you can; if you smell gas, no flame or switch.

## Still unverified

- Any official Greek or Turkish text for wildfire `trapped_in_car` and `trapped_outdoors`, and Turkish text for `shelter_in_house`.
- Official guidance on whether bystanders should try to dig people out. We tell them not to enter damaged buildings and to guide rescuers.
- Hellenic Red Cross, EU (DG ECHO) and Turkish Ministry of Health pages: not checked.
- The 2025 European Resuscitation Council guideline: could not be opened.
