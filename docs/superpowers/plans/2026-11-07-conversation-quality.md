# Conversation Quality Implementation Plan

> **Superseded in order and scope by [`docs/research/2026-11-08-architecture-critique.md`](../../research/2026-11-08-architecture-critique.md).** Tasks 1, 5 and 7 survive as quick wins. Task 3 (VAD pre-roll) is wrong: the first syllable is lost to the browser's mute gate in `console.html`, not the VAD.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a Bangla/English booking call hold together when speech recognition and the router make mistakes: no invented bookings, no crashes on missing arguments, names and phone numbers survive mishearing, and small talk is not treated as a transfer request.

**Architecture:** The model only proposes an action. Code decides whether it may run: missing arguments become a spoken question, bookings/cancellations/moves are confirmed with a yes/no before they run, names are fuzzy-matched against the directory, and phone numbers are parsed and validated in code. Audio problems (clipped first syllable) are fixed in the VAD, not papered over in the prompt.

**Tech Stack:** Python asyncio, SQLite, faster-whisper, Ollama gemma2:9b, Piper/Kokoro, pytest. `difflib` for fuzzy matching (no new dependency).

**Spec:** The observed call logs of 2026-11-07 (two console calls, quoted in the conversation that produced this plan) and the "Goal and status" table in `README.md`.

## Global Constraints

- Clinic time is Asia/Dhaka; dates `YYYY-MM-DD`, times `HH:MM`; spoken forms come from `shefa.spoken`.
- The session `patient_id` is the only acting identity; a model-supplied `patient_id` is ignored.
- Ruff line length 100; coverage floor 88%; per-module ratchet in `src/shefa/coverage_policy.py`.
- Tests never read `configs/local.yaml` or load real models (`SHEFA_IGNORE_LOCAL_CONFIG`, `SHEFA_SKIP_WARMUP`).
- Phone numbers are normalised with `shefa.clinic.store.normalize_phone` (`+8801711000123` -> `01711000123`).

## Review Focus

- Router calls a tool with a required argument missing (`reschedule_appointment` with only `appointment_id`): the caller is asked for it, nothing is raised, nothing is changed.
- Router invents a date/time the caller never said: nothing is booked until the caller says yes to the read-back.
- Caller says "ঠিক আছে", "ধন্যবাদ", "bye": never routed to `transfer_to_human`.
- Phone number dictated as digit words ("সাত আট দুই ...", "seven eight two ...") or digits: parsed, validated as a Bangladeshi mobile, never registered when malformed.
- Doctor/department name mis-heard or mis-spelled ("ডাক্তর সুলতানা", "পিশু বিভাগ", "হাসান"): the agent says who it thinks they mean or lists the choices, never the same apology twice.

---

### Task 1: Missing arguments become a question, never an exception

**Files:**
- Modify: `src/shefa/tools/executor.py:28-160` (replace `args["x"]` reads), `src/shefa/pipeline/actions.py` (new `need_text`)
- Test: `tests/unit/test_tool_arguments.py`

**Interfaces:**
- Produces: `missing_arguments(tool_name: str, args: dict) -> list[str]` in `executor.py` (names of required, non-empty-able arguments that are absent or null, excluding `patient_id`); `execute_tool` returns `{"needs": [<names>]}` instead of raising; `need_text(tool_name: str, result: dict, language: str) -> str | None` in `actions.py`, used by `_generate_reply` after `confirmation_text`/`error_text`.

- [ ] **Step 1: Write failing tests** in `tests/unit/test_tool_arguments.py`: `test_reschedule_without_a_date_asks_for_it` (`execute_tool("reschedule_appointment", {"appointment_id": "1"}, session)` == `{"needs": ["new_date", "new_time"]}`), `test_send_confirmation_without_patient_id_uses_the_session`, `test_need_text_asks_in_both_languages` (bn text contains "কোন দিন" for `new_date`, en contains "which day"), `test_no_tool_raises_keyerror` (parametrised over every tool name with `{}` args).
- [ ] **Step 2: Run** `pytest tests/unit/test_tool_arguments.py -v`; expect FAIL (`KeyError`).
- [ ] **Step 3: Implement** `missing_arguments` from each tool's `parameters["required"]` in `shefa.tools.definitions`; call it at the top of `execute_tool` before the handler. Replace `args["patient_id"]` in `_send_confirmation` and `_lookup_patient_history` with `_acting_patient(session)`.
- [ ] **Step 4: Implement `need_text`** with one template per argument name (`new_date`, `new_time`, `date`, `time`, `doctor_name`, `appointment_id`, `phone`) in bn and en; wire into `_generate_reply` so a `needs` result is spoken verbatim.
- [ ] **Step 5: Run** the full suite; expect PASS.
- [ ] **Step 6: Commit** `fix: missing tool arguments are asked for, not raised`.

