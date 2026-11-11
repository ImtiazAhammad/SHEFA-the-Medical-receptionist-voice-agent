# Decisions log

| Date (BST) | Decision | Why | Alternatives considered |
|---|---|---|---|
| 2026-11-04 | Next.js (Vercel) + Python LiveKit Agents worker + Supabase (Singapore) | WebRTC, interruption handling and one-line engine swaps from LiveKit; Python keeps tools, validation and extraction in one place; Singapore is the nearest Supabase region to Dhaka | Single Next.js app with a browser-side realtime SDK |
| 2026-11-04 | ~~Output voice fixed to Azure Neural TTS `bn-BD`~~ (superseded) | Native Bangladeshi voice | — |
| 2026-11-04 | **Gemini only:** `gemini_live` = Gemini 3.8 Live with `language="bn-BD"` (default); `gemini_pipeline` = Gemini transcribe-live (`bn-BD`+`en-US`, custom vocabulary) → 2.5 Flash → 3.8 Flash TTS with Dhaka-accent instructions | Azure requires a paid/card-verified account (owner could not sign up free); edge-tts is unofficial and returned HTTP 503 on first use; probe showed 3.8 Live accepts `bn-BD` (2.5 native audio rejects it) and no Live model supports text-only output, ruling out a Live + separate-TTS hybrid | Azure bn-BD voices, edge-tts, OpenAI Realtime |
| 2026-11-04 | Live voice: **Kore** (`GEMINI_LIVE_VOICE=Kore`) | Owner listened to Kore / Leda / Aoede `bn-BD` samples and picked Kore as the most natural Dhaka receptionist | Leda, Aoede |
| 2026-11-04 | 25 ms fade-out + 150 ms silence on the last frame of every agent utterance | Owner heard noise at the end of samples; analysis showed an abrupt cut (click), not model noise | Leave raw output |
| 2026-11-04 | Demo clinic modelled on One Smile Dental Lounge, Uttara (public Facebook info); hours, fees and two doctors are demo values; UI labelled "Demo, not affiliated" | Realistic Bangladeshi clinic context for the reviewer | Fully fictional clinic |
| 2026-11-04 | Tools take short `slot_code` / `appointment_code` handles (S1, A1) issued earlier in the same call instead of UUIDs | Voice LLMs mangle long ids; codes also stop the model from acting on any appointment it was not shown in this call | Pass doctor UUID + ISO time |
| 2026-11-04 | Privacy enforced in tools, not only in the prompt: `find_appointments` / `recall_caller_history` need name **and** number to match and return the same reply for "unknown number" and "wrong name"; clinic info never carries personal staff fields; reschedule/cancel only accept codes verified in this call | Prevents patient enumeration and doctor-contact leaks even if the model is talked into trying | Prompt-only refusal |
| 2026-11-04 | Deterministic guardrail audit: caller turns are scanned for private-staff-info, other-patient, prompt-injection, medical-advice, emergency and off-topic requests; agent turns for unexpected phone numbers. Hits are written to `call_events` | Makes every probe and any possible leak visible to staff, independent of what the model said | Rely on the model alone |
| 2026-11-04 | Caller memory: after name + number verification the agent loads the last 3 call summaries, open callbacks and upcoming appointments; finalize links enquiry-only calls to the caller's patient record | Follow-up calls continue from the previous call without re-asking (owner request) | Caller-ID lookup (not available for browser calls; planned for SIP) |
| 2026-11-04 | Post-call finalize runs inside the worker's shutdown hook (90 s budget); FastAPI exposes the same function for the portal's Reprocess button | No network hop on the success path; one implementation | Separate HTTP call to FastAPI at hang-up |
| 2026-11-04 | Reschedule = cancel old → insert new (`rescheduled`) → restore old status if the insert hits the exclusion constraint | Compensating write keeps the DB consistent without a new SQL function migration | Postgres RPC in a transaction |
| 2026-11-04 | `doctor_schedules.weekday` uses Postgres `extract(dow)` (0 = Sunday … 6 = Saturday) | Matches SQL date functions | ISO weekday |
| 2026-11-04 | Evals run the production prompt and tools on text `gemini-3.8-flash` (switched from 2.5 Flash, which intermittently returned empty replies after tool results) with an in-memory clinic, judged by Gemini | Free, repeatable and offline from the DB; voice quality is tested separately by live calls | LiveKit audio simulation |
| 2026-11-04 | Web is on Next 16 (what `create-next-app` installed), with `cacheComponents`/partial prefetching off; route protection lives in `src/proxy.ts` (Next 16 name for middleware) | Avoids Suspense boundaries around every cookie read and keeps the LiveKit room from staying mounted on hidden routes | Pin Next 15 |
| 2026-11-04 | Third-party appointment requests are refused outright (even with the other person's number); the agent offers a callback to the patient instead | First eval run showed the model implying "give me her number and I'll tell you" | Allow family lookups with name + number |
| 2026-11-04 | Language rule moved to the top of the persona in English, plus an English-detection hint on each user turn | English callers were answered in Bangla because the persona, facts and tool messages are Bangla | Separate English persona |
| 2026-11-04 | Portal pre-loaded with 5 calls run through the production agent stack (tools, recorder, finalize) on text Gemini, stored with `engine = text_simulation` | Real data in every portal page before LiveKit keys exist, without fabricating rows | Hand-written seed rows |
| 2026-11-04 | Visitors can call with their own Gemini key, accepted only after a live test (voice-model access + one-token generation), re-tested server-side per call, sealed with AES-256-GCM in dispatch metadata, never stored | Reviewers are not blocked by our free-tier quota (the TTS daily limit was hit during the video build); owner required that no key is accepted untested | Plain key in metadata; no BYOK |
| 2026-11-04 | Video narrated by Nila (Gemini TTS, Kore voice) over Playwright recordings, rendered by `scripts/video/make_video.py` | Owner asked for a Bangla walkthrough in Nila's voice covering every feature; reproducible after each change | Manual screen recording only |

## Voice test results

Probe (text-prompted, 4 Nov): `gemini-3.8-live` bn-BD first audio 1.59–1.66 s across Kore/Leda/Aoede; `gemini-3.1-flash-live-preview` 1.73 s; Flash TTS 6.5–7.3 s for a 20 s paragraph (non-streamed).

Fill in after running the README §3 test script by voice (scores 1–5).

| Engine / voice | Sounds Bangladeshi | Natural phrasing | Code-switching | Digits | Names | Latency (s) | Barge-in | Total |
|---|---|---|---|---|---|---|---|---|
| gemini_live / Kore | | | | | | | | |
| gemini_live / Leda | | | | | | | | |
| gemini_pipeline / Aoede | | | | | | | | |

## Free-tier-only rule (owner requirement)

Every service must run on a free tier; no paid usage.

| Service | Free tier used | Watch out for |
|---|---|---|
| Google AI Studio (Gemini 2.5 Flash / Live) | Free API key | Per-minute request limits; fall back to `gemini-2.5-flash-lite` if a call hits 429 |
| LiveKit Cloud | Build (free) plan | Monthly agent-session minutes |
| Supabase | Free project (Singapore) | Project pauses after a week idle; keep it active until assessment ends |
| Vercel | Hobby | None for this demo |
| GitHub | Free private repo | Add reviewers as collaborators or make public at submission |
| Agent hosting | LiveKit Cloud agent deploy (free plan) or Render free web service + uptime ping | Render free sleeps when idle |

No OpenAI or Azure usage.
