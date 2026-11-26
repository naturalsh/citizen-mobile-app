# 01 Call input and scaling

**Summary.** Each call is short and independent, so the call-handling side scales by adding more identical workers. It never needs sharding. Only stored data might, and at the size of Greece it probably does not. Because this system is for natural disasters, the hard problem is the **sudden surge**: thousands of calls within hours. Size for the peak, scale up before it when a warning is issued, and know what happens when even that is not enough ([Handoff to a human](#handoff-to-a-human)).

## How calls reach the agent

After Chaos describes three ways to route calls to the AI. They change what the load balancer has to do:

| Proposition | Calls the AI gets | Load on the agent |
|---|---|---|
| **A. 112 overflow** | Only calls that would wait once the human queue passes a threshold. | Zero most of the time, then a sudden spike. Needs the warm pool and fast scale-up below. |
| **B. Separate disaster line** | Calls to a dedicated number during exercises and pilots. | Predictable, small. Easiest to build and demo. |
| **C. AI answers every 112 call first** | All calls during the disaster. | Highest and steadiest. The agent must never be the bottleneck, because there is no human path in front of it. |

For the hackathon demo, B (or a simulated A) needs only stages 1 and 2 below. The legal side of A vs. C is in [05](05_Urgency_and_EU_AI_Act.md#propositions-a-b-and-c).

## Disaster surges

- Storm Daniel in Greece (September 2023) reportedly produced over 10,000 emergency calls and more than 3,500 rescue operations. That is a headline figure we could not break down by hour, so **not verified** in detail.
- After the April 2025 Istanbul earthquake, Turkish 112 received 16,712 calls, of which 995 were urgent requests for help (Interior Minister, via Daily Sabah). An earlier count in the same report was about 6,100, mostly people asking for information.
- Surges are sudden but often predictable a few hours ahead: fire-risk maps, weather warnings, and the moment 112 sends an alert message to phones in an area. Use these as signals to grow the warm pool **before** the calls arrive. Idea, **not tested**.
- Commercial products for US 911 already sell this pattern: AI answers overflow calls, groups calls about the same event and hands urgent ones to a human. These are vendor descriptions, not independent evaluations.
- Phone networks themselves may be damaged or overloaded in a disaster. That is outside our control but means calls may drop mid-conversation. Save the partial report as the call goes so nothing is lost.

## Call input

- Phone calls arrive as 8 kHz audio, which is much lower quality than a microphone recording. Everything downstream (cleanup, STT, phasal matching) has to be tested on this kind of audio, not on clean recordings.
- A common open-source setup is **LiveKit** (real-time audio framework with a SIP bridge) plus a SIP trunk from a phone provider.
- One self-hosted LiveKit user reported calls failing beyond about 14 at once until they enabled a network setting called ICE-lite. This is a single forum report, but it shows that SIP networking is a likely place for problems.
- Greece's 112 already receives the caller's location through **AML** on Android phones. We should take this as a separate input next to the audio (see the diagram).

## Load balancer and spawning agents

How LiveKit does it (from its docs):

- The server hands each new call to an available worker, round-robin. If a worker does not accept within a timeout, the call goes to another worker.
- Each worker reports its own load. By default a worker stops taking new calls above 70% CPU.
- Each call runs in its own process. When we deploy an update, workers finish their active calls before shutting down.
- LiveKit does **not** add new servers by itself. Kubernetes or LiveKit Cloud does that.

What this means for "Spawn new agent/process":

- Starting a new server takes too long for someone waiting on an emergency line. Keep a **warm pool** of spare workers running at all times and add more in the background when the spare count drops. So in the diagram, "Spawn new agent/process" means handing the call to a spare worker that is already running.
- "While bottlenecked" means the busy workers are full but the warm pool still has spares. "No capacity left" means the warm pool is empty too.
- If no worker is free, the call goes to a **human 112 operator**.
- One competitor claims LiveKit dispatch gets slow under load (p90 of 245 s at 50 users). This is a competitor quoting a forum post, so **not verified**, but it is a reason to load-test dispatch early.

## Handoff to a human

The diagram sends a call to a human operator in four cases: no capacity, unsupported language, low confidence, or the caller is not understood. In every case:

- The call joins the normal 112 operator queue, the same as if the AI did not exist. If operators are also busy, the existing 112 queue rules apply. The AI should never make this worse.
- In a disaster the operator queue will often be long. The report collected so far should carry its suggested urgency, so operators can pick the most urgent waiting calls first rather than strictly in order.
- The operator receives what the AI has so far: the partial report ([06](06_Report_Structure.md)) and the transcript up to that point, so the caller does not have to start over.
- The AI tells the caller in their language that they are being connected to a person.

## From basic to load balanced to sharded

| Stage | What it looks like | When we need it |
|---|---|---|
| 1. Basic | One worker on one machine. | Hackathon demo. |
| 2. Load balanced | Several workers behind LiveKit's built-in dispatch. Call state lives in a shared store such as Redis, so any worker can look up any call. | More than one call at once. |
| 3. Autoscaled | Kubernetes keeps a warm pool, grows it when a disaster warning is issued, and adds workers as load rises. | Any real deployment, since disasters are the whole use case. |
| 4. Sharded data | The database is split by region or by time. | Only if one database can no longer keep up. |

**Is sharding possible here?** Yes, but probably not needed.

- Calls have no shared state with each other, so workers need no sharding. They are already independent.
- Stored data (reports, transcripts) splits naturally by country, by region or by month. Postgres (with PostGIS, already in the After Chaos stack) can do this with partitioning inside one database, which is much simpler than sharding across several.
- Our judgment, **not verified**: even disaster-peak call volume fits in one well-sized Postgres per country with partitioning. We did not find hourly call-volume figures to confirm this.
- Greece and Türkiye will almost certainly need **separate deployments**, because each country's law controls where its call data is stored and who may receive it (see [07](07_Privacy_and_Encryption.md#türkiye-kvkk)). That is a split by country for legal reasons, not for performance.

## Language choice for the backend

The After Chaos plan debates Python vs. Rust or Java. For the voice agent specifically, the main open-source voice frameworks (LiveKit Agents, Pipecat) are Python-first, and most STT, TTS and noise-removal libraries ship Python clients. So the voice agent is practically Python. The incident backend could still be a different language if the team decides so, talking to the agent over an API.

## Open questions

- What is the peak number of calls at once that we design for? We need hourly figures from Greek and Turkish 112 for past disasters such as Storm Daniel, the 2023 Kahramanmaraş earthquakes or the 2020 Samos–İzmir earthquake.
- With Proposition A, what queue length or wait time triggers the overflow to the AI?
- Do we self-host LiveKit or use LiveKit Cloud? Self-hosting keeps data under our control but means we run the scaling ourselves.

## Sources

- [LiveKit: custom deployment](https://docs.livekit.io/agents/ops/deployment/custom/)
- [LiveKit: agent server overview](https://docs.livekit.io/agents/server.md)
- [LiveKit community: single-server SIP tuning](https://community.livekit.io/t/looking-for-tuning-recommendations-for-single-server-self-hosted-lk-for-sip-inbound/1709)
- [SignalWire: calls are not jobs](https://signalwire.com/c/calls-are-not-jobs) (competitor)
- [Vision Agents: horizontal scaling with Redis](https://visionagents.ai/guides/horizontal-scaling)
- [Greek Civil Protection: 112](https://civilprotection.gov.gr/en/node/72639)
- [Daily Sabah: Istanbul earthquake response, 112 call figures](https://www.dailysabah.com/turkiye/istanbul/officials-provide-updates-on-istanbuls-earthquake-response/amp)
- [CTIF: Storm Daniel 2023 operation](https://ctif.org/news/storm-daniel-2023-largest-inter-agency-operation-ever-greece-over-3500-rescue-operations-and)
- [Patent: call overload handling for a PSAP](https://patents.justia.com/patent/11388625)
- [Knogin: AI triage surge handling](https://knogin.com/en/developers/ai-triage-system) (vendor)
