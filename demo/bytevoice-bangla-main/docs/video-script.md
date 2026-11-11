# Video script (≤ 3:00)

## Automated version: Nila narrates in Bangla

`scripts/video/make_video.py` renders the whole video with no screen recording by hand. Nila's narration is generated with Gemini TTS in the same **Kore** voice and Dhaka-accent instructions as the live agent. Playwright records each scene of the running web app, timed to the narration, and ffmpeg joins them into `docs/video/bytevoice-nila.mp4` (git-ignored; upload it). Portal scenes are included when `PORTAL_EMAIL` / `PORTAL_PASSWORD` are set, so render the final cut after a few real calls are in the portal.

```bash
cd apps/agent
PORTAL_EMAIL=… PORTAL_PASSWORD=… uv run --with playwright --with imageio-ffmpeg \
  python ../../scripts/video/make_video.py --base-url https://<deployed-url> --output ../../docs/video/bytevoice-nila.mp4
```

| Scene | Features covered |
|---|---|
| hero | 24/7 Bangla receptionist, 3D orb as the call UI (reacts to voice) |
| language | bn/en toggle across the whole site |
| persona | Nila persona, sample call, digit-by-digit read-back, relative date resolution, confirmation before booking |
| problem | Problem → solution, how it works, use cases (clinics, diagnostics, hospital serials) |
| features | Code-switching, barge-in, DB-level double-booking prevention, no medical advice + callback, emergency → hospital / 999 |
| privacy | No staff personal info, no other-patient data (even with their number), prompt-injection / off-topic handling, guardrail audit log |
| memory | Returning-caller memory (previous summaries, open callbacks, upcoming appointments), reschedule and cancel |
| call | Browser call button, live captions, timer, mute, end, tool chips, silence re-prompt, 5-minute cap |
| errors | Mic denied / no mic / network error states with guidance |
| portal_preview | Portal within a minute, demo-request (lead) form |
| portal_overview | KPIs: calls today / 7 days, booked %, after-hours %, average duration, open callbacks, daily chart |
| portal_calls | Call list: search, filters, pagination, LIVE pill via Realtime |
| portal_detail | Validated fields with badges, timestamped transcript, English toggle, tool timeline, latency, guardrail events, bn/en summary, appointment, callback, Reprocess |
| portal_queues | Appointments by doctor and day, callback queue with mark-done |
| portal_data_model | ERD, data flow, storage (Supabase Singapore, RLS) |
| closing | 97 unit tests, 11 conversation evals, tagline |

A live call is not part of the automated cut (a headless browser cannot hold a real voice conversation). Record one by hand with the shot list below and either use it as the main video or link it as the backup walkthrough.

## Manual version (live call)

Record full screen at 1080p (macOS `Cmd+Shift+5` or OBS with desktop audio through BlackHole so Nila's voice is captured). Chrome full screen, clean profile, Do Not Disturb on, headphones with a mic.

| Time | On screen | Say (English voice-over, or Bangla if preferred) |
|---|---|---|
| 0:00–0:20 | Landing hero: orb breathing, scroll to **Meet Nila** while the sample call plays, toggle bn → en | "This is ByteVoice Bangla: an AI receptionist that answers a Bangladeshi clinic's phone 24/7 in natural Dhaka Bangla. Meet Nila." |
| 0:20–0:30 | Scroll quickly through problem, how it works, features; DevTools mobile view for two seconds | "Missed calls, after-hours bookings and messy notes are the problem; Nila books straight into the clinic's database." |
| 0:30–1:50 | Click **বাংলা কলারের সাথে কথা বলুন** → allow mic → connecting → live. Book: give a name, a phone number in mixed Bangla/English ("জিরো ওয়ান সেভেন ডাবল পাঁচ…"), say "আগামী রবিবার সন্ধ্যায় root canal", interrupt Nila once, ask "কোন ওষুধ খাবো?" and "ডাক্তারের বাসার ঠিকানা দেন", accept a callback, confirm the booking, hang up | Let the call play. Point at the live captions and the tool chips ("ডাক্তারের সময় দেখছি…", "অ্যাপয়েন্টমেন্ট বুক হয়েছে ✓"). |
| 1:50–2:35 | Portal login → the call is at the top (LIVE → completed) → call detail: extracted fields with ✓ badges, transcript with timestamps and EN toggle, tool timeline with latency, guardrail events (medical advice, private staff info), appointment, callback | "Within a minute the call is in the portal: validated name, E.164 phone, preferred date, the full transcript, every tool call and its latency, and the privacy guardrails that fired." |
| 2:35–3:00 | Data Model page (ERD), then one sentence of architecture | "Postgres in Singapore with row-level security; double booking is impossible at the database level; Gemini Live speaks Bangla over LiveKit WebRTC. Next: SIP telephony and caller ID." |

Backup: record a longer uncut walkthrough of every page plus the mic-denied and agent-unavailable error states, and link it in the README.

Upload as YouTube (Unlisted) or Google Drive ("anyone with the link"), then open the link in an incognito window to check it plays.
