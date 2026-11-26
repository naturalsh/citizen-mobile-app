# 04 Speech to text and text to speech

**Summary.** Greek and Turkish are supported by several commercial STT and TTS services, but almost every accuracy number comes from the vendors themselves, and none is measured on emergency phone calls. We cannot guarantee quality from published numbers. We can measure it: record a small test set of our own and compare two or three services on it. English and French are well supported everywhere and are not the risk.

## Language detection

After Chaos picks the language from the caller's **phone country code**: +30 Greek, +90 Turkish. This is instant and needs no speech, but it is often wrong in exactly the places the demo covers: tourists on roaming, Turkish visitors on Greek islands with Greek SIM cards, residents near the border. So the country code should be the first guess, not the final answer:

1. Open in the country-code language, with one short line in the other main language (for example "Türkçe için konuşmaya devam edin" on a Greek greeting). *Dropped on 2026-10-22 after test calls: the extra line sounded odd to Greek callers, and the call already switches language by itself when the caller speaks another supported one.*
2. Let the STT check the language of the caller's first sentence, and switch if it disagrees with confidence. Several services can detect language at the start of a call; check that it works in live mode.
3. If neither matches, offer English and French, then hand the call to a human (the "Unsupported language" edge).

Mixed-language calls: Deepgram Nova-3 can follow a caller who switches between languages, but only for ten languages, and Greek is not one of them. Soniox claims to handle switching mid-sentence for Greek.

## Languages

| | Greek | Turkish |
|---|---|---|
| Open training data | Common Voice: about 18 validated hours. Greek Podcast Corpus: about 623 hours. | Common Voice: about 129 validated hours from about 1,800 speakers. |
| Live STT confirmed | Deepgram, Speechmatics, Soniox | Soniox (other vendors not confirmed by a primary source) |
| Not confirmed | Google Chirp 3, Azure, ElevenLabs live mode | Deepgram, Speechmatics live mode |
| Best open-model result found | Whisper medium fine-tuned on Greek podcasts: about 21% → 13% WER on Common Voice | Whisper large-v3 fine-tuned: about 8% WER on FLEURS, 14% on Common Voice (self-reported) |
| Language models tuned for it | Llama-Krikri-8B from ILSP, a Greek research institute (successor to Meltemi) | We did not find a well-documented open Turkish model in this pass |
| TTS voices | Azure: Athina, Nestoras. ElevenLabs: several. | Azure: Emel, Ahmet. ElevenLabs: several. |

Which is harder? Turkish has about seven times more *Common Voice* data, recorded by many more speakers, while Greek has a larger single corpus (podcasts). The WER figures above use different test sets, so they cannot be compared directly. On vendor coverage Turkish looks weaker: fewer services confirm live Turkish STT, and we found no open Turkish language model. **Neither language is clearly easier.** Our own test set will decide.

## STT: what the numbers say

- **ElevenLabs** claims 3.1% Greek WER on one test and 5.5% on another, and the same page shows 4.2% for an older version. The figures contradict each other. Vendor claim.
- **Soniox** publishes a Turkish table with itself at 1.25%, Speechmatics 1.4%, Deepgram 1.71%, with no test method given. Vendor claim.
- **Deepgram, Speechmatics, Soniox** confirm live Greek, but publish no Greek WER we could find.
- **Whisper** (open, self-hostable) needs fine-tuning to be competitive in Greek. Self-hosting keeps call audio on our own servers, which matters for [privacy](07_Privacy_and_Encryption.md).
- No source measures any of these on 8 kHz phone audio. Phone audio is consistently harder than the read speech most tests use, and disaster calls add heavy background noise.

## TTS

- **ElevenLabs Flash v2.5** claims about 75 ms to start speaking. Multilingual v2 sounds better but is slower.
- **Azure** is reported to be faster and steadier than ElevenLabs, but less natural. It supports SSML, which lets us control pronunciation of place names and numbers.
- No provider publishes Greek or Turkish latency.
- For a disaster line, a calm, clear, slightly slow voice matters more than an expressive one. Callers may be outdoors in wind, so test playback over a noisy phone line.

