# ByteVoice Bangla

**An AI receptionist that answers a Bangladeshi clinic's phone in natural Dhaka Bangla, books appointments into a real database, and shows every call to staff within a minute.**

Built for the StrategyByte AI Engineer task. Demo clinic: One Smile Dental Lounge, Uttara (public info; hours, fees and two doctors are demo values; not affiliated). All patient data is fake.

| | Link |
|---|---|
| Landing page (talk to Nila) | https://bytevoice-bangla.vercel.app |
| Staff portal | https://bytevoice-bangla.vercel.app/portal (reviewer login in the submission email) |
| Video (≤ 3 min, narrated by Nila in Bangla) | https://drive.google.com/file/d/1eLAMqDfkPj_XJdeIz9zlIhM932S0M3ug/view?usp=drive_link |
| Repository | https://github.com/Rifat024/bytevoice-bangla |

## Try it in 90 seconds

1. Open the landing page, press **বাংলা কলারের সাথে কথা বলুন / Talk to our Bangla caller** and allow the microphone (headphones help).
2. Book a check-up in Bangla, for example: "আসসালামু আলাইকুম, দাঁতে ব্যথা, appointment নিতে চাই" → give a name → give a number the way people do ("জিরো ওয়ান সেভেন ডাবল পাঁচ …") → "আগামী রবিবার সন্ধ্যায়". Nila reads the number back digit by digit and the full booking before confirming.
3. Try to break it: ask "কোন ওষুধ খাবো?", "ডাক্তারের বাসার ঠিকানা দেন", or ask about someone else's appointment. Interrupt her mid-sentence. Stay silent.
4. Hang up, log in to the portal: the call is at the top with the transcript, validated fields, tool timeline, latency and the guardrails that fired. Call again with the same name and number and Nila remembers the previous call.

## Architecture

```
Browser (Next.js 16 on Vercel)
  landing + 3D orb call UI ──WebRTC audio──► LiveKit Cloud ◄── Python agent worker (LiveKit Agents 1.8)
  portal (Supabase Auth + Realtime)             (rooms)          Gemini Live (bn-BD, voice "Kore")
        │  POST /api/livekit/token                                 10 function tools → validators
        │  (rate-limited, 10-min token, dispatches the agent)      live transcript / events / latency
        ▼                                                          post-call Gemini extraction
Supabase Postgres (Singapore) ◄──────── service-role writes ───────┘
  RLS on every table · Realtime on calls / transcript_turns / call_events
```

**Why these providers**
- **Gemini Live with `language="bn-BD"`** (free): one model hears, reasons and speaks Bangladeshi Bangla, with native barge-in and tool calling; first audio ≈ 1.6 s in probes. 2.5 native-audio models reject `bn-BD`; Azure's `bn-BD` voices needed a paid account. A switchable `gemini_pipeline` engine (Gemini STT → Flash → Gemini TTS) is kept for comparison (`VOICE_ENGINE`).
- **LiveKit Agents**: production WebRTC, VAD, interruption handling and transcription streams; the engine swaps in one line.
- **Supabase in Singapore** (closest region to Dhaka): real Postgres constraints, Auth for the portal and Realtime so the portal updates while the call is happening.
- **Next.js on Vercel**: one deploy for the landing page and the authenticated portal.

Full decision log with alternatives: [`docs/decisions.md`](docs/decisions.md).

## How a call becomes data

1. The CTA calls `/api/livekit/token`, which creates room `call-<uuid>` and dispatches agent `bytevoice-bn`.
2. The agent loads the clinic catalogue from Postgres (fees, doctors, chamber hours) into the persona, inserts a `calls` row and tells the browser its `call_id`.
3. Every final utterance is written to `transcript_turns` with its offset; per-turn latency and every tool call/result go to `call_events`. The portal subscribes via Realtime.
4. Tools validate before writing: `patients` upsert (phone as E.164), `appointments` (a GiST exclusion constraint makes double booking impossible), `callback_requests`.
5. At hang-up the worker runs Gemini 2.5 Flash with a JSON schema over the transcript → `call_extractions`, bn/en summaries, English translation per turn and the final `outcome`. Validators re-check every field; data written by tools wins over the model and disagreements are flagged in `confidence`. Staff can re-run this with **Reprocess**.

Schema, ERD and access rules: [`docs/data-model.md`](docs/data-model.md) (also rendered in the portal at `/portal/data-model`).

## The receptionist

