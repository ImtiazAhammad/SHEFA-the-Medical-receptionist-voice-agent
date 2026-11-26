# Brain probe: first contact with the real model (Task 8b)

Date: 2026-11-26. Script: `scripts/brain_probe.py` (`uv run python scripts/brain_probe.py`).
Raw run: `data/bench/brain-probe-20261126-015036.json` (untracked).

## Verdict: the gate FAILS on two of four criteria

| Criterion (brief)                                         | Measured                         | Result |
|-----------------------------------------------------------|----------------------------------|--------|
| Valid `TOOL` line on at least 5 of 6 tool turns           | **0 of 6**                       | FAIL   |
| Regeneration on at most 4 of 20 turns                     | 3 of 20                          | pass   |
| No prompt over the budget (3000 estimated tokens)         | max 2785 estimated (real ≈ 2040) | pass   |
| First spoken sentence p95 ≤ 1100 ms on the 14 non-tool turns | **2059 ms** (nearest rank = max); median 1158 ms; 7 of 14 over 1100 | FAIL   |

Per the brief, Task 9 should not start until the controller rules on the fix.

## Setup

- Model: vLLM at `http://localhost:8001/v1`, `shefa-llm` = `hugging-quants/gemma-2-9b-it-AWQ-INT4`,
  `max_model_len` 4096, chat template `configs/chat_templates/gemma2.jinja`. Client built the way the
  product builds it (`OpenAICompatibleLLM`, temperature 0.3, max_tokens 512, no extra body).
  One request at a time; vLLM was not touched.
- Stores: config, knowledge, audit and clinic all in a temporary folder. Knowledge seeded from
  `configs/knowledge/platform.yaml` (5 About SHEFA entries; the settings hold no `facilities`, so
  the seed wrote no clinic entries) plus 4 fictional clinic entries added by the probe: fee note,
  parking, address, opening hours. Clinic directory: `configs/clinic.example.yaml` (Dr Rahman,
  Dr Sultana, Dr Hossain). The caller is identified (phone on the session) and has one booking with
  Dr Rahman tomorrow 18:00.
- Retrieval is **words only**: the embedding model (`intfloat/multilingual-e5-small`) is not on
  disk, so meaning search is off.
- `today` = 2026-11-28 (a Saturday), so "tomorrow" is a Sunday, a day Dr Rahman sits.
- Each turn: a fresh `CallSession`, the default greeting as the first assistant turn (Bangla, the
  primary language, also for the English callers, as `handle_text` does), then the caller's line.
- One warm-up turn first, not counted (it paid 1.7 s for the one-off embedder load attempt).
- Instrumentation is outside the brain: the model stream is wrapped (prompt size, call time,
  first chunk, raw text per attempt); `retriever_for`, `directory_brief`, `compose` and
  `check_sentence` on `shefa.brain.engine` are wrapped for timing and verdict reasons. Nothing under
  `src/` changed. This is the first and only gate run.

## Every turn

Times in ms from calling `Brain.turn`. "ttft" = first streamed chunk of the first attempt.
Tokens = the prompt's estimate (`prompt._tokens`, chars/2).

| id | kind | expected tool | tool line | regen | tokens | first spoken | ttft | verdicts |
|---|---|---|---|---|---|---|---|---|
| k-fee | knowledge | – | – | | 2671 | 1158 | 371 | ok |
| k-parking | knowledge | – | – | | 2633 | 1304 | 347 | ok, ok |
| k-address | knowledge | – | – | | 2632 | 1216 | 346 | ok, ok |
| k-unknown | knowledge | – | – | | 2607 | 931 | 372 | ok |
| k-about | knowledge | – | – | | 2608 | 534 | 371 | ok, ok |
| k-days | knowledge | – | – | | 2630 | 1281 | 368 | ok |
| t-symptom | tool | find_doctors | **none** | | 2557 | 981 | 339 | ok, ok |
| t-free | tool | free_times | **none** | | 2716 | 1280 | 410 | ok |
| t-mine | tool | lookup_booking | **none** | | 2554 | 372 | 68 | ok |
| t-book | tool | book | **none** | yes | 2674 | 2474 | 367 | fact, fact → safe |
| t-cancel | tool | cancel_booking | **none** | | 2650 | 916 | 375 | ok |
| t-callback | tool | request_callback | **none** | | 2785 | 1342 | 456 | ok, ok |
| m-angry | mood | – | – | | 2737 | 721 | 383 | ok, fact |
| m-anxious | mood | – | – | | 2764 | 1337 | 427 | ok, ok |
| m-rushed | mood | – | – | yes | 2723 | 2059 | 373 | fact, fact → safe |
| m-rude | mood | – | – | | 2639 | 686 | 351 | ok, ok |
| e-fee | english | – | – | | 2718 | 798 | 300 | ok |
| e-address | english | – | – | | 2668 | 788 | 290 | ok, ok |
| e-days | english | – | – | yes | 2666 | 1524 | 290 | language (dropped), ok, ok |
| e-notes | english | – | – | | 2642 | 676 | 288 | ok |

Non-tool first-spoken times, sorted: 534, 676, 686, 721, 788, 798, 931, 1158, 1216, 1281, 1304,
1337, 1524, 2059. Without the two regenerated turns the max is still 1337 ms.

### What the caller heard

Caller line → what SHEFA said (mood/goal as tracked by code).

