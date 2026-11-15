# SHEFA Voice Commons: community voice collection (feature list and v1 spec)

Status: draft for the founder's decisions, 2026-11-15. Nothing is built yet.
Working name: "Shefa Kontho" (name not final). Inputs: three adversarial reviews (ML data usability,
contributor experience, risk/privacy/free tier), the repo's own `docs/fine-tuning-plan.md` and
`docs/model-selection.md`.

## Revision 1 (2026-11-15): decisions taken, and what changed from the draft below

The founder delegated every decision. A fourth reviewer checked the architecture change. Where
the sections below disagree with this box, this box wins.

| Decision | Choice | Why |
|---|---|---|
| Where it runs | **Local-first**: a separate FastAPI app on the founder's PC, audio on their disk, a free tunnel for contributors, optional static page on free hosting | Removes the download-and-clear step, the 1 GB and 5 GB/month caps, the 7-day pause and a foreign cloud holding voices; testable end to end. A cloud adapter was left out because it could not be tested against a real account |
| Static shell | Provided (`collect shell`) | A WhatsApp link must not die when the PC does; phones queue clips meanwhile |
| Recording | 16 kHz 16-bit **WAV** (AudioWorklet), MediaRecorder fallback | Lossy Opus then a codec simulation would damage the data twice; disk is plentiful now |
| Signed-upload function | Dropped | The app itself checks limits (optional Cloudflare Turnstile) |
| D1 live call | `Call a friend` as **voice messages** through a room code; live WebRTC not built | Reviewers: two strangers are never online together, relays are not free, and a phone cannot reliably record while another app holds the microphone |
| D2 reviewers | 2-3 named people with tokens, never a public page; review routes only on the public port during a `--with-review` session | |
| D4 numbers | Words everywhere, **phone numbers as digits**, one normaliser (`collector/text.py`) | Matches the booking parser and what Whisper prints |
| D5 | No cloud function | See above |
| D6 | **Never published**; any release needs fresh consent | |
| D7 | Founder plus one native-speaker reviewer to start; pilot about 60 speakers; the 100-speaker, 8-hour gate stays | |
| Admin and staff | Separate port (8101), localhost only | Admin must never be on the tunnel |

Sections 5 and 7 (pull-and-clear and the Supabase budget) and feature A8 (keep-alive) are obsolete.
Replaced by: `collect backup` (verified copy to another disk, withdrawn clips never survive in it)
and a disk meter with an automatic upload pause. Run instructions: [`../collector.md`](../collector.md).

## Revision 2 (2026-11-16): after the first 221 clips from 30 people

The founder's findings and two reviews (conversation design; security and privacy) led to these
changes. Web contract: [`collector-api-v2.md`](collector-api-v2.md).

| Finding | Change |
|---|---|
| Every round was the same six steps; calls could not go longer | Scripts are branching graphs (`collector/scripts.py`): 5 to 16 turns, forks where the caller chooses what to say, optional extra questions, a goodbye |
| The desk never greeted | Four openings with salam + clinic name + "how can I help?" |
| Patients ask which doctor is better | One fictional clinic, 8 departments x 3 doctors (অধ্যাপক, সহযোগী অধ্যাপক, সহকারী অধ্যাপক). The desk lists them; asked for advice it recommends the most senior and says so as seniority, not as a quality claim |
| Relation/name mismatches | The patient is a PAIR to choose from; names are gender- and age-tagged; department limits who the patient can be |
| People did not know when to speak | The desk's words are always visible, a clear "your turn" cue, the record button can never stay disabled. Reviewer's judgement: this, not the synthetic voice, was the main cause |
| "Use real recorded voices" | Staff voice packs (opt-in, admin-approved, one voice per call). NOT built: playing contributors' clips to other contributors; their consent says "not published" |
| The time offered ignored the day asked for; "correct it" had nothing to correct | Offers follow the doctor's days; a wrong read-back is really wrong |
| Clips were cut at 14 s and kept | Open turns allow 20 s; a cut clip is flagged (`auto_stopped`) and the person is asked to redo it |
| Token sign-in | Username + password, sessions, one-time passwords, per-place lockout; the admin can never sign in through the tunnel |
| One reviewer's flag rejects a clip for good | The admin can restore a rejected clip |

