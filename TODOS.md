# TODOS — Deferred scope, collected across /autoplan phases (2026-09-26)

Everything here was consciously deferred by a prior decision block, never dropped.
Items are grouped by owning review phase. Each entry records the concrete issue,
why it was deferred, current state, where to start, and what unblocks it.

## From CEO review (Phase 1)

- **D5 — Clinic-number decision (port vs divert vs new)**, per clinic. Surfaced at Final Gate.
  Rationale: existing-number trap; decision is user/owner territory, not build. Unblock: first clinic owner yes (Child 8 gate).
- **D7 — FreeSWITCH ESL adapter** (deferred behind ARI-first). Unblock: Child 5 demand survey shows BD clinics run FreeSWITCH.
- **D10 — Rejected platform migration split** (kept in single epic). Recorded decision; no action item.
- **D11 — Demand proof (Child 0 splice)**: named clinics log ≥5 missed calls/day, ≥3 willing to trial. Absent → pivot/halt.
  Now a named stop: verdict assessed before any Child 6 demo spend (eng M13).
- **PA3/D19 — Twilio full removal** — kept as additive dev sink; smoke-test-only; full removal later.
- **PA5 — Clinic hardware/GPU residency** — verified via E12 GPU-residency test + demand check.
- **PA7/D15 — Fleet/multi-branch** — channel discovery (3 HMS vendors, 2 resellers) before fleet engineering; Child 8.

## From Design review (Phase 2)

- **RFC4733 DTMF** — handled on both media adapters for every degrade path; trunk screen during E4 procurement. (Adopted in plan, verify on chosen trunk.)
- **Dashboard offline banner** — heartbeat row coupling confirmed by Eng (Child 4); no separate TODO.
- **Demo safety sign-off** — PREREQUISITE of Child 6 demo DoD, recorded in ops/runbook.md. Owner: named human for emergency script.

## From DX review (Phase 2.5)

- **Bangla Piper voice** (`bn_BD.nf_cycgan.onnx`) — **promoted to a named blocker (eng B5)**, parallel to SIP-trunk procurement. Own:
  acquisition/licensing + quality bar; `sefa doctor` asserts resolved adapter path is the bn voice.
- **`/api/v1/sessions` deprecation (410 + SQLite pointer)** — lands with dashboard API (Child 4).
- **Full error registry + HTTP error-response schema** — stays Child 5 (inline 4-part stub ships in Child 1).
- **Per-clinic `prompts/<clinic_id>/system.md` hot-reload** — Child 8 config, not code fork; precedence chain via one loader (eng M5).
- **Drop unused deps** (`redis`, `sqlalchemy`, `asyncpg`, `alembic`, `langchain-*`, `langgraph`, `sentry-sdk`, `prometheus-client`) + remove `REDIS_URL`/`DATABASE_URL` defaults — verify `sefa doctor` (eng M3).

## From Eng review (Phase 3)

- **T1 re-scope**: "3 candidate clinics" narrowed to "2 concrete SIP-trunk fallbacks" — disposition table records this (Child 0 artifact).
- **T7 full-disk encryption + named raw-audio deletion** — promoted INTO Child 3 (not deferred) because "encryption at rest" is unenforceable without it.
- **T3 (≥3/4 clean bookings)** and **T8 (weekly gate metrics)** — no owning child; disposition table records "re-scope to Child 2/7 + Child 4" mapping. Tracked here until table lands.
- **T6 outreach tracker** — dropped with rationale (outreach is the gate, not code, Q6); disposition table records it.
- **41-item → 8-child disposition table** — ships as a Child 0 artifact; this file is superseded by it when it lands.
- **Cross-model confirmation** — Codex not installed; single-model for all phases. Headroom retained until a second model confirms; re-run /plan-eng-review before scale-up spend if a second model becomes available.