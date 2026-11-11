# CLAUDE.md: ByteVoice Bangla (StrategyByte AI Engineer take-home)

Deadline: **Thu 5 Nov 2026, 23:59 BST (UTC+6)**. Target finish 21:00 BST.

## Start of every session
1. Read `docs/BUILD_PLAYBOOK.md` in full. It is the build playbook and the single source of truth (`README.md` is the reviewer-facing submission README).
2. Go to **§12 Progress checklist** and continue from the first unchecked item. Do not redo ticked items.
3. The original brief is `StrategyByte_AI_Engineer_Task_Brief.pdf` (read it natively with the Read tool if anything in the playbook is unclear).

## While working
- Tick `[x]` in §12 as soon as an item is done, and append a row to the **Session log** before ending a session (what changed, what's next, blockers).
- Record every deviation from the plan (provider swap, cut feature, schema change) in `docs/decisions.md` with the reason.
- Look up current library APIs (LiveKit Agents, Gemini Live model ids, Supabase SSR, R3F) with Context7 before writing code. Model ids and plugin APIs change often.
- Keep the end-to-end success path working at all times; follow the cut-line in §11 when behind.
- Fake patient data only. Never commit secrets: `.env*` is git-ignored, and `.env.example` holds names only.
- Draft the submission email, but never send it; the user sends it.

## Code rules
- Pydantic models / TypeScript DTOs for every request body and tool argument; never `any`.
- Types in `types/` (web) or `schemas/` (agent); fixed values in `constants`.
- try/except or try/catch in every handler and tool, with structured logging (`logger.debug` / a logger, never `print` or `console.log`).
- Full-word identifiers; all database access through the repository layer.
- Production-only comments: no narration, ticket references, TODOs or commented-out code. Put the why in commit messages.
