# 05 Urgency and the EU AI Act

**Summary.** Under the EU AI Act, an AI that classifies emergency calls or sets dispatch priority is **high-risk**. An AI that only transcribes calls is not. So the agent should *suggest* an urgency level with its reasons, and a human 112 operator *confirms* it. In a disaster, the agent's biggest value is sorting thousands of calls so operators reach people in danger first, and spotting which calls are new events and which repeat a known one.

## What the law says

- The EU AI Act lists, in Annex III point 5(d), AI used to **evaluate and classify emergency calls**, to **dispatch or prioritise** emergency responders, and for **emergency healthcare triage**. These are high-risk.
- **Transcription tools for emergency calls are explicitly excluded.** Transcribing is fine. Classifying is regulated.
- High-risk does not mean banned. It means obligations: risk management, data quality, logging, human oversight and accuracy testing.
- Timing: obligations for this category were due 2 August 2026. A provisional agreement (6 May 2026) reportedly moves them to **2 December 2027**. **Not verified** against the final published text.
- **Saying it is an AI is already required.** Article 50 requires that people are told they are talking to an AI, unless it is obvious. This applies from **2 August 2026** and was not delayed. The After Chaos script already opens by saying the agent is automated, which covers it.

## Türkiye

- Türkiye is not in the EU, so the AI Act does not apply to a Turkish deployment.
- As of 2026 Türkiye has no single AI law. A 2024 AI bill and a November 2025 bill amending several laws for AI are both reported as still under review. **Not verified** against the parliament's own records.
- The same design (AI suggests, human confirms, AI says it is automated) is the safe choice in both countries, and keeps one product for both.

## Propositions A, B and C

After Chaos lists three ways to route calls to the AI ([01](01_Call_Input_and_Scaling.md#how-calls-reach-the-agent)). From the research:

- **A (overflow)** and **B (separate line)** fit the law and the evidence best. The AI only talks to people who would otherwise wait, and life-threatening calls go back to the front of the human queue.
- **C (AI answers every call first)** puts every 112 caller through a high-risk AI system, including those a human could have answered immediately. If the AI misses a life threat, that caller is now worse off than without the system. It needs the strongest evidence of life-threat recall before anyone would approve it.
- The burnout point behind C is real, but it can also be served by A: the AI takes the overflow and the structured summaries shorten each human call.
- One figure that supports triage either way: after the April 2025 Istanbul earthquake, 995 of 16,712 calls to Turkish 112 (about 6%) were urgent requests for help.

## What this means for our design

Every urgency label is a classification, **including "not urgent"**. So every report, urgent or not, waits for an operator to confirm its urgency. The difference is only how fast the operator sees it: urgent reports stream in live, others arrive when the call ends.

| Agent may | Agent should not |
|---|---|
| Transcribe and summarise the call | Treat its urgency label as final, at any level |
| Suggest an urgency level with its reasons and a confidence score | Dispatch responders |
| Flag critical words (from [phasal matching](03_Phasal_Matching_and_Keyword_Boosting.md)) | Hide its reasoning from the operator |
| Suggest that a call is about an already-known event | Drop or merge a call without an operator seeing it |
| Hand the call to a human when unsure | Keep a caller in the AI flow when it does not understand them |

## Urgency in a disaster

Disaster calls differ from everyday ones. Many callers report the same fire or flood, and the most urgent calls are about people who cannot get out.

Suggested signals, each shown to the operator as a reason:

- **Life in danger now**: trapped, water rising inside the house, fire reaching the house, injured.
- **People who cannot leave alone**: elderly, disabled, children, people needing medical equipment.
- **New event or known event**: is the location inside an area we already have reports for? A new fire far from known ones matters more than the hundredth call about the same one. See [06](06_Report_Structure.md#grouping-calls-about-the-same-event).
- **Critical words** matched by phasal matching or found in the transcript.
- **How the caller sounds**, such as panic or a very weak voice. A research idea only, and riskier to rely on.

## Evidence from real emergency calls

- A peer-reviewed study (Blomberg et al., 2019) ran machine learning on 108,607 calls to the Copenhagen emergency centre. It recognised cardiac arrest **faster** than dispatchers (median 44 s vs. 54 s) but had **more false alarms**. The authors positioned it as decision support. This is everyday medical calls, not disasters, but it is the best evidence that AI suggestions help call takers.
- The widely quoted "95% vs. 73%" accuracy figures come from early press coverage, not the peer-reviewed study. Do not quote them.
- US vendors sell AI that triages overflow calls and groups calls about the same event during surges. We found no independent evaluation of these in a real disaster.

## Open questions

- What urgency scale do Greek and Turkish 112 operators use during disasters? We should match it rather than invent one. Until then, [06](06_Report_Structure.md) uses a placeholder.
- How do we measure life-threat recall before the demo? It needs test calls where we know the right answer ([04](04_STT_and_TTS.md#our-own-test-set), step 5).
- Does any part of the system count as a medical device? A June 2026 law-firm note says emergency triage tools that qualify as medical devices fall under both the medical device rules and the AI Act.

## Sources

- [EENA: how the AI Act will shape emergency services](https://eena.org/blog/how-the-ai-act-will-shape-the-future-of-emergency-services/)
- [McCann FitzGerald: draft guidelines on high-risk classification](https://www.mccannfitzgerald.com/knowledge/data-privacy-and-cyber-risk/essential-services-spotlight-eu-ai-act-draft-guidelines-on-high-risk-ai-classification)
- [Osborne Clarke: high-risk AI in medtech and digital health](https://www.osborneclarke.com/insights/eu-draft-guidelines-sharpen-high-risk-ai-classification-medtech-and-digital-health)
- [Rayvn: AI Act timing for emergency dispatch](https://rayvn.global/blog/eu-ai-act-emergency-dispatch-high-risk) (vendor blog)
- [Corti: cardiac arrest recognition study](https://corti.ai/stories/machine-learning-as-a-supportive-tool-to-recognize-cardiac-arrest-in-emergency-calls)
- [Knogin: AI triage surge handling](https://knogin.com/en/developers/ai-triage-system) (vendor)
- [Goodwin: AI Act transparency obligations now in force](https://www.goodwinlaw.com/en/insights/publications/2026/08/alerts-technology-dpc-eu-ai-act-transparency-obligations-now-in-force)
- [Legal 500: Türkiye artificial intelligence](https://www.legal500.com/guides/chapter/turkiye-artificial-intelligence/)
- [Moroğlu Arseven: Turkish draft AI law (December 2025)](https://www.morogluarseven.com/insights/ma-gazette-en/ma-gazette-edition-156-18-december-2025-en/draft-law-proposing-amendments-to-certain-laws-regarding-artificial-intelligence-submitted-to-the-turkish-grand-national-assembly/)
- [Daily Sabah: Istanbul earthquake 112 call figures](https://www.dailysabah.com/turkiye/istanbul/officials-provide-updates-on-istanbuls-earthquake-response/amp)