### Task 2: Confirm before booking, cancelling or moving

**Files:**
- Create: `src/shefa/pipeline/confirm.py`
- Modify: `src/shefa/pipeline/voice_pipeline.py` (`_generate_reply`, before `execute_tool`), `src/shefa/session/manager.py` (nothing new if `session.metadata` is used)
- Test: `tests/unit/test_confirm.py`

**Interfaces:**
- Produces: `NEEDS_CONFIRMATION = frozenset({"book_appointment", "cancel_appointment", "reschedule_appointment"})`; `read_back(name: str, arguments: dict, language: str) -> str` (uses `spoken_date`/`spoken_time`/`spoken_doctor`); `yes_no(text: str) -> bool | None` (bn: হ্যাঁ, জি, ঠিক আছে, ওকে, করুন; en: yes, yeah, ok, sure; no: না, লাগবে না, no, cancel that; anything else `None`); pending action stored at `session.metadata["pending"] = {"name": str, "arguments": dict}`.

- [ ] **Step 1: Write failing tests**: `test_yes_no_bangla_and_english` (table of utterances), `test_a_booking_is_read_back_and_not_run_until_yes` (fake router returns `book_appointment`; first turn speaks the read-back and the clinic store has no appointment; second turn "হ্যাঁ" books it), `test_no_discards_the_pending_action`, `test_an_unrelated_reply_keeps_the_question_open_once_then_drops_it`.
- [ ] **Step 2: Run**; expect FAIL (module missing).
- [ ] **Step 3: Implement** `confirm.py`; in `_generate_reply`, if `session.metadata.get("pending")` and `yes_no(latest_user_text)` is not `None`, run or drop it without calling the router; otherwise for a tool in `NEEDS_CONFIRMATION` store it and speak `read_back(...)`.
- [ ] **Step 4: Run** full suite (update `test_voice_flows.py` booking/cancel/reschedule flows to say yes); expect PASS.
- [ ] **Step 5: Commit** `feat: read back and confirm bookings before they run`.

### Task 3: Keep the first syllable (VAD pre-roll)

**Files:**
- Modify: `src/shefa/pipeline/vad.py` (`EnergyVAD.__init__`, `_tick`, `_flush`, `_reset_segment`)
- Test: `tests/unit/test_vad.py`

**Interfaces:**
- Produces: `EnergyVAD(..., pre_roll_s: float = 0.3)`; the flushed segment starts `pre_roll_s` seconds before the first speech chunk (or at the start of the buffer if less is available).

- [ ] **Step 1: Write failing tests**: `test_segment_includes_pre_roll_before_first_speech` (noise, then speech; flushed bytes begin with the last 0.3 s of noise), `test_pre_roll_never_exceeds_available_audio`, `test_pre_roll_zero_restores_old_behaviour`.
- [ ] **Step 2: Run**; expect FAIL.
- [ ] **Step 3: Implement** a bounded `collections.deque` of recent non-speech chunks, prepended when speech starts; keep `vad.py` at 100% coverage.
- [ ] **Step 4: Verify live**: `scripts/simulate_call.py "শিশু বিভাগে কে আছে?"` transcribes "শিশু", not "িশু".
- [ ] **Step 5: Commit** `vad: keep 0.3 s before speech so the first syllable is not clipped`.

### Task 4: Names and departments match fuzzily and fail helpfully

**Files:**
- Modify: `src/shefa/clinic/store.py:305` (`find_doctor`, new `find_department`), `src/shefa/integrations/ehr.py` (`list_doctors` department lookup, `get_doctor_info`), `src/shefa/integrations/calendar.py` (`_resolve_doctor`), `src/shefa/pipeline/actions.py` (`error_text` for unknown doctor/department)
- Test: `tests/unit/test_fuzzy_names.py`

**Interfaces:**
- Produces: `ClinicStore.find_doctor(query: str) -> dict | None` keeps its signature but also matches after dropping titles (`ডক্টর`, `ডাক্তর`, `ডাক্তার`, `ডা.`, `dr`) and by `difflib.SequenceMatcher` ratio >= 0.75 on Bangla/English names; `ClinicStore.closest_doctors(query: str, n: int = 2) -> list[dict]`; `ClinicStore.find_department(query: str) -> dict | None` (strips `বিভাগ`/"department", fuzzy).