- **k-fee** "ডাক্তার রহমানের ভিজিট ফি কত?" → "ডাক্তার রহমানের প্রথম ভিজিট ফি ৮০০ টাকা।" Correct.
- **k-parking** "আপনাদের ক্লিনিকে গাড়ি পার্কিংয়ের জায়গা আছে?" → "হ্যাঁ, ক্লিনিকের বেসমেন্টে গাড়ি পার্কিং আছে। আপনার কাছে আর কি প্রশ্ন আছে?" Correct.
- **k-address** "ক্লিনিকটা কোথায়? ঠিকানাটা একটু বলবেন?" → "ঠিকানাটা হলো বাড়ি ১২, রোড ৫, ধানমন্ডি, ঢাকা। সিটি কলেজের পাশে।" Correct.
- **k-unknown** "আপনাদের ক্লিনিকে কি কোনো ক্যান্টিন আছে?" → "না, আমাদের ক্লিনিকে ক্যান্টিন নেই।" **Invented** (no fact about a canteen; hits were empty). The checker passed it: a "no, we don't have it" sentence carries no number, time or name.
- **k-about** "আপনি কি মানুষ নাকি মেশিন? আপনাকে কে বানিয়েছে?" → "আমি মেশিন। ইমতিয়াজ আহাম্মদ একজন এআই ইঞ্জিনিয়ার আমাকে তৈরি করেছেন।" From the platform entries; "আমি মেশিন" is blunt but true.
- **k-days** "ডাক্তার সুলতানা কোন কোন দিন বসেন?" → "ডাক্তার সুলতানা सोमवार, বুধবার এবং শনিবার দিন বসেন।" Days right, but **Monday came out in Hindi (Devanagari)** and the language check passed it.
- **t-symptom** "আমার বাচ্চার তিন দিন ধরে জ্বর, কোন ডাক্তার দেখাবো?" → "আপনার বাচ্চার জ্বর তো খুব দুঃখজনক। ডাক্তার সুলতানা শিশু বিশেষজ্ঞ।" No tool; answered from the directory block, correctly.
- **t-free** "কাল সন্ধ্যায় ডাক্তার রহমানের কোন সময় খালি আছে?" → "ডাক্তার রহমান কাল সন্ধ্যায় আপনাকে দেখার জন্য সময় আছে?" No tool; an odd echo-question.
- **t-mine** "আমার অ্যাপয়েন্টমেন্টটা কবে আছে একটু দেখবেন?" → "আপনার নাম কি?" No tool; asks a name although the caller is identified (the prompt never says so).
- **t-book** "আমার নাম করিম আহমেদ, কাল বিকেল ৫টায় ডাক্তার রহমানের কাছে একটা সিরিয়াল দিন।" → safe sentence "এ বিষয়ে আমার কাছে নিশ্চিত তথ্য নেই, তাই আন্দাজে বলব না। …". Attempt 1 "কাল বিকেল ৫টায় ডাক্তার রহমানের কাছে সিরিয়াল দিতে পারি।" and attempt 2 (a question repeating it) both failed "the number 5 is not in the facts".
- **t-cancel** "ডাক্তার রহমানের সাথে আমার সিরিয়ালটা বাতিল করতে চাই।" → "আপনার সিরিয়াল বাতিল করতে চান?" No tool.
- **t-callback** "রিপোর্ট নিয়ে একজনের সাথে কথা বলতে চাই, কেউ আমাকে পরে ফোন করতে পারবেন?" → "আপনার রিপোর্ট সম্পর্কে জানতে চাওয়া খুবই ঠিক। আপনার রিপোর্ট কোন ডাক্তারের?" No tool.
- **m-angry** (tracked mood **calm**) "তিনবার ফোন করেছি কেউ ধরে না! এটা কী ধরনের সার্ভিস? ক্লিনিক কয়টায় খোলে বলেন।" → "আমি স্বাগত জানাই।" ("I welcome you" — meaningless). The real answer "ক্লিনিকটি শনি থেকে বৃহস্পতিবার সকাল ৯টা থেকে রাত ৯টা পর্যন্ত খোলা, শুক্রবার বন্ধ।" was correct but failed the check ("the time রাত ৯ is not in the facts"), and since a sentence was already spoken, the reply stopped there.
- **m-anxious** (anxious) "আমি খুব চিন্তায় আছি, রিপোর্ট দেখাতে কি আবার পুরো ফি দিতে হবে?" → "না, এক মাসের মধ্যে এলে ফি ৩০০ টাকা, পুরো ফি লাগে না। আপনার কেমন আছে?" Fact right; the follow-up is broken Bangla.
- **m-rushed** (rushed) "তাড়াতাড়ি বলেন, ক্লিনিক কয়টা পর্যন্ত খোলা?" → safe sentence. Both attempts stated the hours correctly from the fact and both failed the time check.
- **m-rude** (tracked mood **calm**) "ধুর, আপনারা কিছুই জানেন না। পার্কিং আছে কি নাই সোজা বলেন।" → "আপনার কথা বুঝলাম। ক্লিনিকের বেসমেন্টে গাড়ি পার্কিং আছে, রোগীদের জন্য বিনা খরচে।" Good.
- **e-fee** "How much does Dr Rahman charge for a new patient?" → "For a new patient, Dr. Rahman charges 800 taka." Correct.
- **e-address** "Where exactly is the clinic located?" → "We are at House 12, Road 5, Dhanmondi, Dhaka. We are next to City College." Correct.
- **e-days** "Which days does the child specialist see patients?" → "The child specialist sees patients on Monday, Wednesday and Saturday. What time would you like to book?" Attempt 1 answered in Bangla with a **wrong day** (Tuesday) and was dropped for language only; the regeneration pushed a booking on an information question (the push check did not catch "What time would you like to book?").
- **e-notes** "Do I need to bring anything for a heart check-up?" → "Yes, please bring any old reports and ECGs." Correct.

## Why the tool criterion failed

The model never wrote `TOOL` in 20 turns. With the full directory in the prompt (and its block
saying "Answer questions about doctors … from it … and offer to book"), gemma answers or asks a
question instead of acting. The tool section sits in the middle of a ~5,100-character system
block, followed by cues, facts and the directory.

Off-gate experiments on the same composed prompts for the 6 tool turns (scratch scripts, not
committed; non-streaming, max_tokens 120, **one sample per cell** at temperature 0.3, so these are
indications, not rates). Counted the engine's way: a sentence held right before a `TOOL` line is
dropped and the line still counts.