Not changed: contributors have no accounts; the first version's cards still resolve for clips that
waited on a phone. Still untested with real people: whether forks are understood, whether labels
get read aloud, the auto-stop rate, and which rank words callers really say ("প্রফেসর", "বড় ডাক্তার").

## 1. What it is, in one paragraph

A free web page anyone can open from a link. They see a made-up hospital-phone situation, hear the
agent's real question, and answer in their own words. The clips teach SHEFA's speech recogniser
the things it gets wrong today: Bangla hospital phrases, names, dates, times and phone digits, on
phone-like audio, from many voices. A small, invited group of reviewers writes down what was said.
The founder pulls each day's audio to their own PC and clears it from the free cloud store.

**The line to tell contributors (draft Bangla, needs a native check):**
> আমরা বাংলায় কথা বোঝে এমন একটা হাসপাতাল-রিসেপশনিস্ট সহকারী (SHEFA) বানাচ্ছি, যাতে ফোনে
> ডাক্তারের সিরিয়াল নিতে কাউকে অপেক্ষা করতে না হয়। এটা একটা বাণিজ্যিক পণ্যের অংশ। সহকারীকে
> আপনাদের মতো সাধারণ মানুষের কথা শেখাতে ১০ মিনিট লাগবে: পর্দায় একটা পরিস্থিতি দেখবেন, প্রশ্ন
> শুনবেন, নিজের মতো করে উত্তর বলবেন। আসল নাম বা নম্বর বলবেন না। আপনার কণ্ঠ শুধু সহকারীকে
> শেখাতে ব্যবহার হবে, আর চাইলে যেকোনো সময় মুছে ফেলতে পারবেন।

Do not promise "never published" unless the founder decides that (see decision D6).

## 2. The "not garbage" contract (what makes a clip usable for SHEFA)

1. **Matches the production call.** SHEFA asks ONE closed question at a time (who/doctor, day, time,
   phone digits, patient name, read-back yes). Callers answer short and slow. So the core mode is
   "answer the agent", not free chat.
2. **Known context per clip.** Every clip stores which agent question it answers (prompt id), the
   expected slot type, and the facts the speaker was given. This is what lets us score slot accuracy.
3. **Hard cases on purpose.** Corrections ("না না, শুক্রবার"), times as numbers mid-sentence
   ("দশটা তিরিশ"), sound-alike names, hesitation, silence-then-answer, "yes but...".
4. **Goal, not script.** Cards show the intent and facts, not sentences, so people do not read aloud.
   For digits, dates and times the card supplies a random value to say naturally.
5. **Speaker-disjoint splits**, decided by contributor id before anything else. A frozen gold test
   set nobody tunes against.
6. **One transcript convention** (section 6), enforced in the review UI and shared with training and scoring.
7. **Phone realism comes from the export step** (ffmpeg G.711/AMR round trips, noise), not from
   asking people to phone in. A small real-8 kHz test set is a later addition.

## 3. Feature list

Tiers: **P0** = needed to start collecting safely. **P1** = soon after the first pilot.
**P2** = later, only if the data proves worth it. **Cut** = deliberately not built.

### 3.1 Contributor side