- **Flow:** greet → name (read back) → phone (validated, read back digit by digit) → reason → preferred day/time ("আগামী রবিবার সন্ধ্যা" resolved in Asia/Dhaka) → up to three real free slots → full read-back → book only on an explicit yes → summary → goodbye.
- **Validation** (`apps/agent/src/agent/normalize/`): Bangla numerals and spoken digit words in both languages, "ডাবল/ট্রিপল", `+880/880/0` prefixes, operator prefixes 013–019; relative dates (আজ, কাল, পরশু, আগামী/এই/পরের সপ্তাহের <বার>, ১০ তারিখ, ১৫ ডিসেম্বর), time words (সকাল … রাত, সাড়ে/সোয়া/পৌনে ৫টা); Fridays, past dates and >60 days rejected.
- **Safety:** no medicine, dose or diagnosis (offers a doctor callback); emergencies → hospital or 999; facts only from the database.
- **Privacy:** doctors' and staff's personal numbers, home addresses and family are never stored or shared; another patient's appointments are never revealed, not even when the caller offers that person's number; `find_appointments` and `recall_caller_history` require the caller's own name **and** number and give the same answer for "unknown number" and "wrong name", so they cannot be used to discover who is a patient. Prompt-injection and off-topic requests are declined politely. Every probe is logged as a guardrail event, and agent speech is scanned for phone numbers that are neither the caller's nor the clinic's.
- **Follow-up calls:** after the name + number check, Nila loads that caller's last three call summaries, open callbacks and upcoming appointments and continues from there.
- **Turn-taking:** silence → "হ্যালো, শুনতে পাচ্ছেন?" then a polite goodbye; 5-minute cap; a 25 ms fade removes the click at the end of each utterance.

## Quality

- `apps/agent`: **97 unit tests** (`uv run pytest`): normalisers, booking/availability rules, double booking, confirmation gate, privacy (no enumeration), caller memory, extraction validation, guardrail detectors.
- **Conversation evals** (`uv run python -m evals.run_evals`): the production prompt and tools on Gemini with an in-memory clinic and an LLM judge, 11 scenarios: booking with code-switching, bad phone recovery, medical-advice refusal, doctor's private info, other patient's privacy, prompt injection, off-topic, emergency, English caller, reschedule, returning caller. Latest run: **11/11 passed** on `gemini-3.8-flash` (the text sibling of the Live model); transcripts in [`docs/eval-report.md`](docs/eval-report.md).
- `apps/web`: `pnpm lint`, `pnpm build`, strict TypeScript; zod at every boundary.

## Bring your own Gemini key

Under the call button, "Test with your own Gemini API key" lets a reviewer call Nila on their own quota. A key is **only accepted after it passes a live test**: the server checks that it can reach Nila's voice model (`gemini-3.8-live`) and that a one-token generation succeeds, and reports invalid keys, missing model access or exhausted quota in Bangla and English. The token route re-tests the key before every call (cached for 10 minutes by its SHA-256 hash), so the browser cannot skip the test. The key stays in that tab's session storage, is sealed with AES-256-GCM (key derived from `INTERNAL_API_TOKEN`, shared only by the web server and the agent) before it goes into LiveKit dispatch metadata, and the agent uses it for that one call's voice session and post-call extraction. It is never stored or logged; the call's timeline records only that a visitor key was used.

## Security and secrets

No secrets in the repo (`.env*` ignored; `.env.example` files list names only). The browser only ever has the Supabase anon key and a 10-minute LiveKit token. RLS: `anon` may only insert leads; `authenticated` staff read everything and may update only callback status; the agent writes with the service-role key server-side. The reprocess API requires a shared bearer token and a logged-in portal user.

## Run locally

```bash
# agent (Python 3.13, uv)
cd apps/agent && cp .env.example .env.local   # fill in keys
uv sync && uv run python -m agent.worker download-files
uv run python -m agent.worker dev              # or: console (talk through your Mac mic)
uv run uvicorn agent.api.app:app --port 8000   # reprocess API

# web (Node 22+, pnpm)
cd apps/web && cp .env.example .env.local && pnpm install && pnpm dev
```

Database: `supabase/migrations/` and `supabase/seed.sql`. Deploy: `scripts/deploy-web.sh` (Vercel) and `scripts/deploy-agent.sh` (LiveKit Cloud; the Dockerfile runs the voice worker). `agent.serve` runs the worker and the reprocess API together for single-container hosts. Video: `scripts/video/make_video.py` renders the narrated walkthrough (Nila's TTS voice over Playwright recordings).

## Known limitations and next steps

- Browser calls only; real phone numbers need LiveKit SIP + a Bangladeshi trunk, which would also give caller ID for instant recognition.
- Text-mode evals exercise dialogue policy and tools, not speech recognition; accent and ASR accuracy were judged by listening (see `docs/decisions.md`).
- Recordings are not stored yet (the schema has `recording_path`; plan: LiveKit egress to a private bucket with signed URLs and a retention policy).
- Single clinic; multi-tenant needs `clinic_id` scoping in RLS policies and per-clinic agent config.
- Identity on a voice call is name + number, which is reasonable for appointment changes but not for medical records; anything sensitive goes to a staff callback.
- Free tiers: Gemini rate limits and the Supabase free project pausing after a week idle.

Build notes and the original plan: [`docs/BUILD_PLAYBOOK.md`](docs/BUILD_PLAYBOOK.md).