## Latency budget

A commonly cited target from voice-agent vendors is under **800 ms** from the caller finishing to the agent starting to speak. It is not an emergency-service requirement, but callers in a disaster will hang up or repeat themselves if the agent is slow.

| Step | Budget |
|---|---|
| Final audio chunk through VAD | 50 ms |
| STT | 150 ms |
| Language model, first words | 400 ms |
| TTS, first audio | 150 ms |
| Network | 50 ms |

This table assumes the system has already decided the caller has finished. **That decision is the hidden cost.** Waiting for 500 ms of silence uses most of the budget by itself. Newer systems combine silence detection with a check on whether the sentence sounds finished, which brings it to about 150 to 250 ms. The agent also needs echo cancellation and must stop talking quickly when the caller interrupts.

Our pipeline adds steps the table leaves out: signal cleanup, phasal matching, and masking and unmasking personal details. Phasal matching runs alongside STT, so it should not add delay. Measure the other two.

## Our own test set

1. Write 30 to 50 short, realistic disaster lines per language, starting with the demo's earthquake: answers to the four script questions, street and neighbourhood names from Samos and İzmir, "the building next to us collapsed", "my mother is under the rubble", "we are trapped on the third floor", "the road is blocked".
2. Have different people read them **over a real phone call**, some in a quiet room and some with background noise (wind, rain, sirens, crowd).
3. Run each recording through two or three STT services, with and without [cleanup](02_Signal_Cleanup.md) and [keyword boosting](03_Phasal_Matching_and_Keyword_Boosting.md).
4. Compare the word error rate overall, and separately on place names and critical words.
5. Run the full agent on the same recordings and measure what After Chaos lists as its main safety metric: **how many life-threatening calls it catches** (life-threat recall), and whether it extracted the right facts.

## Open questions

- Do we need a language model that speaks Greek well (such as Krikri), or is a large general model enough? Test both on Greek transcripts.
- Which open Turkish language models exist and are usable? Not covered yet.
- Are Google and Azure Greek STT worth including in the test? Their Greek support was not confirmed in this pass.

## Sources

- [ElevenLabs: Greek STT](https://elevenlabs.io/speech-to-text/greek) (vendor)
- [Soniox: Greek](https://soniox.com/speech-to-text/greek), [Soniox: Turkish comparison](https://soniox.com/compare-stt/soniox-vs-deepgram/turkish) (vendor)
- [Speechmatics: Greek](https://www.speechmatics.com/speech-to-text/greek) (vendor)
- [Deepgram: Nova-3](https://deepgram.com/learn/introducing-nova-3-speech-to-text-api) (vendor)
- [Greek Podcast Corpus (arXiv 2406.15284)](https://arxiv.org/pdf/2406.15284)
- [Greek medical dictation ASR (arXiv 2509.23550)](https://arxiv.org/pdf/2509.23550)
- [Common Voice 25.0 Turkish](https://datacollective.mozillafoundation.org/datasets/cmn2e7kbl01k2mm07gm5n1bc9)
- [BuzzASR Turkish Whisper fine-tune](https://huggingface.co/BuzzASR/turkish) (self-reported)
- [Turkish Whisper vs Wav2Vec2 with call-centre audio (arXiv 2307.04765)](https://arxiv.org/abs/2307.04765)
- [Krikri (arXiv 2505.13772)](https://arxiv.org/pdf/2505.13772)
- [ElevenLabs: TTS models](https://elevenlabs.io/docs/overview/capabilities/text-to-speech.md)
- [Azure Greek voices](https://json2video.com/ai-voices/azure/languages/greek/), [Azure Turkish voice Emel](https://json2video.com/ai-voices/azure/voices/tr-tr-emelneural) (third-party catalogue)
- [Smallest.ai: latency budget](https://smallest.ai/blog/designing-voice-assistants-stt-llm-tts-tools-and-latency-budget)
- [Tian Pan: turn-taking and endpointing](https://tianpan.co/blog/2026/05/10/voice-agent-turn-taking-250ms-threshold-reshapes-architecture)
