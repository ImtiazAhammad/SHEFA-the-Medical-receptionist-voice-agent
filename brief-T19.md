# Brief — T19 (P2) — coverage floor + ratchet

- Task: T19 — Child 0 — `--cov-fail-under=47` now; ratchet per child; rewritten
  modules 100% themselves
- Surfaced by: D-ENG27 (M10)
- Files: pyproject.toml, AGENTS.md
- Verify: `pytest` green with floor

## Verbatim plan text

> The coverage bar matches reality: land `--cov-fail-under=47` (today's measured
> floor, 39 tests, adapters 0%) now and ratchet per child; REWRITTEN modules
> (pipeline, adapters, call-control, auth) must hit 100% themselves while the
> legacy tail converges; the AGENTS.md `=100` DoD stays for new modules
> (D-ENG27).

## Current state (measured this session, not assumed)

- Suite: 639 tests passing, measured TOTAL **88.76%** (2101/2367 lines).
- The plan's "47" was measured when the repo had 39 tests and adapters at 0%.
  T1–T18 lifted it to 88.76%. Landing 47 today would permit a 41-point
  regression — see Ruling 1.
- Per-module at the rewritten set the plan names (pipeline, adapters,
  call-control, auth):
  - 100%: `pipeline/vad.py`, `pipeline/error_taxonomy.py`,
    `pipeline/language_detector.py`, `telephony/control.py`, `auth.py`,
    `audio.py`, `config/settings.py`, `models/base.py`, `tts/piper_tts.py`,
    `stt/whisper_local.py`
  - **NOT 100%**: `pipeline/voice_pipeline.py` (80%), and the network adapters
    (`openai_llm` 46%, `anthropic_llm` 26%, `openai_compatible_llm` 44%,
    `openai_stt` 35%, `elevenlabs_stt` 44%, `elevenlabs_tts` 39%,
    `vits_tts` 35%).
- `pyproject.toml` `[tool.pytest.ini_options]` has only `asyncio_mode` and
  `testpaths` — no addopts, no coverage config at all.
- `AGENTS.md:20` says "100% test coverage is the goal" with no floor and no
  statement that rewritten modules are held to 100%.

## Ruling 1 — the floor value

The plan names 47 as "today's measured floor", measured at 39 tests. The repo
now measures 88.76%. A floor is a ratchet: setting it below the measured value
does not "match reality", it licenses regression. Land the floor at the
**current measured floor**, not the plan's stale number. The plan's intent
("the coverage bar matches reality") is served by 88; 47 would be an
anti-ratchet.

## Ruling 2 — rewritten modules at 100%

`voice_pipeline.py` (rewritten in T11–T14) is at 80%, and the network adapters
are 26–46%. The plan requires rewritten modules to hit 100% themselves. Rather
than silently drop the requirement or silently claim it, T19:
- enforces 100% per-file on the modules that ARE at 100%, so they cannot
  silently regress, and
- records the not-yet-100% modules explicitly as a named convergence list, so
  the gap is visible rather than implied.

This is `fail_under` + `per-file` machinery, not new tests. Closing the
adapter gaps is real test work and is NOT T19 (see Deferred).

## Steps

1. Write a failing test that reads the pytest/coverage config and asserts:
   a. a coverage floor is configured and is >= the measured floor (88),
   b. the per-file 100% set is non-empty and every listed file really is 100%,
   c. the convergence list is explicit and every listed file is below 100%.
   RED: no coverage config exists today.
2. Run → RED.
3. Implement:
   - `pyproject.toml`: `[tool.pytest.ini_options] addopts` with
     `--cov=sefa --cov-report=term-missing` and a `[tool.coverage.report]`
     `fail_under` at the measured floor, plus `per_file_ignores` NOT used to
     hide anything.
   - a small, testable module holding the ratchet policy (the 100% set and the
     convergence list) so a test can assert both against real coverage data.
   - `AGENTS.md`: state the real floor, that it ratchets upward per child, and
     that rewritten modules are held to 100%.
4. Run → GREEN. Full suite green WITH the floor active (`pytest` bare).
5. Ruff.
6. Commit + `graphify update .`.

## Verify gate

`pytest` (bare, no flags) green with the floor enforced.