| Variant | valid tool lines |
|---|---|
| As built (the gate run) | 0/6 |
| + a closing "Decide first … your whole reply is the TOOL line" rule | 3/6 (free_times, cancel, callback) |
| + two few-shot chat turns (user → TOOL line) | 2/6 (free_times; book after one sentence) |
| rule + few-shot turns | 3/6 (free_times, book; cancel after one sentence) |
| Separate JSON-only router call, vLLM `structured_outputs` with an enum of tools + "none", ~330 prompt tokens, temperature 0 | **6/6 right tool**; 2 false tools on 6 non-tool controls (fee → lookup_booking, Sultana's days → find_doctors) |

The structured output is enforced by the server, not just obeyed: asked for "a short poem about
rain" with the schema, the model returned `{"tool": "none"}`.

The router took 335–590 ms when it said "none" and up to 1.2 s for a `book` with Bangla arguments
(it also dropped "বিকেল" from "বিকেল ৫টা"). A full `TOOL` line inside the talker takes 1.4–1.9 s to
stream (about 40 Bangla-heavy tokens) before anything can be said.

## Why the latency criterion failed

Where the time goes, per turn (all from the run's JSON plus vLLM `/tokenize`; no extra
generations):

1. **Code before the model: ~5–17 ms.** Retrieval 0.3–0.6 ms (cached retriever), directory
   0.1–0.2 ms, compose < 0.1 ms.
2. **First chunk: 290–460 ms, almost all prefill of the per-turn part of the prompt.** Real prompts
   are 1,670–2,040 tokens. The cacheable prefix (greeting + persona, conduct, tools) is only
   ~1,120–1,160 tokens, because `_system` puts the per-turn cues, known state and facts *before*
   the directory, so the ~560–900 tokens after the first difference (directory included) are
   prefilled every turn. Evidence: t-mine's composed prompt is identical to t-symptom's up to the
   caller's line (only 26 new tokens) and its first chunk came at **68 ms**. (m-rude also had only
   38 new tokens against k-parking, seven requests earlier, yet took 351 ms; that cache entry had
   most likely been evicted: vLLM runs at 0.6 GPU memory.)
3. **Decoding the first sentence: the largest part.** Whole-stream decode is 30–36 tokens/s on
   every turn. A 40–50-character Bangla sentence is 25–32 tokens, so 700–950 ms. English is about
   half the tokens.
4. **Holding the finished sentence: 10–165 ms.** `_may_start_tool` is true for a whitespace-only
   tail, so a sentence is held until non-space text follows or the stream ends. On one-sentence
   replies gemma emits 2 more tokens (blank lines) before stopping: first-spoken equals stream end
   (k-fee 1157.8 vs 1156.7) and the hold is ~60–125 ms.

Every Bangla answer of ordinary length lands at 1,150–1,350 ms; English under 800 ms. The two
regenerated non-tool turns (m-rushed, e-days) add a whole second generation.

## Other findings

1. **Checker cannot ground a time written in words.** `_ground_hours` reads only `HH:MM` in the
   facts, so a knowledge entry "সকাল ৯টা থেকে রাত ৯টা" (or "9 am to 9 pm") never grounds the same
   time spoken back; checked directly: `check_sentence("রাত ৯টা পর্যন্ত খোলা।")` with that entry fails
   "the time রাত ৯ is not in the facts", and the English "until 9 pm." fails too. It caused 1 of
   the 3 counted regenerations (m-rushed, ending in the safe sentence), m-angry's lost second
   sentence, and the uncounted warm-up's regeneration and safe fallback. Clinic staff will write
   hours in words.
2. **t-book's "number 5" failure** is the same family: the caller's own "৫টা" cannot ground a
   reply (by design), so any read-back before a tool result fails. That is correct once the tool
   exists; today it costs a regeneration.
3. **Invented "no"** (k-unknown) passes the checker: a negative claim about a facility has nothing
   for the fact rules to catch.
4. **Day facts are a bag**: grounds hold the whole directory, so e-days' first attempt
   "ডাক্তার সুলতানা মঙ্গলবার … দেখেন" (Tuesday is wrong for her) **did pass** the day rule, which runs
   before the language rule (Dr Rahman sits Tuesday). It was dropped only for being in Bangla.
5. **Hindi leak**: "सोमवार" passed the language check in a Bangla reply.
6. **Mood rules missed** the angry ("তিনবার ফোন করেছি কেউ ধরে না!") and rude ("ধুর, … কিছুই জানেন না")
   callers; both tracked as calm. Goal "information" was tracked for t-free (a free-times request)
   and goal "booking" for e-days (an information question). The push rule only runs when the goal
   is "information", so e-days' "What time would you like to book?" was not caught: a goal-tracking
   fault, not a push-wording one.
7. **Gemma accepts a history that starts with the assistant greeting**: no server error in 21
   turns. The chat template folds the system text into the first *user* turn, so the instructions
   come after the greeting.
8. **No numbered lists or other shapes** (`1.`, bullets, `**`) appeared in any raw output; none of
   the regenerations came from sentence shape. Outputs end with runs of blank lines (`\n\n\n`) that
   the engine ignores.
9. **Prompt estimate is conservative**: chars/2 gave 2,671 / 2,785 / 2,770 where vLLM's tokenizer
   counts 1,868 / 2,037 / 1,733. The budget leaves room.
10. "Known so far" says nothing about the caller being identified, so the model asks for a name
    before a lookup (t-mine).

## Proposals (for the controller to rule on)

1. **Tool turns: a JSON-only router call** with vLLM structured output (enum of tool names +
   "none"), on a short prompt (tools list, the turn, known state; no directory), run *concurrently*
   with the talker stream (vLLM runs up to 6 sequences). If the router names a tool, the talker's
   held first sentence is discarded and `_act` runs; if "none", the talker's sentence is spoken
   with no added wait (not measured: the probe kept to one request at a time, and running two
   sequences will slow each stream somewhat). This is the only variant that reached the 5/6 bar
   here (6/6). Its false
   tools on information questions need a guard: code accepts `find_doctors`/`lookup_booking` only
   when the code-tracked goal or words support it, or the talker's answer already passed the check.
   Prompt wording alone reached 3/6 at best and was unstable.
2. **Checker: ground spoken times in words.** Let `_ground_hours` read the same `_BN_TIME`/`_EN_TIME`
   phrases it reads in sentences (and `৯টা` with a period word), not only `HH:MM`. Small, contained,
   and removes most regenerations seen here.
