# 03 Phasal matching and keyword boosting

**Summary.** These are two different ways to make sure critical words are not missed, and they work well together.

- **Phasal matching** compares the caller's audio to a database of averaged recordings of known words. It works on the sound itself, so it can catch a word even when the STT gets it wrong. It is a proven technique for a *small* list of words, not a replacement for STT.
- **Keyword boosting** tells the STT which words to expect, so it leans toward them. It is cheap and most STT services offer it.

Suggested design: STT with keyword boosting does the main transcription. Phasal matching runs alongside it on a short list of the most critical words in each language, and acts as a second opinion.

## Phasal matching

### What it is in research terms

Matching incoming audio against stored examples of a word is called **template matching**, and when you search for a word inside continuous speech it is called **keyword spotting**. Despite the name, phasal matching should not rely on the phase of the sound wave (see point 2 below).

### Lessons from research

1. **Do not compare raw waveforms.** The same word differs every time: speed, pitch, loudness, accent, phone line. Systems first turn audio into features that describe how it sounds, usually MFCCs, and compare those.
2. **Phase is usually thrown away, but it can help as an extra.** Standard features keep only the strength of each frequency and drop the phase, because raw phase looks random from one recording to the next. Several studies found that *adding* carefully processed phase features to MFCCs cut errors by roughly 10 to 20%. No study we found uses phase alone.
3. **Line up the timing before comparing.** People say words at different speeds. **DTW** stretches and squeezes one recording to line it up with the other before measuring the difference.
4. **Averaging needs alignment first.** If you average recordings without lining them up, the result smears into something that matches nothing. Align with DTW, then average. A 2024 paper (multi-sample DTW) found a way to keep the variation of all stored examples while running almost as fast as a single average.
5. **The modern version uses neural "word fingerprints".** Instead of MFCCs, a multilingual neural model turns each word into a short list of numbers (an acoustic word embedding). In one study on radio in Swahili, this approach with only **one minute** of example recordings did about as well as an STT trained on **30 hours** of data. When the STT had matching training data, the STT won. This is the strongest argument for phasal matching in languages where STT is weaker.

### How to build the word averages db

1. Pick 20 to 50 critical words and phrases per language, focused on disasters. Examples: fire, flood, earthquake, trapped, water rising, fire is close, injured, children, elderly. Greek: φωτιά, πλημμύρα, σεισμός, εγκλωβισμένοι, συντρίμμια (rubble), τραυματίας. Turkish: yangın, sel, deprem, mahsur, enkaz altında (under the rubble), yaralı. The demo replays an earthquake, so start with earthquake terms.
2. Record each one from many different speakers (men, women, older people, regional accents), **over a real phone line**.
3. Store the aligned average, or all examples, for each word. Start with averages, as the diagram assumes. Switch to all examples (multi-sample DTW) if averages miss too many words.
4. At runtime, slide over the incoming audio and flag a match when the distance falls under a threshold. Tune the threshold on held-out recordings to balance missed words against false alarms.

### Risks

- Greek and Turkish both change word endings a lot (εγκλωβισμένος, εγκλωβισμένη, εγκλωβισμένοι). Each form may need its own template. Count forms, not words, against the 20 to 50 limit, and drop rare forms first.
- More templates means more false alarms. Keep the list short.
- A match should *raise attention* (for example, flag possible urgency for the operator). It should not decide anything on its own.

## Keyword boosting

### What it is

You give the STT a list of words, optionally with weights. The STT becomes more likely to pick those words, but it is not forced to: if the audio clearly says something else, it still writes what was said.

### What to boost

- Emergency terms in each language.
- **Place names**: municipalities, villages, neighbourhoods. These are the words STT gets wrong most often, and in a disaster the location is the most important field in a report.
- **The names of the active event's area**: when a fire or flood is already known, boost the villages and roads in and around it for every call.
- Idea, **not tested**: when AML gives us the caller's location, load the street and place names for that area as boosted words for that call. The diagram shows this as the AML → Keyword list edge.

### What to watch out for

- **Check streaming support.** Some services only support boosting on recorded files, not on live audio. We need it live.
- **Check Greek and Turkish support.** We found no source confirming that boosting works for either language. Ask each vendor.
- **Do not over-boost.** Too many words or too high weights make the STT "hear" boosted words that were never said.

## Open questions

- Which 20 to 50 words go into the critical list for each language? This needs someone who knows 112 call content.
- MFCC with DTW, or neural word embeddings? MFCC with DTW is simpler to build for a demo. Embeddings did better in the low-data study above. Test both on our recordings.
- Who records the template examples, and how do we get phone-quality recordings from enough speakers?

## Sources

- [Wollongong: keyword spotting with template matching](https://ro.uow.edu.au/infopapers/1772)
- [Multi-sample DTW for few-shot keyword spotting (arXiv 2404.14903)](https://arxiv.org/abs/2404.14903)
- [Jacobs et al., Interspeech 2023: ASR vs acoustic word embeddings](https://arxiv.org/pdf/2306.00410)
- [Transformer acoustic word embeddings for low-resource keyword spotting (2025 preprint)](https://arxiv.org/html/2506.17690v1)
- [Saratxaga et al., Interspeech 2010: phase features for ASR](https://www.isca-archive.org/interspeech_2010/saratxaga10_interspeech.html)
- [Yamamoto et al., Interspeech 2010: long-term phase features](https://www.isca-archive.org/interspeech_2010/yamamoto10_interspeech.html)
- [Loweimi et al.: phase-based features](https://mini.dcs.shef.ac.uk/wp-content/papercite-data/pdf/loweimi_nolisp13.pdf)
- [Soniox: context biasing](https://soniox.com/wiki/context-biasing)
- [FluidAudio: custom vocabulary (batch only)](https://docs.fluidinference.com/asr/custom-vocabulary)
- [TurboBias 2.0: streaming context biasing (arXiv)](https://arxiv.org/pdf/2608.21343)
