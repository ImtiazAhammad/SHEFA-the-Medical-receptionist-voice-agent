# Fine-tuning plan (12 GB GPU)

Order of work: first **use the existing models** (done: see
[`demo-guide.md`](demo-guide.md)), then **fine-tune**, then fall back to free providers only where a
local model is not good enough. Everything below fits on one 12 GB card, but only with the live
system stopped while training. Sources, licences and numbers are in
[`research/bangla-english-voice-models-2026-11.md`](research/bangla-english-voice-models-2026-11.md)
and its notes in [`research/notes/`](research/notes/).

## Before any training: measure

Training without a test set cannot show it helped. The conversation lab is that test set:
`shefa lab run --speech` on the current models gives the baseline report. Add scenarios for every
failure you hear, and keep the reports to compare after each fine-tune. Then:

1. Re-measure VRAM on the real card (the existing bench ran on a 16 GB card).
2. Bench the language-model challengers with thinking off, against gemma2:9b:
   ```bash
   PYTHONPATH=src python scripts/bench_router.py gemma2:9b gemma4:e4b qwen3.5:9b gemma3:12b-it-qat
   ```
   Switch only if one reaches 11/12 right tool, at least 98% Bangla script purity and a first
   token under 1 s.
3. Run the blind voice test (`shefa lab voices`).

## 1. The language model: QLoRA on receptionist dialogues (highest value per GPU-hour)

*Why:* decides whether SHEFA sounds like a Dhaka receptionist: short turns, polite আপনি, everyday
Bangladeshi words (পানি, চারটা, not Kolkata forms), and the right tool every time.

- **Data:** no Bangla appointment-booking dialogue set exists. Generate 2,000-5,000 multi-turn
  dialogues from the clinic directory and the lab scenarios (bookings, reschedules, unknown
  doctors, closed days, emergencies, language switches), using a strong model, then have
  Bangladeshi speakers correct them. The lab's `results.json` gives you real transcripts of where
  the current model goes wrong.
- **Recipe:** Unsloth QLoRA, r=16, sequence length 2,048, batch 1-2 on the 7-9B model (an 8B QLoRA
  peaked at 6.6 GB in a published run). Hours, not days.
- **Licence:** Gemma's own terms for gemma2/gemma3; Gemma 4 and Qwen3.5 are Apache-2.0.

## 2. Speech recognition: Whisper LoRA with phone-line augmentation

*Why:* decides whether SHEFA understands real callers on real phone lines, and one model could then
hear Bangla, English and Banglish.

- **Data, Bangladeshi:** SUBAK.KO (241 h, CC BY 4.0), OpenSLR 53 (CC BY-SA 4.0, share-alike: legal
  review), validated Common Voice bn (CC0), a DocTalkBN slice (558 h of real telemedicine audio,
  licence not stated: ask first). Mix in **20-30% English** or the model forgets English.
- **Augmentation:** resample to 8 kHz, G.711 mu-law/A-law and AMR codec round trips, packet loss,
  clinic noise (`scripts/make_noisy_clinic_fixture.py` is a start).
- **Recipe:** PEFT LoRA with 8-bit weights on Whisper-medium or large-v3-turbo (large-v2 trained in
  under 8 GB this way), 100-300 h. Normalise every transcript to Unicode NFC before scoring.
- **Best data of all:** a few hundred consented, de-identified recordings of real calls to the
  pilot clinic, which also become the test set.

## 3. The voice: a Bangladeshi voice talent, then a Piper fine-tune

*Why:* no public Bangla voice has a Bangladeshi accent, a clean commercial licence and high
naturalness at the same time. Data quality decides naturalness: the same model went from MOS 3.16
to 4.46 just by training on 20 h of professional recordings instead of a generic corpus.

- **Record:** 1-3 h (1,000-2,500 lines) from one consenting Bangladeshi speaker reading clinic
  scripts: dates, times, phone numbers, doctor names, questions. A written agreement must cover
  commercial synthetic use.
- **Recipe:** fine-tune Piper (VITS, medium, 22.05 kHz) from an existing checkpoint, about 1,000
  extra epochs, batch 8-16 on 12 GB. Optionally pre-adapt on Rasa or IndicVoices-R (CC BY 4.0,
  Indian accent) for phonetic coverage first. The result runs on CPU like the current voice; point
  `pipeline.tts.voice_path` at it and compare it in `shefa lab voices`.
- **Avoid in production:** MMS-TTS and BanglaKontho (non-commercial), IndicTTS (needs an MoU), the
  published bangla-speech-processing VITS voices (0-byte configs, no licence file).

## Free providers: where they still help

For demos or while fine-tuning is in progress: Gemini or Groq for the language model
(`--profile gemini|groq`), Azure's bn-BD voices as the listening-test reference (`--voices azure`).
Groq's free Whisper is stock Whisper, about 70% word errors on Bangla in the project bench, so it
can only hear English.
