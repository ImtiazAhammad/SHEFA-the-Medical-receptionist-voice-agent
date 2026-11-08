# Bangla voice models: survey, measurements and decisions (2026-11-09)

What was read, what was measured, and what we do next. Anything marked **UNVERIFIED** was not
checked against a primary source and must not be repeated to a customer.

## 1. BnTTS (verbex-ai / Hishab): skip

- The repository (github.com/verbex-ai/BnTTS, mirror hishab-nlp/BnTTS) holds `README.md`, `docs/`
  and `eval_data/`. **No source code, no requirements, no LICENSE file, no weights**: the README says
  "Pretrain weight link: Up-comming". No BnTTS checkpoint was found on Hugging Face.
- Paper: arXiv 2502.05729 (NAACL 2025 Findings). XTTS-based, 3,856 h of training data of which 3,636 h
  is unreviewed pseudo-labelled in-house audio; 4.2 h of studio recordings from four speakers.
  Speaker-adapted BnTTS-n scored SMOS 4.624 / naturalness 4.600 / clarity 4.869 against Azure 4.154 /
  4.100 / 4.686 and Google 4.017 / 3.949 / 4.700 (10 native raters, studio-quality 24 kHz). Its CER
  (0.034 on BnStudioEval, 0.069 on the text-diverse set) is worse than Google (0.020 / 0.049) and
  Azure (0.021 / 0.045). The authors state it fails on text under about 2 words or 20 characters,
  which is most of what a receptionist says ("জি", "ধন্যবাদ").
- No speed, VRAM, 8 kHz, numbers or code-mixing results. No comparison with Piper.
- Licence: no licence on the code, none on weights, training-data licences unstated. The base model
  XTTS-v2 is under the Coqui Public Model License (the card says so; the text of that licence was
  not reachable, and it is widely understood to be non-commercial: **UNVERIFIED**). Coqui as a
  company has closed.
- **Decision:** not usable today and probably not for a commercial product. Revisit only if weights
  and a permissive licence appear. Treat Verbex's published numbers as marketing, not a benchmark we
  can reproduce.
- Same organisation, possibly useful later: Titu STT (`hishab/titu_stt_bn_conformer_large`,
  `titu_stt_bn_fastconformer`) as an ASR challenger. Licences **UNVERIFIED**.

## 2. kawshikbuet17 and tts-playground

- `tts-playground` (MIT) is setup guides plus Gradio and real-time-factor scripts. No MOS/WER/CER, no
  samples, no paper. Its only Bangla measurement: Indic Parler-TTS on an RTX 3090 runs at RTF about
  1.9-2.0 for a single utterance (slower than real time) and 0.29 when 8 texts are batched; output
  is 44.1 kHz. A phone call is one utterance at a time, so batching does not help us.
- Other repos: Bangla heteronym benchmark (pronunciation disambiguation, 99.7% accuracy with
  BanglaBERT-large; a possible TTS front end), Bengali Orpheus and CosyVoice3 fine-tune adapters
  (Apache-2.0, trained on private data, no metrics), a synthetic Bengali telecom speech dataset
  (CC BY 4.0, 19.4 h, 24 kHz, **entirely synthetic** and the card says it may not generalise to real
  calls). No papers by this author were found.

## 3. Candidates worth a bake-off (nothing here is adopted yet)

| Model | Task | Licence (as listed) | Evidence | Concern |
|---|---|---|---|---|
| Piper `bn_BD-google-medium` (current) | TTS | CC-BY-SA 4.0 data | Round-trip WER 14.6% (own bench) | Not Bangladeshi accent confirmed; share-alike |
| EMTIAZZ/bangladeshi-bangla-tts-vits | TTS | Apache-2.0 tag; training data not named | None published | Needs old Coqui `TTS==0.22.0`; 1 GB checkpoint; 288 downloads |
| ai4bharat/indic-parler-tts | TTS | Apache-2.0, gated | Native-speaker score 86.2% (fine-tuned on 140 h Bengali) | RTF about 2 per utterance; 44.1 kHz; accent not confirmed Bangladeshi |
| ai4bharat/IndicF5 | TTS (cloning) | MIT tag | No Bengali numbers | Needs a reference clip; GPU |
| kawshikbuet17 CosyVoice3 / Orpheus adapters | TTS | Apache-2.0 | None | Private training data, provenance unknown; heavy |
| facebook/omnilingual-asr (1B/3B) | ASR | Apache-2.0 | No Bengali figure read | 6-10 GB VRAM |
| OmiKhan/bangla-asr-whisper-medium (current) | ASR | Apache-2.0 | WER 11.8% average on clean sets; 16.5% on FLEURS in our bench | One training set has no stated licence |
| OmniVoice, MMS-TTS-ben | TTS | **Non-commercial** | n/a | Excluded |

