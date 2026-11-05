# Client demo plan (Linux, 12 GB GPU)

The client judges conversation quality first: how the agent handles a patient's request and what it
does next. This plan gets that ready on the 12 GB Linux machine in two days. Background and the full
scenario table are in [`demo-guide.md`](demo-guide.md).

Fine-tuning is not part of this plan. It needs corrected training data that two days won't produce,
and [`fine-tuning-plan.md`](fine-tuning-plan.md) fits on 12 GB when the time comes.

## Current state

- The browser demo code is in place: chat and talk in `/console`, 19 lab calls, booking, emergency
  handover, reminders.
- No conversation has been judged yet, and the docs say nobody has listened to the Bangla voice.
  This is the main demo risk.
- The measured numbers in the docs come from a 16 GB card. Re-measure VRAM on the 12 GB card.
- On Windows, 1,220 tests passed and 11 failed. Re-run `uv run pytest` on Linux and compare. CI runs
  on Linux with Python 3.12.

## Setup

```bash
git pull
sudo apt install espeak-ng
uv sync --extra local-stt-gpu --extra kokoro
uv pip install transformers huggingface_hub   # only for the one-time speech model conversion
```

Start Ollama with the low-memory settings. If it already runs as a service, stop that first or these
settings won't apply.

```bash
OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0 OLLAMA_KEEP_ALIVE=-1 ollama serve
```

In a second terminal, pull the model **before** running `shefa doctor` or `shefa fetch-models`.

```bash
ollama pull gemma2:9b
uv run shefa setup          # prints your console token once; save it
uv run shefa fetch-models
uv run shefa doctor         # every line should say ok
```

## Testing the models

| What you're testing | Command | What to check |
|---|---|---|
| Conversation and actions | `uv run shefa lab run` | Right action, right day, emergency handover, no medicine advice |
| How it sounds | `uv run shefa lab run --audio` | Listen to every reply |
| Hearing a caller | `uv run shefa lab run --speech` | Synthetic patient over a simulated phone line; real callers will be harder |
| Which voice is best | `uv run shefa lab voices --voice piper:models/piper/bn_BD-google-medium.onnx --voice azure:bn-BD-NabanitaNeural` | Needs an Azure key; 2-3 Bangladeshi listeners score it blind |
| Other language models | `PYTHONPATH=src python scripts/bench_router.py gemma2:9b gemma4:e4b qwen3.5:9b` | Pull them first; switch only at 11/12 or better on the right tool, 98%+ Bangla script, under 1 s to first token |

Reports are written to `lab-report/report.html` and `voice-test/index.html`. Add
`--only bn-booking,emergency-bn` to run some calls. To try another language model, set both
`pipeline.llm.model` and `models.adapters.llm_local.model` in `configs/local.yaml`, then re-run the
lab.

## Two-day plan

**Day 1: find the problems**

1. Finish setup, run `lab run --audio` and listen to all 19 calls.
2. Run `nvidia-smi` during a call and confirm at least 1 GB is free.
3. Run the blind voice test. If the Piper voice sounds robotic, use Azure for the demo.
4. List what fails and fix those first.
5. Decide how the client will reach the demo (see open items) and test it.

**Day 2: fix and rehearse**

1. Fix the failures, mostly in the prompt and guard rails, and re-run the lab after each change.
2. Run `lab run --speech`, then rehearse live at least three times on the demo network.
3. Keep the lab report with audio as a backup in case the live demo fails.

## Demo order

Start the server with `uv run shefa serve --host 0.0.0.0 --https` and open `/console`.

1. A Bangla booking, with the booking appearing under **Today**.
2. A switch to English mid-call.
3. A doctor on leave, then a request for medicine advice.
4. Chest pain in the middle of a booking, the strongest moment.
5. The agent calling you, to show how reminders sound.

## Fallbacks

Use `uv run shefa setup --force --voices azure` for the voice, adding `--profile gemini` for the
language model. Keys go in `.env`. `--force` issues a new token. Both send conversation text off the
machine, so use invented patients only, and tell the client if the voice is a cloud one.

## Open items

- **How the client reaches the demo:** `--host 0.0.0.0` only works on the same network. A remote
  client needs a secure tunnel, tested on Day 1.
- **`shefa doctor` crash:** `llm_status` in `src/shefa/model_fetch.py` raises `TypeError` when Ollama
  has no models, because `/v1/models` returns `data: null`. Pulling a model first avoids it.
- **Hardcoded phone numbers:** `src/shefa/static/test-call.html` and
  `docs/designs/shefa-spec-epic-plan.md` contain real phone numbers. Don't open `/test-call.html` in
  front of the client.

## Knowledge graph

`graphify-out/` holds the built graph. Query it with `graphify query "<question>"`, and refresh it
after code changes with `graphify update .`. Rebuild the HTML view with `graphify export html`.