3. **First-sentence latency**: instruct a short first sentence (under about 8 words, the answer
   first: "৮০০ টাকা।"), or let the engine speak the first clause at a comma once it passes the
   check. At ~33 tokens/s, the 1,100 ms bar leaves about 22 tokens after a 350 ms first chunk.
4. **Prompt order for the prefix cache**: put everything that is the same for the call (persona,
   conduct, tools, directory) first and the per-turn parts (cues, language, known state, facts)
   last. The evidence above (68 ms first chunk on a full cache hit versus ~350 ms when ~650 tokens
   are new) suggests up to ~250 ms saved per turn; the clean Bangla turns miss the bar by 58–237 ms.
   Not tested here. Also release the held sentence when the stream ends or after a short tail of
   only whitespace (~60–125 ms). Separately, 30–36 tokens/s may be worth checking on the vLLM side
   (outside this task).
5. Smaller: say "the caller is identified by phone" in Known so far; extend the mood words for
   "কেউ ধরে না", "ধুর", "কিছুই জানেন না"; treat Devanagari as wrong language; fix goal
   tracking for "which days does … see patients" (tracked as booking, so the push rule never ran).

After a fix, re-run `uv run python scripts/brain_probe.py`; it exits 0 only when all four
criteria pass.


## Re-run after 8c

Date: 2026-11-26. Same script, extended (`uv run python scripts/brain_probe.py`, defaults
`--runs 2 --concurrent 3`). Raw runs (untracked): `data/bench/brain-probe-20261126-072737.json`
(first gate run) and `data/bench/brain-probe-20261126-073610.json` (after the stream-close fix
below; **the numbers here are from this one** unless marked). Same setup as above (temp stores,
`configs/clinic.example.yaml`, words-only retrieval, caller identified with one booking,
`today` = 2026-11-28, client built as the product builds it). vLLM untouched.

What changed in the brain (Task 8c):

- **Router beside the reply** (`shefa.brain.router`): one JSON-only call, temperature 0, 40
  tokens max, output forced by vLLM `structured_outputs` with a regex for the compact JSON
  `{"tool":…,"mood":…,"goal":…}` (25 tokens instead of 33 for the pretty-printed JSON schema
  form). Tools: the 8 of `TOOL_NAMES` without `find_doctors`, plus `none`. Fixed instructions
  first (prefix cache), then the last 4 turns and the caller's line. Error, timeout
  (`brain.router_timeout_s` = 1.5 s) or unreadable output = no route, plain reply.
- **Engine**: router and reply start together; reply sentences wait for the route. A named tool
  closes the reply unheard and calls `_act` (still the stub, which speaks the repeat prompt) with
  arguments built by code; `none` releases the sentences. Router mood/goal override the word
  rules (a question never replaces a real goal). The talker's TOOL protocol and the whitespace
  hold are gone; tool-like text is still never spoken.
- **Prompt**: persona, conduct, directory (brain header without "offer to book"), the
  identified-caller line, then the per-turn parts. A cut history now starts with a caller turn
  (see "Prefix cache in a longer call").
- **Client**: per-request settings override the client's; a stream closed early now closes the
  HTTP response (see "Orphaned generations").