| ID | Tier | Feature | Notes |
|---|---|---|---|
| C1 | P0 | Link carries the sender's name (`?from=`) and plays a 20-second voice note from the founder | Trust comes from a person, not a page |
| C2 | P0 | Three-line consent with icons and one tick (18+, voice used to teach a machine Bangla and commercial, no real details, deletable). Long text behind "আরও জানুন" | Store consent version, timestamp, text shown |
| C3 | P0 | In-app browser detection (Facebook/Messenger) with a big "Chrome-এ খুলুন" and copy-link | These browsers often block the mic |
| C4 | P0 | **Answer the agent**: situation card (intent + facts + made-up persona), agent question played by TTS, tap to record (push-to-talk), 10 s limit, level meter, playback, "ঠিক আছে / আবার" | Echo cancellation, AGC, noise suppression OFF where the browser allows; push-to-talk after the prompt avoids TTS bleed |
| C5 | P0 | Prompt mix inside C4: slot answers, a free first request ("আমি ... দেখাতে চাই"), digit/date/time drills, corrections, yes/no, hard cases, doctor and patient names | Replaces the separate "drills" and "noise" modes |
| C6 | P0 | Setting tag (home/street/fan/TV...) plus automatic SNR and clipping check | Replaces the "noise round" mode |
| C7 | P0 | Offline-first: each clip saved on the phone first, uploaded with retry, visible "N waiting" status, wake lock, resume | Page under 100 KB, plain fetch, no heavy SDK |
| C8 | P0 | **Pass the phone**: one device, "next person" button, new speaker id each time | Built for family gatherings; speakerphone is close to real 8 kHz |
| C9 | P0 | Mic permission asked on first Record tap, mic check is the first clip | No page-load popups |
| C10 | P0 | Thank-you screen: clips, minutes, group progress bar, delete code, optional taps for age band, gender, division (asked AFTER the 3rd clip), WhatsApp share with a pre-filled Bangla message, QR | Division only, never district |
| C11 | P0 | "Delete my recordings" with the delete code | Code stored hashed |
| C12 | P0 | Bangla-first copy, voice-over on every card, large buttons, works on low-end Android | |
| C13 | P1 | "Call a friend": two people talk on a normal WhatsApp/phone call, each phone records its own mic here, a 6-letter code keeps turns in sync (async relay also allowed) | Human-to-human, secondary to C4 |
| C14 | P1 | Solo fallback when the partner does not show in 60 seconds: same card, TTS front desk | |
| C15 | P1 | Shareable image card ("আমি ১২টা বাক্য দিয়ে SHEFA-কে বাংলা শেখালাম"), no personal data on it | |
| C16 | P1 | Opt-in first name or nickname on a thank-you list, nothing else beside it | |
| C17 | P2 | Live in-browser two-person call (WebRTC) with a relay (TURN) | Only after C13 shows people want it |

### 3.2 Review and transcription

| ID | Tier | Feature | Notes |
|---|---|---|---|
| R1 | P0 | Reviewer page behind login for 2-3 named, trusted reviewers (not public): listen, type, submit; keyboard shortcuts | Typing uses the phone/PC Bangla keyboard |
| R2 | P0 | Gold and test clips are transcribed BLIND by two people, then adjudicated; model drafts shown only for training-pool clips | Drafts anchor reviewers to errors like "বুক গরম" |
| R3 | P0 | Flags: unusable, other language, real personal details spoken, offensive | Flagged clips are excluded and listed for the admin |
| R4 | P0 | Style guide shown in the page; clips with disallowed script or digit style are rejected | See section 6 |
| R5 | P0 | Verify, not type, for scripted prompts: "আপনি কি বলেছেন: '...'?" Yes/Fix | Expected text is already known |
| R6 | P1 | 5% of the queue seeded with known-answer clips to measure reviewer reliability; at least 10% double review; track disagreement per reviewer | |
| R7 | P2 | Open reviewer sign-up | Only with the tooling for harassment and poisoning |

### 3.3 Admin (founder)

| ID | Tier | Feature | Notes |
|---|---|---|---|
| A1 | P0 | Admin login; service key stays on the founder's PC and never in the website | |
| A2 | P0 | Campaign/invite links with sender names | |
| A3 | P0 | Counters (clips, minutes, speakers, review backlog) and free-tier meters; global kill switch when storage reaches 70% | |
| A4 | P0 | Prompts, personas and situation cards live in JSON files in the repo, not a web editor | |
| A5 | P0 | **Pull and clear** script (section 5) | |
| A6 | P0 | Export script: manifest, NFC-normalised transcripts, speaker-disjoint train/dev/test, gold set, 8 kHz codec copies | Runs offline on the PC |
| A7 | P0 | Deletion requests and a tombstone list so a withdrawn clip never re-enters an export | |
| A8 | P0 | Weekly keep-alive request so the free project is not paused after 7 idle days | |
| A9 | P1 | Coverage view: speakers by division/age band/gender/device/setting vs target | |