- [ ] **Step 1: Write failing tests**: `ডাক্তর সুলতানা` -> Sultana, `ডক্টর সুলতানার` -> Sultana, `পিশু বিভাগ` -> the paediatrics department, `হাসান` with only `হোসেন` in the directory -> `find_doctor` is `None` but `closest_doctors` returns `হোসেন`; `test_unknown_doctor_message_names_the_closest_and_lists_the_rest` (bn text contains the suggestion and the doctor list, and differs from the generic apology).
- [ ] **Step 2: Run**; expect FAIL.
- [ ] **Step 3: Implement** with a small `_normalise_bn` (drop titles, zero-width characters, trailing possessive `-র`/`-ের`).
- [ ] **Step 4: Run** full suite; expect PASS.
- [ ] **Step 5: Commit** `directory: fuzzy doctor/department matching with a useful "did you mean" reply`.

### Task 5: Phone numbers: parse, validate, confirm caller ID

**Files:**
- Create: `src/shefa/phone_words.py`
- Modify: `src/shefa/integrations/ehr.py:14` (`verify_patient`), `src/shefa/pipeline/voice_pipeline.py` (digit-only transcripts are never re-heard, see Task 7), `src/shefa/pipeline/actions.py` (templates)
- Test: `tests/unit/test_phone_words.py`

**Interfaces:**
- Produces: `parse_spoken_digits(text: str) -> str` (Bangla digits ০-৯, Latin digits, Bangla words এক..নয়/শূন্য, English words zero..nine, `double`/ডাবল repeats the next digit; separators ignored); `is_bd_mobile(number: str) -> bool` (after `normalize_phone`: `^01[3-9]\d{8}$`); `speak_digits(number: str, language: str) -> str` (digit words, grouped 3-4-4 with pauses).
- `verify_patient` returns `{"verified": False, "error": "invalid phone"}` for a malformed number and does NOT register a patient; if the session has a caller ID (`call_context`), the agent first asks "আপনার নম্বর কি 017..., ঠিক?" using `speak_digits`.

- [ ] **Step 1: Write failing tests**: `সেভেন আট টু সেভেন থ্রি সেভেন জিরো সেভেন ফোর` is too short and invalid; `০১৭৮২৭৩৭০৭৪` -> `01782737074`; `zero one seven eight two seven three seven zero seven four` -> same; `ডাবল সেভেন` -> `77`; `test_verify_patient_rejects_a_malformed_number_without_registering` (patient count unchanged for `0787374`); `test_speak_digits_reads_each_digit`.
- [ ] **Step 2: Run**; expect FAIL.
- [ ] **Step 3: Implement** the parser and validator; call `parse_spoken_digits` on the `phone` argument inside `verify_patient`.
- [ ] **Step 4: Run** full suite; expect PASS.
- [ ] **Step 5: Commit** `identity: parse and validate spoken phone numbers; never register a malformed one`.

### Task 6: Small talk, goodbyes and a transfer that cannot happen

**Files:**
- Create: `src/shefa/pipeline/social.py`
- Modify: `src/shefa/pipeline/voice_pipeline.py` (`_generate_reply`, before the router), `src/shefa/pipeline/actions.py` (router hint: transfer only when asked or in an emergency), `src/shefa/clinic/store.py` (`callback_requests` table + `add_callback_request`), `src/shefa/tools/executor.py` (`_transfer_to_human` records a callback when no `on_call_numbers`)
- Test: `tests/unit/test_social.py`

**Interfaces:**
- Produces: `classify_social(text: str) -> Literal["bye", "thanks", "ack"] | None` (বাই, আল্লাহ হাফেজ, খোদা হাফেজ, ধন্যবাদ, ঠিক আছে, ওকে, bye, thanks, ok); `social_reply(kind: str, language: str) -> str`; `ClinicStore.add_callback_request(phone: str, reason: str) -> int`.
- A `bye` reply ends the call politely; `ack` outside a pending confirmation gets "আর কিছু লাগবে?"; when no human number is configured, `transfer_to_human` says "আমরা আপনাকে ফোন করব" and stores the request.

