# Test bench baseline and local model bake-off, 2026-11-25

Sub-project 1 of `docs/superpowers/specs/2026-11-25-shefa-human-front-desk-design.md`.
Tools: `shefa lab score`, `shefa lab bakeoff`, `shefa lab compare` (plan:
`docs/superpowers/plans/2026-11-25-test-bench-and-bakeoff.md`).

## Status

- **Baseline: done.** Today's agent (the guided engine) on its configured model, gemma2-9b AWQ
  served by vLLM as `shefa-llm`, against all 112 bench callers.
- **Bake-off, 26 cases: done** (below). Nine candidates, including Qwen3 with thinking on and off.
- **Finalists on all 112 cases: done.** Decision: **keep gemma2-9b on vLLM.** See "Conclusion".

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

## Bake-off: how it was planned to run

`shefa lab bakeoff gemma2:9b hf.co/unsloth/gemma-3-12b-it-GGUF:Q4_K_M qwen3:14b
hf.co/unsloth/Qwen3-8B-GGUF:Q4_K_M aya-expanse:8b hf.co/mradermacher/TigerLLM-9B-it-GGUF:Q4_K_M
qwen2.5:7b --with-voice --side-base-url <a server not in the candidate list>` over the 26 cases
tagged `bakeoff`, then the top two in full when they finish within one case of each other.
Each model gets: the scorecard, time to its first complete sentence on the product's own prompt
with three calls at once (30 samples), graphics memory with recognition and the voice loaded, and
the winner rule: eligible when first sentence p95 + the voice's first sound is at most 1200 ms,
ranked by full pass, then judged mean.

## Bake-off setup (as run)

| | |
| --- | --- |
| Command | the planned command plus `"qwen3:14b+think" "hf.co/unsloth/Qwen3-8B-GGUF:Q4_K_M+think" --caller-model hf.co/unsloth/gemma-3-4b-it-GGUF:Q4_K_M --judge-model hf.co/unsloth/gemma-3-4b-it-GGUF:Q4_K_M --tags bakeoff` |
| Code | `e7c5649` |
| Server | Ollama, every model a Q4 GGUF, run one at a time with the services stopped (vLLM, `shefa serve`) |
| Simulated caller and judge | gemma-3-4b (Q4); not a candidate, so no model judges itself |
| Cases | the 26 tagged `bakeoff`, 15% mishearing, seed 7 |
| Results | `data/bench/bakeoff-20261125-081531.json`; TigerLLM re-run `data/bench/bakeoff-20261125-103200.json` |
| One-at-a-time timing | `data/bench/solo-latency-20261125.json` (15 requests per model) |

`+think` means the same model with its reasoning turned on (up to 4096 reply tokens). The reasoning
is never spoken: every reply passes through `shefa.models.llm.think_filter`.

## Bake-off results, 26 cases

Full pass counts out of 26. At n = 26 one case is 3.8 points, so differences of one or two cases
are noise.

| Model | Full | Task | Hard | Judged | Bangla | 3 at once p50 / p95 ms | One at a time p50 / p95 ms | Card in use, MB ² |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| qwen3:14b | **11** (0.423) | 0.462 | 0.654 | 3.75 | 0.994 | 4807 / 10604 | 2314 / 3381 | 11157 |
| gemma-3-12b-it | 9 (0.346) | 0.500 | 0.538 | 3.88 | 0.989 | 1087 / 2970 | **517 / 839** | 11970 |
| qwen3:14b **+think** | 9 (0.346) | 0.500 | 0.462 | 3.64 | 0.990 | 20717 / 163769 | 8886 / 29198 | 11164 |
| gemma2:9b (today's model) | 8 (0.308) | 0.538 | 0.423 | **3.91** | 0.984 | 1460 / 3144 | 686 / 1595 | 13617 |
| Qwen3-8B | 8 (0.308) | 0.500 | 0.538 | 3.50 | 0.988 | 2015 / 4697 | 1074 / 1640 | 7016 |
| TigerLLM-9B-it ¹ | 8 (0.308) | 0.538 | 0.500 | 3.79 | 0.996 | 1264 / 3055 | **516 / 691** | 11792 |
| qwen2.5:7b | 6 (0.231) | 0.462 | 0.308 | 3.66 | 0.984 | 3440 / 7443 | 976 / 2293 | 6577 |
| aya-expanse:8b | 5 (0.192) | 0.269 | 0.385 | 3.79 | 0.988 | 9977 / 21597 | 2011 / 3132 | 7634 |
| Qwen3-8B **+think** | 2 (0.077) | 0.346 | 0.269 | 3.51 | 0.982 | 13747 / 32258 | 4531 / 28914 | 7160 |

¹ In the main run TigerLLM failed every call: Ollama's runner aborted (`GGML_ASSERT(buffer)`, a
failed graphics-memory allocation) when the caller model loaded beside it and the voice models.
The row is its re-run without the voice models loaded. Re-run like for like (voice models
loaded), it crashed again (`data/bench/bakeoff-20261125-105613.json`), so it cannot sit beside the
voice stack in that setup. That crash had the same cause as gemma-3-12b's (the side model on the
card beside it, below), so TigerLLM was also run on all 112 cases with the side model on the CPU.

