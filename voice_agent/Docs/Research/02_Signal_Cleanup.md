# 02 Signal cleanup

**Summary.** Use an off-the-shelf noise remover, most likely DeepFilterNet, and judge it only by whether it lowers the STT error rate on our own phone recordings. Cleanup that sounds better to a person can still make recognition worse.

## Why this step exists

Disaster calls are especially noisy: strong wind and fire in wildfires, rain and rushing water in floods, sirens, crowds, people shouting, a phone held at a distance. Most of this noise changes constantly, which favours DeepFilterNet over RNNoise. On top of that the phone network cuts the audio to 8 kHz. Cleaner audio gives the STT fewer wrong words, and it also helps the agent tell when the caller has stopped talking, so it interrupts less.

## Options

| Tool | Type | Good at | Weak at |
|---|---|---|---|
| **DeepFilterNet** | Open source | Changing noise such as sirens and voices. Generalises better in one comparison. | Heavier than RNNoise. Built for 48 kHz audio. |
| **RNNoise** | Open source | Steady noise such as fans and engines. Very small, runs anywhere. | Changing noise. |
| **Krisp** (telephony version) | Commercial | Built for phone audio up to 16 kHz. | Paid, closed. Vendor claims only. |
| **ai-coustics** | Commercial | Claims to be tuned for STT rather than for human ears. | Vendor claim, **not verified**. |

## What to watch out for

- **None of these has published results on 8 kHz phone audio.** DeepFilterNet expects 48 kHz, so we would upsample, clean, then downsample. That needs testing.
- **Over-cleaning hurts.** Removing noise can also remove parts of the voice that the STT relies on. The vendor point about "tuned for STT, not for ears" is a reasonable concern even though the product claim is unverified.
- **"Reconstruction"** (rebuilding the missing high frequencies of phone audio) is a separate technique called bandwidth extension. We did not find evidence that it improves STT for phone calls, so we suggest leaving it out until cleanup alone has been measured.

## How to decide

1. Take our own test recordings (see [04](04_STT_and_TTS.md#our-own-test-set)).
2. Run STT on each recording three ways: no cleanup, RNNoise, DeepFilterNet.
3. Keep whichever gives the lowest word error rate, and check the added delay per audio chunk.

## Open questions

- How much delay does DeepFilterNet add per audio chunk once it includes upsampling from 8 kHz and back? This counts against the [latency budget](04_STT_and_TTS.md#latency-budget).
- Does cleanup improve phasal matching as well as STT, or should phasal matching use the raw audio? Test both.

## Sources

- [Mercu Buana: DeepFilterNet3 vs RNNoise](https://publikasi.mercubuana.ac.id/index.php/sinergi/article/view/21917)
- [Mozilla: RNNoise](https://hacks.mozilla.org/2017/09/rnnoise-deep-learning-noise-suppression/)
- [Telnyx: noise suppression for AI agents](https://telnyx.com/release-notes/expanded-noise-suppression-ai-agents) (vendor)
