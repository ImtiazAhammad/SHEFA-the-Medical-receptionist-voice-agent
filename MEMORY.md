# Sefa Medical Voice Agent

## What This Is

HIPAA-compliant, bilingual (English/Bangla) voice AI medical receptionist. Automates patient calls with real-time STT, language detection, LLM-powered conversation, and TTS response — all through Twilio Media Streams.

## Quick Start

```bash
# Install (with local models)
uv sync --extra local-stt --extra local-tts

# Configure for local mode (Ollama + Whisper + Piper)
cp .env.example .env   # no API keys needed for local mode

# Run
uv run uvicorn sefa.main:app --port 8000 --reload

# Dashboard
open http://localhost:8000/dashboard
```

## Architecture

```
Phone Call -> Twilio Media Streams -> WebSocket
                                         |
                                    Voice Pipeline
                                    STT -> Language Detect -> LLM -> TTS
                                         |                    |
                                    Session Manager      Tool Calls
                                                       (9 tools)
```

## Pipeline Providers (configurable in configs/default.yaml)

| Component | Local Option | Cloud Option |
|-----------|-------------|--------------|
| STT | faster-whisper (GPU) | OpenAI Whisper API, ElevenLabs Scribe |
| LLM | Ollama (qwen3-coder-next) | OpenAI GPT-4o, Anthropic Claude |
| TTS | piper-tts | ElevenLabs Multilingual |

## API Endpoints

- `GET /health` — health check
- `GET /dashboard` — web dashboard
- `GET /api/v1/sessions` — active calls
- `GET /api/v1/sessions/{call_sid}` — session detail
- `POST /api/v1/calls/outbound?to_number=...` — make outbound call
- `GET /api/v1/config` — pipeline config
- `GET /api/v1/tools` — LLM tool schemas

## 9 LLM Tool Functions

1. `verify_patient` — identity verification (name/DOB/phone/MRN)
2. `check_appointment_slots` — query available slots
3. `book_appointment` — book for verified patient
4. `cancel_appointment` — cancel existing
5. `reschedule_appointment` — move to new date/time
6. `get_doctor_info` — doctor profile and availability
7. `lookup_patient_history` — recent visits, medications
8. `send_confirmation` — bilingual SMS/email
9. `transfer_to_human` — escalate to human receptionist

## Hardware Requirements (Local Mode)

- GPU: NVIDIA with 16GB+ VRAM recommended (tested on RTX 4060 Ti)
- RAM: 16GB+
- Storage: ~60GB for models (Ollama qwen3-coder-next + Whisper large-v3)

## Project Structure

```
src/sefa/
  main.py              # FastAPI app, routes, dashboard
  config/settings.py   # Pydantic config from YAML
  models/              # STT/TTS/LLM adapters
  pipeline/            # Voice pipeline + language detection
  session/manager.py   # Session management
  tools/               # LLM function-calling tools
  telephony/           # Twilio integration
  integrations/        # Calendar, EHR, notifications
  static/index.html    # Web dashboard
  utils/               # Compliance, logging
```