### 3.4 Platform safety (all P0)

- S1. Uploads go through a small Cloudflare/Supabase function that checks Cloudflare Turnstile and returns a **signed upload URL**. This is a correction to my earlier "no server of our own": a tiny function is needed, and its free quotas are still to be checked.
- S2. Per-clip size cap (about 300 KB), per-session and per-day clip quotas, Opus only.
- S3. Consent record: version, timestamp, text, and the plain sentence that a trained model cannot be un-trained.
- S4. Tombstone table, hashed delete code.
- S5. "Say a made-up identity" is the main privacy protection. Reviewers are told clips may still contain real details and must not share them.
- S6. The founder's PC decodes untrusted audio inside a sandbox (ffprobe/ffmpeg checks first), service key kept out of the repo.
- S7. No public audio, ever. Reviewers only see clips through the login.

### 3.5 Cut from this project (and why)

| Cut | Why |
|---|---|
| Public transcription page | Strangers hear strangers, label poisoning, anchoring; all three reviews agreed |
| Live WebRTC call in v1 | Two strangers are never online together, free TURN is limited, least like production speech |
| Contributors wall with district/age/gender | Can identify a person; replaced by opt-in names (C16) |
| Separate drills and noise-round modes | Folded into C4/C6 |
| Per-contributor leaderboard | Rewards fast junk; use group goals and "accepted" counts instead |
| In-page PII detector, custom Bangla typing helper | Offline check and the phone keyboard are enough |
| Web editors for prompts/campaigns | JSON files |

## 4. What each clip stores

clip id, speaker id (device-local random id plus pass-the-phone sub-id), session id, prompt id,
expected slot type, facts given, setting tag, SNR, clipping flag, duration, device model and
browser (from the user agent), consent version, upload time, state
(uploaded/pulled/verified/reviewed/purged), sha256, transcript(s), reviewer ids, flags, optional
profile (division, age band, gender). A cap of 5% of the pool per speaker.

## 5. Pull and clear (state machine, never deletes unreviewed audio)

1. Take a cutoff time. List clips uploaded before it that are not yet pulled.
2. Download each, check size and sha256, write a local manifest, make a second copy.
3. Mark verified. Clips that are verified AND fully reviewed AND past the grace period become purgeable.
4. Delete only the exact object names through the Storage API, after the founder types a confirmation.
5. Re-runnable and safe if interrupted. A database lease stops two admins running it at once.
6. If storage fills before review catches up, uploads stop (kill switch); nothing unreviewed is deleted.

## 6. Transcript convention (draft, to confirm)

- NFC Unicode normalisation everywhere. The repo's own research found that skipping it inflates
  Whisper-medium's FLEURS WER from 16.2% to 27.9%.
- Numbers, times, dates written as **Bangla words** ("সকাল দশটা তিরিশ মিনিটে"): matches what the
  current model outputs and what the booking parser reads. Phone digits as words one by one or as
  digits: to decide once (D4).
- English loanwords in Bangla script ("অ্যাপয়েন্টমেন্ট"). No punctuation, no case.
- One normaliser script shared by training and scoring; its version is stored in every export.

## 7. Free-tier budget (corrected arithmetic)

| Item | Limit | Source |
|---|---|---|
| Supabase storage | 1 GB | reviewer-verified from Supabase docs, re-check before launch |
| Supabase download | 5 GB/month (+5 GB cached) | same |
| Max file size | 50 MB | same |
| Realtime | 200 connections | same |
| Pause | after 1 week idle | same |
| Anonymous sign-ins | 30/hour per IP; shared mobile IPs may lock people out | same |
| Cloudflare TURN | 1,000 GB free, reset period not stated | reviewer-verified, unconfirmed reset |
| Function quotas (Cloudflare/Supabase) | not checked | TO CHECK |

