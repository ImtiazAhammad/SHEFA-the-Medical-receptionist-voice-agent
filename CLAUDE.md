# SHEFA - bilingual (Bangla/English) voice receptionist for clinics in Bangladesh

## Start here

Current state, what has been built, decisions and next steps (kept up to date by every session):

@docs/project-status.md

Other docs worth knowing before changing things:
- `docs/demo-guide.md` - how to run and show the agent without a phone line (lab, voice test, console)
- `docs/fine-tuning-plan.md` - what to train next and with which data
- `docs/research/bangla-english-voice-models-2026-11.md` - model, dataset and free-tier research
- `docs/research/verbex-comparison.md` - competitor voice and the data needed to match it
- `docs/telephony-options.md` - why SIP, the trunk options, testing without one
- `AGENTS.md` - testing and coverage rules

## Rules for this repo

- Run `uv run pytest` and `uv run python scripts/check_coverage.py` before committing; keep ruff
  clean (`uv run ruff check src tests`). Modules listed as fully covered in
  `src/shefa/coverage_policy.py` must stay at 100%.
- Dates, times, IDs and fees are rendered in code (`src/shefa/spoken.py`), never by the model.
- Bangla text: Python's `\w` does not match Bangla vowel signs, and the danda (।) is in the
  Devanagari block. Use explicit script ranges.
- After finishing a piece of work, update `docs/project-status.md` (what was done, decisions,
  next steps) so the next session starts with the full picture.

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

Key routing rules:
- Product ideas/brainstorming → invoke /office-hours
- Strategy/scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Design system/plan review → invoke /design-consultation or /plan-design-review
- Full review pipeline → invoke /autoplan
- Bugs/errors → invoke /investigate
- QA/testing site behavior → invoke /qa or /qa-only
- Code review/diff check → invoke /review
- Visual polish → invoke /design-review
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Save progress → invoke /context-save
- Resume context → invoke /context-restore
- Author a backlog-ready spec/issue → invoke /spec