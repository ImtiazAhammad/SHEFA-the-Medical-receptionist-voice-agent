# SHEFA First-Clinic Plan — Original-Item Disposition Table (Child 0 artifact)

- Source: `docs/designs/shefa-first-clinic.md` (the "41-item plan")
- Epic: `docs/designs/shefa-spec-epic-plan.md`
- Surfaced by: D-ENG19 (H9)
- Task: T16 — `docs/designs/shefa-first-clinic-disposition.md` updates `README.md`
- Verify: every original item mapped; nothing silently dropped

## Purpose

D-ENG19 observed that the original first-clinic plan's scope would otherwise be
silently dropped during re-scoping: several original items had no owning child.
This disposition table is the Child 0 artifact that records, for **every**
original item in `shefa-first-clinic.md`, whether it is **in** the epic
(and in which of the 8 children / Child 0), **re-scoped** (what it became), or
**dropped with rationale** (and the gate/decisions that supersede it).

Every row carries a disposition of `IN`, `RE-SCOPED`, or `DROPPED` plus the
reason. Nothing is silently dropped.

## The eight children

1. **Media path** — B2BUA bridge (Asterisk ARI + FreeSWITCH ESL), SIP trunk,
   spend guard, replace Twilio-only endpoints.
2. **Safety-Net conversation** — deterministic prompts, structured intents,
   emergency→transfer, no medical advice, degrade-to-transfer, disclosure + warm close.
3. **Lead sink + full dashboard** — additive SQLite calls table, desk
   notification, full D4 dashboard contract, D5 integrity.
4. **Test the real loop** — silence/noise/accents/code-switch/interruptions,
   ≤2s median (Q11), calibration (E11), automated tests + VRAM (E12).
5. **Runbook + dev docs** — X1/X2/X4/X6/X7/X8 (SIP-flavored).
6. **Demo deliverable** — 60s Bangla video of the proven loop (D1/D2).
7. **Booking depth + HMS paste-in** — booking slip in SQLite, availability
   lookup, discover-then-build HMS gate, push-selling outbound deferred.
8. **Multi-branch / fleet** — post-first-yes per-clinic deployment playbook.

Plus **Child 0 "Developer loop"** (`sefa doctor`/`replay`/`bench`/`serve`),
which ships first.

## Original plan items — disposition

Keys: `IN` = implemented inside the epic; `RE-SCOPED` = lives on with a changed
shape; `DROPPED` = superseded by a later, recorded decision (rationale given).

### Implementation Tasks (T1–T8)

| Original item | Disposition | Now lives as |
|---|---|---|
| **T1** Verify BD inbound number + forward-on-no-answer on **3 candidate clinics/carriers**; record per-number/min cost; name a local fallback | **RE-SCOPED** | "3 candidate clinics" narrowed to **2 concrete SIP-trunk fallbacks** (per plan / ENG review). Trunk procurement + forward-on-no-answer verified on the trunk at Child 1; SIP spend guard replaces per-call Twilio cost capture; local fallback named in Child 1 deps. |
| **T2** SQLite call-log sink to twilio.py (caller ID, ts, duration, transcript, disposition, resolved-by-desk); two-number query; retention delete + audit log | **IN** | Child 3 — additive SQLite `calls` table (Q10), two-number header, audited-delete (D4). |
| **T3** Bangla booking-loop acceptance bar ≥3/4 clean complete bookings; record median parse/confirm latency | **RE-SCOPED** | No owning child as stated → **Child 2/7 + Child 4**. Bangla booking-loop quality asserts inside Child 2 conversation tests + Child 7 booking depth; median parse-to-reply latency gate is Child 4's ≤2s (Q11). |
| **T4** Cloud-vs-local STT/LLM smoke test (60 min), record result, decide pilot stack | **RE-SCOPED** | Child 4 — the smoke test becomes the Child 4 latency/VRAM real-loop measurement; on-prem remains marketed end state; cloud escape restricted to synthetic/demo audio (E6). |
| **T5** 20-min HMS discovery (fields, export/API, who touches it) | **IN** | Child 7 — discover-then-build HMS paste-in gate. |
| **T6** Outreach tracker (objection codes), verify 10-20 names real + reachable, warm-count threshold, first-5 pre-test | **DROPPED** | Outreach is the gate, not code (Q6). Outreach execution is tracked operationally (Go/No-Go gate + runbook), not as a shipped feature; demand verdict D11 is the owning stop. |
| **T7** Enable full-disk encryption on box + named raw-audio deletion procedure (sub-2-ring disclosure-or-exclude note) | **IN / PROMOTED to Child 3** | The plan asserts encryption-at-rest, which is unenforceable without this — so it is **promoted INTO Child 3** (not deferred). Impl is owner-ops (infra task), not application code; Child 3 carries it as a named task. |
| **T8** Weekly progress metrics (warm referrals, forwarder-verified candidates, demos scheduled) in the Go/No-Go Gate | **RE-SCOPED** | No owning child as stated → **Child 4**. The real-loop test child owns the measured-outcome gates the original gate table expressed. |

