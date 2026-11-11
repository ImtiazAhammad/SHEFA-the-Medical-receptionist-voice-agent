# ByteVoice Bangla — Build Playbook

> **Working title:** ByteVoice Bangla, StrategyByte's AI receptionist for Bangladeshi dental clinics and hospitals.
> **Purpose of this file:** the single source of truth for building the StrategyByte AI Engineer take-home.
> Any Claude Code session, on any account, can pick up the work from here. Start at
> [§12 Progress checklist](#12-progress-checklist-resume-here) and continue from the first unchecked box.
>
> **Deadline: Thursday 5 November 2026, 23:59 BST (UTC+6).** Aim to finish by 21:00 BST, which leaves three hours of buffer.
>
> This file becomes the submission README in Phase 6. The playbook then moves to `docs/BUILD_PLAYBOOK.md`.

---

## 1. Brief digest

Source: `StrategyByte_AI_Engineer_Task_Brief.pdf` (in this folder) and the HR email "AI Engineer Role: Task Brief and Submission Details" (4 Nov 2026).

StrategyByte (an Australian company, product **ByteVoice**) is launching in Bangladesh. We need to build a working demo **end to end**:

| Part | Component | Must have |
|---|---|---|
| A | Landing page | At least 3 sections, with the **hero as the main focus**. Responsive, deployed publicly. **3D in the hero = plus.** Bilingual toggle = plus. |
| B | Hero CTA | A prominent **"Talk to our Bangla caller"** button that starts a live **browser** voice call (mic permission, WebRTC/web SDK). Shows the *connecting / live / ended* states and handles mic-permission and connection errors gracefully. |
| C | Bangla caller | Natural colloquial Bangla receptionist for a clinic. Handles code-switching (Bangla and English), numbers, dates and times, and Bangladeshi names. Flow: greet → name (confirm) → phone (read back digit by digit) → reason → preferred date/time ("next Sunday evening") → book or answer the enquiry → decline out-of-scope requests (medical advice) and offer a human callback → close with a summary. |
| D | Data portal | Login (reviewer credentials go in the submission). Call list: date, time, caller, duration, status; searchable/filterable. Per-call view: extracted fields (name, phone, reason, preferred date/time, outcome), full transcript with speaker labels and timestamps, and status (booked / enquiry / follow-up needed / incomplete / failed). Show **how the data is organised, structured and stored**. |

**What success looks like (our acceptance test):** the reviewer opens the landing page, clicks the hero button, books a dental appointment in Bangla and hangs up. They then log in to the portal and, **within 1–2 minutes**, see that call, its transcript and the patient's details neatly organised.

**Evaluation weights:** Bangla caller quality **30%** · Data structure & portal **25%** · Hero & landing design **20%** · Code quality & architecture **15%** · Docs & presentation **10%**.

**Assessed on the caller:** natural Bangla (not literal translation), low latency, smooth turn-taking including interruptions, accurate capture of names, numbers, dates and times, recovery from mishearing, silence and mixed Bangla/English, confirmation before booking, and safe behaviour (no medical advice, no invented information).

**Be ready to explain:** the schema and its relationships; where data is stored (DB, region, recordings); how data moves from the live call into storage; how extracted fields are validated (Bangla digits, phone formats); why each provider was chosen.

**Rules:** any tools or AI assistants are allowed; free tiers are fine. Use **fake patient data only**. **No secrets in the repo.** Keep everything live until the assessment is complete. Be honest about what is incomplete: a solution that works end to end beats a polished one that only partly works.

**Submission:** email `hr@strategybyte.com.au` with the subject `AI Engineer Task Submission: Rifat Bin Siraj` and 4 links: landing page, portal (plus reviewer login), GitHub repo (make sure they have access), and the video (≤3 min).

---

## 2. Architecture

```
┌────────────────────────── Browser ──────────────────────────┐
│ Next.js 15 (Vercel)                                         │
│  • Landing + 3D audio-reactive orb (React Three Fiber)      │
│  • Call widget (livekit-client)  ──── WebRTC audio ───┐     │
│  • Portal (Supabase Auth + Realtime)                  │     │
└───────┬───────────────────────────────────────────────┼─────┘
        │ POST /api/livekit/token                       │
        │ (rate-limited, 10-min TTL, dispatches agent)  ▼
        │                                     ┌──────────────────┐
        │                                     │ LiveKit Cloud    │
        │                                     │ (SFU + rooms)    │
        │                                     └────────┬─────────┘
        │                                              │ agent joins room
        │                         ┌────────────────────▼─────────────────────┐
        │                         │ apps/agent  (Python 3.12)                │
        │                         │  • livekit-agents 1.x worker             │
        │                         │    VOICE_ENGINE = gemini_live |          │
        │                         │                   gemini_pipeline        │
        │                         │  • function tools → validators           │
        │                         │  • live persistence (turns, events)      │
        │                         │  • FastAPI: /health, post-call           │
        │                         │    extraction, /calls/{id}/reprocess     │
        │                         └────────────────────┬─────────────────────┘
        │                                              │ service-role writes
        ▼                                              ▼
┌──────────────────────────────────────────────────────────────┐
│ Supabase (region ap-southeast-1, Singapore: closest to BD)   │
│  Postgres (schema §4) · Auth (staff/reviewer) · Realtime     │
│  Storage bucket `recordings` (private, signed URLs; stretch) │
└──────────────────────────────────────────────────────────────┘
```

**Why this stack (keep these lines for the README and the interview):**
- **LiveKit Agents (Python):** production-grade WebRTC, VAD and interruption handling, turn detection, transcription events and function tools. The LLM/voice engine swaps with one line, which makes the bake-off cheap and the "provider choice" story concrete. ByteVoice-class products are built this way.
- **Gemini 3.8 Live with `language="bn-BD"`:** one free model hears, thinks and speaks Bangladeshi Bangla, with built-in interruption handling and tool calling. Fallback `gemini_pipeline` (Gemini STT → Flash → Gemini TTS with a Dhaka-accent instruction) is also free on the same key.
- **Python agent server:** the AI-engineering depth lives here: tools, validators, extraction, evals.
- **Supabase in Singapore:** managed Postgres with real constraints, Auth for the portal login, and Realtime so the portal updates **while the call is happening**. Singapore is the nearest region to Dhaka.
- **Next.js on Vercel:** one deploy for the landing page and the portal, with server components for authenticated portal reads.

---

## 3. Phase 0: Voice engine (Gemini only, free)

**Owner requirements:** native **Bangladeshi** Bangla (not Indian/Kolkata), and **free tools only**. Azure Speech needs a paid/card-verified account and was dropped; edge-tts (unofficial) failed with HTTP 503 on first use and was rejected as unreliable.

**Finding (probed 4 Nov with the free AI Studio key):** `gemini-3.8-live` and `gemini-3.1-flash-live-preview` accept the **`bn-BD` (Bangladesh) language code** with native audio output; `gemini-2.5-flash-native-audio-*` rejects `bn-BD`. No Live model allows TEXT-only output, so a "Live brain + separate TTS" hybrid is not possible. First audio ≈ 1.6 s (including connection setup) in text-prompted probes.

Engines in `apps/agent/src/agent/engines.py`, switched with `VOICE_ENGINE`:

| `VOICE_ENGINE` | Ears | Brain | Voice | Notes |
|---|---|---|---|---|
| `gemini_live` **(default)** | Gemini 3.8 Live (hears audio directly, `language="bn-BD"`) | same | Gemini Live voice (`GEMINI_LIVE_VOICE`, default `Kore`) | One model: lowest latency, built-in barge-in, input/output transcription on |
| `gemini_pipeline` | `gemini-3.5-transcribe-live` via `google.beta.GeminiSTT` (`bn-BD` + `en-US`, custom vocabulary) | Gemini 2.5 Flash | `gemini-3.8-flash-tts` with Dhaka-accent `instructions` | More control over voice style; higher latency (VAD + 3 hops) |

**End-of-turn click fix:** generated audio stops mid-waveform, which is heard as a click. `agent/audio/smoothing.py` holds back one frame and fades the last 25 ms, then adds 150 ms of silence. It is applied to both the realtime output node and the TTS node (unit-tested in `tests/test_audio_smoothing.py`).

**Voice samples** (Kore / Leda / Aoede on 3.8 Live; Aoede / Leda on 3.8 Flash TTS) were sent to the owner to pick the most Dhaka-sounding voice; record the pick in `docs/decisions.md`.

**How to try it (no LiveKit needed):** `cd apps/agent && uv run python -m agent.worker console` talks through your Mac mic and speakers (use headphones). Switch with `VOICE_ENGINE=gemini_pipeline uv run python -m agent.worker console`.

**Test script (speak it; log the scores in `docs/decisions.md`):**
1. "আসসালামু আলাইকুম, আমি একটা appointment নিতে চাই, দাঁতে খুব ব্যথা।"
2. Name: "আমার নাম তাহমিনা আক্তার"
3. Phone, mixed: "জিরো ওয়ান সেভেন, ডাবল পাঁচ, তিন দুই এক, নাইন এইট সেভেন" → expect a digit-by-digit read-back of `01755321987`. Then give a 10-digit number and expect "please repeat".
4. "আগামী রবিবার সন্ধ্যার দিকে হবে? রুহান স্যারের কাছে root canal করাতে চাই।"
5. Interrupt the agent mid-sentence.
6. "এই ব্যথার জন্য কোন ওষুধ খাবো?" → expect a polite decline plus a callback offer.
7. Stay silent for 10 s.

**Score 1–5 on each:** sounds Bangladeshi · natural phrasing · code-switching · digit accuracy · names (রুহান, তাহমিনা) · first-audio latency · barge-in smoothness. Keep `gemini_live` unless `gemini_pipeline` is clearly more Bangladeshi-sounding.

## 4. Data model (first-class deliverable)

**Applied 4 Nov 2026** to Supabase project `bytevoice-bangla` (ref `ajxqxqdlgxehhkfokmif`, Singapore, URL `https://ajxqxqdlgxehhkfokmif.supabase.co`).
- Schema: [`supabase/migrations/20261104073000_init_schema.sql`](../supabase/migrations/20261104073000_init_schema.sql)
- Seed: [`supabase/seed.sql`](../supabase/seed.sql)
- ERD, table guide, access control and validation rules: [`docs/data-model.md`](data-model.md)

Compared with the first sketch, the applied schema adds `doctor_services` (which doctor does which service), `leads` (landing-page form), the `call_overview` view (portal list), column-level update rights on callbacks, and FK indexes. `call_events.type` is now `event_type`.

Fixed IDs for code and env: clinic `a7c1e5d2-1b3f-4c8e-9d20-5e6f7a8b9c01`; doctors `d0c70001-0000-4000-8000-00000000000{1,2,3}` (Ruhan, Nusrat, Rakib); services `5e7f0001-0000-4000-8000-00000000000{1..7}`.

**RLS:** enable on all tables. `authenticated` gets **select** on everything (staff portal). `anon` gets nothing. Only the Python service writes, using the **service-role key** held server-side. Add the tables `calls`, `transcript_turns` and `call_events` to the `supabase_realtime` publication.

**Seed (`supabase/seed.sql`, fake data only):** 1 clinic modelled on the real **One Smile Dental Lounge** (ওয়ান স্মাইল ডেন্টাল লাউঞ্জ, House 30, Sector 11, Uttara, Dhaka, opposite Zamzam Tower; reference: https://www.facebook.com/OneSmileDL/). Lead doctor from the public page: ডা. মোঃ মুশফিকুর রুহান (micro-endodontist & aesthetic dentist); two more doctors are fictional (ডা. নুসরাত জাহান, ডা. রাকিব হাসান). Hours (Sat–Thu 10:00–21:00, Fri closed) and fees are **demo values**, not the clinic's real ones; label the landing page and portal "Demo, not affiliated with One Smile Dental". 7 services with BDT fees, weekly schedules, and the reviewer auth user (created via the Supabase Admin API or dashboard; the password goes only in the submission email).

**Talking points:** normalised patients (phone is the natural key, stored as E.164) · calls and turns are append-only · extractions are separate from raw transcripts (re-runnable with `/calls/{id}/reprocess`) · **double booking is impossible at the DB level** (gist exclusion) · events table = audit trail and latency metrics · enums give the portal clean filters.

---

## 5. Data flow (live call → storage → portal)

1. The visitor clicks the hero CTA → `POST /api/livekit/token` (Next route). It rate-limits per IP, creates the room `call-<uuid>`, and returns a token with a **10-min TTL** that has `RoomAgentDispatch(agent_name="bytevoice-bn")`.
2. The browser joins the room and publishes the mic. The agent worker joins on dispatch.
3. On session start the agent inserts a `calls` row (`in_progress`, `engine`, `after_hours`, computed in Asia/Dhaka).
4. On every final user or agent transcription (`conversation_item_added` / transcription events) the agent inserts a `transcript_turns` row with its `offset_ms`. The portal subscribes via Realtime, so the call appears **live**.
5. Tool calls → validators → DB writes (`patients` upsert, `appointments`, `callback_requests`). Each tool call and its result is logged to `call_events`, along with per-turn latency (end of user speech → first agent audio).
6. On disconnect, or the `end_call` tool, or the **5-min cap**, the agent sets `ended_at`, then calls the FastAPI `POST /calls/{id}/finalize`. That runs Gemini 2.5 Flash (text) with a **JSON schema** over the transcript to produce `call_extractions`, `summary_bn`/`summary_en`, English `text_en` per turn and the final `outcome`. The validators re-check all fields before writing; if they disagree with the tool data, the tool data wins and the disagreement is flagged in `confidence`.
7. If finalize fails, the call stays `completed` with outcome `incomplete` and an error event, and staff can press **Reprocess** in the portal.

**Tool contract (agent function tools):**

| Tool | Args | Behaviour |
|---|---|---|
| `get_clinic_info` | `topic: hours\|location\|services\|fees\|preparation\|doctors` | Returns DB facts only (bn + en). |
| `check_availability` | `date_text`, `time_hint?`, `service_code?`, `doctor_name?` | Resolves the relative date in Asia/Dhaka, validates against opening hours and schedules, returns up to 3 free slots. |
| `book_appointment` | `patient_name_bn`, `phone_spoken`, `service_code`, `doctor_id`, `slot_start_iso`, `confirmed: bool` | Rejects if `confirmed` is false, the phone is invalid or the slot is taken (handles the exclusion-violation error). Upserts the patient. |
| `find_appointments` | `phone_spoken` | Returns the caller's upcoming appointments (for reschedule/cancel). |
| `reschedule_appointment` | `appointment_id`, `new_slot_start_iso`, `confirmed` | Atomic: cancel and rebook in one transaction. |
| `cancel_appointment` | `appointment_id`, `confirmed` | Sets the status to `cancelled`. |
| `request_human_callback` | `reason`, `priority` | Creates a `callback_requests` row. |
| `end_call` | `summary_bn` | Agent says goodbye, then disconnects. |

---

## 6. Validation layer (`apps/agent/src/agent/normalize/`, pytest-covered)

- `digits.py`: Bangla digits `০১২৩৪৫৬৭৮৯` → ASCII. Spoken digit words in Bangla (শূন্য, এক, দুই … নয়) and English (zero/oh, one … nine), plus **"ডাবল/double X"** and **"ট্রিপল/triple X"** → digit string.
- `phone.py`: strip spaces and dashes; accept `+880`, `880` and `0` prefixes; validate `^01[3-9]\d{8}$` (operator prefixes 013–019); output E.164 `+8801XXXXXXXXX` plus a Bangla read-back string grouped as `০১৭১১ – ২৩৪ – ৫৬৭` (spoken digit by digit).
- `dates.py`: resolves "আজ, কাল/আগামীকাল, পরশু, আগামী <weekday>, এই <weekday>, next <weekday>, <n> তারিখ, <day> <month>" plus time hints "সকাল/দুপুর/বিকেল/সন্ধ্যা/রাত" and "সাড়ে/পৌনে/সোয়া <n>টা" in **Asia/Dhaka**. Rejects past dates and Fridays (closed), and snaps to opening hours.
- `names.py`: stores the Bangla script as spoken, plus a simple transliteration for `full_name_en` (the LLM proposes one and it is stored; no hard validation beyond non-empty and length).
- **Confirmation gate:** the agent must read back name → phone (digit by digit) → service → date/time and hear an explicit yes (হ্যাঁ / জি / ঠিক আছে / yes) before `book_appointment(confirmed=true)`. The tool itself refuses `confirmed=false`.

---

## 7. Agent persona & system prompt (draft; refine during bake-off)

Persona: **"নীলা" (Nila)**, receptionist at **ওয়ান স্মাইল ডেন্টাল লাউঞ্জ, উত্তরা**. Warm, polite, efficient. Uses the respectful আপনি form and everyday Dhaka Bangla, not textbook (সাধু) style. Keeps English loanwords patients actually use (appointment, doctor, scaling, root canal, filling, X-ray, fees, serial).

```text
তুমি "নীলা", ওয়ান স্মাইল ডেন্টাল লাউঞ্জ (উত্তরা, ঢাকা)-র রিসেপশনিস্ট। ফোনে রোগীদের সাথে কথা বলছ।

কথার ধরন:
- সবসময় আপনি সম্বোধন, ভদ্র কিন্তু স্বাভাবিক ঢাকার কথ্য বাংলা। বইয়ের ভাষা বা সাধু ভাষা না।
- ছোট ছোট বাক্য, এক টার্নে একটাই প্রশ্ন।
- রোগী ইংরেজি শব্দ মিশিয়ে বললে (appointment, scaling, root canal) তুমিও সেই শব্দগুলো স্বাভাবিকভাবে ব্যবহার করবে।
- রোগী পুরোপুরি ইংরেজিতে কথা বললে ইংরেজিতে উত্তর দেবে।

কাজের ধারা:
1. সালাম দিয়ে ক্লিনিকের নাম বলে জিজ্ঞেস করো কীভাবে সাহায্য করতে পারো।
2. নাম জিজ্ঞেস করে আবার বলে নিশ্চিত করো।
3. মোবাইল নম্বর নাও, তারপর প্রতিটি সংখ্যা আলাদা করে পড়ে শুনিয়ে নিশ্চিত করো। ১১ সংখ্যা না হলে আবার জিজ্ঞেস করো।
4. সমস্যা বা কোন সেবা লাগবে জেনে নাও।
5. পছন্দের দিন ও সময় জেনে check_availability দিয়ে খালি সময় দেখো, সর্বোচ্চ ৩টা অপশন বলো।
6. বুক করার আগে নাম, নম্বর, সেবা, ডাক্তার, দিন-সময় একসাথে বলে "ঠিক আছে?" জিজ্ঞেস করো; হ্যাঁ বললে তবেই book_appointment।
7. শেষে সংক্ষেপে কী ঠিক হলো বলে ধন্যবাদ জানিয়ে end_call।

কঠোর নিয়ম:
- কোনো ওষুধ, ডোজ, রোগ নির্ণয় বা চিকিৎসা পরামর্শ দেবে না। বিনয়ের সাথে বলবে এটা ডাক্তার দেখে বলবেন, এবং চাইলে ডাক্তারের কলব্যাকের ব্যবস্থা করবে (request_human_callback)।
- ফি, সময়, ডাক্তার, ঠিকানা: শুধু টুলের দেওয়া তথ্য বলবে, কখনো বানিয়ে বলবে না। না জানলে কলব্যাক অফার করবে।
- জরুরি অবস্থা (প্রচুর রক্তপাত, মুখ ফুলে শ্বাসকষ্ট) শুনলে সাথে সাথে নিকটস্থ হাসপাতালের জরুরি বিভাগে যেতে বলবে বা ৯৯৯-এ কল করতে বলবে।
- কিছু বুঝতে না পারলে আন্দাজ করবে না; ভদ্রভাবে আবার বলতে অনুরোধ করবে বা দুইটা অপশন দিয়ে জিজ্ঞেস করবে।
- আজকের তারিখ ও সময় (Asia/Dhaka): {now_dhaka}। শুক্রবার ক্লিনিক বন্ধ।
```

The worker injects `{now_dhaka}` and the clinic facts at session start. Silence handling: after ~6 s of user silence re-prompt ("হ্যালো, আপনি কি শুনতে পাচ্ছেন?"); after the second silence, say a polite goodbye and `end_call`. Hard cap: 5 minutes (protects free-tier quotas).

**Example opening (our own, not the brief's):** "আসসালামু আলাইকুম, ওয়ান স্মাইল ডেন্টাল থেকে নীলা বলছি। বলুন, আপনাকে কীভাবে সাহায্য করতে পারি?"

---

## 8. Landing page + 3D hero (`apps/web`)

**Sections (Bangla default, EN toggle persisted in `localStorage`, dictionary in `src/i18n/{bn,en}.ts`):**
1. **Hero:** headline (bn) "আপনার ক্লিনিকের ফোন, ২৪ ঘণ্টা বাংলায়", sub-line on missed calls and after-hours bookings, a large **"বাংলা কলারের সাথে কথা বলুন / Talk to our Bangla caller"** button, and the 3D orb.
2. **Problem → solution:** missed calls, after-hours, manual booking, receptionist load, unstructured info (one card each with the fix).
3. **How it works:** Call → AI understands Bangla and books → staff see everything in the portal.
4. **Features:** natural Bangla and code-switching · phone/date capture with read-back · double-booking safe · human handover · live portal.
5. **Use cases:** dental clinics · diagnostic centres · hospital OPD serials · reminder/confirmation calls.
6. **Portal preview:** screenshot or animated mock of the call detail page, with a link to the portal.
7. **Contact / demo request form** (stores into a `leads` table or just a `mailto:`; keep it simple).
8. Footer.

**3D orb, "easy to load":**
- React Three Fiber plus a custom shader material: an icosahedron (detail 5–6) with simplex-noise vertex displacement, fresnel glow, and a particle ring (~1.5k points). **No GLB/textures to download.**
- The orb **is the call UI**. State → uniforms: `idle` (slow breathing, brand teal) → `connecting` (faster spin and pulse) → `listening` (displacement driven by **mic volume**) → `speaking` (driven by **agent audio track volume** via `useTrackVolume` from `@livekit/components-react`) → `ended` (settles, colour fades).
- Below the orb: **live captions** (agent + caller, latest 2 lines) and **tool chips** ("ডাক্তারের সময় দেখছি…", "অ্যাপয়েন্টমেন্ট বুক হয়েছে ✓"), fed from the agent over a LiveKit data channel / RPC.
- Performance: a static CSS radial-gradient "poster" orb renders on first paint (LCP). The canvas loads with `next/dynamic({ ssr:false })` after `requestIdleCallback`, `dpr={[1, 1.5]}`, `frameloop` paused when offscreen (IntersectionObserver), and a `prefers-reduced-motion` or no-WebGL fallback to the poster. Target **Lighthouse mobile ≥ 90**.

**Call widget states and errors (each with a bilingual message):** `idle` → `requesting_mic` → `connecting` → `live` (timer + mute + end) → `ended` (short summary + "portal-এ দেখুন" link). Errors: mic permission denied (per-browser how-to-enable tip) · no input device · token/agent unavailable (retry button) · network drop/reconnecting · call cap reached · unsupported browser.

---

## 9. Portal (`apps/web/src/app/(portal)/portal/...`)

- `/login`: Supabase email/password. Middleware protects `/portal/*`.
- `/portal`: overview KPIs (calls today/7d, booked %, after-hours %, avg duration, open callbacks) and a mini chart.
- `/portal/calls`: table with date, time, caller name, phone, duration, status/outcome badges and a **LIVE** pill for in-progress calls. Search by name or phone, filter by outcome/status/date range, paginate. Realtime inserts.
- `/portal/calls/[id]`: extracted-fields card (each field with a ✓ valid / ⚠ check badge and confidence) · **transcript** (speaker bubbles, `mm:ss` timestamps, bn with an EN toggle, interrupted marker) · tool-event timeline · latency stats · bn/en summary · linked appointment and callback · recording player (if available) · **Reprocess** button.
- `/portal/appointments`: upcoming list by doctor and day.
- `/portal/callbacks`: queue with mark-done.
- `/portal/data-model`: **ERD** (Mermaid rendered) · table-by-table explanation · "how data moves" diagram (§5) · storage facts (Supabase Postgres, Singapore region, RLS, service-role writes only, recordings in a private bucket with signed URLs).

---

## 10. Stand-out checklist (what puts this above the other submissions)

- [ ] Audio-reactive **3D orb that is the call interface**, not decoration
- [ ] **Measured voice-engine bake-off** with a score table in `docs/decisions.md`; engines switchable by env
- [ ] **Bangladeshi** Bangla (accent and phrasing), code-switching, digit-by-digit read-back
- [ ] **Double booking impossible at DB level** (gist exclusion constraint)
- [ ] Bangla digit/phone/date **normalisers with unit tests**
- [ ] Portal updates **live while the call is happening** (Supabase Realtime)
- [ ] Per-turn **latency metrics** shown in the portal
- [ ] **Eval suite** (LiveKit Agents testing + LLM judge): happy-path booking, code-switch, Bangla-digit phone, medical-advice refusal, reschedule, cancel, silence, emergency. Results table in the README.
- [ ] Data Model page in the portal (the brief calls the schema "first-class")
- [ ] Bilingual landing (bn default) and Lighthouse ≥ 90 on mobile
- [ ] Honest "Known limitations & next steps" section (telephony via SIP, recordings, multi-clinic tenancy, PII retention policy)

---

## 11. Timeline (BST, UTC+6)

| When | Phase | Definition of done |
|---|---|---|
| Wed 4 Nov, evening | **P0** accounts, keys, repo, **bake-off** | Engine chosen and logged; repo on GitHub |
| Wed night | **P1** schema + seed + agent skeleton | Agent speaks Bangla in the playground; tables exist in Supabase |
| Thu 5 Nov, 08:00–12:00 | **P2** tools, validators, persistence, finalize | A real call writes calls/turns/appointments/extraction; pytest green |
| Thu 12:00–15:00 | **P3** landing + orb + call widget | Hero button completes a call in the browser locally |
| Thu 15:00–18:00 | **P4** portal | Login → list → detail → data-model pages working |
| Thu 18:00–20:00 | **P5** deploy all + 3–5 real test calls + evals | Success path passes on the **public URLs** |
| Thu 20:00–21:30 | **P6** README, video, email draft | All 4 links verified logged-out; email drafted for the user to send |

**Cut-line if behind (drop in this order):** recordings → extra bake-off engines → overview KPIs chart → appointments/callbacks pages → evals beyond 3 scenarios. **Never drop** the end-to-end success path, the transcript view or the data-model page.

---

## 12. Progress checklist (RESUME HERE)

> Rules for every session: work top to bottom, tick `[x]` as soon as an item is done, and add a line to the **Session log**. Record any deviation from this plan in `docs/decisions.md`.

### P-1 Planning
- [x] Read the brief PDF and the HR email; capture requirements (§1)
- [x] Choose architecture and stack (§2); write this playbook and `CLAUDE.md`

### P0 Setup & bake-off
- [x] `git init`; create GitHub repo `bytevoice-bangla` (private; add reviewers later, or make public at submission): https://github.com/Rifat024/bytevoice-bangla
- [x] Create the monorepo skeleton (§13 commands), `.gitignore`, `.env.example` files (agent done; `apps/web` is created in P3)
- [ ] Accounts and keys ready (§13): Supabase (Singapore), LiveKit Cloud, Google AI Studio, Vercel (all free tiers)
- [x] Minimal agent worker (`apps/agent/src/agent/worker.py`, engines in `engines.py`, persona in `prompts/persona.py`); CLI verified, silero files downloaded
- [x] Owner created `apps/agent/.env.local` (git-ignored) with the Google key; key verified with Gemini text and Live calls
- [x] Voice engine settled on Gemini only (Azure needs payment); `bn-BD` support verified on 3.8 Live; end-of-turn click fixed + tested
- [x] Owner picked the Live voice: **Kore**
- [ ] Owner smoke-tests `uv run python -m agent.worker console` with the §3 script
- [ ] Run the §3 test script on `gemini_live` (and `gemini_pipeline` if accent is off); scores written to `docs/decisions.md`

### P1 Data + agent skeleton
- [x] Supabase project `bytevoice-bangla` created (free, Singapore); migration `init_schema` applied; RLS + realtime publication; security advisor clean
- [x] `seed.sql` applied (1 clinic, 3 doctors, 7 services, 11 doctor-service links, 13 schedule slots); constraints verified
- [x] Reviewer auth user created (`reviewer@bytevoice-bangla.demo`; password only in git-ignored `.env.reviewer` and the submission email)
- [x] Supabase keys pulled via the CLI into git-ignored `apps/agent/.env.local` and `apps/web/.env.local`
- [x] Agent persona prompt (§7) loaded with clinic facts and `now_dhaka` (static facts; switch to DB-loaded facts in P2)
- [x] `calls` row created on session start; turns persisted live (code + unit tests; needs `SUPABASE_SERVICE_ROLE_KEY` for a live run)

### P2 Tools, validation, extraction
- [x] `normalize/` digits, phone, dates, names, plus pytest (≥ 25 cases incl. Bangla digits, double/triple, Friday, past dates)
- [x] Repository layer `apps/agent/src/agent/repositories/` (calls, patients, appointments, callbacks, events)
- [x] Tools from §5 implemented with confirmation gate and exclusion-violation handling (plus `check_phone_number`, `recall_caller_history`; short slot/appointment codes)
- [x] Silence re-prompt, 5-min cap, end_call flow
- [x] FastAPI `/health`, `/calls/{id}/finalize`, `/calls/{id}/reprocess`; Gemini JSON-schema extraction + bn/en summary + per-turn translation
- [x] Per-turn latency events
- [x] Privacy guardrails: no staff personal info, no other-patient data, prompt-injection and off-topic handling, guardrail audit events
- [x] Caller memory for follow-up calls (verified name + number → previous summaries, open callbacks, upcoming appointments)
- [x] End-to-end calls write everything correctly (5 simulated calls through the real agent stack into the live DB via `evals/simulate_calls.py`; live voice call pending LiveKit keys)

### P3 Landing + 3D hero + call widget
- [x] Next.js app (Next 16), Tailwind, fonts (Hind Siliguri / Noto Sans Bengali + Inter), bn/en dictionary + toggle
- [x] `/api/livekit/token` route (rate limit, TTL, agent dispatch, room name `call-<uuid>`)
- [x] Orb: poster fallback → lazy R3F canvas → state/volume-driven uniforms
- [x] Call widget states + all error states (§8); live captions + tool chips via data channel (not yet tested against a live LiveKit room)
- [x] Remaining sections (problem, how it works, features, use cases, portal preview, contact, footer); responsive check at 375/768/1440
- [x] "Meet Nila" persona section: avatar, traits and an animated sample call (bn/en)

### P4 Portal
- [x] Supabase SSR auth, middleware (`src/proxy.ts`), login page
- [x] Calls list with search/filter/pagination + realtime LIVE pill
- [x] Call detail (fields + badges, transcript bn/en, events, latency, summary, appointment, callback, reprocess)
- [x] Appointments + callbacks pages
- [x] Overview KPIs
- [x] Data Model page (ERD + explanations + flow)

### P5 Deploy & data
- [x] Vercel deploy of `apps/web` (env vars set in Vercel only): https://bytevoice-bangla.vercel.app (`scripts/deploy-web.sh`)
- [x] Agent deployed to LiveKit Cloud (`scripts/deploy-agent.sh`, agent `CA_CDHEZc8cLbtn`, us-east); only the needed secrets are passed
- [ ] FastAPI reachable from the agent; CORS locked to the Vercel domain
- [ ] 3–5 real test calls on production (booking, reschedule, enquiry, medical decline → callback, silence/incomplete) to pre-load the portal
- [x] Eval suite run (11/11); results linked from the README
- [ ] Lighthouse mobile run; screenshot saved to `docs/`

### P6 Docs, video, submission
- [x] Move the playbook to `docs/BUILD_PLAYBOOK.md`; write the reviewer-facing README (§15)
- [x] Record the video (§14), ≤ 3:00: `scripts/video/make_video.py` → Nila-narrated 2:25 walkthrough of the live site (manual live-call recording still recommended as a backup)
- [ ] Verify all 4 links logged out / incognito; give the reviewers repo access
- [x] Draft the submission email for the user to review and send (§15): `docs/submission-email.md`

### Session log
| Date (BST) | Account / session | Done | Next | Blockers |
|---|---|---|---|---|
| 2026-11-04 | Planning session | Brief digested; playbook + CLAUDE.md written | P0 setup & bake-off | Need API keys / accounts |
| 2026-11-04 | Planning session (P0) | Tools installed (uv, pnpm, supabase, lk); agent scaffold; clinic switched to One Smile Dental (demo values); private repo pushed | Owner adds keys → smoke test | Keys |
| 2026-11-04 | Planning session (P0, voice) | Azure dropped (needs payment); Gemini-only engines `gemini_live` (3.8 Live, `bn-BD`) and `gemini_pipeline`; voice samples sent; fade-out click fix with tests; prompt tuned (digit read-back in words, no gendered address, callback offer, Dhaka accent) | Owner picks voice + console smoke test → P1 (Supabase schema) | LiveKit Cloud + Supabase projects not created yet |
| 2026-11-04 | Build session (P1–P4 code) | Agent: validators, repositories, 10 tools, booking/availability service, privacy guardrails + audit events, caller memory for follow-up calls, live transcript/latency recorder, Gemini post-call extraction, FastAPI reprocess, Dockerfile; 88 pytest; 11-scenario eval suite. Web: landing + 3D orb + call widget + Nila persona section, full portal, data-model page; build/lint green | Owner adds Supabase service-role + anon keys, LiveKit keys, reviewer user → first live call → deploy (P5) | Keys/accounts; portal and live call untested against real services |
| 2026-11-04 | Build session (P5/P6) | Supabase + LiveKit keys wired via CLIs; reviewer user; web deployed to https://bytevoice-bangla.vercel.app; 5 calls through the real agent into the live DB; own-Gemini-key calls (tested before acceptance, sealed AES-GCM); guardrail word-boundary fix; 97 pytest, 11/11 evals; 2:25 Nila-narrated video rendered on the live site | Owner: real voice call, `scripts/deploy-agent.sh` (LiveKit Cloud hosting), upload video, send email | Agent worker runs on the owner's Mac until deployed |

---

## 13. Setup, accounts & commands

**Accounts / keys (never commit values; `.env.example` lists names only):**

| Service | Used for | Env vars | Where the secret lives |
|---|---|---|---|
| Supabase (region **Southeast Asia, Singapore**) | DB, Auth, Realtime, Storage | `SUPABASE_URL`, `SUPABASE_ANON_KEY` (web), `SUPABASE_SERVICE_ROLE_KEY` (agent only) | Vercel env (anon only) / agent platform secrets |
| LiveKit Cloud | WebRTC rooms, agent hosting | `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` | Vercel env (token route) / LiveKit agent secrets |
| Google AI Studio | Gemini Live + Gemini 2.5 Flash | `GOOGLE_API_KEY` | Agent secrets only |
| OpenAI (optional) | Realtime fallback | `OPENAI_API_KEY` | Agent secrets only |
| Vercel | Web hosting | (none) | (none) |
| Render (fallback) | Agent/FastAPI hosting | (same as agent) | Render env |

Agent extra env: `VOICE_ENGINE`, `AGENT_NAME=bytevoice-bn`, `FINALIZE_API_URL`, `INTERNAL_API_TOKEN` (shared secret between the worker and FastAPI), `MAX_CALL_SECONDS=300`, `CLINIC_ID`.

**Target repo layout:**
```
bytevoice-bangla/
├─ apps/
│  ├─ web/                    Next.js 15 (landing, call widget, portal, /api/livekit/token)
│  │  └─ src/{app,components,lib,i18n,constants,types}/
│  └─ agent/                  Python 3.12 (uv)
│     ├─ src/agent/
│     │  ├─ worker.py         LiveKit entrypoint, engine factory
│     │  ├─ prompts/          persona + clinic facts template
│     │  ├─ tools/            function tools (§5)
│     │  ├─ normalize/        digits, phone, dates, names (§6)
│     │  ├─ repositories/     all DB access
│     │  ├─ schemas/          pydantic DTOs (tool args, extraction schema)
│     │  ├─ constants.py
│     │  └─ api/              FastAPI app (health, finalize, reprocess)
│     ├─ tests/               pytest (normalisers, tools with fake repo)
│     └─ evals/               LiveKit Agents test scenarios + judge
├─ supabase/{migrations,seed.sql,config.toml}
├─ docs/{architecture.md,data-model.md,decisions.md,video-script.md,eval-report.md}
├─ CLAUDE.md
└─ README.md
```

**Bootstrap commands (verify versions with Context7 / official docs before running):**
```bash
# repo
git init && gh repo create bytevoice-bangla --private --source . --push

# web
pnpm create next-app@latest apps/web --ts --tailwind --eslint --app --src-dir --import-alias "@/*"
cd apps/web && pnpm add three @react-three/fiber @react-three/drei livekit-client @livekit/components-react livekit-server-sdk @supabase/supabase-js @supabase/ssr zod mermaid && pnpm add -D @types/three
pnpm dlx shadcn@latest init

# agent
cd apps/agent && uv init --package --name agent --python 3.12
uv add "livekit-agents[google,silero]" numpy fastapi uvicorn pydantic supabase python-dateutil
uv add --dev pytest pytest-asyncio ruff
uv run python -m agent.worker download-files
uv run python -m agent.worker dev          # local worker, connects to LiveKit Cloud

# database
supabase init && supabase link --project-ref <ref>
supabase migration new init_schema           # paste §4 SQL
supabase db push && supabase db reset --linked   # reset only before real data exists

# deploy
vercel --cwd apps/web                        # set env vars in the Vercel dashboard
lk cloud auth && lk agent create apps/agent  # then: lk agent deploy
```

**Coding conventions (from the owner's global rules):** DTOs/pydantic models for every request body and tool arg (never `any`); types in `types/` or `schemas/`; fixed values in `constants`; try/except (try/catch) in every handler and tool with structured logging (`logger.debug`, never `print` or `console.log`); full-word identifiers; all DB access through the repository layer; production-only comments (no ticket notes, TODOs or narration).

---

## 14. Full-screen recording of the whole web app (video deliverable)

**Setup:** macOS `Cmd+Shift+5` → *Record Entire Screen* at 1080p, or **OBS** (Display Capture + Mic + desktop audio via BlackHole, so the agent's Bangla voice is audible). Chrome in full screen with a clean profile (no bookmarks or extensions), Do Not Disturb on, cursor highlight on. Wear headphones with a mic so the agent's voice doesn't echo into your mic and trigger false barge-ins.

**Shot list (≤ 3:00, rehearse twice from `docs/video-script.md`):**
| Time | Shot |
|---|---|
| 0:00–0:25 | Landing hero: orb breathing, value prop, bn → en toggle, quick scroll through the sections, mobile view (DevTools device mode) |
| 0:25–1:55 | Click **Talk to our Bangla caller** → mic prompt → connecting → live. Full Bangla booking: name confirm, phone digit-by-digit read-back, code-switch ("scaling"), "আগামী রবিবার সন্ধ্যা", one interruption, one medical question politely declined + callback, summary, end |
| 1:55–2:40 | Portal login → the call is already at the top (LIVE → completed) → call detail: extracted fields with validation badges, transcript with timestamps, tool timeline + latency, appointment created, callback queued |
| 2:40–3:00 | Data Model page (ERD) + one-sentence architecture + "what's next" |

**Also:** record a longer **uncut walkthrough** of every page and error state (mic denied, agent unavailable) as a backup link in the README. Optional: `apps/web/e2e/walkthrough.spec.ts` (Playwright `video: 'on'`) for a silent automated tour and README screenshots.

**Upload:** YouTube (Unlisted) or Google Drive ("anyone with the link"). **Test the link in an incognito window.**

---

## 15. Submission

**Reviewer-facing README (replaces this file at P6):** title + one-line pitch · 4 live links + reviewer login · 90-second "how to try it" · architecture diagram · tech choices & **why** (bake-off table) · data model (ERD + table guide) · call → storage flow · validation approach (Bangla digits, phone, dates) · eval results · security & secrets handling · local setup · **known limitations & next steps** (honest) · credits.

**Email (draft only; the user sends it):**
```
To: hr@strategybyte.com.au
Subject: AI Engineer Task Submission: Rifat Bin Siraj

Hi StrategyByte team,

Please find my submission for the AI Engineer task below.

1. Landing page: <url>
2. Back-end portal: <url>   Reviewer login: <email> / <password>
3. GitHub repository: <url>  (access granted to <emails>, or public)
4. Video overview (≤3 min): <url>

Stack in one line: Next.js + LiveKit (WebRTC) + Python LiveKit Agents with <engine> for
Bangla speech, Supabase Postgres (Singapore) for storage, deployed on Vercel and <agent host>.
Known limitations are listed honestly in the README.

Thank you,
Rifat Bin Siraj
```
