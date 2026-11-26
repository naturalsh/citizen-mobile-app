# Research

Findings for the open questions in [Voice_Agent_Flow.md](../Voice_Agent_Flow.md). Each doc covers one part of the diagram, starts with a short summary, and ends with open questions and sources.

**Scope.** The voice agent is the overflow intake of **After Chaos** (Team Euclides Minds, Greece–Türkiye Hackathon 2026), part of its "Listen" step. It is for **natural disasters**: earthquakes, wildfires, floods and storms. In those events call volume jumps far beyond what operators can answer, and many callers report the same event:

- Storm Daniel in Greece (2023) reportedly brought over 10,000 emergency calls.
- After the April 2025 Istanbul earthquake, Turkish 112 received 16,712 calls, of which 995 were urgent requests for help.

When human operators are full, the agent answers callers who would otherwise wait on hold. It says it is automated, asks a short set of questions (where, what happened, how many people, anyone injured or in danger), reads the key facts back, and turns the answers into a structured report. Life-threatening calls go back to the front of the human queue. Reports also feed the After Chaos incident map, where calls are merged with drone, beacon and field data. It is not meant for everyday single-incident calls.

Both **Greece and Türkiye** are in scope; the demo replays the 2020 Samos–İzmir earthquake, which hit both. The caller's language is chosen from the phone's country code, with Greek and Turkish as the main languages and English and French as fallbacks.

| Doc | Diagram nodes | Question it answers |
|---|---|---|
| [01 Call input and scaling](01_Call_Input_and_Scaling.md) | Call input, Load Balancer, Spawn new agent, Handoff to human | How do calls get in, how do we go from one agent to many, and what happens when the AI cannot handle a call? Is sharding needed? |
| [02 Signal cleanup](02_Signal_Cleanup.md) | Signal clearing | How do we clean noisy phone audio before recognition? |
| [03 Phasal matching and keyword boosting](03_Phasal_Matching_and_Keyword_Boosting.md) | Phasal Matching and STT, Word averages db, Keyword list | How do we catch critical words reliably in Greek and Turkish? |
| [04 Speech to text and text to speech](04_STT_and_TTS.md) | Language detection, Phasal Matching and STT, Respond/ TTS | Which STT and TTS work for Greek, Turkish, English and French, and how fast is fast enough? |
| [05 Urgency and the EU AI Act](05_Urgency_and_EU_AI_Act.md) | Handle Transcript and Urgency | How do we judge urgency, and what does the law require? |
| [06 Report structure](06_Report_Structure.md) | Report/Data Structuring, Group calls about the same event, Data Routing | What goes in a report, how do we group many calls about one event, and in what format? |
| [07 Privacy and encryption](07_Privacy_and_Encryption.md) | Mask / Unmask personal details, PHI Stripper, Prediction core | What is encrypted, what is stripped, and can the agent still respond? |
| [08 Drone beacon network](08_Drone_Beacon_Network.md) | After Chaos "Listen": phone/sensor beacons | How do drones reach phones under rubble, keep a link to a working network, take turns on batteries, and cover several sites? |
| [09 Location questioning](09_Location_Questioning.md) | Handle Transcript and Urgency | How do call-takers get an address a crew can find, and how does the agent ask for it? |
| [10 One data picture and message automations](10_Unified_Data_and_Messages.md) | Data Routing, After Chaos incident map | How do calls, drones, phones, field reports and texts become one picture on one dashboard, and which messages go out automatically? |

## Decisions still open

The research narrows the options but does not pick them. These need a team decision, mostly after our own test set exists ([04](04_STT_and_TTS.md#our-own-test-set)):

- STT and TTS provider for each language
- Self-host the models or use EU-hosted providers ([07](07_Privacy_and_Encryption.md))
- Noise remover ([02](02_Signal_Cleanup.md))
- Phasal matching method: MFCC with DTW, or neural word embeddings ([03](03_Phasal_Matching_and_Keyword_Boosting.md))
- Urgency scale, matched to what Greek and Turkish 112 operators use ([05](05_Urgency_and_EU_AI_Act.md))
- Which overflow proposition to build: A (overflow threshold), B (separate disaster line) or C (AI answers every call first) ([01](01_Call_Input_and_Scaling.md#how-calls-reach-the-agent), [05](05_Urgency_and_EU_AI_Act.md#propositions-a-b-and-c))
- What the prediction core predicts ([07](07_Privacy_and_Encryption.md))
- Drone beacon design: landed beacon, satellite or relay chain, which operator to partner with ([08](08_Drone_Beacon_Network.md#ideas-and-decisions))

## How to read the evidence

- **Vendor claim**: a number published by the company selling the product. Useful as a hint, not as proof.
- **Not verified**: we found the claim but could not confirm it from a primary source.
- Almost no published benchmark uses Greek or Turkish *phone* audio. The single most useful next step for the whole project is to record our own small test set (see [04](04_STT_and_TTS.md#our-own-test-set)).

## Glossary

| Term | Meaning |
|---|---|
| AML | Advanced Mobile Location. The phone sends its GPS location automatically when someone calls 112. |
| Backhaul | The link that carries a cell's traffic to the rest of the network. For the drone beacon: the relay chain or a satellite link. |
| BLE | Bluetooth Low Energy. Short-range, low-power radio in every phone. |
| Common Voice, FLEURS | Public sets of recorded speech used to train and test STT. Mostly people reading sentences aloud, so easier than real calls. |
| dB (decibel) | How many times weaker or stronger a signal is: every 10 dB is a factor of 10, so 30 dB is 1,000 times weaker. |
| DPIA | Data protection impact assessment. A written risk review GDPR requires before high-risk processing. |
| DTW | Dynamic Time Warping. Lines up two recordings of the same word spoken at different speeds so they can be compared. |
| EIDO | Emergency Incident Data Object. A JSON standard for sharing incident data between emergency systems. |
| IMSI / IMEI | The ID numbers of a SIM card and of a phone. Personal data. |
| Kubernetes | Software that runs and scales many copies of a service across servers. |
| Master prompt | The fixed instructions given to the language model at the start of every call. |
| MFCC | Mel-frequency cepstral coefficients. The standard way to turn audio into numbers that describe how it sounds. |
| NER | Named entity recognition. A model that finds names, places and similar items in text. Used to find personal details to mask. |
| p90 | 90th percentile. 90% of cases are at or below this value. |
| Partitioning | Splitting one database table into parts (for example by month) inside the same database. Simpler than sharding, which splits data across several databases. |
| Phasal matching | Our term for comparing the caller's audio to a database of averaged recordings of known words. In research this is called template matching or keyword spotting. See [03](03_Phasal_Matching_and_Keyword_Boosting.md). |
| PHI / PII | Protected health information / personally identifiable information. Names, addresses, phone numbers, medical details. |
| Prediction core | The part of the system that learns from calls. One likely use: showing where a fire or flood is spreading from where and when calls come in. Exact scope not defined yet. |
| PSAP | Public Safety Answering Point. The call centre that answers 112. |
| Redis | A fast in-memory database, often used to share short-lived state between servers. |
| Round-robin | Handing out work to each server in turn. |
| SIP | The protocol that carries phone calls over the internet. |
| Small cell | A cell tower in a box, small enough to carry on a large drone. |
| STT / TTS | Speech to text / text to speech. |
| TLS | The standard encryption for data sent over a network (the "s" in https). |
| VAD | Voice activity detection. Decides when someone is speaking and when they have stopped. |
| WER | Word error rate. The share of words the STT gets wrong. Lower is better. |
| Worker | A server process running our agent code. One worker handles several calls at once, each call in its own sub-process. |