### Design Tasks (D1–D8)

| Original item | Disposition | Now lives as |
|---|---|---|
| **D1** 5-beat demo storyboard + 30s voice preview clip | **IN** | Child 6 demo deliverable. |
| **D2** One-page Bangla pitch (4 beats, consent 4th, preview clip link, box/laptop wording) | **IN** | Child 6 demo deliverable. |
| **D3** Post-disclosure warm closing + terminate; two reveal scripts + letdown variant | **RE-SCOPED** | Child 2 — disclosure + warm close are the safety-net conversation. The two reveal scripts are pre-written demo/outreach material living in the runbook (Child 5), not app code. |
| **D4** Full "today's calls" dashboard contract (two-number header, ring caveat, groups, filters, empty/coded/pending, refresh, DRY SQLite) | **IN** | Child 3 — full D4 contract. |
| **D5** Recording-active indicator, daily integrity check, zero-log/dropped-line alert | **IN** | Child 3 — D5 integrity. |
| **D6** Disposition coder (daily), written confirmed-lost definition, ambiguous → general | **RE-SCOPED** | Child 3 — confirmed-lost definition encoded in the dashboard's two-number derivation; the who-codes-daily operational piece lives in the runbook (Child 5). |
| **D7** Second-advertised-line primary fallback + CDR last resort; 2-line degrade script | **RE-SCOPED** | SIP-world: trunk forward-semantics screening during procurement (Child 1 E4); numeric analysis fallback documented in runbook (Child 5). |
| **D8** Pin latency ceiling ≤1.5s median parse-to-reply as smoke pass/fail | **RE-SCOPED** | Superseded to **≤2s median parse-to-reply** (X9 reconciled the 1.5s-vs-2s drift); lands as Child 4's Q11 latency gate. |

### Developer-Experience Tasks (X1–X9)

| Original item | Disposition | Now lives as |
|---|---|---|
| **X1** "Week One Build / Runbook" section (prereqs, env, bring-up, first-logged-call) | **IN** | Child 5 runbook (SIP-flavored). |
| **X2** Two concrete Twilio-BD fallbacks; cloud-pilot escape; smoke verdict record | **RE-SCOPED** | Becomes "2 concrete SIP-trunk fallbacks" (T1 re-scope) in Child 1; cloud escape restriction (E6) + verdict record in Child 4. |
| **X3** Canonical 6-value disposition enum + confirmed-lost predicate | **IN** | Child 3 — one canonical `calls.disposition` enum + dashboard derivation. |
| **X4** Error-path table (symptom/cause/fix/verify), write-before-transcribe, busy-call + quiet-vs-dead rule | **IN** | Child 5 error registry + Child 3 integrity (zero-log = quiet-vs-dead rule). |
| **X5** 2-failed-parses → handoff into call-flow spec; degrade + reveal scripts | **IN** | Child 2 — degrade-to-transfer conversation behavior. |
| **X6** Canonical Build Spec with file/module refs + one DoD list; dashboard data contract | **IN** | Child 5 dev docs (schema, view query, retention-log fields). |
| **X7** ops/runbook.md single living doc (daily check, T+14 verify-delete, coding checklist) | **IN** | Child 5 runbook. |
| **X8** dev/README copy-paste (env, webhook, DDL, test-call command) | **IN** | Child 5 dev docs. |
| **X9** Reconcile latency phrase to ≤2s (fix 1.5s-vs-2s drift) | **IN** | Folded into Child 4's Q11 ≤2s gate; this doc uses ≤2s throughout. |

