# SHEFA frontend: design brief (shape)

Status: **awaiting confirmation.** No code is written from this brief until it is confirmed. Visual
direction is deliberately not decided here; it is the next step (new-work: visual authority,
world options, concept choice) and needs the user's choice.

Product truth: `PRODUCT.md`. Stack: React + Vite + TypeScript, built to static files and served by
FastAPI. Devices: desktop and phone equally.

## 1. Job and audience

One app, one sign-in, four parts. Mode by surface: **Operate** for staff, owner and doctor parts;
**Persuade-lite / Operate** for the public booking page (the patient completes a task, not a pitch).

| Role | Situation | Job |
|---|---|---|
| Front desk | Shared desktop/tablet, phone ringing, interrupted every minute | See what the agent is doing, take over, fix appointments, return callbacks |
| Owner | Phone, evening, wants a verdict | Is it working? Calls, failures, bookings per doctor, reminder results, quality, settings |
| Doctor | Phone or desk between patients | My day, call notes, availability and leave |
| Patient | Phone, slow network, Bangla first | Book or ask in under a minute without calling |

## 2. Outcome and proof

- Front desk can take over any live call or resolve any callback in **two taps**.
- Nothing the agent did is hidden: each call shows transcript, what the agent understood, the action it took, and whether a person confirmed it.
- Owner sees five numbers that matter (answered, booked, handed to a person, failed, reminders confirmed) and can drill from each to the calls behind it.
- A patient books without an account in under a minute, on a slow phone connection.
- Proof that is real today: the working booking engine, call log, directory and reminders. Nothing fabricated: no sample patients, no invented statistics in any screen or screenshot.

## 3. Information architecture

```
/                      public: chooses language, links to Book / Call us
/book                  Patient: pick doctor or problem -> day -> time -> phone -> confirm
/book/done/:ref        Patient: confirmation with the reference, add to calendar, change/cancel link
/app                   signed-in shell (role decides which sections exist)
  /app/live            Front desk: live board of calls + callbacks needing a person
  /app/calls           Front desk, owner: history; /app/calls/:id transcript, audio*, actions
  /app/appointments    Front desk: day view by doctor; move, cancel, mark done / no-show
  /app/doctors         Front desk (read), owner (edit): directory and profiles; schedule and leave
  /app/me              Doctor: my day, my notes, my availability
  /app/overview        Owner: five numbers, trend, problems list
  /app/reminders       Owner, front desk: what will be called, results, quiet hours
  /app/voice           Owner: voice test (listen and score), agent greeting and language
  /app/settings        Owner: clinic hours, human numbers, retention, roles
```
\* call audio is stored only if the clinic turns it on; default off (privacy). Open decision.

## 4. Key flows and states

- **Live board.** Rows for active calls: who (masked number), how long, language, current step (asking for doctor / confirming / booking), agent confidence, `Take over` and `Listen`. Empty: "No calls right now" plus last call time. Error: connection lost banner with retry; the board never shows stale data as live.
- **Take over.** Transfers the call to the desk's phone or opens the browser softphone; the agent hands off with a spoken line and a summary appears for the person.
- **Callbacks.** Created when the agent cannot reach a human or the caller asks for one: reason, number, language, time waiting; resolved with one tap and a note.
- **Appointment day view.** Columns per doctor, 15-minute rows, drag to move, confirm dialog with the same read-back the agent uses; conflicts shown before saving.
- **Call detail.** Timeline of turns with what was heard, what the agent decided (tool, arguments), what it said; flags: low confidence, language switch, repeated failure, transfer. A "this was wrong" action files the call into the evaluation set.
- **Patient booking.** Problem or doctor first, then the earliest free times, then phone number with an SMS or call confirmation (open decision), then reference. Works with no account. Rate-limited, no personal data beyond name and phone.
- **First run.** Empty clinic -> import doctors (file or manual), set human phone numbers, test call from the browser.
- **States everywhere:** loading skeletons, empty, error with next step, offline/slow, permission denied, long Bangla names, 40-doctor clinic, 200 calls a day.

## 5. Interaction and layout (intent)

- Desktop: left navigation by section, a dense table or board in the centre, a detail panel on the right. Phone: bottom navigation (4 items per role), full-screen detail, big touch targets.
- One live region for the call board with polite screen-reader announcements for new calls.
- Language switch (বাংলা / English) is always visible and remembered; every string exists in both; numbers and dates follow the language.
- Keyboard: every action reachable; `g l` / `g a` style go-to shortcuts on desktop.

## 6. Backend needs (new or changed)

Existing: sign-in, roles, directory, appointments, status change, call log, reminders, health, ring and browser call WebSocket, typed chat.
Missing and required by this brief:

1. Roles `desk`, `owner`, `doctor`, `patient` mapped to permissions, with per-doctor scoping.
2. Live calls feed (Server-Sent Events): active sessions, step, language, confidence.
3. Call detail API: turns with decisions, flags; "wrong" feedback endpoint.
4. Take-over and callback queue endpoints.
5. Overview statistics endpoint (the five numbers, per day).
6. Directory and schedule write API (not only YAML import), leave management.
7. Public booking API: availability, create, cancel by reference; rate limit and abuse protection.
8. Settings API: human numbers, quiet hours, retention, audio storage flag.
9. Client error reporting and an audit log of staff actions.

## 7. Scope and boundaries

- Fidelity: production-ready, full flows, all four parts, Bangla and English, desktop and phone.
- Delivery in milestones, each shippable: M0 shell, auth, i18n, design system, error and empty-state kit; M1 front desk (live, callbacks, appointments); M2 owner (overview, calls, settings); M3 doctor; M4 patient booking; M5 voice and reminders pages.
- Untouched: the voice pipeline, booking engine rules, existing API contracts (extend, do not break), the current console stays until M1 ships.
- Anti-goals: no marketing site, no payment, no chat widget with free-text medical advice, no analytics that identify patients.

## 8. Constraints and open decisions (the builder must not invent)

- Stack, devices: decided. Visual world: **open** (next step, needs the user).
- Open: store call audio or not; patient-page confirmation channel (SMS, call, none); doctor sign-in (phone OTP, password); hosting of the patient page; consent wording; brand name treatment and logo (none exists).
- Accessibility floor: WCAG 2.2 AA, keyboard complete, Bangla fonts with correct shaping, reduced motion respected, tolerant of slow networks (patient page budget: first view under 150 kB of JavaScript).
- Testing: component tests, Playwright flows per role, axe checks, and a real-phone pass before M1 is called done.