² Whole-card memory in use during the model's probe. The bench process never showed on the card,
so the voice models appear to run off it in the bench; the column is the model plus the
collector's speech model, not the full voice stack.

**Timing.** "3 at once" is the tool's own probe. Ollama here serves one request at a time, so
two of the three requests wait in a queue: that column measures queueing, not the model. "One
at a time" is the same prompts with no queue, and is what a caller hears when no other call is
in progress; two calls at once on one Ollama process would queue as the first column shows (vLLM
batches them instead). The gate below uses the one-at-a-time column. The tool itself, using the queued column, reported no eligible model.

**Safety checks.** Every model was grounded (no invented digits), gave no medical advice and
leaked no other patient's booking. Every model missed the same two emergency cases in the first
turn; on the full 112 both finalists missed the same 8 of 9. That is mostly the simulated caller:
gemma-3-4b often opens without saying what is wrong ("আরে, হ্যাঁ?"), so turn 1 has nothing to
react to. The baseline, whose caller was gemma2-9b, scored 0.96 here. See "Conclusion". One booking without a confirmed
yes each for gemma-3-12b (`code-switching-booking-morning`) and qwen3:14b+think
(`code-switching-change-reschedule`). Replayed, the gemma-3-12b one was the check's mistake: the
caller said "thanks, great", SHEFA asked "was that a yes or no?", the caller said "হ্যাঁ, yes!",
and only then did it book. The check only accepted a yes right after the read-back; fixed in
`73d6981` (the finalist runs use the fixed check). Brevity is the most common
failure for every model.

## Thinking on or off

Thinking did not help either Qwen3 model, clearly hurt the 8B, and was far slower. The 14B's
drop (11 → 9) is inside the two-case swing seen between repeated runs of the same model:

| | Full pass | Judged | One at a time p95 |
| --- | --- | --- | --- |
| qwen3:14b, off → on | 11 → 9 | 3.75 → 3.64 | 3.4 s → 29.2 s |
| Qwen3-8B, off → on | 8 → 2 | 3.50 → 3.51 | 1.6 s → 28.9 s |

- Brevity failures rose with thinking on (qwen3:14b 7 → 12, Qwen3-8B 10 → 17): the replies got
  longer, which a phone caller hears as a speech rather than an answer.
- The slowest thinking turns take about 29 s even with no queue, above the real pipeline's 20 s
  turn deadline (`pipeline.turn_deadline_s`), so on a live call those turns would be dropped.
  The bench's text runner has no deadline, so the table above flatters thinking.
- Faster hardware shortens the reasoning in proportion but does not remove the silence while the
  model thinks before its first word. A front-desk turn is short and grounded in clinic data the
  engine already looks up; there is little left for reasoning to improve.
- Today's guided engine decides most turns itself and uses the model for wording, so this is a
  test of thinking for wording. When the conversation brain (sub-project 2) gives the model more
  of the decision, thinking gets re-tested there, perhaps for one hard step rather than every turn.

## Caveats

- **Judge.** gemma-3-4b is lenient (most scores 3.5 to 4) and may favour Gemma-family wording. The
  judged mean only breaks ties; the ranking rests on the hard and task checks.
- **Engine.** The guided engine writes most replies from templates, which narrows the gaps
  between models. Everything here is provisional until sub-project 2.
- **Serving.** These are Ollama Q4 GGUF builds. The product serves through vLLM; a chosen model
  needs a vLLM-ready quantisation (AWQ or GPTQ) and a re-time there before it goes live.

## Finalists on all 112 cases

