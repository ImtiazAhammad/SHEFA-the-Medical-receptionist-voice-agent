# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

React + Vite + TypeScript single-page app, built to static files and served by the existing FastAPI server (one deployable on the clinic's own machine). Chosen by the user on 2026-11-08.

## Users

Four audiences, each with their own part of one app (role-based, one sign-in):

- **Front-desk staff** at a Bangladeshi clinic: busy, interrupted, often on a shared desktop or tablet. They watch what the voice agent is doing, take over a call, fix or move appointments, and work the list of callers who need a human.
- **Clinic owner / manager**: wants to know whether the agent is paying for itself. Call volume, missed or failed calls, bookings per doctor, reminder results, quality problems, settings. Often on a phone.
- **Doctors**: want their own day: who is booked, notes from the call, availability and leave. Short visits to the app between patients.
- **Patients (public page)**: book or ask a question on the web without phoning. Mostly on a phone, Bangla first, little patience, some with low literacy and slow connections.

## Product Purpose

SHEFA is an open-source, privacy-first, bilingual (Bangla/English) AI voice receptionist for Bangladeshi clinics. It answers and places phone calls, books and changes appointments, answers questions about doctors, departments and schedules, and calls patients with reminders. The frontend is how a clinic runs, supervises and trusts it. Success: the front desk handles only the calls that need a person, nobody is double-booked or wrongly booked, and the owner can see that the agent works.

## Positioning

Self-hosted and open-source: patient audio and records stay on the clinic's own machine, with open models only, behind a Bangladeshi SIP trunk rather than a foreign cloud. Bangla is the primary language, not a translation.

## Operating Context

- Calls arrive by phone (Asterisk plus a Bangladeshi SIP trunk, not yet verified live) or from the browser (WebSocket) for demos and the patient page.
- Clinic time is Asia/Dhaka; dates are shown in the user's language (Bangla or English), times in 12-hour words for speech and a plain clock on screen.
- Data: SQLite clinic directory (departments, doctors, profiles, weekly schedules, leave), appointments, patients identified by phone number, call log with transcripts, reminders.
- The agent is one voice in a conversation that can fail; staff must always be able to see what it did and step in.
- Real hardware is modest: one machine with a single GPU; the UI must not assume fast networks.

## Capabilities and Constraints

- Existing API (FastAPI): sign-in with HttpOnly cookie, roles with permissions (`records:read`, `records:write`, `calls:place`, `sessions:read`, `chat:use`, `config:read`), directory, appointments with status changes, call log, reminders, health, WebSocket call in the browser, typed chat.
- The doctor directory holds a `profile` per doctor (designation, experience, gender, languages, room, conditions seen, aliases, one-line blurb, fees, booking notes).
- Real doctor data came from Labaid's public listing for local demos only; schedules there are placeholders. Do not present placeholder schedules or invented fees as facts anywhere in the UI.
- Not decided yet: hosting of the patient page (same machine or public), patient identity and consent for the public page, doctor sign-in method, SMS or WhatsApp confirmations, billing.

## Brand Commitments

Name: SHEFA (শেফা). Keep "SHEFA"/"shefa" spelled consistently. No logo or brand assets exist yet.

## Evidence on Hand

- Working console (`src/shefa/static/console.html`, `signin.html`): Talk, Today, Calls, Clinic, Status tabs; never opened by the user on a phone.
- A competitor reel (Verbex, 2026) analysed in `docs/research/`; it shows voice expressiveness, not a product UI. Nothing there may be copied.
- No real clinic, patient, testimonial, or usage data exists. Do not fabricate any in the interface or in screenshots.

## Product Principles

1. **Supervise, don't trust blindly.** Every agent action is visible, explainable and reversible by a person.
2. **Bangla first.** Bangla is designed, typeset and tested as the primary language; English is the second view of the same product.
3. **Each role sees only its part.** The front desk is not shown revenue; a doctor is not shown other doctors' notes; the public page shows nothing internal.
4. **Honest about uncertainty.** Placeholder, unverified or missing data is labelled as such, never smoothed over.
5. **Works under pressure.** The front desk can act in two taps while a phone is ringing; a patient on a phone can book in under a minute.

## Accessibility & Inclusion

- Bangla and English with correct Bangla shaping, readable sizes and numerals, and no UI that depends on English words.
- Phone and desktop equally supported; touch targets and keyboard operation both first-class.
- WCAG 2.2 AA as the floor; high contrast in a bright reception room; reduced-motion respected.
- Low-bandwidth tolerant: the patient page must stay usable on a slow mobile connection.
