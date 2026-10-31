# Model selection — measured, 2026-10-31

Harness: `scripts/bench_models.py` (run from a throwaway venv; see its docstring). Raw results are in
`docs/history/bench-*-2026-10-31.json`. GPU: RTX 4060 Ti 16 GB.

Test data: **30 real Bengali recordings** (Google FLEURS `bn_in` test) and **16 clinic sentences**
(appointments, doctors, departments, emergencies, spoken phone numbers) rendered with the Piper
Bangla voice. Each in three conditions: `clean`, `phone` (8 kHz, 300–3400 Hz, mu-law) and
`phone_noise` (phone plus babble/hiss at 10 dB SNR).

Caveats: the clinic sentences are synthetic speech from a single voice, so treat them as a
smoke test, not as accuracy. FLEURS is read speech, not a worried patient on a bad line. Real
recorded clinic calls are the only test that counts, and the harness can score them as soon as
there are some. Nobody on the team has yet listened to the TTS output.

## Speech-to-text (word error rate, lower is better)

| Model | FLEURS clean | FLEURS phone | FLEURS phone + noise | Clinic phone + noise | VRAM |
|---|---|---|---|---|---|
| **OmiKhan/bangla-asr-whisper-medium** (Apache-2.0) | **16.5%** | **17.7%** | **22.7%** | 38.3%* | 1.6 GB |
| Whisper large-v3, stock (the old product default) | 70.0% | 72.7% | 81.1% | 89.1% | 3.7 GB |
| Whisper small, stock | 109.8% | 113.4% | 111.1% | 107.4% | 0.6 GB |

\* The noise in that cell is babble made from the same synthetic voice, which is unusually hard.

**Decision: use OmiKhan/bangla-asr-whisper-medium.** The stock model the product configures today
(`large-v3`, `configs/default.yaml`) gets about 3 words in 4 wrong on Bengali. The fine-tune is about
4x better and uses less GPU memory. Phone-band audio costs about 1 point of WER; clinic noise about 5.

**Packaging (solved):** `python scripts/fetch_stt_model.py` downloads the fine-tune and converts it
to CTranslate2 for faster-whisper (checked: 22% WER on 8 FLEURS clips, same text as the PyTorch path).
The earlier "garbage" conversions were a wrong `tokenizer.json`, not bad weights: the fine-tune ships
its own tokenizer, and a stray copy of Whisper's stock one made every output unreadable. The script
now copies the fine-tune's tokenizer and refuses to run if it matches the stock one.

## Language model (router prompt in production JSON mode, 12 cases + free-text replies)

| Model | Valid JSON | Right tool | Right args | Bangla purity | Median / p95 reply | VRAM |
|---|---|---|---|---|---|---|
| **gemma2:9b** (current) | 12/12 | **12/12** | **11/12** | 95% | **1.0 s / 2.1 s** | 7.2 GB |
| qwen2.5:7b | 12/12 | 9/12 | 9/12 | 98% | 1.6 s / 4.1 s | 4.9 GB |
| TigerLLM-9B (Bangla fine-tune) | 12/12 | 9/12 | 9/12 | 75% | 1.0 s / 2.4 s | 10.0 GB |
| aya-expanse:8b | 12/12 | 6/12 | 6/12 | 80% | 2.3 s / 6.4 s | 6.0 GB |
| gemma-3-12b-it (Q4_K_M) | 12/12 | 11/12 | 11/12 | **99.6%** | 0.9 s / 2.5 s | 10.3 GB |
| Qwen3-8B (Q4_K_M, default thinking) | 11/12 | 10/12 | 9/12 | 7% | 4.4 s / 6.5 s | 5.3 GB |

**Decision: keep gemma2:9b.** It picks the right tool most reliably and fits in 7 GB. Gemma 3 12B is
a close second with cleaner Bangla (99.6% vs 95%) but needs 3 GB more and missed one tool; worth
re-testing on more cases before switching. Qwen3-8B was run with its default thinking mode on, which
costs seconds per reply and leaked English; a no-think run is untested. Gemma's licence is Google's
own terms, not OSI open source; Qwen3 is Apache-2.0 if that ever matters.

## Text-to-speech

| Voice | Round-trip WER* | Real-time factor | Licence |
|---|---|---|---|
| **Piper bn_BD-google-medium** (current) | 14.6% | 0.30 | CC-BY-SA 4.0 (attribution + share-alike; take legal advice) |
| bangla-speech-processing/bangla_tts_female / male | not testable | n/a | MIT tag, but see below |

\* Synthesize, transcribe with OmiKhan, compare. Real human speech scores 16–17% with the same
judge, so Piper is as intelligible to the recogniser as a person is. This says nothing about how
natural it sounds to a patient.

The two "MIT" Bangla VITS voices are **not usable as published**: their `config.json` files are
0 bytes, the source repo has no licence file, and it targets Python 3.8-era Coqui. There is no
better licence-clean Bangla voice found yet, so Piper stays.

## Bugs found by the harness

- `parse_action` rejected valid router JSON wrapped in a Markdown code fence, silently dropping
  bookings and emergency transfers for providers without JSON mode. Fixed.
- `VITSTTS` points at a placeholder `repo_owner/vits_bangla` and can never load.
- `tests/fixtures/noisy_clinic.wav` is a synthetic tone, not speech; it cannot measure STT.