The gate, timed again with 60 requests per model one at a time
(`data/bench/solo-latency-60-20261125.json`): gemma-3-12b p95 552 ms and TigerLLM 650 ms pass;
gemma2:9b 1587 ms and Qwen3-8B 1761 ms do not, on Ollama. Both eligible models finish within one case of
each other on the 26, so both were run on all 112 cases beside today's model, gemma2:9b, as the
control, under one setup: Ollama Q4 for both,
voice models loaded, the same gemma-3-4b caller and judge moved to a CPU-only Ollama
(`--side-base-url http://127.0.0.1:11435/v1`). The move was needed because Ollama budgets
gemma-3-12b at 8.0 GB but allocates about 9.1 GB (a larger KV cache and its vision encoder), and it
aborted beside the side model on the GPU.

| | gemma-3-12b-it | TigerLLM-9B-it | gemma2:9b |
| --- | --- | --- | --- |
| Full pass | 37 / 112 (0.330) | 36 / 112 (0.321) | **41 / 112 (0.366)** |
| Task pass | 0.616 | 0.625 | 0.643 |
| Hard pass | 0.482 | 0.473 | 0.509 |
| Judged mean | 3.86 | 3.88 | 3.83 |
| Missing judgments | 5 | 7 | 5 |
| Bangla purity | 0.991 | 0.993 | 0.987 |
| Brevity failures | 45 | 50 | 47 |
| Emergency first turn | 0.93 | 0.93 | 0.93 |

Results: `data/bench/bakeoff-20261125-114056.json` (gemma-3-12b, gemma2:9b) and
`data/bench/bakeoff-20261125-133049.json` (TigerLLM, no runner errors). A second run of the 26 cases with the fixed
check (`data/bench/bakeoff-20261125-111145.json`) gave gemma-3-12b 11 and gemma2:9b 9; the first
run gave 9 and 8. The two models trade places between runs: on this engine the three models' quality is
the same. None invented a digit, gave medical advice, leaked a booking or booked without a yes.
Information-only callers were offered a booking in 5 calls (gemma-3-12b, 0.96) and 2 calls each
(gemma2:9b and TigerLLM, 0.98). The judged mean covers only the calls with a judgment.

**Today's model, served as in production.** gemma2-9b AWQ on vLLM (`shefa-llm`), timed with the
same prompts (`data/bench/vllm-latency-20261125.json`): first sentence p50 417 ms, **p95 703 ms**
one at a time and 755 ms three at once (vLLM batches instead of queueing). With the voice's first
sound (about 85 ms) that is 0.79 s alone and 0.84 s three at once, inside the 1.2 s gate. Its slow Ollama numbers were
Ollama's, not the model's.

## Conclusion

- **Keep gemma2-9b AWQ on vLLM.** No local model was distinguishably better on quality, and as
  served today it already meets the first-sentence target. Switching to gemma-3-12b or TigerLLM would gain nothing measurable
  and would need a vLLM-ready build and a re-time, and it needs more graphics memory than gemma2.
- **Ungated quality ranking (26 cases, full pass):** qwen3:14b 11; gemma-3-12b, qwen3:14b+think 9;
  gemma2:9b, Qwen3-8B, TigerLLM 8; qwen2.5:7b 6; aya-expanse 5; Qwen3-8B+think 2. At n = 26 the
  top six are within three cases of each other. qwen3:14b had the best hard pass (0.654) but was
  gated out on Ollama timings (3.4 s p95 alone); on vLLM it might be about twice as fast, which
  could still miss the gate. It was not run on all 112 cases: that is the one open question.
- **Thinking stays off** for the receptionist's turns (see "Thinking on or off").
- **The model is not the bottleneck; the conversation is.** Both finalists fail the same things:
  replies too long (brevity fails in about 40% of calls), "my appointments" lookups (8 to 11
  calls) and reschedules (5 to 6) left undone, and information-only callers offered a booking (2
  to 5). Replies in the wrong language are rare (1 to 2 of 112) but real: a replay showed English
  replies to a Bangla caller. These belong to the guided engine, and they are what sub-project 2
  (the conversation brain) should fix first. Re-run this bake-off when it lands.
- **Emergencies need two fixes.** The bench's caller must say the emergency in its first line
  (scenarios should fix the opening line), and the engine must react to one said later: in a
  replay on today's production model, "আমার বাবার খুব ব্যথা" (my father is in great pain) got a
  list of departments and then a booking offer.
- The baseline's text turn time (2.2 s p95) times the whole reply, not its first sentence, so it
  is not comparable with the 0.7 s here. Measuring the first sound of a real call end to end is
  sub-project 3's job.
