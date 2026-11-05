# Verbex.ai voice: what it shows and how much data matching it takes

Checked 2026-11-05 at the owner's request (https://verbex.ai/product#user-call-audio).

## Who they are

Verbex.ai is the company formerly called Hishab (Singapore-registered, Bangladeshi team). It runs
the government's 333 helpline pilot and an iFarmer farmer-engagement line, and claims in-house
models with "natural voice dialogue that is virtually indistinguishable from human speech".
Sources: [TBS](https://www.tbsnews.net/features/panorama/voice-possibility-how-verbexai-giving-ai-bangladeshi-accent-1138101),
[Daily Star](https://images.thedailystar.net/node/3510746).

## The sample call (measured, not listened to)

`/assets/audio/ifarmercustomer.mp3`: 3 min 23 s, mono, 97% of energy in 300-3400 Hz, so a real
phone recording. Two voices (~235 Hz and ~156 Hz median pitch; which one is the agent is not
known without listening). Median gap between speakers about 1.0 s (p90 about 2 s), no overlaps.
Both voices move pitch about equally (~5 semitones within a phrase), so the synthetic one has
human-like intonation. The phone band also hides synthesis artefacts that wideband playback
would expose. Not transcribed (needs a speech model; Hugging Face was blocked in that session).

## Their data scale

- Voice, BnTTS (Findings of NAACL 2025, [ACL](https://aclanthology.org/2025.findings-naacl.279),
  [arXiv](https://arxiv.org/abs/2502.05729v1)): XTTS-based, pretrained on **3,850 h** of labelled
  Bangla speech (open-source + pseudo-labelled + synthetic), adapted with **4.22 h of studio
  recordings from 4 speakers**. XTTS weights are non-commercial (Coqui Public Model License).
- Speech recognition: a **20,000+ h** labelled Bangla dataset is described by a team member.
- Conversation: years of real call-centre traffic.

## What SHEFA needs to get close

The pretraining step is borrowed by starting from a model already trained on Bangla; the part to
reproduce is the adaptation step with your own voice.

| Target | Voice talent recordings | Base | On a 12 GB card |
|---|---|---|---|
| Clear, consistent (better than today) | 1-3 h, one speaker | Piper fine-tune | CPU |
| Natural, expressive, near Verbex | 4-10 h per voice | Indic Parler-TTS or Svara (Apache-2.0) fine-tune | 2-3 GB GPU; easier with `--profile gemini` |
| Their pretraining from scratch | 3,000+ h | not needed | no |

Data to record: studio quality (quiet room, same mic, 44.1-48 kHz), one speaker per voice; about a
third acted receptionist dialogues with a partner (conversational prosody, not read news);
greetings, questions, confirmations with dates/times/phone numbers/fees/names, apologies,
backchannels (জি, আচ্ছা, একটু অপেক্ষা করুন), calm-urgent emergency lines; exact transcripts with
numbers written as spoken (matching `src/shefa/spoken.py`); a written commercial-synthesis
agreement with the talent.

For understanding: 100-300 h fine-tuning per `docs/fine-tuning-plan.md`, plus 200-500 consented
real front-desk calls from the pilot clinic (accents, noise, code-switching, phrasing; also the
test set). For speed: their ~1.0 s median turn gap is the target; `shefa lab run --audio`
measures SHEFA's (aim under 1.2 s).
