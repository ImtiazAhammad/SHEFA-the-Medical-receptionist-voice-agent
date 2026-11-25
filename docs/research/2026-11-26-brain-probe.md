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
