# Dialogue Manager Implementation Plan

**Status 2026-11-08:** Tasks 1-8 are implemented and tested (1492 tests; lab 26/26 with real models and voices). Open: the real-microphone acceptance run, a browser check of the mic-gate change, and the items in `docs/research/2026-11-08-verbex-demo-analysis.md` section 4 that are not met yet (A1 p95, A3 interruption, A4 real-audio WER, V1/V4/V5 voice).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (the user said "go ahead"; implemented natively, one task after another). Steps use checkbox syntax.

**Goal:** Make SHEFA hold a conversation: it knows the doctors, answers indirect questions from that knowledge, asks for what is missing, confirms before it changes anything, and survives mishearing.

**Architecture:** Doctor knowledge lives in the clinic directory (enriched `profile`) and is given to the model as a compact, cached block in both the router and the chat prompt. The model proposes; code resolves names against the directory, asks for missing arguments, and requires an explicit yes before booking, cancelling or moving. Facts (dates, times, fees) are still rendered in code.

**Tech Stack:** Python asyncio, SQLite, Ollama gemma2:9b, pytest.

**Spec:** `docs/research/2026-11-08-architecture-critique.md` (target design and doctor fields).

## Where the earlier plans stand

| Plan | State | Used here |
|---|---|---|
| `2026-11-01-asterisk-telephony-and-reminders.md` | Tasks 1-8 built and merged (PR #7); never run against a real Asterisk | Not touched. Live test with a softphone is a separate step |
| `2026-11-07-conversation-quality.md` | Superseded | Its tasks 1, 2, 5, 6, 7 are Tasks 4-6 below; task 3 (VAD pre-roll) is replaced by Task 7 (browser mic gate) |
| `docs/fine-tuning-plan.md` | Later phase | Needs the lab and bench from Task 8 as its baseline |
| README roadmap items 1-6 | 1-5 done/built, 6 in progress | Updated in Task 8 |

## Global Constraints

- Clinic time is Asia/Dhaka; dates `YYYY-MM-DD`, times `HH:MM`; spoken forms from `shefa.spoken`.
- The session `patient_id` is the only acting identity; model-supplied ids are ignored.
- Ruff line length 100; coverage floor 88%; per-module ratchet in `src/shefa/coverage_policy.py`.
- Tests never read `configs/local.yaml` or load real models.
- The directory block must stay under ~1,500 tokens for 20 doctors so it fits `num_ctx` 4096 with history.

## Data

The sample clinic (`configs/clinic.example.yaml`) is fictional and says so. Real names come from `scripts/import_labaid_directory.py` (Labaid's public listing, robots.txt checked, written to the gitignored `configs/clinic.labaid.local.yaml`; schedules are placeholders because the site publishes none). Ibn Sina and Popular were not scraped: their robots.txt restricts automated access; use their data only with their permission or exports the clinic provides.

## Review Focus

- Indirect request ("my child has a fever", "is there a lady doctor", "who is best for the heart") is answered from the directory, with no tool call and no medical advice.
- Caller says a doctor's name as heard ("ডাক্তর সুলতানা", "হাসান"): resolved to the right doctor, or a "did you mean" naming the closest, never the same apology twice.
- Tool call with a missing argument: a question, not an exception.
- Booking/cancel/reschedule never runs on the model's say-so alone.
- Dictated phone number (digits or digit words): parsed and validated; a malformed one registers no patient.

---

### Task 1: Enriched doctor profile in the directory
Files: `src/shefa/clinic/store.py` (`profile` column + migration, `upsert_doctor(..., profile=)`, `doctors()` returns `profile` dict), `src/shefa/clinic/loader.py` (read and validate `profile`), `configs/clinic.example.yaml`. Test: `tests/unit/test_doctor_profile.py`.
Interface: profile keys `designation, experience_years, gender, languages, room, conditions{en,bn}, aliases, blurb{en,bn}, fees{new,followup,report}, booking_notes{en,bn}`; unknown key -> `ClinicError`.

### Task 2: Directory block in the prompts
Files: create `src/shefa/clinic/brief.py` (`directory_brief(store) -> str`); modify `src/shefa/prompts.py`, `src/shefa/session/messages.py`, `src/shefa/pipeline/actions.py` (`extractor_system_prompt(..., directory="")`, canonical-name hint). Tests: `tests/unit/test_directory_brief.py`, additions to `tests/unit/test_action_extraction.py`; extend `scripts/bench_router.py` with indirect phrasings and the directory.

### Task 3: Fuzzy names, ambiguity and "did you mean"
Added after real data arrived: Labaid's listing has several Rahmans and Hossains, so a surname must resolve to *one* doctor or produce "Which one: Lutfor Rahman or Mahbubor Rahman?" (`ClinicStore.find_doctors(query) -> list[dict]`; `find_doctor` returns a doctor only when exactly one matches).
Files: `src/shefa/clinic/store.py` (`find_doctor` fuzzy + aliases, `closest_doctors`, fuzzy `find_department`), `src/shefa/pipeline/actions.py` (`error_text` unknown doctor). Test: `tests/unit/test_fuzzy_names.py`.

### Task 3b: Answer the question that was asked
Live finding (2026-11-08): "is there a lady doctor?" and "where is the room?" both returned the same full doctor card, and the card has no room. `_doctor_card` must include the profile (designation, room, gender, languages, experience, notes), and directory questions (`get_doctor_info`, `list_doctors`, `list_departments`) are answered by a grounded model reply that states only what was asked, with dates, times and fees still rendered by `shefa.spoken`. Test: a scripted model asked about the room answers with the room and nothing else.

### Task 4: Missing arguments, my appointments, phone validation
Files: `src/shefa/tools/executor.py`, `src/shefa/tools/definitions.py` (`list_my_appointments`), `src/shefa/integrations/ehr.py` (`verify_patient` validates), create `src/shefa/phone_words.py`, `src/shefa/pipeline/actions.py` (`need_text`, templates). Tests: `test_tool_arguments.py`, `test_phone_words.py`.

### Task 5: Confirm before acting; small talk
Files: create `src/shefa/pipeline/confirm.py` and `src/shefa/pipeline/social.py`; modify `voice_pipeline.py`. Tests: `test_confirm.py`, `test_social.py`.

### Task 6: Turn and language robustness
Files: `voice_pipeline.py` (`_convincing_switch`, noise segments not counted toward escalation). Test: `test_language_stickiness.py`.

### Task 7: Browser microphone gate
Files: `src/shefa/static/console.html` (no 0.25 s tail; gate only while audio is actually queued). Verified in a real browser with Playwright where possible.

### Task 8: Evaluate and document
Files: `configs/lab/scenarios.yaml`, `scripts/bench_router.py`, `README.md`, this plan's checkboxes. Run `shefa lab run --audio`, `scripts/bench_router.py`, full pytest; compare against the pre-change baseline recorded in the commit message of Task 2.
