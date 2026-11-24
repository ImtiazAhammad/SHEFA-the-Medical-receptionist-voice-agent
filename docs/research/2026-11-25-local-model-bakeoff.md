# Test bench baseline and local model bake-off, 2026-11-25

Sub-project 1 of `docs/superpowers/specs/2026-11-25-shefa-human-front-desk-design.md`.
Tools: `shefa lab score`, `shefa lab bakeoff`, `shefa lab compare` (plan:
`docs/superpowers/plans/2026-11-25-test-bench-and-bakeoff.md`).

## Status

- **Baseline: done.** Today's agent (the guided engine) on its configured model, gemma2-9b AWQ
  served by vLLM as `shefa-llm`, against all 112 bench callers.
- **Bake-off of the other local models: not run yet.** The graphics card (RTX 4060 Ti, 16 GB)
  is held by the running services: vLLM with gemma2-9b (9.9 GB, serving `shefa serve` and the
  voice-collection site's live agent), the voice-collection server's speech model (1.1 GB),
  `shefa serve` on :8000 (2.4 GB) and Ollama. An 8 to 9 GB candidate cannot load beside them. The
  bake-off needs a maintenance window in which those services are stopped; it is waiting for the
  founder's go-ahead.

## Setup (baseline)

| | |
| --- | --- |
| Command | `shefa lab score --side-base-url http://localhost:8001/v1 --caller-model shefa-llm --judge-model shefa-llm` |
| Code | `bde3073` |
| Agent under test | the configured product model (`shefa-llm`, gemma2-9b AWQ on vLLM), guided engine |
| Simulated caller and judge | the same `shefa-llm` (caller at temperature 0.7, judge at 0.0) |
| Cases | 112: 86 in `configs/lab/bench/*.yaml` and 26 in `configs/lab/scenarios.yaml` |
| Mishearing | 15% of words, learned from the volunteer recordings, seeded per scenario (seed 7) |
| Scorecard | `data/bench/scorecard-local_shefa-llm-20261125-030610283.json` |

The judge is the same model as the agent, so the judged scores may flatter it. The bake-off refuses
that setup; the baseline accepts it because the card has room for one model only.

## Baseline results

| Measure | Value |
| --- | --- |
| Full pass (every hard check and every task check) | **0.304** |
| Hard pass (the seven safety checks) | 0.482 |
| Task pass (the caller's goal met: booked, rescheduled, escalated...) | 0.554 |
| Judged mean, 1 to 5 | **3.21** |
| Turn time p95 (text, no voice) | 2214 ms |
| Bangla purity | 0.983 |
| Errors / missing judgments | 0 / 0 |

Hard checks: grounded 1.00 (digits only), no unconfirmed booking 1.00, no medical advice 1.00,
privacy 1.00, emergency first turn 0.96, not pushed to book 0.96, **brevity 0.54**.

Judged, by dimension: warmth 3.03, **feelings first 2.54**, no repetition 3.16, phone clarity
3.85, natural Bangla 3.72, tactful limits 3.43, **recovers mishearing 2.77**.

Judged, by caller type: **confused elderly 2.45**, **angry 2.79**, code switching 2.98, anxious
3.05, rushed 3.23, quiet 3.26, rude 3.26, ordinary 3.29, talkative 3.48, off-topic 3.71.

Most frequent failures: brevity (51 calls), English words in Bangla replies (12), booking not
completed (caller holds no appointment, 11), "my appointment" lookups not done (10), reply in the
wrong language (7), reschedules not done (6), emergency not handled in the first turn (5), an
information-only caller offered a booking (4).

## What the baseline says

- **Safe but not helpful enough.** The agent never invented a digit fact, never booked without a
  confirmed yes, never gave medical advice and never leaked another patient's booking; but under
  realistic mishearing it completed the caller's goal in only about half the calls.
- **Empathy is the weakest dimension.** Feelings first (2.54) and recovering from mishearing (2.77)
  are the lowest scores, and the angry and confused elderly callers get the worst experience. This
  is the gap sub-project 2 (the conversation brain) targets.
- **Too long.** Almost half the calls have a reply over two sentences that the model wrote itself.
- **Turn time** is 2.2 s at p95 before any voice, against a 1.2 s first-audio target; sub-project 3
  (listening) targets this.

## What the bench cannot yet show

- These numbers rank today's guided engine; when the conversation brain (sub-project 2) lands, the
  baseline and the bake-off are re-run against it.
- `grounded` checks digits only; invented numbers spoken as words are not caught yet.
- `privacy` catches a leaked full name or phone, not a partial name with the slot.
- No human labels exist yet, so the judge's agreement with people is unmeasured; the founder marks
  real transcripts in the console (sub-project 4).

## Bake-off: how it will run

`shefa lab bakeoff gemma2:9b hf.co/unsloth/gemma-3-12b-it-GGUF:Q4_K_M qwen3:14b
hf.co/unsloth/Qwen3-8B-GGUF:Q4_K_M aya-expanse:8b hf.co/mradermacher/TigerLLM-9B-it-GGUF:Q4_K_M
qwen2.5:7b --with-voice --side-base-url <a server not in the candidate list>` over the 26 cases
tagged `bakeoff`, then the top two in full when they finish within one case of each other.
Each model gets: the scorecard, time to its first complete sentence on the product's own prompt
with three calls at once (30 samples), graphics memory with recognition and the voice loaded, and
the winner rule: eligible when first sentence p95 + the voice's first sound is at most 1200 ms,
ranked by full pass, then judged mean.
