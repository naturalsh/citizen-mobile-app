# Voice Agent Flow

## 1.1 Diagramm (Work in Progress)
```mermaid
flowchart TD

A[Call input, 112 overflow or disaster line] --> B{Load Balancer}
AML[/AML caller location/] --> F
AML -->|Local place names| KB
B -->|While not bottlenecked| C[Signal clearing, reconstruction to be tested]
B -->|While bottlenecked| D(Spawn new agent/process from warm pool)
B -->|No capacity left| HO[[Handoff to human 112 operator]]
D --> C
C --> LD{Language from country code, caller can switch}
LD -->|Greek, Turkish, English, French| E[Phasal Matching and STT]
LD -->|Unsupported language| HO
WDB[("Word averages db")] -->|Phasal matching| E
KB[("Keyword list, emergency terms and place names")] -->|Keyword boosting| E
E --> MK[Mask personal details]
MK --> F[Handle Transcript and Urgency]
F --> UM[Unmask personal details]
UM --> G[Respond/ TTS]
G --> Cout[/Answer to caller/]
Cout -->|Caller replies or interrupts| C
F -->|Low confidence or caller not understood| HO
UM -->|Suggested urgency, awaiting operator| H[Urgent Report/Data Structuring]
UM -->|Every call| I[Report/Data Structuring]
H -->|Streamed live during the call| DUP[Group calls about the same event]
I -->|Final report when the call ends| DUP
DUP --> J(Data Routing)
J -->|Full data| K[/Reports are sent to 112 personnel/]
J -->|Timestamped events| MAP[/After Chaos incident map/]
J --> P[PHI Stripper]
P -->|Stripped data only| L[(Prediction core and model training data)]
```

## 1.2 Required Research

Findings for each point are in [Research/](Research/README.md).

 - How do we guarantee reconstruction and phasal matching can be done in greek (and turkish), languages that models haven't really been trained on?
 - TTS / STT
 - How do we structure the reports
 - What data needs to be encrypted when it reaches agents? What needs to be stripped? How do we make sure that the agents can respond even when that happens
    - (This can be done with a PHI Stripper and a good master prompt)
    - Research: the PHI Stripper works for the training copy. For the live agent we use reversible masking (Mask / Unmask nodes), see [07](Research/07_Privacy_and_Encryption.md).
 - How does load balancing work? How do we build from basic to load balanced to sharded data? Is sharding even possible here?