- [ ] **Step 1: Write failing tests**: table for `classify_social`; `test_goodbye_never_calls_the_router` (router fake asserts it is not called); `test_transfer_without_numbers_records_a_callback`.
- [ ] **Step 2: Run**; expect FAIL.
- [ ] **Step 3: Implement** and wire; show callbacks in the console Status/Calls tab only if trivial (otherwise leave for later).
- [ ] **Step 4: Run** full suite; expect PASS.
- [ ] **Step 5: Commit** `conversation: handle thanks/ok/bye in code; a missing human line becomes a callback request`.

### Task 7: Language switching needs evidence, digits are neutral

**Files:**
- Modify: `src/shefa/pipeline/voice_pipeline.py` (`_convincing_switch`, the re-hear block)
- Test: `tests/unit/test_language_stickiness.py`

**Interfaces:**
- Produces: `_convincing_switch(result) -> bool` is true only when the transcript has >= 3 words AND `result.confidence >= 0.6`; a transcript that is mostly digits (`>= 70%` digit characters) never triggers a re-hear and never switches the language; `MIN_CONFIDENCE_TO_SWITCH_LANGUAGE = 0.6`.

- [ ] **Step 1: Write failing tests**: `test_a_dictated_number_is_not_heard_again` (STT returns `01782737074` as English; `stt.calls == ["auto"]`, language unchanged), `test_a_low_confidence_long_english_guess_is_heard_again`, keep the existing three tests passing.
- [ ] **Step 2: Run**; expect FAIL.
- [ ] **Step 3: Implement** the two conditions.
- [ ] **Step 4: Run**; expect PASS.
- [ ] **Step 5: Commit** `voice: digits never flip or re-hear a turn; a switch needs confidence`.

### Task 8: Regression scenarios and router evals from the real call

**Files:**
- Modify: `configs/lab/scenarios.yaml`, `scripts/bench_router.py` (`CASES`)
- Test: `tests/unit/test_lab.py` (scenario file still validates)

**Interfaces:**
- Consumes: scenario schema already used in `configs/lab/scenarios.yaml`.

- [ ] **Step 1: Add scenarios**: `misheard-doctor` (ডাক্তর সুলতানা), `clipped-department` (িশু বিভাগে কে আছে?), `phone-dictation-bn`, `phone-dictation-en`, `goodbye-bn` (ঠিক আছে / বাই ends politely), `reschedule-without-time`, `invented-slot-needs-confirmation`, `my-appointments` ("আমার কি কোনো অ্যাপয়েন্টমেন্ট বুক আছে?" must not transfer).
- [ ] **Step 2: Add router cases** to `scripts/bench_router.py` for the same utterances (expected tool or `None`).
- [ ] **Step 3: Run** `uv run shefa lab run --audio` and `PYTHONPATH=src python scripts/bench_router.py gemma2:9b`; expect all scenarios pass and router tool accuracy >= 16/20.
- [ ] **Step 4: Commit** `lab: regression scenarios from the 2026-11-07 console calls`.

### Task 9: Offline, warm and quiet

**Files:**
- Modify: `src/shefa/cli.py` (`run_serve`: set `HF_HUB_OFFLINE=1` when `fetch-models` has run), `src/shefa/warmup.py` (warm the English voice), `src/shefa/main.py` (route `/favicon.ico` as 204; stop logging each `/api/v1/calls/ringing` poll), `src/shefa/config/settings.py` (log call at startup uses `%s` with structlog: fix the format)
- Test: `tests/unit/test_cli.py`, `tests/unit/test_warmup.py`

- [ ] **Step 1: Write failing tests**: `test_serve_sets_hf_offline_when_models_are_present`, `test_warm_up_synthesises_both_languages`, `test_favicon_needs_no_auth`.
- [ ] **Step 2: Run**; expect FAIL.
- [ ] **Step 3: Implement**; confirm with `uv run shefa serve` that no `huggingface.co` request appears in the log.
- [ ] **Step 4: Run** full suite; expect PASS.
- [ ] **Step 5: Commit** `ops: run offline after setup, warm the English voice, quiet logs`.

---

## Skills worth installing (from `npx skills find`, not yet verified beyond install counts)

- `wshobson/agents@llm-evaluation` (13.3K installs): for Task 8 and any later router/dialogue eval set.
- `wshobson/agents@prompt-engineering-patterns` (24.2K installs): for the router prompt in `extractor_system_prompt`.
- `sickn33/agentic-awesome-skills@voice-agents` (896) and `davila7/claude-code-templates@voice-agents` (347): turn-taking, barge-in and latency patterns for the next round (the console is half-duplex and cannot be interrupted).

Not planned here: barge-in, caller-ID confirmation over Asterisk, and the Bangla voice quality work; each deserves its own plan.