### Engineering Tasks (E1–E12)

| Original item | Disposition | Now lives as |
|---|---|---|
| **E1** Webhook HMAC + param validation + 4xx-not-500 + UNIQUE(CallSid) idempotency; dashboard basic-auth+TLS separate routes | **IN** | Child 1 — trunk-origin verification (not X-Twilio-Signature) + idempotency; dashboard auth already landed in Child 0 / adds to Child 3 dashboard. |
| **E2** Day-one ANI-reliability forward test; hashed ANI dedup + masked display; ANI caveat | **IN** | Child 1 ARI/ESL + Child 3 display. |
| **E3** re_called_evidence column, daily clinic check-in, 3-bucket reporting + remainder | **IN** | Child 3 — two-number/three-bucket derivation from the calls table. |
| **E4** Forward verification (no-answer only + busy ask), record forward type, verified_rings, UI caveat, first-N reported separately | **IN** | Child 1 — trunk forward screen during procurement; caveat renders actual N. |
| **E5** Disclosure-failure = terminate + metadata-only (never silent); pre-render clips at startup | **IN** | Child 2 — disclosure + warm-close. |
| **E6** Cloud-pilot escape restricted to synthetic/demo audio only | **IN** | Child 4 — verdict-record restriction; real audio stays on the pinned box. |
| **E7** Pre-decide 3rd+ concurrent = metadata-only (CDR) capture; never a dropped row | **IN** | Child 1 — busy-call policy at webhook time. |
| **E8** Per-call costed guard + daily Usage poll + 50%/90% alerts + hard stop; max-call-duration guard | **IN** | Child 1 — SIP spend guard (~$10 cap). |
| **E9** Heartbeat row from separate scheduler, daily encrypted backup, supervisor + /health + notification | **IN** | Child 3 — D5 integrity + supervisor. |
| **E10** Resample→16k mono→normalize→transcribe; shift-log summary-only; verify-delete enumerates WAL/temp/exports; epoch UTC + clinic-day boundary + zero-duration rows | **IN** | Child 1/3 — audio contract + retention hygiene; the resample/16k boundary already landed (T4, `AudioFrame`). |
| **E11** Pre-week synthetic disposition fixture (20–30 calls, 2 coders, agreement bar), end-of-week blind gold re-code | **RE-SCOPED** | Child 4 — real-loop calibration with an agreement bar. |
| **E12** Automated test list (harness, idempotency, crash, retention, authz, ANI); N=2 concurrency smoke + p95 + peak VRAM + GPU-residency | **IN** | Child 4 — E12 automated tests + VRAM. |

## Review-accepted block traceability

The original plan also carries four `autoplan-accepted` review blocks
(CEO: 12, Design: 10, DX: 10, Eng: 11). These are the source findings behind
the task rows above; each is operationalized by (or specifically dropped by)
named rows so nothing from the blocks is silently lost either.

