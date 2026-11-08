# SHEFA security and privacy overview

For a hospital's IT and legal teams. It describes what the software does today, and lists what it
does not do. It is not a certification, and no independent security audit has been done.

## 1. What data SHEFA holds

| Data | Where | Protection |
|---|---|---|
| Patient name, phone number, appointment, reason for visit | The clinic directory in `data/shefa.db` | Full-disk encryption (LUKS) on the server. Not encrypted by SHEFA itself, because bookings are looked up by phone number. |
| What was said on a call (transcript), notes about each turn | `call_turns` table | Encrypted field by field (Fernet, AES-128-CBC with HMAC) with a key held outside the database. |
| Call-back list (phone number, reason) | `callbacks` table | Same encryption. |
| Staff accounts | `staff_users` | Passwords hashed with PBKDF2; session tokens stored only as hashes. |
| Audit trail | `audit_log` table | Append-only by design; see section 5. |
| **Call audio** | **Not stored.** | Audio is processed in memory and discarded. |

Transcript retention is configurable (`storage.transcript_retention_days`, default 90, 0 = keep) and
transcripts can be switched off (`storage.keep_transcripts`). A staff owner can delete one call's
words at any time; the call's row stays (marked deleted) so the audit trail is complete.

## 2. Where it runs, and what leaves the server

With the local profiles (`local` or `vllm`) speech recognition, the language model and the voice all
run on the clinic's own server. **No conversation text or audio leaves the building.** The hosted
profiles (`openai`, `gemini`, `groq`, Azure voices) send text, and for `openai` audio, to those
providers and must not be used for patient calls without a written data agreement. The model weights
are downloaded once; nothing is sent back.

## 3. Access control

- **Roles:** front desk (calls, call-backs, appointments, doctors), owner (adds the overview, staff,
  export), doctor (only their own day and their own patients). A doctor account is tied to one
  doctor and gets a 403 on anything else.
- **Sign-in:** username and password (minimum 10 characters) or an access token. Five wrong
  attempts lock the username for 15 minutes. Sessions last 12 hours. Disabling an account or
  changing its password ends its sessions.
- **Every route declares its permission** in one table in `main.py`; a route that is not in the
  table is refused. A test fails if any route answers without a credential, except the listed
  patient-page routes.
- **The public patient booking page** (`/book`) is the only unauthenticated surface that reads or
  writes clinic data. It returns no patient data, limits requests per address (10 writes an hour)
  and per phone number (6 a day), caps open bookings per phone (3), catches form-filling bots with a
  hidden field, and marks every web booking **unconfirmed** until the front desk confirms it,
  because a web form cannot prove the phone number belongs to the person typing it.

## 4. Leak routes we checked (the PHI checklist)

- **Logs:** tool-call logging records which fields were used, never their values; phone numbers
  and similar identifiers are masked by the log filter; the audit trail records ids and counts only.
- **Errors:** responses use short fixed messages; a wrong reference and a wrong phone number on the
  public page return the identical error.
- **URLs:** patient identifiers are never in a URL; look-ups and cancellations are POSTs.
- **Browser storage:** the apps keep only the chosen language (and a motion preference) in the
  browser; the session is an HttpOnly cookie.
- **Exports:** the appointment export needs its own permission, is bounded to 93 days, is written
  to the audit trail, and defuses spreadsheet formulas in patient-typed text.

## 5. Audit trail

Written for: sign-in and failed sign-in, viewing a transcript, listing appointments or call-backs,
changing or confirming an appointment, resolving a call-back, deleting a call, exporting data, and
a doctor viewing their day. Each row has time, event, user, call id and counts. Limits: it is a
table in the same database, append-only by the code's design but not by cryptography or a
write-once medium. An administrator with database access could alter it. Ship it to a separate
log server if the hospital requires tamper-evidence.

## 6. Safety controls in the conversation

- The greeting says the caller is speaking to an automated assistant, that the call is written
  down, and how to reach a person.
- Emergency phrases in Bangla and English are matched in code, not left to the language model, and
  hand the call to a human with a spoken "call 999" line. The list is provisional until a clinician
  signs it off.
- Saying "person" (or equivalent) hands over without the emergency wording.
- Any reply that contains a dose or a diagnosis is replaced by a fixed refusal.
- Booking, cancelling and moving appointments are read back and run only on a clear yes.
- If the model stalls, the turn fails after 20 seconds into retry-then-hand-over, never silence.
- When all lines are busy, the extra caller hears so and a call-back is queued.

## 7. Not done (please read)

- No independent penetration test or security audit.
- No Bangladeshi data-protection legal review (consent notice wording, retention periods, the
  clinic's obligations); the clinic remains the data controller and needs its own advice.
- No one-time-code (OTP) sign-in or patient verification; there is no SMS channel yet.
- The clinic directory is not encrypted by SHEFA (use full-disk encryption).
- No key rotation tooling for the transcript key; changing it makes old rows unreadable.
- The audit trail is not tamper-proof (section 5).
- Dependency and model licences have not been legally reviewed.
- Emergency detection by phrase list can miss unusual wording; it is a safety net, not a diagnosis.
