# Verbex voice demo: what it shows and the benchmarks it sets

Source: `verbex_voice_demo.mp4` (130.5 s, 1280x720, 30 fps, AAC 48 kHz stereo). Analysed with
SHEFA's own tools (PyAV for decoding, the Bangla Whisper model for words and timing, the Silero VAD
inside faster-whisper, and `scripts/analyze_voice.py` for the measurements). I cannot hear audio, so
every statement about *how it sounds* is out of scope; what follows is measured or read from the
frames and the transcript.

## 1. What the file is (and is not)

It is **not a recorded phone call or an agent session.** It is an animated promotional reel for an
**expressive Bangla text-to-speech voice**: a waveform over tinted scenes, karaoke-style text, and a
small style tag on each phrase.

- Opens with a narrator: "Have you ever noticed how many times the colour of our voice changes in a
  single day?", then plays acted scenes: a sleepy "two more minutes, please" (tag: *mumbling sleepily*),
  an office rush ("already", "boss", "washroom-এ"; tag: *inhaling sharply*), friends joking in dialect
  ("ভাত ঠান্ডা হয়া যাইতেছে"; tags: *shouting, taunting*, *mocking anger*, *laughing uncontrollably*),
  a couple, a first salary, a newborn ("আলহামদুলিল্লাহ"), a daughter's wedding, "Abbu, stop crying,
  take your medicine"; ends "Verbex AI".
- The tags are **inline style directions** attached to phrases, so the voice is controllable per
  phrase (emotion, volume, breath, laughter), not just per voice.

So it can benchmark *voice quality and expressiveness*. It cannot benchmark response delay,
turn-taking, interruption handling, speech recognition, tool use or booking, because none of those
are in it. Anything below labelled "agent" is a SHEFA target set from other sources, not a Verbex
measurement.

## 2. Measurements

Verbex reel vs SHEFA's current Bangla voice (Piper `bn_BD-google-medium`) saying a comparable
narration (11.8 s) and a clinic line (7.8 s).

| Measure | Verbex reel | SHEFA Piper (narration / clinic line) | Reading |
|---|---|---|---|
| Sample rate | 48 kHz | 22.05 kHz | Reel is wideband; irrelevant on a phone line (8 kHz G.711) but matters on the web and in the app |
| 95% / 99% of energy below | 1.97 / 4.95 kHz | 1.14 / 2.28 and 1.41 / 2.58 kHz | Reel is brighter; Piper is dull above ~2.5 kHz |
| Speech level (RMS) | -13.8 dBFS | -19.7 / -20.3 dBFS | Reel is mastered about 6 dB louder |
| Peak | +2.0 dBFS after decoding | -0.3 / 0.0 dBFS | The reel is hot and clips; do **not** copy this |
| Noise in pauses | -20.8 dBFS (music/effects bed) | -54 / -70 dBFS (digital silence) | Reel has a continuous bed; ours is silent |
| Speech share of time | 73% | 88 / 82% | Reel breathes more |
| Pauses between phrases | median 0.46 s, p90 1.38 s, nine over 1 s | median 0.31-0.33 s, p90 0.38 s, none over 1 s | **Reel varies its pauses (p90/median 3.0); Piper does not (1.15)** |
| Phrase length | median 1.2 s, p90 3.5 s | 3-4 phrases of 2-4 s | Reel is short, conversational |
| Pace | 2.0 words/s (p10 1.9, p90 2.6) | not measured (no word timings) | |
| Pitch (voiced frames) | median 198 Hz; 24 semitones range (many speakers) | 132 / 127 Hz (one male voice); 13.5 / 9.6 semitones | Reel has at least four distinct voices: ~110 Hz men, ~190-230 Hz women, ~290-340 Hz a child |
| Within-phrase pitch movement | 4.1 semitones | 4.2 / 2.7 semitones | **No difference on this metric.** It does not separate the two; do not read it as "Piper is as expressive". |

Scene map (from the VAD and word timings): most hand-offs between speakers are **0.2-0.5 s**
apart; deliberate beats of **1.1-1.9 s** precede emotional lines ("কান্না থামাও তো", "জানি", the sign-off).
The reel is edited, so these gaps are directed, not what a live system produces.

