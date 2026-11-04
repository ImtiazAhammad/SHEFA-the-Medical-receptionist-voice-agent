# Showing SHEFA to a client (no phone line needed)

A clinic owner wants to know two things: **does it sound natural**, and **what happens when the
caller does something unexpected**. This guide gets a machine ready and shows both, without a SIP
trunk. The model choices behind it are in
[`research/bangla-english-voice-models-2026-11.md`](research/bangla-english-voice-models-2026-11.md).

## 1. Choose a setup

| Setup | Needs | What runs where | Command |
|---|---|---|---|
| **Fully local** (the product) | NVIDIA GPU (12 GB), [Ollama](https://ollama.com) | Everything on this machine | `shefa setup` |
| **Hybrid, free** | Any small GPU or CPU, a free Gemini key | Speech and voices local, language model on Gemini | `shefa setup --profile gemini` |
| **Hybrid, free (backup)** | A free Groq key | Same, language model on Groq | `shefa setup --profile groq` |
| **Laptop, no GPU** | An OpenAI key | Speech recognition and language model on OpenAI | `shefa setup --profile openai` |
| **Reference voices** | A free Azure Speech key | Add to any of the above: Azure bn-BD neural voices | `... --voices azure` |

Every setup except "fully local" sends conversation text off the machine. Use only invented
patients in demos, never real ones.

```bash
uv sync --extra local-stt-gpu --extra kokoro      # Kokoro (English voice) also needs espeak-ng
```

```bash
uv run shefa setup                                # or one of the profiles above; prints your token
```

```bash
uv run shefa fetch-models                         # voices, Bangla speech model, `ollama pull`
```

```bash
uv run shefa doctor                               # every line should say ok
```

Keys go in `.env` (`GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENAI_API_KEY`, `AZURE_SPEECH_KEY`,
`AZURE_SPEECH_REGION`).

**12 GB card settings** (from the research VRAM budget). Start Ollama like this, so gemma2:9b, the
Bangla speech model and the English language detector fit together (about 10 GB):

```bash
OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0 OLLAMA_KEEP_ALIVE=-1 ollama serve
```

Close anything else that uses the GPU, ideally including the desktop session, and confirm with
`nvidia-smi` that at least 1 GB is free during a call.

## 2. Rehearse with the conversation lab

The lab plays 19 phone calls against the real agent and a fresh copy of the sample clinic, and
writes a report you can show the client:

```bash
uv run shefa lab run --audio            # every reply spoken with the real voices
```

```bash
uv run shefa lab run --speech           # also: patient voiced, sent over a simulated 8 kHz phone line, transcribed
```

Open `lab-report/report.html`. Each call shows the transcript, a player for every line and for the
whole call, the action the agent took, how long it took to decide and to start speaking, the
clinic database after the call, and the checks:

- every reply: it replied, no internal text leaked, it was brief, it was in the caller's
  language, and the Bangla used Bangla script;
- each scenario: the right action ran (booked, cancelled, moved), the booking is on the right day,
  the call was handed to a human when it had to be, and forbidden words (medicine names) were
  never said.

`--only bn-booking,emergency-bn` runs a few. `shefa lab list` lists them. To add a case, add an
entry to `configs/lab/scenarios.yaml`: scripted `turns`, or a `persona` for the language model to
play. Dates are written `{bn:Sun}` / `{en:Sun}` / `{iso:Sun}` so a scenario never goes stale.

Run the lab after every change of model, prompt or voice, and compare the reports. A scenario
that "needs work" is the list of things to fix before the client sees them.

### What the scenarios show the client

| The client asks | What SHEFA does | Scenario |
|---|---|---|
| Can it book in Bangla? In English? | Books, reads back day, time, doctor and a reference number | `bn-booking`, `en-booking` |
| We talk Bangla with English words | Answers in Bangla | `code-switch` |
| What if the caller switches to English? | Switches with them | `language-switch` |
| A Hindi speaker calls? | Does not answer in the wrong language; offers the front desk | `other-language` |
| The doctor is on leave / it's Friday | Says so; books nothing; offers another time | `doctor-on-leave`, `friday-closed` |
| A doctor we don't have | Says so; never invents a doctor | `unknown-doctor` |
| "Monday... no, Wednesday" | Books the corrected day | `self-correction` |
| "Which medicine should I take?" | Never prescribes; offers a doctor | `medical-advice` |
| Chest pain, fainting | Hands the call to a human at once, even mid-booking | `emergency-bn`, `emergency-mid-booking` |
| "Are you a robot?" / "Hello? Hello?" | Short, honest, back to the point | `are-you-a-robot`, `hello-hello` |
| A rambling elderly caller, an impatient one | Unscripted calls played by the model | `persona-grandmother`, `persona-busy-worker` |
| Can it move or cancel? | Moves or cancels the caller's own booking only | `reschedule`, `cancel` |

## 3. Pick the voice by ear

```bash
uv run shefa lab voices --voice piper:models/piper/bn_BD-google-medium.onnx --voice azure:bn-BD-NabanitaNeural
```

```bash
uv run shefa lab voices --language en --voice kokoro:af_heart --voice kokoro:bf_emma --voice azure:en-IN-NeerjaNeural
```

Open `voice-test/index.html` and have two or three Bangladeshi colleagues score each line from 1
to 5 without knowing which voice is which, then press Reveal. Azure's Nabanita is the reference to
beat. If the local Bangla voice is far behind, that is the signal to record a voice talent (see the
fine-tuning plan).

## 4. The live demo

```bash
uv run shefa serve --host 0.0.0.0 --https
```

Open the printed `https://<ip>:8000/console` on a phone or laptop and paste the token.

1. **Type to the agent** with the chips (departments, booking, a doctor's hours, an emergency).
   It works without a microphone and shows the booking appear under **Today**.
2. **Tap the phone button and talk**, in Bangla, then switch to English.
3. **"Have the agent call me"**, then answer: this is how reminder calls sound.
4. Open the lab report for the cases you did not try live.

## 5. What to say honestly

- The phone line in the lab is simulated (8 kHz mu-law); a real trunk adds its own noise and
  delay. The patient voice in `--speech` mode is synthetic, so real callers will be harder.
- English words inside a Bangla sentence come back from the Bangla speech model in Bangla script
  (অ্যাপয়েন্টমেন্ট). The agent understands them that way.
- The Bangla voice has not yet been rated by Bangladeshi listeners; step 3 is that test.
- Measured numbers come from a 16 GB card; re-measure on the 12 GB card with the checklist at the
  end of the research report.
