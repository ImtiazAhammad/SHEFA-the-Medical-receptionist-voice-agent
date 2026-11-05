# SHEFA project status and handoff

Last updated: 2026-11-05. Read this first in a new session; it is imported by `CLAUDE.md`.

## What the project is

A privacy-first, bilingual (Bangla / English) voice receptionist for clinics in Bangladesh. It
answers patient calls, tells callers which doctors and departments are available and when, books,
moves and cancels appointments, hands emergencies to a human, and calls patients back with
reminders. Everything (speech recognition, language model, voice) is meant to run on the clinic's
own machine. The owner (Imtiaz) is preparing a **client demo**; the client cares most about how
natural the conversation sounds and how edge cases are handled.

## Where the work is

- Branch `claude/nice-hamilton-20inuo`, open as PR
  [#8](https://github.com/ImtiazAhammad/SHEFA-the-Medical-receptionist-voice-agent/pull/8) into
  `main`. PR #7 and earlier are merged into `main`.
- 1231 tests pass, ruff clean, coverage 96.7% with the per-module ratchet holding
  (`scripts/check_coverage.py`).
- Nothing in PR #8 has run against real model weights: the cloud session that built it had no GPU
  and no access to Hugging Face, Ollama, OpenAI, Gemini, Groq or Azure. **The first real run on
  the owner's PC is the next step** (see "Next steps").

## Done in the 2026-11-03 to 11-05 session (PR #8, oldest first)

1. **Housekeeping.** `audioop-lts` for Python 3.13 (5 mu-law tests failed without it); stopped
   tracking `data/shefa.db-shm`/`-wal`; `uv.lock` re-locked (it was out of date with
   `pyproject.toml`).
2. **OpenAI adapters fixed.** The OpenAI speech adapter never ran (multipart form passed as
   `content=` raised TypeError), did not wrap raw PCM as WAV, and reported confidence inverted
   (`no_speech_prob` itself), so every utterance would have been answered "could you repeat?". The
   OpenAI LLM no longer sends `"tools": null`.
3. **`shefa fetch-models`** (`src/shefa/model_fetch.py`): downloads Piper voices (atomically, via
   piper's own downloader), builds the Bangla Whisper model with `scripts/fetch_stt_model.py`,
   checks Kokoro/VITS/Azure voices, checks the LLM server and runs `ollama pull`. Only what the
   configured providers need; every failure prints its fix. `shefa doctor` reuses these checks.
4. **`shefa setup --profile local|openai|gemini|groq` and `--voices local|azure`** (`--demo` =
   `--profile openai`). `gemini`/`groq` send only the LLM to a hosted free tier via the
   OpenAI-compatible adapter (key from `${GEMINI_API_KEY}` / `${GROQ_API_KEY}`), keeping speech and
   voices local and freeing ~7 GB VRAM. `--voices azure` uses `bn-BD-NabanitaNeural` +
   `en-IN-NeerjaNeural`. Every non-local profile prints that text leaves the machine.
5. **Typed chat that uses the real pipeline.** `/api/v1/chat` used to call the LLM with tools and
   never execute them. `VoicePipeline.handle_text()` now runs the same language switch, emergency
   handoff, other-language route, action router, tools and templates as a call, with a silent
   voice, and returns `reply, greeting, language, state, actions`. A model failure is
   `503 model_unavailable` and the history is rolled back. The console Talk tab has a text box and
   demo chips.
6. **A voice per language.** `pipeline.tts.voices.<lang>` (`VoiceConfig`: provider, voice_path,
   voice_id, model, device). `LanguageRoutedTTS` (`models/tts/routed.py`) reads each sentence with
   the voice for its script. Default: Piper `bn_BD-google-medium` for Bangla, **Kokoro-82M**
   (`af_heart`, CPU) for English. New adapters: `kokoro_tts.py`, `azure_tts.py`, a real Coqui
   `vits_tts.py` (the old one loaded a placeholder hub entry), shared thread streaming in
   `threaded.py`.
7. **Speech recognition per language.** `pipeline.stt.per_language` + `detector`:
   `LanguageRoutedSTT` (`models/stt/routed.py`) lets a stock multilingual Whisper (**`small`**,
   0.6 GB; upgrade to `large-v3-turbo` if VRAM allows) detect each turn's language and transcribe
   English; Bangla goes to the OmiKhan Bangla fine-tune (which forgets English). Assamese counts as
   Bangla; a third language is only chosen when the detector is >= 0.8 sure. Transcripts are NFC
   normalised.
8. **Barge-in fix.** Voice streams are closed with `contextlib.aclosing` in `speak_to`, the routed
   voice and the threaded voices, so a cut-off reply stops synthesising at once instead of at
   garbage collection.
9. **Language detector bugs** (`pipeline/language_detector.py`), found by the lab: the danda `।`
   (U+0964, in the Devanagari block) made every Bangla sentence ending in it "OTHER" (sent to the
   front desk); the keyword fallback used `\w`, which drops Bangla vowel signs, so no Bangla
   keyword could match and mixed Bangla-English was answered in English.
10. **Spoken forms** (`src/shefa/spoken.py`, `src/shefa/bangla.py`). Templates
    (`pipeline/actions.py`) and reminder calls (`reminders.py`) say "বৃহস্পতিবার, ৫ নভেম্বর বিকেল
    ৪টায়" / "Thursday 5 November at 4 pm", group schedules ("every day except Friday, 9 am to 12
    noon"; Bangladeshi week order, Saturday first), speak references as their number (APT-00001 ->
    "১" / "1"; the ID parser accepts that), use the Bangla doctor name, and never say "Dr. Dr.".
    Facts still come only from tool results, rendered in code.
11. **Conversation lab** (`src/shefa/lab/`, `configs/lab/scenarios.yaml`): `shefa lab run
    [--audio] [--speech] [--only ids]` plays 19 calls (Bangla/English booking, code-switch,
    language switch, Hindi caller, doctor on leave, Friday closed, unknown doctor, self-correction,
    medical advice, two emergencies, "are you a robot?", "hello?", reschedule, cancel, two
    LLM-played personas) through `handle_text`, each against a fresh copy of
    `configs/clinic.example.yaml`, audit rows to its own file. Per-reply checks (replied, no
    internal text, brief, caller's language, clean Bangla script) and per-scenario expectations
    (state, actions, bookings, booked dates, never-say words). `--audio` speaks replies and times
    first sound; `--speech` also voices the patient over simulated 8 kHz mu-law and transcribes
    (WER). Output `lab-report/report.html`, `results.json`, `audio/*.wav`.
12. **Blind voice test**: `shefa lab voices --voice piper:<onnx> --voice azure:<voice> ...
    [--language bn|en]` writes `voice-test/index.html` (shuffled letters, 1-5 scores, reveal).
13. **Docs**: `docs/demo-guide.md` (client demo playbook), `docs/fine-tuning-plan.md`,
    `docs/research/bangla-english-voice-models-2026-11.md` + `docs/research/notes/` (sourced
    research), `docs/research/verbex-comparison.md`, `docs/telephony-options.md`, README updates.

## Key decisions and why

- **Keep the measured stack**: gemma2:9b (only model with 12/12 right tool in the project bench,
  7.2 GB), OmiKhan Bangla Whisper-medium (16.5% WER vs 70% for stock large-v3, 1.6 GB), Piper
  bn_BD on CPU. New models replace these only after passing the same bench. Challengers to bench,
  thinking off: `gemma4:e4b`, `qwen3.5:9b`, `gemma3:12b-it-qat` (switch rule: >= 11/12 tool, >= 98%
  Bangla script purity, < 1 s first token).
- **12 GB budget** (~10 GB): gemma2:9b + Bangla Whisper + Whisper small + voices on CPU, with
  `OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0 OLLAMA_KEEP_ALIVE=-1`. The old bench ran on a
  16 GB 4060 Ti; the RTX 4060 Ti exists only as 8/16 GB, so **confirm the owner's actual card**.
- **Tool calls stay on the JSON action router** (`pipeline.llm.tool_calls: false`) for every
  profile, including OpenAI/Gemini, because it is the tested production path.
- **Facts are never paraphrased by the model**: dates, times, IDs, fees are rendered in code from
  the tool result.
- **No SIP yet.** Amber IT declined to sell a SIP trunk. Demo without a phone line (console + lab);
  see `docs/telephony-options.md` for the trunk alternatives (IP-phone line from an IPTSP, FXO
  gateway on the clinic's landline, operator enterprise products; never a SIM box).
- **Voice naturalness is the weakest link**: nobody has rated the Piper Bangla voice yet. Verbex.ai
  (ex-Hishab) reaches near-human Bangla with ~3,850 h pretraining + 4.22 h studio adaptation; for
  SHEFA the realistic route is recording 4-10 h of a Bangladeshi voice talent and fine-tuning a
  model already trained on Bangla (Indic Parler-TTS / Svara, Apache-2.0; Piper with 1-3 h for a
  cheaper step). XTTS (BnTTS's base) is non-commercial.

## Next steps (in order)

1. On the PC: `uv sync --extra local-stt-gpu --extra kokoro` (+ `espeak-ng`), `uv run shefa setup`,
   `uv run shefa fetch-models`, `uv run shefa doctor`. Fix whatever is not ok. Confirm the Piper
   `bn_BD-google-medium` voice really downloads (the catalog's `bn` folder was added recently; not
   verified from the cloud session).
2. `uv run shefa lab run --audio`, then `--speech`. Read `lab-report/report.html`; fix scenarios
   that "need work" (expect some with the real gemma2 router). Measure VRAM with `nvidia-smi`.
3. `uv run shefa lab voices` with Piper vs `azure:bn-BD-NabanitaNeural` (needs a free Azure key);
   2-3 Bangladeshi listeners score blind.
4. Bench LLM challengers with `PYTHONPATH=src python scripts/bench_router.py gemma2:9b gemma4:e4b
   qwen3.5:9b gemma3:12b-it-qat`.
5. Client demo per `docs/demo-guide.md`.
6. Then fine-tuning per `docs/fine-tuning-plan.md` (LLM QLoRA on reviewed dialogues -> Whisper
   LoRA with phone augmentation -> voice talent + TTS fine-tune).
7. Open ideas offered but not built: a phone-band option for `shefa lab voices` (compare voices as
   a caller hears them); transcribing the Verbex sample call (needs huggingface.co allowed); FXO
   gateway support for outbound calls; telling emergency callers to dial 999; hysteresis that keeps
   the previous turn's language for very short utterances.

## Not verified / known gaps

- No real model has run with any of the new code: Kokoro, Azure, VITS, Whisper routing, Gemini/Groq
  profiles were tested with fakes only.
- English words inside Bangla speech come back from the Bangla model in Bangla script.
- The lab's `--speech` patient voice is synthetic and the phone line is simulated.
- `escalation.on_call_numbers` is empty, so a transfer has nowhere to go on a real line.
- Licences to confirm before production: Piper bn_BD voice card, hishab models, DocTalkBN,
  OpenSLR 37.

## Working conventions

- Tests: `uv run pytest` (coverage floor enforced) then `uv run python scripts/check_coverage.py`;
  modules at 100% are listed in `src/shefa/coverage_policy.py` and must stay there. New code gets
  tests, bug fixes get regression tests. Lint: `uv run ruff check src tests` (line length 100).
- Config: `configs/default.yaml`, overridden per machine by gitignored `configs/local.yaml`
  (written by `shefa setup`); tests set `SHEFA_IGNORE_LOCAL_CONFIG=1`.
- Watch Bangla text handling: Python's `\w` does not match Bangla vowel signs, and the danda is in
  the Devanagari block. Use explicit script ranges.
- Commits: descriptive messages; work on a branch and open PRs into `main`.
