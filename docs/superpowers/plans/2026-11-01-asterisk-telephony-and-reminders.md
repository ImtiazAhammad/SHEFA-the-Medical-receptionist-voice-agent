# Asterisk Telephony, Reminders and Operations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (the user chose "continue autonomously, one task after another"). Steps use checkbox syntax.

**Goal:** Replace Twilio with a self-hosted Asterisk plus a Bangladeshi SIP trunk, add outbound appointment reminders, and make calls observable and recoverable.

**Architecture:** Asterisk terminates the SIP trunk. Media crosses to SHEFA over Asterisk's **AudioSocket** (a TCP stream of 8 kHz signed-linear PCM, 20 ms frames, one connection per call), so no ARI websocket is needed. Control (hang up, transfer, originate an outbound call) uses ARI's REST API over `httpx`. The existing `VoicePipeline`, `MediaQueues`, `CallLeg`/`CallControl` seams are reused unchanged; Twilio stays as a dev sink.

**Tech Stack:** Python asyncio, Asterisk 20 (PJSIP, res_audiosocket, ARI), httpx, SQLite, FastAPI.

**Spec:** README "Goal and status" roadmap table, items 3-6; `docs/carrier-inquiry.md`.

## Global Constraints

- Clinic-local time is Asia/Dhaka; dates `YYYY-MM-DD`, times `HH:MM`.
- Settings models extend `StrictModel` (unknown keys are errors); one provider knob: `telephony.provider`.
- Line length 100, ruff clean, coverage floor 88%, per-module ratchet in `src/shefa/coverage_policy.py`.
- No credential is ever written to a tracked file; templates read from environment.
- Audio inside the pipeline is s16le 16 kHz mono; the wire is s16le 8 kHz mono.

## Review Focus

- A caller hangs up mid-sentence: pipeline and queues are torn down, leg released, no leaked task.
- AudioSocket frame split across TCP reads / several frames in one read: parsed correctly.
- ARI unreachable or returns 4xx on transfer: caller keeps the line, result is `transferred: False` (no false "connecting you").
- Reminder for a cancelled or already-past appointment: never placed.
- Patient does not answer / call fails: retried at most `max_attempts`, never in quiet hours, never twice for one appointment in a day.

---

### Task 1: AudioSocket codec

**Files:** Create `src/shefa/telephony/audiosocket.py`; Test `tests/unit/test_audiosocket.py`; Modify `src/shefa/audio.py` (add `s16le_16k_mono_to_slin8k`).

**Interfaces:**
- Produces: `KIND_HANGUP=0x00, KIND_UUID=0x01, KIND_DTMF=0x03, KIND_AUDIO=0x10, KIND_ERROR=0xFF`; `encode_frame(kind: int, payload: bytes) -> bytes`; `async read_frame(reader: asyncio.StreamReader) -> tuple[int, bytes] | None` (None on clean EOF); `audio.s16le_16k_mono_to_slin8k(data: bytes) -> bytes`.

- [ ] Test: `encode_frame(0x10, b"ab")` equals `b"\x10\x00\x02ab"`; `read_frame` over a reader fed two frames in one chunk and a third split byte-by-byte returns all three in order, then None.
- [ ] Test: downsample of 320 bytes (10 ms at 16k) returns 160 bytes.
- [ ] Implement both; payload length is 2-byte big-endian.
- [ ] Commit.

### Task 2: Asterisk call handling and call leg

**Files:** Create `src/shefa/telephony/asterisk.py`; Test `tests/unit/test_asterisk.py`; Modify `src/shefa/config/settings.py` (`AsteriskConfig`, `TelephonyConfig.asterisk`).

**Interfaces:**
- `AsteriskConfig(StrictModel)`: `ari_url="http://127.0.0.1:8088/ari"`, `ari_user="shefa"`, `ari_password=""`, `audiosocket_host="127.0.0.1"`, `audiosocket_port=4573`, `trunk_endpoint="PJSIP/trunk"` (outbound endpoint prefix), `caller_id=""`, `dial_context="shefa-outbound"`.
- `class AsteriskCallLeg(CallLeg)`: `__init__(call_sid, channel_id="")`; `transfer(to)` POSTs `/channels/{id}/redirect?endpoint=<trunk>/<to>`; `hangup()` DELETE `/channels/{id}`; `dial(number)` -> `originate_call(number)`; `play_file` returns an error dict (unsupported).
- `async originate_call(number: str, call_uuid: str | None = None, variables: dict[str,str] | None = None) -> dict[str, str]`: POST `/channels` with `endpoint`, `extension="s"`, `context=dial_context`, `callerId`, `variables` incl. `SHEFA_UUID`. Returns `{"call_sid": uuid, "status": "dialing"}` or `{"error": ...}`.
- `async handle_audiosocket(reader, writer) -> None`: first frame must be UUID; call_sid = that UUID string; registers leg, runs `VoicePipeline().process_audio_stream` with `MediaQueues`, plays frames out paced at 20 ms, tears down on hangup/EOF/error.
- `async start_audiosocket_server() -> asyncio.AbstractServer`.