## 4. What we measured ourselves (multi-turn router benchmark, 29 cases)

`scripts/bench_dialogue.py`, Ollama, temperature 0, thinking off.

| Model | Tool+args right | Median reply |
|---|---|---|
| gemma2:9b | **24/29** | 1.5 s |
| Qwen3-14B | 21/29 | 1.5 s |
| Qwen3-8B | 18/29 | 1.3 s |
| Gemma 3 12B | 16/29 | 1.6 s (template problem suspected) |

Reading it:
- A larger model on the same 16 GB card did **not** win. Size alone is not the lever at this scale.
- Qwen3-14B invented a patient (name, date of birth, phone) when a caller merely complained about
  identity. A model that fabricates arguments cannot be trusted to act without a code check, which is
  what the read-back-then-yes flow provides.
- Every model fails the same two emergency phrases ("chest pain and sweating", "my son just
  fainted"). Emergencies are therefore decided by the keyword layer, not by the model; that layer
  was widened and is tested (`tests/unit/test_emergency_recall.py`).
- 29 cases, one run: a direction, not a verdict.

## 5. Decisions

1. **Language model:** keep `gemma2:9b` as the default. Do not switch to Qwen3-14B. A 27-32B model
   might be worth it on a hospital GPU with 24-48 GB; test it there with the same benchmark.
2. **vLLM:** supported as an option for concurrency (it batches callers), measured against Ollama
   before it becomes the default.
3. **TTS:** Piper stays. Run the bake-off in section 6 before adopting anything. No candidate can be
   judged for naturalness without a Bangladeshi listener.
4. **ASR:** keep OmiKhan; benchmark omnilingual-asr 1B/3B on phone-degraded audio.
5. **Fine-tuning:** yes, in this order of value: (a) Whisper LoRA on phone-augmented Bangla plus
   clinic vocabulary, (b) a licensed Bangladeshi voice recorded for Piper, (c) router fine-tune only
   after real consented call transcripts exist. See `docs/fine-tuning-plan.md`.

## 6. TTS bake-off protocol

For each candidate, in an isolated virtualenv (several need old dependency pins):

1. Synthesize the 16 clinic lines in `scripts/bench_models.py` plus 20 short answers ("জি", "ঠিক আছে",
   "ধন্যবাদ"), 10 dates/times/phone numbers read aloud, and 10 code-mixed lines.
2. Convert to the phone path: resample to 8 kHz, G.711 mu-law round trip.
3. Score: round-trip WER with the OmiKhan model, real-time factor and time to first audio on the
   target GPU, VRAM, and failures on text shorter than 20 characters.
4. A Bangladeshi listener ranks blind samples (`shefa lab voices`) for accent and naturalness. Tools
   cannot do this step.
5. Adopt only if it wins on 2-4, has a clean commercial licence (quote the licence and the
   training-data licence), and runs under 500 ms to first audio.

## Sources
- https://github.com/verbex-ai/BnTTS , https://arxiv.org/abs/2502.05729
- https://github.com/kawshikbuet17/tts-playground
- https://huggingface.co/EMTIAZZ/bangladeshi-bangla-tts-vits
- https://huggingface.co/ai4bharat/indic-parler-tts , https://huggingface.co/ai4bharat/IndicF5
- https://github.com/facebookresearch/omnilingual-asr
- https://huggingface.co/OmiKhan/bangla-asr-whisper-medium
