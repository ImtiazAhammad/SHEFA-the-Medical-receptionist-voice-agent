# Brief — T18 (P2) — bounded queues + put timeouts + concurrency assert

- Task: T18 — Child 0 — bounded queues + put timeouts + concurrency assert (task
  count baseline, qsize 0); instance-attrs registry + autouse fixture
- Surfaced by: D-ENG21 (H11), D-ENG22 (M1)
- Files: twilio.py, sip.py, registry.py, tests/conftest.py
- Verify: N=2 test passes AND leaks detected
- Plan block: `docs/designs/shefa-spec-epic-plan.md:877-881`; design decision at
  plan:265.

## Verbatim plan text

> Concurrency is bounded and asserted: the two media queues are bounded with
> `put()` timeouts (the playback worker currently `break`s on send errors and
> silently accumulates); the N=2 / 3rd+=CDR tests assert task count returns to
> baseline and `playback_queue.qsize() == 0` after each call; `ModelRegistry`
> adapters move from class attrs to instance attrs with an autouse reset fixture
> so the suite is order-independent (D-ENG21, D-ENG22).

## Current state (read, do not assume)

- `src/sefa/telephony/twilio.py:173-174` — BOTH queues unbounded:
  `asyncio.Queue()` for `audio_queue` and `playback_queue`. No `maxsize`.
- `src/sefa/telephony/twilio.py:192-193` — `_playback_worker` does
  `except Exception: break`, so the FIRST send error silently kills the
  playback worker for the rest of the call while the pipeline keeps putting
  frames into a queue nobody drains → unbounded growth.
- `src/sefa/telephony/twilio.py:205` — `await audio_queue.put(audio_bytes)`
  with no timeout → a stalled pipeline blocks the socket reader forever.
- `src/sefa/pipeline/voice_pipeline.py:80` — `await playback_queue.put(frame)`
  with no timeout (same unbounded/stall class, pipeline side).
- `src/sefa/models/registry.py:16-18` — `_stt`, `_tts`, `_llm` are CLASS attrs.
  `self._stt = ...` in `get_stt` shadows into the instance, but a test that
  assigns `ModelRegistry._llm = fake` mutates shared class state for the whole
  process → order-dependent suite.
- `tests/conftest.py` — 10 lines, only a `sample_config` fixture. No autouse
  registry reset.
- There is NO `src/sefa/telephony/sip.py` yet. The plan's Files list names it
  (Child 1 owns it). T18 does not create it — see Ruling 1.
- No queue-size or put-timeout config key exists in `settings.py` /
  `configs/default.yaml` yet.

## Scope decisions

1. `sip.py` is NOT created (it belongs to Child 1, per the T16 disposition
   table). T18 makes the queue behavior correct in the one place media queues
   exist today (`twilio.py`) and keeps the helper reusable for `sip.py`.
2. Bounds and timeouts are configurable (`pipeline.media.*`), because a
   queue depth is a deployment property (clinic box vs trunk), not a constant.

## Steps (RED-GREEN order)

1. Write failing tests in `tests/unit/test_concurrency_bounds.py`:
   a. `test_media_queues_are_bounded` — the queue factory returns queues with
      a `maxsize` > 0.
   b. `test_audio_queue_put_times_out_when_the_pipeline_never_drains` — put
      into a full queue raises `QueueFull` (not hang).
   c. `test_playback_worker_survives_a_send_error` — a `send_json` that raises
      once then succeeds: the worker keeps draining afterwards (today it
      `break`s → RED).
   d. `test_playback_worker_gives_up_only_after_the_drain_budget` — persistent
      send errors exit the worker, but only after consuming the bounded
      backlog, so the queue is not orphaned mid-flight.
   e. `test_queue_drains_to_zero_after_a_call` — after a simulated call the
      playback queue is empty (`qsize() == 0`).
   f. `test_task_count_returns_to_baseline_after_a_call` — no task leaked.
   g. `test_n2_concurrent_calls_leave_no_tasks_or_queued_frames` — the N=2
      concurrency assertion.
   h. `test_registry_state_is_per_instance` — two `ModelRegistry()` instances
      do not share adapters.
   i. `test_autouse_fixture_resets_the_shared_registry` — the autouse fixture
      clears `registry` between tests (order-independence).
2. Run them — RED.
3. Implement:
   - `settings.pipeline.media.*`: `audio_queue_maxsize`, `playback_queue_maxsize`,
     `audio_put_timeout_s`, `playback_put_timeout_s`.
   - A queue factory + bounded-put helpers in `telephony/` (reusable by `sip.py`).
   - `_playback_worker` no longer `break`s on the first error; it counts
     consecutive failures, logs, and exits only past a bounded budget.
   - `ModelRegistry.__init__` sets `self._stt/_tts/_llm = None` (instance attrs).
   - `tests/conftest.py` autouse fixture resetting the shared `registry`.
4. Run — GREEN. Run the full suite (618 baseline must hold).
5. Run ruff on touched files.
6. Commit: `T18: bounded media queues + put timeouts + concurrency assert (D-ENG21, D-ENG22)`.
7. `graphify update .`

## Verify gate

- N=2 test passes.
- Leaks ARE detected: a deliberately leaked task / un-drained frame makes the
  assertion fail (prove the assertion has teeth — do not skip this).