- [ ] Tests (real loopback sockets, fake pipeline injected via a module-level factory `pipeline_factory`): inbound audio reaches the audio queue as 16k PCM; queued playback is written as 20 ms 8k frames; hangup frame cancels everything and releases the leg; garbage first frame closes the connection.
- [ ] Tests (httpx `MockTransport` via module `_client_factory`): transfer 200 -> `transferred: True`; transfer 404/connection error -> `transferred: False` with error; originate sends the variables and returns the uuid.
- [ ] Implement; add to coverage ratchet if 100%.
- [ ] Commit.

### Task 3: Wire provider selection

**Files:** Modify `src/shefa/main.py` (lifespan starts the AudioSocket server when `provider == asterisk`; outbound endpoints use `telephony.outbound.place_call`); Create `src/shefa/telephony/outbound.py`; Test `tests/unit/test_outbound.py`.

**Interfaces:** `async place_call(number: str, call_uuid: str | None = None, variables: dict | None = None) -> dict` dispatches on `settings.telephony.provider` (twilio -> `initiate_outbound_call`, asterisk -> `originate_call`, others -> error dict).

- [ ] Tests: dispatch per provider; unknown provider returns `{"error": ...}`.
- [ ] Implement and update the "not configured" messages in main.py to be provider-neutral.
- [ ] Commit.

### Task 4: Asterisk deployment kit

**Files:** Create `deploy/asterisk/{pjsip.conf.tmpl,extensions.conf.tmpl,ari.conf.tmpl,http.conf,modules.conf}`, `deploy/asterisk/docker-compose.yml`, `src/shefa/telephony/asterisk_config.py`, `docs/asterisk-setup.md`; Modify `src/shefa/cli.py` (`shefa asterisk render --out DIR`); Test `tests/unit/test_asterisk_config.py`.

**Interfaces:** `render_asterisk_config(env: Mapping[str,str]) -> dict[str,str]` maps file name -> text; raises `ValueError` listing missing env vars (`SIP_TRUNK_HOST, SIP_TRUNK_USER, SIP_TRUNK_PASSWORD, ARI_PASSWORD`; optional `SIP_TRUNK_PORT`, `CALLER_ID`, `PUBLIC_IP`).

- [ ] Tests: rendering with a full env contains the host and the AudioSocket line `AudioSocket(${UUID},127.0.0.1:4573)`; a missing variable is named in the error; the password never appears in `docs/`.
- [ ] Implement with `string.Template`.
- [ ] Commit.

### Task 5: Reminders and follow-ups

**Files:** Create `src/shefa/reminders.py`; Modify `src/shefa/clinic/store.py` (`reminders` table, `due_reminders`, `record_reminder_attempt`); Test `tests/unit/test_reminders.py`.

**Interfaces:**
- Store: `due_reminders(now: datetime, lead_hours=24, max_attempts=2, retry_after_minutes=90) -> list[dict]` (booked, future, within lead window, attempts < max, last attempt older than retry gap); `record_reminder_attempt(appointment_id: int, outcome: str, now: datetime)`; `mark_reminder_done(appointment_id)`.
- `reminder_text(appointment: dict, language: str) -> str` (deterministic, speaks date/time/doctor/ID).
- `in_quiet_hours(now: datetime, start="20:00", end="08:00") -> bool`.
- `async run_reminder_cycle(store, place, now) -> list[dict]` places calls through `place(number, call_uuid, variables)`; skips quiet hours.

- [ ] Tests: cancelled and past appointments never due; attempt cap respected; retry gap respected; quiet hours place nothing; each placement records an attempt; `reminder_text` contains date, time and doctor in both languages.
- [ ] Implement; wire `shefa reminders run-once` in CLI.
- [ ] Commit.

### Task 6: Call log and owner console

**Files:** Modify `src/shefa/main.py` (record each call in `CallsStore`, add `GET /api/v1/calls`, `GET /api/v1/appointments?date=`); Test `tests/unit/test_owner_api.py`.

- [ ] Tests: finished call appears in `/api/v1/calls`; appointments for a date list with patient phone masked except the last 4 digits.
- [ ] Implement.
- [ ] Commit.

### Task 7: Reliability

**Files:** Modify `src/shefa/main.py` (`/health` reports asterisk ARI reachability and DB writable), Create `scripts/backup_db.sh`; Test `tests/unit/test_health.py`.

- [ ] Tests: health is `degraded` when ARI is unreachable and provider is asterisk.
- [ ] Implement; document backups.
- [ ] Commit.

### Task 8: Docs

- [ ] README roadmap statuses, `docs/asterisk-setup.md` linked from README, `docs/carrier-inquiry.md` cross-link.
- [ ] Commit.