| Accepted block item | Traced to |
|---|---|
| CEO — A+C parallel keep + Approach D documented | Child 2 (after-hours safety-net) + Child 3 (capture) + Child 6 (demo); epic scope |
| CEO — forward-on-no-answer day-one prereq, "3 candidate clinics" | **T1 re-scope** → 2 concrete SIP-trunk fallbacks, Child 1 E4 |
| CEO — Twilio BD provisioning + cost + local fallback | T1/X2 → Child 1 trunk + fallback name |
| CEO — 60-min cloud-vs-local smoke test | T4/E6 → Child 4 |
| CEO — 20-min HMS discovery | T5 → Child 7 (discover-then-build HMS gate) |
| CEO — Bangla booking-loop quality bar ≥3/4 + latency ceiling | T3 → Child 2/7 + Child 4 ≤2s (Q11) |
| CEO — outreach list sourcing + first-5 pre-test + warm-count | **T6 dropped** (outreach = gate, not code; Q6) |
| CEO — call-log follow-up disposition + two-number reporting | T2/D4 → Child 3 |
| CEO — weekly gate progress metrics | T8 → Child 4 |
| CEO — objection coding on `no` | **T6 dropped** (outreach = gate, not code; Q6) |
| CEO — full-disk encryption + named raw-audio deletion | **T7 promoted → Child 3** |
| CEO — DRY SQLite sink + audited retention delete | T2 → Child 3 (Q10, audited-delete) |
| Design — demo-first 5-beat storyboard | D1 → Child 6 |
| Design — one-pager, 4 beats, consent 4th | D2 → Child 6 |
| Design — passive-week post-disclosure warm close | D3 → Child 2 |
| Design — dashboard "today's calls" contract | D4 → Child 3 |
| Design — recording indicator + daily integrity + zero-log alert | D5 → Child 3 |
| Design — day-2/3 artifact + reveal scripts | D3 → Child 5 runbook + Child 6 |
| Design — disposition coder + confirmed-lost def + ambiguous→general | D6 → Child 3 |
| Design — degraded forwarding fallback (2nd line / CDR) | D7 → Child 1 E4 + Child 5 |
| Design — latency ceiling + ring caveat + booking slip | D8/X9 + Child 3/7 (≤2s, Q11) |
| Design — disclosure-timing choice recorded | E5 → Child 2 |
| DX — Week One Build/Runbook section | X1 → Child 5 |
| DX — two named fallbacks + cloud escape + smoke verdict record | X2 → Child 1 + Child 4 (E6) |
| DX — canonical 6-value disposition enum + confirmed-lost predicate | X3 → Child 3 |
| DX — crash-safe write-before-transcribe + error-flag + retry | X4 → Child 3/5 |
| DX — error-path table + busy-call + quiet-vs-dead rule | X4 → Child 5 + Child 3 |
| DX — 2-failed-parses → handoff + degrade/reveal scripts | X5 → Child 2 |
| DX — SF_N_RINGS / SF_LATENCY_MS / SF_SPEND_CAP config keys | E8/X9 → Child 1 spend + Child 4 latency |
| DX — gate-blocking scripts timeboxed | D3/X5 → Child 5 runbook |
| DX — ops/runbook.md single living doc | X7 → Child 5 |
| DX — dev/README + canonical Build Spec + one DoD list | X6/X8 → Child 5 |
| Eng — webhook HMAC + idempotency + 4xx-not-500 + dashboard auth | E1 → Child 1 (trunk origin) + Child 0 (dashboard auth, already landed) |
| Eng — day-one ANI-reliability test + hashed-ANI dedup + mask | E2 → Child 1 + Child 3 |
| Eng — re_called_evidence + daily check-in + 3-bucket reporting | E3 → Child 3 |
| Eng — forward semantics honest + verified_rings + busy ask | E4 → Child 1 |
| Eng — disclosure-failure = terminate + pre-rendered clips | E5 → Child 2 |
| Eng — cloud-pilot restricted to synthetic audio | E6 → Child 4 |
| Eng — 3rd+ concurrent = metadata-only, never dropped row | E7 → Child 1 |
| Eng — per-call spend guard + usage poll + alerts + hard stop | E8 → Child 1 |
| Eng — heartbeat + backup + supervisor + /health + notification | E9 → Child 3 |
| Eng — resample→16k mono + shift-log summary-only + verify-delete WAL + epoch UTC | E10 → Child 1/3 (audio contract landed as T4 `AudioFrame`) |
| Eng — Build Spec DoD: synthetic disposition calibration + blind gold re-code + automated test list + N=2 smoke + p95 + VRAM | E11/E12 → Child 4 |

## What was NOT silently dropped (explicit supersession record)

The disposition above is complete: every original T/D/X/E item maps to a child
or a recorded re-scope, or is dropped with a rationale naming the superseding
decision (Q6 for outreach, T1 re-scope for the clinic-count, ≤2s for the
latency ceiling). The review-accepted blocks trace to the same rows. Nothing
from the original plan is carried forward without a row here; anything
superseded is superseded by a named epic decision, not by omission.

## Supersedes

This table ships as a Child 0 artifact and supersedes `TODOS.md` (the
"From Eng review (Phase 3)" block, in particular lines 36–40). Operational
policies that were deferred to the runbook are tracked as tasks in the epic's
Child 5, not here.