## 3. What transfers to a clinic receptionist, and what does not

Transfers:

1. **Register.** Spoken, colloquial Bangla, not textbook Bangla, with **English words inside Bangla
   sentences pronounced as English** ("already", "boss", "washroom-এ"). Callers say "appointment",
   "doctor", "fee", "slot". SHEFA picks a voice per *turn*, not per word, so code-mixed sentences
   are read by one voice that handles only one of the two languages.
2. **Pace and pause shape.** Short phrases and pauses that vary with meaning. Our uniform 0.3 s is
   the clearest measured difference.
3. **Controllable style.** A receptionist needs a small set, not shouting or laughing: warm, calm,
   apologetic ("sorry, that time is taken"), reassuring, clear-for-numbers, urgent-but-steady for
   emergencies. This needs a voice that accepts a style instruction. Piper cannot.
4. **Distinct, consistent voices.** One voice per clinic (male or female choice) held for the whole
   call.

Does not transfer: shouting, mockery, laughter, dialect banter, music beds, +2 dBFS mastering.

## 4. Benchmarks SHEFA should meet

Voice (measurable with `scripts/analyze_voice.py`, plus a human listening score):

| # | Target | Verbex reel | SHEFA now |
|---|---|---|---|
| V1 | Pause variability p90/median >= 2.0 on a 10-sentence clinic script | 3.0 | 1.15 |
| V2 | Speech level -16 dBFS RMS, peak <= -1 dBFS (no clipping) | -13.8, +2.0 | -20, 0.0 |
| V3 | Output sample rate >= 22.05 kHz for web; telephony down-sampled with a band-pass tuned so numbers stay intelligible | 48 kHz | 22.05 kHz |
| V4 | Code-mixed sentences ("আপনার appointment কাল সকাল ১০টায়") read with both words correct, by span | yes | no |
| V5 | At least 6 selectable styles (neutral, warm, apologetic, reassuring, numbers-clear, urgent-steady), chosen per phrase by the dialogue manager | per-phrase tags | none |
| V6 | Blind listening score for Bangla voices (1-5, three Bangladeshi listeners, `shefa lab voices`) at or above the best available reference voice | n/a | not yet run |

Agent (not in the video; targets from the production-voice-agent research and SHEFA's own logs):

| # | Target | SHEFA now |
|---|---|---|
| A1 | Reply starts <= 1.0 s p50 and <= 1.8 s p95 after the caller stops | 1.3-1.7 s typical; p95 not measured on real mic audio |
| A2 | Booking task success >= 95% on the lab scenarios, including mis-heard names, phone dictation, interruptions; zero bookings without a spoken read-back and an explicit yes | 19/19 lab calls pass, but they are scripted; confirm-before-act not built |
| A3 | Caller can interrupt the agent; playback stops within 300 ms | cannot interrupt (half-duplex) |
| A4 | Bangla word error rate on recorded clinic-phone audio, measured, with names and digits reported separately | never measured on real phone audio |
| A5 | No call ends in silence: every turn produces speech or a handover | one silent turn seen on 2026-11-07 |

## 5. Candidate path for V4/V5 (needs a bake-off, not a decision)

[Indic Parler-TTS](https://huggingface.co/ai4bharat/indic-parler-tts) (AI4Bharat) is controlled by
a text description of the speaker and style, lists Bengali among the languages with emotion prompts,
and is trained on ~1,800 hours. Licence is reported inconsistently across sources (Apache-2.0 on
one model card, MIT on another listing): read the official licence file before use. Unknowns to
measure on this machine: latency for a 2-second sentence, VRAM next to gemma2 and Whisper, whether
it reads English words inside Bangla, and the listening score. Piper stays as the fast fallback.
No open model with per-phrase emotion tags and code-mixing was found in search.

## 6. Limits of this analysis

- Single 130 s reel, edited and mastered; one data point, not a distribution.
- The VAD merges overlapping voices and music with speech, so pause statistics are approximate.
- The pitch tracker is a simple autocorrelation method; octave errors are possible; it cannot tell
  naturalness. Human listening is the real test.
