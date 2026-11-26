# 07 Privacy and encryption

**Summary.** Encrypt everything, both while it moves and while it is stored. Strip personal data only from the copy that goes to the prediction core and training, not from what the live agent and the 112 operators see, because they need the name and address to help. If we do not want an outside language model to see personal details, mask them with placeholders that are swapped back afterwards, so the agent can still respond.

## What gets encrypted

| Data | Encrypt in transit | Encrypt at rest | Notes |
|---|---|---|---|
| Call audio | Yes, secure phone audio and TLS | Yes, if recorded | |
| Transcripts | Yes, TLS | Yes | |
| Reports | Yes, TLS | Yes | |
| Training data | Yes | Yes | Stripped first |

Any outside service that does STT, language processing or TTS **sees the raw content**. You cannot strip audio before STT, because STT needs to hear it. So the real controls for the live path are:

- Use providers that process data inside the EU (and inside Türkiye for Turkish calls, see below), and sign a data-processing agreement with each.
- Or self-host the models (for example a fine-tuned Whisper and an open language model) so call data never leaves our servers.

## What gets stripped, and where

| Destination | Names, phone numbers | Exact address | Health details |
|---|---|---|---|
| Live agent's language model | Masked if it is an outside service | Masked if it is an outside service | Kept, needed to judge urgency |
| 112 personnel and the After Chaos map | Kept | Kept | Kept |
| Prediction core and training | Removed | Reduced to municipality, plus time of call | Kept only if there is a legal basis |

The coarse location and time are kept for the prediction core on purpose: in a disaster, where and when calls cluster is the most useful signal it gets.

## Can the agent still respond? Reversible masking

The original idea of a PHI stripper and a good master prompt works for the training copy. For the live agent, removing the address would make it useless. The answer is **reversible masking** (the Mask and Unmask nodes in the diagram):

1. Before the transcript goes to the language model, replace personal details with placeholders: "My mother Eleni is under the rubble at Themistokleous 5" becomes "My mother `<PERSON_1>` is under the rubble at `<ADDRESS_1>`".
2. The master prompt tells the model to use the placeholders as they are.
3. The model replies "Is `<PERSON_1>` able to answer you?" or reads back "You are at `<ADDRESS_1>`, correct?", and our code swaps the real values back before TTS.
4. The model also fills the report with placeholders (`"spoken_address": "<ADDRESS_1>"`). The same unmask step fills in the real values before the report is sent.

The language model never sees the real details, and the caller hears a normal reply. Microsoft's open-source **Presidio** tool has a reversible mode that does this. Note that STT and TTS services still see the real content, so this protects only the language-model step.

## Finding personal data in Greek and Turkish

- Presidio defaults to English and misses names in other languages unless it is given a model for that language.
- **Greek**: spaCy has a Greek model (`el_core_news_lg`) that finds names and places, but its licence (CC BY-NC-SA) **does not allow commercial use**. elNER is an alternative set of labelled Greek news text that we could train on.
- **Turkish**: several BERTurk-based models on Hugging Face find names and places, reporting scores of about 0.94 to 0.96. Each model's licence still needs checking.
- Names in Greek and Turkish change form with grammar (Γιώργος, Γιώργο, Γιώργου), so test the detector on spoken, inflected names, not only on news text.
- Phone numbers, ID numbers and similar fixed patterns are easier to catch with simple rules than with models.

## GDPR (Greece and other EU countries)

- Health information is a **special category** under GDPR Article 9 and needs an extra legal basis.
- Handling a live emergency call most plausibly rests on **protecting someone's life** (vital interests) or the **health-care basis** (Article 9(2)(c) or (h)).
- **Training models on call data is a separate purpose.** It needs its own legal basis and a privacy impact assessment (DPIA). Data from calls cannot simply flow into training.
- Stripped or pseudonymised data is still personal data under GDPR if it can be linked back to a person. It lowers the risk but does not remove the need for a legal basis.

## Türkiye (KVKK)

- Türkiye's data protection law is the KVKK (Law No. 6698). Health data is a special category there too.
- In 2024 Law No. 7499 changed the rules for special-category data and for sending data abroad. Sending personal data out of Türkiye now generally needs a standard contract approved by the data protection board, which must be reported to the board. Consent alone stopped being enough for transfers from September 2024.
- We could not confirm the exact conditions for processing health data in an emergency from the sources we found. **Not verified**; needs Turkish legal advice.

## Data between Greece and Türkiye

After Chaos works across both countries, and the demo earthquake hit both. Moving call data across the border is restricted both ways:

- Out of Türkiye: needs the KVKK transfer rules above.
- Out of Greece: GDPR only allows transfers outside the EU with a legal mechanism such as standard contractual clauses. We did not find an EU adequacy decision for Türkiye in this research, so assume one is needed. **Not verified.**
- Simplest design: each country's calls are processed and stored in that country (see [01](01_Call_Input_and_Scaling.md)). Only the shared incident picture, ideally without personal details, crosses the border.

This is general research, not legal advice. A real deployment needs a data protection officer in each country to sign off.

## Open questions

- Self-host or EU-hosted providers? Self-hosting is safer for data and harder to run.
- Do we keep call recordings at all, and for how long?
- What legal basis would training use, and who would approve the DPIA?
- What incident data may be shared between the Greek and Turkish sides, and in what form?

## Sources

- [LangChain: multilingual anonymisation with Presidio](https://python.langchain.com/docs/guides/privacy/presidio_data_anonymization/multi_language)
- [spaCy: el_core_news_lg](https://huggingface.co/spacy/el_core_news_lg)
- [elNER: Greek NER corpus](https://github.com/nmpartzio/elNER)
- [akdeniz27: Turkish BERT NER](https://huggingface.co/akdeniz27/convbert-base-turkish-cased-ner)
- [Latensis: Turkish NER](https://huggingface.co/mursideaki/latensis-ner-tr)
- [GDPR Article 9 commentary](https://www.noze.it/en/insights/gdpr-health-data-article-9/)
- [Cottgroup: KVKK amendments (Law 7499)](https://cottgroup.com/en/blog/kvkk-gdpr/item/amendments-to-the-law-on-the-protection-of-personal-data-no-6698-within-the-scope-of-the-8-judicial-package-and-the-reflections-of-it)
- [Mondaq: changes in the Turkish data protection law](https://mondaq.co.uk/turkey/data-protection/1440344/changes-in-the-pdpl-was-published-in-the-official-gazette)
- [EDPB opinion on AI training, summary](https://www.wsgrdataadvisor.com/2024/12/eu-privacy-regulators-confirm-that-legitimate-interest-is-a-valid-legal-basis-for-ai-model-training-and-deployment/)
- [Korff: sensitive data and legitimate interest (EDPB consultation)](https://edpb.europa.eu/sites/default/files/webform/public_consultation_reply/korff-gdpr-sensitive-data-legitimate-interest-ai-241016.pdf)
