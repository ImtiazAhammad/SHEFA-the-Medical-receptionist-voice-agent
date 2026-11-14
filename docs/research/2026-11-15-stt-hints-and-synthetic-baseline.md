# Speech model: synthetic baseline and the "hints" experiment (2026-11-15)

**Result in one line: giving the Bangla Whisper fine-tune hint words (hotwords or an initial prompt)
makes it much worse, so do not use hints as a cheap fix for "বুক গরম"-style errors.**

## What was measured

* Model: the agent's own Bangla Whisper-medium fine-tune (`models/stt/bangla-whisper-medium-ct2`,
  faster-whisper 1.2.1, beam 5, VAD on), on the RTX 4060 Ti.
* Audio: 29 short caller phrases (booking, days, times, names, digits, "বুক করো"), spoken by the
  agent's Piper Bangla voice, so ONE clean synthetic speaker. Optional G.711 phone round trip and
  white noise from `shefa.collector.audio.phone_round_trip`.
* Scripts: kept outside the repo; the reusable pieces are `shefa collect score` and
  `shefa.collector.tools`. Word error rate is computed with the shared normaliser
  (`shefa.collector.text`), so number spelling variants do not count as errors.

## Results

| Condition | Plain | Full word list as hotwords (about 60 words) |
|---|---|---|
| clean | 21.9% | 110.0% |
| phone 8 kHz (mu-law) | 18.4% to 23.5% across two runs | 100.0% |
| phone 8 kHz + noise 15 dB (A-law) | 28.7% | 112.8% |

Smaller hints, same clips:

| Hint | clean | phone 8 kHz |
|---|---|---|
| none | 21.9% | 23.5% |
| 3 booking words (`বুক করো অ্যাপয়েন্টমেন্ট ডাক্তার`) | 53.7% | 54.7% |
| 10 doctor surnames | 73.8% | 60.0% |
| one short initial-prompt sentence | 57.0% | 56.4% |

## What it means, and what it does not

* Hints are harmful on this model in this setup: it starts repeating or replacing words with the hint
  words. This is the test the plan asked for before any training; it is rejected.
* The remaining cheap idea is snapping the OUTPUT to the words the agent expects at that turn
  (doctor names, weekdays, digits, yes/no), which is code, not a model setting. Not built.
* The plain figures (18% to 29%) are high for easy clean speech because the phrases are very short
  (one wrong word out of three is 33%). They are a pipeline check, not evidence about real callers.
  **Nobody has measured the model on real patients on a real phone line.** That is what the
  community collection and `shefa collect score` are for.
* Synthetic single-speaker audio can behave differently from real voices; repeat the hints test on
  real clips before treating it as final.