Volume: 16 kHz WAV is about 32 KB/s, so 1 GB is about 8.7 hours. Opus is about 3 KB/s, so 1 GB is
about 90 hours. Example day, 100 contributors x 10 clips x 5 s = about 1.4 hours: WAV 160 MB (1 GB
in about 6 days; a daily pull would use about 4.8 GB of the 5 GB monthly download), Opus about
15 MB. **Decision: Opus.** (One reviewer's figure of 7 hours/day was wrong; this is the corrected one.)

## 8. Success gates and go/no-go

- **Baseline first.** The current model is already a Bangla fine-tune: 16.5% WER on FLEURS, 17.7%
  on phone-band audio (`docs/model-selection.md`). The 38.3% clinic figure is synthetic
  single-voice babble, so it is weak evidence. Nobody has measured WER on real callers.
- **Cheap tests before any training:** ~~give the speech model the doctor names and booking words as
  hints~~ (tested 2026-11-15: hints make this model much WORSE, 22% to 54-110% word error on synthetic
  clips; see `docs/research/2026-11-15-stt-hints-and-synthetic-baseline.md`), and snap its output to the vocabulary the agent expects at that
  turn (doctor names, weekdays, digits). If slot accuracy is already at 90%, skip fine-tuning.
- **Go for fine-tuning only if** the collection reaches at least about 100 speakers and 8-10 usable
  hours (7,200 clips of 5 s is 10 hours; 150 speakers x 48 clips), plus a blind two-reviewer gold set
  of 1-2 hours from 20+ held-out speakers. Below that, use the data only as a test set. These
  thresholds are the ML reviewer's estimate from memory, not a measured result.
- **Ship a fine-tuned model only if** slot-critical words (name, phone digits, date, time, yes/no)
  reach at least 90% on the phone-path test set (the repo's existing gate), FLEURS WER does not
  worsen by more than 1-2 points, and results are reported per setting/device with confidence
  intervals.
- Training itself: LoRA with replay of general Bangla and 20-30% English, as in
  `docs/fine-tuning-plan.md` section 2. Out of scope for this project.

## 9. Known risks and unverified claims

- **Law.** A reviewer reports a Personal Data Protection Ordinance 2025 in Bangladesh treating
  biometric data as sensitive. I have NOT verified this. Get a lawyer to read the current text,
  especially on voice and on sending data abroad (Supabase region is outside Bangladesh).
- **Withdrawal after training** is not technically possible; the consent text says so.
- **Free TURN, function quotas, Cloudflare Pages commercial terms:** unverified.
- **Existing data:** DocTalkBN (557.63 h of telemedicine audio, broadcast not phone, licence not
  stated) is the closest public match; the repo's notes say to ask first. It does not remove the
  need for this collection, because it is not phone-quality and not closed-question answers.
- **Contributor minimums** (100-150 speakers) depend on how many people the founder can reach.

## 10. Decisions needed from the founder

D1. Live two-person call: reviewers recommend deferring; proposal is C13 first, C17 (live WebRTC) only if wanted after the pilot.
D2. Reviewers are 2-3 named people with login, not a public page. OK?
D3. Opus recording at 16 kHz. OK?
D4. Number convention (words everywhere vs phone digits as digits).
D5. A tiny function for signed uploads and anti-abuse. OK?
D6. Will the audio ever be published (affects the consent promise)?
D7. Who are the 2-3 reviewers, and roughly how many contributors can you reach?

## 11. Build order

1. Baseline + cheap hint tests on the existing model (no contributors needed).
2. C1-C12, S1-S7, A1-A8 minimal: record, upload, queue, pass-the-phone, thank-you.
3. R1-R5 reviewer page and the pull/export scripts.
4. Pilot with 5-10 people, listen to every clip, fix the cards and the style guide.
5. Campaign. Count speakers and hours against section 8.
6. C13, C14, C15, C16, A9. C17 only if wanted.