The router prompt was written and tuned on a separate set of 24 lines (15 tool, 9 non-tool, none
of them in the probe; 24/24 right on the first try) and frozen before the gate ran. Its three
built-in examples are near-copies of probe turns (≈ k-fee, k-days/e-days, t-book); without those
4 turns the router scores 29/30 right and 2/56 false in both runs. The probe's
turns: 31 tool turns (4 to 5 per tool, Bangla and English, two emergencies and two "a person,
please") and 59 non-tool turns (15 knowledge, 10 doctor questions including symptom → doctor,
10 moods, 16 English, 8 small talk). Each turn is a fresh call (greeting + caller's line).

### Verdict: router and regenerations pass; first-spoken latency FAILS

| Criterion | run 1 | run 2 | 3 calls at once | Result |
|---|---|---|---|---|
| Router right tool on tool turns (≥ 90%) | 30/31 (96.8%) | 30/31 (96.8%) | 30/31 | pass |
| Router names a tool on non-tool turns (≤ 10%) | 2/59 (3.4%) | 2/59 (3.4%) | 2/59 | pass |
| Regenerations (≤ 20% of turns) | 9/90 (10%) | 8/90 (8.9%) | 9/90 | pass |
| First spoken p95, non-tool turns, one call at a time (≤ 1100 ms) | **1338 ms** | **1407 ms** | 1612 ms (not gated) | FAIL |

p95 is nearest-rank over the 59 non-tool turns (a turn that never spoke would count as
infinite; none did). A non-tool turn counts as a false tool when the router named any tool. The
first gate run (before the stream-close fix) gave the same router results (30/31, 2/59), 10 and
11 regenerations, and p95 1409 / 1342 ms.

The router's misses, identical in every run (temperature 0):

- t-move2 "সিরিয়ালের সময়টা একটু পিছিয়ে সন্ধ্যা ৭টায় করে দিন।" (push my serial back to 7 pm) → `book`
  instead of `reschedule_booking`.
- d-heart "বুক ধড়ফড় করে মাঝে মাঝে, কোন ডাক্তারের কাছে যাওয়া উচিত?" (palpitations now and then,
  which doctor?) → `hand_over`. Arguably cautious, counted as false.
- m-upset "গতবার দুই ঘণ্টা বসিয়ে রেখেছিলেন … এবার কি দেরি হবে?" (will there be a delay this
  time?) → `lookup_booking`.

### Where the time goes (non-tool turns, final run)

| | run 1 p50 / p95 | run 2 p50 / p95 | 3 at once p50 / p95 |
|---|---|---|---|
| Router call | 525 / 612 ms | 536 / 627 ms | 690 / 798 ms |
| Reply first token | 80 / 120 ms | 83 / 148 ms | 121 / 199 ms |
| First sentence finished in the stream | 532 / 1126 ms | 519 / 1166 ms | 622 / 1220 ms |
| Decode of the first sentence (first token → finished) | 457 / 1036 ms | 425 / 1087 ms | 509 / 1074 ms |
| Finished sentence waiting for the router | 0 / 276 ms (23 of 59 turns waited) | 56 / 270 ms (28 turns) | 60 / 295 ms (27 turns) |
| First spoken | 599 / 1338 ms | 573 / 1407 ms | 709 / 1612 ms |

- **First token is solved**: 80 ms median against 290–460 ms in 8b. The call-constant prefix
  (persona, conduct, directory) is cached; vLLM's prefix-cache hit share over the whole probe was
  93.7%. Real prompts are 1,117 tokens median, 1,369 max (vLLM tokenizer).
- **Decode is the remainder**: 25.4 ms per token (median, first sentences of run 1; ~39
  tokens/s), first sentences 16 tokens median. The non-regenerated turns over 1100 ms are all one
  long Bangla first sentence of 40–44 tokens (k-parking 1170, k-rahman-time 1126, m-rude 1270,
  k-pharmacy 1407 ms): 40 × 25.4 ≈ 1,020 ms of decode alone.
- **Regenerations decide the p95**: of the 9 / 10 turns over the limit, 6 / 6 were regenerated
  (a whole second generation, 1,170–1,500 ms). Without regenerated turns the p95 is 1126 / 1167
  ms: over by 26 / 67 ms, which is decode. Bangla turns without regeneration: p50 665 ms, max 1270;
  English: p50 525 ms, max 774.
- **The router costs a little**: its ~525 ms (25 output tokens) ends after the reply's first
  sentence on 23–28 of 59 turns, holding speech by up to ~275 ms (p95). Short English answers are
  the ones held.

So the latency criterion misses for two reasons, in this order: checker false positives that
force a regeneration (out of 8c's scope, listed below), and decode speed on long Bangla first
sentences (hardware-bound at ~39 tokens/s on this card for gemma2-9b AWQ).

### Regenerations by reason (final run 1)

7 `unsupported`, 2 `fact`. The `unsupported` ones are mostly the checker refusing true answers:
"it only repeats the caller's own words" on d-exp ("ডাক্তার রহমানের অভিজ্ঞতা 18 বছরের।"), d-english
("হ্যাঁ, ডাক্তার হোসেন ইংরেজিতে কথা বলেন।"), s-salam ("আসসালামু আলাইকুম, ভালো আছি।"); "it says yes to something
the facts do not state" on d-lady (the directory lists a female doctor as `female`). The two
`fact` ones are the word-form time issue from 8b (m-rushed "রাত ৯টা", e-hours "9 pm"), still open.
Several of these end in the safe sentence after the second attempt fails the same way. The
refused answers are true per `configs/clinic.example.yaml` (Rahman 18 years, Sultana follow-up
400 and female, Hossain speaks English), and re-checking the 9 failing first sentences with the
word-rule goal and with the old directory header gives the same verdicts: this is the checker,
not 8c's goal override or header.

### Orphaned generations (found and fixed in 8c)

The first gate run waited up to 1.6–1.8 s (p95 ~1.1 s) after a turn for vLLM to go idle:
closing the client's stream generator did not close the HTTP response, so vLLM kept generating
the cut-off reply (after a routed tool or after the second sentence). `OpenAICompatibleLLM` now
closes the response in a `finally`; after the fix the wait is ≤ 58 ms (the polling step). The
probe waits for an idle server before each turn, so the sequential timings were not skewed by
this, but on a live line every cut-off reply had been running on the GPU beside the next turn.

### Prefix cache in a longer call

A 7-turn call (one session, replies kept in history): the template folds the system text into
the first user turn, so once the 6-turn window slides and starts on an assistant turn, the prompt
opens with a different reply every turn and the cache misses (first token 600–700 ms from turn 4
on, measured before the fix). A cut history now drops leading assistant turns: first token
49, 121, 171, **612** (the one miss as the window first slides), 196, 212, 209 ms. First spoken in
that call still reached 1.1–2.5 s on turns with long Bangla answers.

### Every turn (final run 1)

`rtr` router ms, `ttft` reply first token, `ready` first sentence finished in the stream,
`first` first spoken; all ms from `Brain.turn`. Tool turns speak `_act`'s stub repeat prompt.

```
id             expected           route              mood/goal             regen        rtr  ttft  ready  first  reply
----------------------------------------------------------------------------------------------------------------------
t-free         free_times         free_times         calm/booking                       587   136    619    620  দুঃখিত, আমি স্পষ্টভাবে বুঝতে পারলাম না। আবার বলবেন?
t-free2        free_times         free_times         calm/booking                       581   106      -    614  দুঃখিত, আমি স্পষ্টভাবে বুঝতে পারলাম না। আবার বলবেন?
t-free-en      free_times         free_times         calm/information                   539    93    411    545  Sorry, I didn't catch that clearly. Could you say that again
t-free-en2     free_times         free_times         calm/booking                       528    81    238    534  Sorry, I didn't catch that clearly. Could you say that again
t-book         book               book               calm/booking                       533   144      -    571  দুঃখিত, আমি স্পষ্টভাবে বুঝতে পারলাম না। আবার বলবেন?
t-book2        book               book               calm/booking                       535   113      -    568  দুঃখিত, আমি স্পষ্টভাবে বুঝতে পারলাম না। আবার বলবেন?
t-book3        book               book               calm/booking                       564   143      -    600  দুঃখিত, আমি স্পষ্টভাবে বুঝতে পারলাম না। আবার বলবেন?
t-book-en      book               book               calm/booking                       503    85    376    509  Sorry, I didn't catch that clearly. Could you say that again
t-book-en2     book               book               calm/booking                       518   101    339    528  Sorry, I didn't catch that clearly. Could you say that again
t-mine         lookup_booking     lookup_booking     calm/lookup                        548    74      -    579  দুঃখিত, আমি স্পষ্টভাবে বুঝতে পারলাম না। আবার বলবেন?
t-mine2        lookup_booking     lookup_booking     calm/lookup                        522    73      -    552  দুঃখিত, আমি স্পষ্টভাবে বুঝতে পারলাম না। আবার বলবেন?
t-mine-en      lookup_booking     lookup_booking     calm/lookup                        560    64    406    566  Sorry, I didn't catch that clearly. Could you say that again
t-mine-en2     lookup_booking     lookup_booking     calm/lookup                        499    56    451    504  Sorry, I didn't catch that clearly. Could you say that again
t-cancel       cancel_booking     cancel_booking     calm/change                        612   111    512    627  দুঃখিত, আমি স্পষ্টভাবে বুঝতে পারলাম না। আবার বলবেন?
t-cancel2      cancel_booking     cancel_booking     calm/change                        558    84      -    590  দুঃখিত, আমি স্পষ্টভাবে বুঝতে পারলাম না। আবার বলবেন?
t-cancel-en    cancel_booking     cancel_booking     calm/change                        516    71    282    521  Sorry, I didn't catch that clearly. Could you say that again
t-cancel-en2   cancel_booking     cancel_booking     calm/change                        559    87    350    568  Sorry, I didn't catch that clearly. Could you say that again
t-move         reschedule_booking reschedule_booking calm/change                        575   102      -    609  দুঃখিত, আমি স্পষ্টভাবে বুঝতে পারলাম না। আবার বলবেন?
t-move2        reschedule_booking book               calm/change                        474   106      -    505  দুঃখিত, আমি স্পষ্টভাবে বুঝতে পারলাম না। আবার বলবেন?
t-move-en      reschedule_booking reschedule_booking calm/change                        524    79    342    529  Sorry, I didn't catch that clearly. Could you say that again
t-move-en2     reschedule_booking reschedule_booking calm/change                        580    59    373    586  Sorry, I didn't catch that clearly. Could you say that again
t-callback     request_callback   request_callback   calm/change                        616   170      -    656  দুঃখিত, আমি স্পষ্টভাবে বুঝতে পারলাম না। আবার বলবেন?
t-callback2    request_callback   request_callback   calm/change                        556   109      -    590  দুঃখিত, আমি স্পষ্টভাবে বুঝতে পারলাম না। আবার বলবেন?
t-callback-en  request_callback   request_callback   calm/change                        543    72    204    549  Sorry, I didn't catch that clearly. Could you say that again
t-callback-en2 request_callback   request_callback   calm/change                        591    92    409    597  Sorry, I didn't catch that clearly. Could you say that again
t-urgent       hand_over          hand_over          anxious/change                     578    78    584    594  দুঃখিত, আমি স্পষ্টভাবে বুঝতে পারলাম না। আবার বলবেন?
t-urgent-en    hand_over          hand_over          anxious/change                     551    49    233    557  Sorry, I didn't catch that clearly. Could you say that again
t-person       hand_over          hand_over          calm/unknown                       558    79      -    599  দুঃখিত, আমি স্পষ্টভাবে বুঝতে পারলাম না। আবার বলবেন?
t-person-en    hand_over          hand_over          calm/unknown                       588    78    404    605  Sorry, I didn't catch that clearly. Could you say that again
t-bye          end_call           end_call           calm/unknown                       538    84    519    547  দুঃখিত, আমি স্পষ্টভাবে বুঝতে পারলাম না। আবার বলবেন?
t-bye-en       end_call           end_call           calm/unknown                       543    64    170    548  Sorry, I didn't catch that clearly. Could you say that again
k-fee          -                  -                  calm/information                   496    65    712    713  ডাক্তার রহমানের প্রথম ভিজিট ফি ৮০০ টাকা। আপনার আর কোন প্রশ্ন
k-parking      -                  -                  calm/information                   521    97   1169   1170  হ্যাঁ, ক্লিনিকের বেসমেন্টে গাড়ি পার্কিং আছে, রোগীদের জন্য ব
k-address      -                  -                  calm/information                   525    97    366    531  ধানমন্ডি, ঢাকা। সিটি কলেজের পাশে।
k-unknown      -                  -                  calm/information                   498    67    504    506  না, আমাদের ক্লিনিকে ক্যান্টিন নেই। আপনি কি আর কিছু জানতে চান
k-about        -                  -                  confused/unknown                   537   108    270    546  আমি একটি মেশিন। ইমতিয়াজ আহাম্মদ একজন এআই ইঞ্জিনিয়ার আমাকে 
k-days         -                  -                  calm/information                   512    81    837    838  ডাক্তার সুলতানা বুধবার, শনিবার এবং রবিবার দিনে বসেন। কোন দিন
k-hours        -                  -                  calm/information                   539   106    378    544  সকাল ৯টায় খোলা। আপনার আর কি জানতে চান?
k-friday       -                  -                  calm/information                   515    85    545    546  না, শুক্রবারে ক্লিনিক খোলা থাকে।
k-report       -                  -                  calm/information                   537   108    947    948  এক মাসের মধ্যে রিপোর্ট দেখাতে আসলে ৩০০ টাকা দিতে হবে। আপনার 
k-followup     -                  -                  calm/information      unsupported   513   105    758   1503  এ বিষয়ে আমার কাছে নিশ্চিত তথ্য নেই, তাই আন্দাজে বলব না। আমি
k-hossain-fee  -                  -                  calm/information                   534    80    913    914  মেডিসিনের ডাক্তারের প্রথম ভিজিটের ফি ৭০০ টাকা। আপনার আর কি জ
k-landmark     -                  -                  calm/information                   505    80    537    538  আপনার প্রশ্নের উত্তর দিতে খুশি। ক্লিনিকের কাছে বড় জায়গা আছ
k-pharmacy     -                  -                  calm/information                   538   116    675    676  আপনার প্রশ্নের উত্তর জানা আমার কাছে নেই। আপনার জন্য আমি ডেস্
k-how-book     -                  -                  calm/information                   518    95    497    525  আপনার কথা শুনে ভাল লাগছে। আপনার কী প্রকার সাহায্য প্রয়োজন?
k-rahman-time  -                  -                  calm/information                   513    90   1126   1126  ডাক্তার রহমান বৃহস্পতিবার ও তুষারবার সন্ধ্যা ৪টা থেকে ৮টা পর
d-child        -                  -                  anxious/information                527    80    584    585  আমি বুঝি, আপনার বাচ্চার জ্বর আছে। শিশু বিভাগে ডাক্তার সুলতান
d-heart        -                  hand_over          anxious/change                     583    82      -    618  দুঃখিত, আমি স্পষ্টভাবে বুঝতে পারলাম না। আবার বলবেন?
d-sugar        -                  -                  calm/information                   497    77    738    739  ডায়াবেটিসের জন্য ডাক্তার হোসেন আপনাকে দেখতে পারেন। আপনার আর
d-lady         -                  -                  calm/information      unsupported   501    78    529   1174  এ বিষয়ে আমার কাছে নিশ্চিত তথ্য নেই, তাই আন্দাজে বলব না। আমি
d-exp          -                  -                  calm/information      unsupported   501    77    661   1338  এ বিষয়ে আমার কাছে নিশ্চিত তথ্য নেই, তাই আন্দাজে বলব না। আমি
d-room         -                  -                  calm/information                   505    83    773    774  ডাক্তার হোসেন প্রথম তলায় এক নম্বর রুমে বসেন।
d-list         -                  -                  calm/information                   498    76    529    529  আপনার প্রশ্নের উত্তর দিতে খুশি। এখানে হৃদরোগ বিভাগ, শিশু বিভ
d-degree       -                  -                  calm/information                   482    57    510    510  ডাক্তার সুলতানার ডিগ্রি MBBS এবং DCH। আপনার আর কি জানতে চান?
d-sunday       -                  -                  calm/information                   503    78    979    980  রবিবারে ডাক্তার হোসেন, ডাক্তার রহমান, এবং ডাক্তার সুলতানা বস
d-english      -                  -                  calm/information      unsupported   510    85    644   1305  এ বিষয়ে আমার কাছে নিশ্চিত তথ্য নেই, তাই আন্দাজে বলব না। আমি
m-angry        -                  -                  upset/complaint                    578   119    698    700  আমি খুব দুঃখিত, আপনার কথা বলা সঠিক।
m-anxious      -                  -                  anxious/information                629   166    746    747  চিন্তা করবেন না, আমি আপনাকে সাহায্য করব। রিপোর্ট দেখাতে এক ম
m-rushed       -                  -                  rushed/information    fact         587   120    701   1400  এ বিষয়ে আমার কাছে নিশ্চিত তথ্য নেই, তাই আন্দাজে বলব না। আমি
m-rude         -                  -                  upset/information                  522    84   1269   1270  আপনার কথা বুঝলাম, বেসমেন্টে গাড়ি পার্কিং আছে, রোগীদের জন্য 
m-upset        -                  lookup_booking     upset/change                       626   110      -    665  দুঃখিত, আমি স্পষ্টভাবে বুঝতে পারলাম না। আবার বলবেন?
m-confused     -                  -                  confused/information               499    93    646    646  আপনি যা বুঝতে চান তা বুঝতে পারছি।
m-chatty       -                  -                  chatty/small_talk                  627   145    836    837  আপনার ভাইয়ের ছেলেকে দেখিয়েছেন ডাক্তার সুলতানা? তিনি খুবই ভ
m-complain     -                  -                  upset/complaint                    519    84    747    748  আমি দুঃখিত, আপনার অভিজ্ঞতা খারাপ হয়েছে। আপনাকে কিভাবে সাহায
m-worried-en   -                  -                  anxious/information                556    91    423    564  I understand you're worried, don't you fret. Dr. Sultana see
m-angry-en     -                  -                  upset/complaint                    576   112    416    584  I'm so sorry for the trouble this has caused. What doctor ar
e-fee          -                  -                  calm/information                   525    92    448    532  Dr. Rahman charges 800 taka for a new patient. Would you lik
e-address      -                  -                  calm/information                   503    67    532    533  We are at House 12, Road 5, Dhanmondi, Dhaka. We are next to
e-days         -                  -                  calm/information                   492    61    251    499  Mondays, Wednesdays, and Saturdays. What time would you like
e-notes        -                  -                  calm/information                   513    81    599    599  I understand you're wanting to know what to bring for your h
e-parking      -                  -                  calm/information                   505    67    397    510  Yes, we have free parking in the basement for our patients. 
e-hours        -                  -                  calm/information      fact         507    67    538   1001  I don't have confirmed information about that, so I won't gu
e-friday       -                  -                  calm/information                   496    61    197    501  We are closed on Fridays. What else can I help you with?
e-report       -                  -                  calm/information                   518    80    467    525  It costs 300 taka to show a report within one month.
e-who          -                  -                  calm/information                   529    91    202    535  I am a computer. How can I help you today?
e-sugar        -                  -                  calm/information                   494    62    389    500  I understand you're looking for information about high blood
e-lady         -                  -                  calm/information      unsupported   492    60    168    688  I don't have confirmed information about that, so I won't gu
e-room         -                  -                  calm/information                   502    67    449    506  I understand you're looking for Dr. Sultana's room. She's in
e-rahman-days  -                  -                  calm/information                   500    62    774    774  Dr. Rahman sees patients on Tuesdays, Thursdays, and Sundays
e-canteen      -                  -                  calm/information                   488    74    380    493  I understand you're looking for information about the clinic
e-how-book     -                  -                  calm/information                   482    79    405    488  I understand you'd like to know about booking an appointment
e-exp          -                  -                  calm/information                   500    67    312    504  Dr. Hossain has fifteen years of experience. Would you like 
s-salam        -                  -                  calm/small_talk       unsupported   561    67    618   1258  এ বিষয়ে আমার কাছে নিশ্চিত তথ্য নেই, তাই আন্দাজে বলব না। আমি
s-hello        -                  -                  calm/small_talk       unsupported   540    60    354   1001  হ্যালো, আপনার কী আছে?
s-thanks-ask   -                  -                  calm/information                   497    78    608    608  আপনার কথা আমার কাছে খুবই মনে হলো। লিফট আছে, ক্লিনিকের তৃতীয়
s-hello-en     -                  -                  calm/unknown                       476    58    241    480  Yes, this is Shefa Clinic. How can I help you?
s-name         -                  -                  calm/small_talk                    532    56    294    535  আমার নাম শেফা। আপনার কি সাহায্য লাগছে?
s-weather      -                  -                  chatty/small_talk                  585    83    375    590  হ্যাঁ, খুবই গরম। আপনার কী জানতে চান?
s-how-en       -                  -                  calm/small_talk                    540    58    268    545  I'm doing well, thank you. How can I help you?
s-lang         -                  -                  calm/information                   489    60    409    494  না, আমি বাংলাতেই কথা বলি। আপনার কি কোনো প্রশ্ন আছে?
```

### Observations beyond the gate

1. Router mood never says `angry` (angry and rude callers come back `upset`), and it overrides the
   word rules, so `angry_turns` no longer counts up for "!!" or "ফালতু"; the "angry two turns →
   offer a person" rule depends on it. Router goal for callbacks and emergencies is `change`.
2. Wrong facts still pass the checker: k-days "ডাক্তার সুলতানা বুধবার, শনিবার এবং রবিবার" (Sunday is
   wrong), k-unknown "no canteen" invented, e-days pushes "What time would you like to come?" on
   an information question.
3. The conduct prompt still names `hand_over` ("get hand_over with reason emergency"), a tool the
   reply can no longer call; the router covers emergencies (both emergency turns routed right).
4. `_act` is still the stub: every routed turn speaks the repeat prompt. Task 9 fills it.

## After Task 7b (final checker, after fix round 1)

Date: 2026-11-26. `PYTHONUNBUFFERED=1 uv run python scripts/brain_probe.py --runs 1 --concurrent 1`
(one sequential pass, then the 7-turn call) on the final code (d2e7b19). Raw run (untracked):
`data/bench/brain-probe-20261126-102428.json`. Same setup as 8c. Earlier 7b runs
(`…-085134.json` before the review, `…-101153.json` before the fix round's second pass) no longer
describe the checker and are not used here.

What changed (Task 7b and its fix round): the checker passes true answers it refused (a near-copy
of the question that adds a number, day, time or doctor; a yes confirming a named doctor's
checked day; a backed doctor-code yes; a greeting given back), reads the directory's gender and
language codes in words, matches times written in words and checks clock times hour and minute,
checks each clause's days, times and numbers against the doctors it names (today never backs a
doctor's day; call values carry their doctor), judges a doctor's language/gender claims on that
doctor's own codes, refuses invented facility answers, letters and digits of other scripts,
"open" on a day the facts close, and more "when would you like to come" pushes. The engine
answers a pure facility question no fact of the turn covers by code (`reply_source:
"facility"`): the clinic's knowledge entry for the topic when retrieval missed it, else "not
known". A department named in a question is an information goal. A router `upset` no longer
hides the word rules' `angry`.

| | 8c run 1 | 7b final |
|---|---|---|
| Regenerations | 9/90 (7 unsupported, 2 fact) | **5/90** (3 fact, 2 unsupported) |
| First spoken p50 / p95, 59 non-tool turns | 599 / 1338 ms | 512 / **1523** ms |
| same, 55 turns the model answered (4 code-answered left out) | - | 532 / 1523 ms |
| p95 without regenerated turns | 1126 ms | **1029 ms** |
| Turns over 1100 ms | 9 | 6 |
| Router call p50 / p95 | 525 / 612 ms | 535 / 599 ms |
| Reply first token p50 / p95 | 80 / 120 ms | 83 / 140 ms |
| First sentence finished p50 / p95 | 532 / 1126 ms | 529 / 1143 ms |
| Finished sentence held by the router | 0 / 276 ms, 23 turns | **0 / 0 ms, 0 turns** |
| Router right / false | 30/31, 2/59 | 30/31, 2/59 (same misses) |

The latency gate (p95 ≤ 1100 ms) fails on regenerated turns: with 59 turns the nearest-rank p95
is the 57th, so three slow turns set it. Without regenerated turns it passes (1029 ms). Over
1100 ms: k-rahman-time 2293, k-days 2151, m-confused 1523, d-lady 1320 (all regenerated),
k-parking 1177 and m-chatty 1164 (long Bangla first sentences at ~25 ms/token).

**Router hold after streaming (first measurement):** the tool field is known about 190–210 ms
into the turn (whole answer ~535 ms), before every first sentence finished: no sentence waited.

Regenerations by reason, and whether the refusal was right:
- `fact` k-days: "…सोमবার … দুপুর ১০টা থেকে তিনটা…", then "…দশটা থেকে তিনটা…" (3 is not her hour;
  right), ended in the safe sentence.
- `fact` k-rahman-time: "ডাক্তার রহমান বৃহস্পতিবার ও সোমবার…" twice (Monday is wrong; right).
- `fact` m-confused "হ্যাঁ, শিশু ডাক্তার শিশুদের দেখেন…" ("ডাক্তার শিশুদের" read as a doctor's name:
  the false refusal 8c already listed, still open; the retry passed).
- `unsupported` d-lady "হ্যাঁ, আমাদের কয়েকজন মহিলা ডাক্তার আছেন।" twice ("several"; right).
- `unsupported` e-lady "Yes, we do." twice (nothing in it to back; arguable).

The probe's cases:

| case | 8c | 7b final |
|---|---|---|
| d-exp "…অভিজ্ঞতা আঠার বছরের।" | refused (parrot) | passes |
| d-english "হ্যাঁ, ডাক্তার হোসেন ইংরেজিতে কথা বলে।" | refused (parrot) | passes |
| s-salam "আসসালামু আলাইকুম, ভালো আছি।" | refused (parrot) | passes |
| k-followup "…ফলো-আপ ফি চারশো টাকা।" | refused (parrot) | passes |
| m-rushed "রাত ৯টা", m-angry, e-hours "nine in the evening" | refused (fact) | pass |
| k-days wrong hour / Devanagari for Dr Sultana | passed (wrong) | refused |
| e-days "What time would you like to come?" | spoken | **dropped (push)**; goal `information` |
| d-lady female doctor yes | refused | the model said "several" twice: refused, safe sentence |
| k-unknown, e-canteen, k-pharmacy | invented yes/no on some runs | code: "not known" in 11–14 ms |
| k-friday, the long call's address | wrong "খোলা থাকে" / answered | code speaks the clinic's entry (retrieval missed it) in 7–12 ms |
| s-thanks-ask "ক্লিনিকে লিফট আছে।" (no fact) | spoken | refused after the first sentence |
