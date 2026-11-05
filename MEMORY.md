# SHEFA Medical Voice Agent - quick reference

Current state, decisions and next steps: [`docs/project-status.md`](docs/project-status.md).

## What this is

Privacy-first, bilingual (Bangla/English) voice receptionist for clinics in Bangladesh: answers
calls, explains doctors/departments/schedules, books/moves/cancels appointments, hands
emergencies to a human, and calls patients with reminders. All models can run on the clinic's
machine.

## Quick start

```bash
uv sync --extra local-stt-gpu --extra kokoro    # Kokoro (English voice) needs espeak-ng
uv run shefa setup                              # token, console mode, sample clinic (see --profile, --voices)
uv run shefa fetch-models                       # voices, Bangla speech model, ollama pull
uv run shefa doctor                             # every line should say ok
uv run shefa serve                              # http://127.0.0.1:8000/console
uv run shefa lab run --audio                    # 19 recorded edge-case calls -> lab-report/report.html
uv run shefa lab voices                         # blind voice test -> voice-test/index.html
```

## Architecture

```
Caller -> browser console (WebSocket) | Asterisk AudioSocket | Twilio (dev sink)
       -> VoicePipeline: VAD -> STT (routed by language) -> language/emergency checks
          -> JSON action router (LLM) -> tools (clinic store, SQLite) -> spoken templates
          -> TTS (one voice per language, sentence streaming)
Typed chat (/api/v1/chat) -> VoicePipeline.handle_text (same logic, no audio)
```

## Default models (configs/default.yaml)

| Part | Bangla | English |
|---|---|---|
| Speech recognition | OmiKhan bangla-asr-whisper-medium (CTranslate2) | stock Whisper `small` (also detects the language) |
| Language model | gemma2:9b via Ollama, JSON action router | same |
| Voice | Piper bn_BD-google-medium (CPU) | Kokoro-82M `af_heart` (CPU) |

Profiles: `shefa setup --profile gemini|groq` (LLM on a free tier), `--profile openai`, `--voices
azure` (bn-BD-NabanitaNeural). Per-machine choices live in gitignored `configs/local.yaml`.

## Where things are

```
src/shefa/
  main.py               FastAPI app, console API, /api/v1/chat
  cli.py                shefa setup/serve/doctor/fetch-models/lab/clinic/asterisk/reminders/token
  model_fetch.py        fetch-models + doctor checks
  pipeline/             voice_pipeline.py (calls + handle_text), actions.py (router + templates),
                        language_detector.py (language + emergency), vad.py
  spoken.py, bangla.py  dates/times/schedules/references as spoken in bn/en
  models/               stt/ (whisper_local, routed, openai, elevenlabs), tts/ (piper, kokoro,
                        azure, vits, routed, threaded), llm/ (openai_compatible, openai, anthropic)
  clinic/               directory + booking engine (SQLite, no double-booking)
  lab/                  conversation lab (scenarios, runner, report) and voice test
  telephony/            browser, asterisk (AudioSocket + ARI), twilio, outbound
  reminders.py          reminder / follow-up calls with quiet hours
configs/default.yaml, configs/clinic.example.yaml, configs/lab/scenarios.yaml
docs/                   project-status, demo-guide, fine-tuning-plan, research/, telephony-options,
                        asterisk-setup, carrier-inquiry, model-selection
```
