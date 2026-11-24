# SHEFA as a human-like front desk, on local models

Design spec, 2026-11-25. Status: awaiting review.

## 1. Why

SHEFA does not yet handle callers the way a trained front-desk officer does. Reading the code
(2026-11-24) and the voice-collection site's real calls found:

| Cause | Status |
| --- | --- |
| Booking is a fixed form (`pipeline/guided.py`): one closed question at a time, answers matched by keyword lists. | Confirmed in code |
| Almost every reply is a sentence written in code (`_dialogue_state` returns template text in nearly every branch); the model speaks only when nothing matched; one fixed greeting. | Confirmed in code |
| Two misunderstood answers in a row hand the call to a person. | Measured, small sample: 8 of 9 real volunteer calls with the live agent ended in handover |
| No barge-in: a reply is spoken to the end; speech that arrives meanwhile is answered afterwards; the browser clients send silence while the agent speaks. | Confirmed in code |
| Turn end is a fixed 800 ms silence timer; no acknowledgements while a caller talks. | Confirmed in code |
| The model's instructions are about 15 rules; nothing on empathy, de-escalation, off-topic or rude questions; no sense of the caller's mood. | Confirmed in code |
| A turn takes about 3.3 s at the 95th percentile. | Recorded in settings, not re-measured on a phone line |
| Bangla recognition: 22% word errors on clean synthetic audio; never measured on 8 kHz phone audio. | Partly measured |

The model is not the main limit; the harness around it is.

## 2. What we are building

**Said by the founder:**
- Stay local and low-cost. No cloud models. Voice data is being collected to fine-tune later.
- Behave like a highly trained front-desk officer: polite, helpful, empathetic; answer from the
  clinic's knowledge base only; handle questions outside it tactfully, as instructed; stop and listen
  when the caller talks over it; answer dynamically, never the same lines every call; handle any
  caller (angry, emotional, talkative, quiet, ordinary) naturally.
- A caller who only wants information gets it, without being steered toward booking.
- The knowledge base also holds facts about SHEFA itself (who made it, what it can do), answered
  naturally.
- Compare local models by measurement and use the best one for dynamic replies.
- A super admin console for the platform operator only (the founder): prompts, models and the other
  controls a super admin needs. Built so a per-clinic owner level can be added later.

**Assumed (approved 2026-11-25):**
- Code stays in charge of facts and actions; nothing unverified is said or booked; bookings keep the
  read-back and the caller's "yes". Only the talking becomes dynamic.
- "Better" is decided by a repeatable test bench, not by impression.
- Everything runs on one RTX 4060 Ti (16 GB) beside speech recognition and the voice.

**Success**
- On the test bench: zero hard-check failures (no invented facts, no unconfirmed bookings, no medical
  advice, no other caller's data) and a judged score that beats today's guided flow on every caller type.
- First audio within 1.2 s for 95% of turns with three calls at once.
- Barge-in stops SHEFA within 300 ms of real caller speech and is never triggered by SHEFA's own echo
  on the bench's echo cases.
- On real volunteer live calls: handovers fall from 8 in 9 to a minority, and "odd" / "misheard"
  verdicts fall.

**Not in scope:** cloud models; fine-tuning (it comes later and slots into the same design);
per-clinic owner editing (designed for, not built); new telephony providers.

## 3. Shape: four sub-projects, in this order

Each gets its own implementation plan.

1. **Test bench and model bake-off** (section 4). First, so every later change is measured.
2. **The conversation brain**, including the knowledge base and the versioned config store the
   console will edit (section 5).
3. **Listening**: barge-in, turn-taking, speed (section 6).
4. **Super admin console** (section 7). The config store comes in 2; the console UI is built last.

The new engine runs behind `pipeline.engine: agent | guided` (default `guided`) until the bench
says it is better; then the default flips. The guided flow stays as the fallback engine.

## 4. Test bench and model bake-off

**Cases** (`bench/calls/*.yaml`, about 60 to start): a caller persona, a goal, the facts the caller
knows, and optional fixed lines. Personas: angry, anxious or crying, talkative, quiet, confused
elderly, rushed, rude or abusive, off-topic chatter, Bangla-English switching. Goals: information
only, booking, change or cancel, "my appointment", emergency, medical-advice request, questions about
SHEFA, questions the knowledge base cannot answer.

**Mishearing:** caller lines pass through a noise model built from real recognition errors in the
volunteer recordings (`clips.expected_text` against the machine draft): dropped words, misheard
names, digits and Bangla homophones, at a rate set per run.

**Two-sided calls:** a caller model plays the persona turn by turn against the agent, up to a turn
limit, so whole conversations are tested.

**Hard checks** (code, pass or fail per call): every number, time, fee, name and date in a reply is in
the facts the agent was given or a tool result; no booking without read-back and "yes"; no medical
advice; no other caller's data; an emergency gets the emergency line within one turn; an
information-only caller is never pushed toward booking; no reply over 2 sentences unless the caller
asked for a list.

**Judged scores** (1 to 5, a judge model with a fixed rubric): warmth; acknowledges feelings before
facts; no repetition across the call; clear for phone listening; natural Bangla; tactful with
off-limits questions; recovers from mishearing. A set of real transcripts marked by the founder in the
console calibrates the judge (agreement is reported with each scorecard).

**Bake-off:** candidates already installed: gemma2:9b (current), Gemma 3 12B, Qwen3 14B and 8B
(thinking off), Aya Expanse 8B, TigerLLM 9B, Qwen2.5 7B. Any model added in the console can be benched
the same way. Measured per model: hard-check pass rate, judged score, Bangla purity, first-token time
at the 95th percentile with three concurrent calls, and graphics memory with recognition and the voice
loaded. The winner is the best quality whose first audio stays within 1.2 s at p95.

**Output:** `shefa bench run [--model M] [--cases tag]` prints and saves a scorecard (JSON plus a short
text summary) under `data/bench/`; the console lists scorecards and compares two.

The existing `scripts/bench_dialogue.py` router cases become one case group.

## 5. The conversation brain

### 5.1 A turn

1. **Hear**: the caller's words for this turn (from section 6), with language and voice cues.
2. **Track** (`brain/state.py`): update `CallState`: goal (information, booking, change, lookup,
   complaint, small talk, unknown), booking details given so far, language, mood, how many times the
   caller repeated themselves, what SHEFA last offered.
3. **Retrieve** (`brain/knowledge.py`): up to 4 knowledge-base entries for this turn, plus directory
   facts (doctors, schedules, free times) from the clinic store when the turn needs them.
4. **Compose** (`brain/prompt.py`): the published persona prompt and conduct rules, a short cue for
   the caller's mood and goal, the retrieved facts each with an id, the last turns plus a running
   summary, and the tool list.
5. **Generate**: one streamed call to the model. The reply is plain spoken text. When it needs to
   act, it opens with a single tool line (`TOOL {...}`), code runs the tool, and a second call speaks
   the result.
6. **Check** (`brain/check.py`), sentence by sentence before each is spoken: every number, time, fee,
   name and date appears in the given facts or a tool result; no claim that a booking, cancellation or
   call-back happened unless a tool returned success; no medical advice phrases; no other caller's
   data. A failing sentence triggers one regeneration with the reason; a second failure speaks a safe
   fixed sentence for that situation.
7. **Speak** each passing sentence as soon as it is ready (section 6).

### 5.2 Tools

`find_doctors(specialty|symptom|name)`, `free_times(doctor, day|period)`,
`book(doctor, day, time, name, phone)` (only after read-back and "yes"), `lookup_booking`,
`cancel_booking`, `reschedule_booking`, `request_callback(reason)`, `hand_over(reason)`, `end_call`.
They wrap today's executor (`tools/executor.py`). The parsers in `pipeline/guided.py` and
`pipeline/grounding.py` (dates, times, Bangla numbers, phone numbers, doctor names) become argument
validators: a tool call with an argument that does not resolve returns a clear error the model turns
into a natural clarifying question.

### 5.3 Knowledge base

Entries: `id, scope (clinic id | platform), topic, tags, text_bn, text_en, active, version`.
Platform entries hold "About SHEFA" (who made it, what it can and cannot do). Clinic entries hold
fees, address, directions, parking, tests and services, insurance, reports, visiting rules, payment,
and anything the founder adds. Doctors and schedules are not copied in; they stay live in the clinic
store.

Retrieval: word matching (BM25 over Bangla and English, using the existing name folding) plus a small
multilingual meaning-matching embedding model on the CPU; results merged, top 4 above a score floor.
No entry above the floor means "not in the knowledge base": the conduct rules decide the answer (say
so kindly, offer the desk's call-back when it helps), and the checker blocks any invented specifics.

### 5.4 Caller mood and conduct

Mood per turn: `calm, anxious, upset, angry, confused, rushed, chatty, quiet`, from the words (a
small classifier prompt folded into the tracking step) and the voice (loudness against the caller's own
average, speech rate, interruptions, repeated questions). The label becomes a one-line cue, for
example "The caller is upset: acknowledge it in a few words before anything else; keep sentences
short."

Conduct rules (editable, versioned): acknowledge feelings first; never argue; apologise for the
clinic's delays without blaming anyone; answer only from facts; say plainly when something is not
known and offer the desk; no medical advice, but urgent symptoms get the emergency line at once; never
reveal another person's data; small talk briefly and warmly, then back to the caller's need; never push
booking on an information-only caller; rude caller: stay calm, one polite boundary, then a second,
then hand over and end; persistent anger (two turns) or an explicit request: offer a person.

### 5.5 Booking without the corridor

The model asks for missing details naturally and in any order; details given early (a talkative
caller saying doctor, day and name in one breath) are kept. Read-back and "yes" before `book` stay.
Misunderstanding is handled by rephrasing and offering choices, not by a two-strike handover; handover
happens when the caller asks, when the checker fails repeatedly, or when the conduct rules say so.

### 5.6 Greeting and closing

Generated from the greeting-style prompt with the clinic name, the time of day, and for a returning
caller (caller ID) their name if known. Varied phrasing; a fixed greeting is the fallback. Closings
summarise what was done ("আপনার সিরিয়াল বৃহস্পতিবার বিকেল ৫টা") when something was done.

### 5.7 Config store

`config_versions(id, scope, key, value_json, status draft|live|archived, author, created_at, note)`
in the main database. Keys: `prompt.persona`, `prompt.conduct`, `prompt.greeting`, `prompt.tools`,
`model.llm`, `model.llm.params`, `model.stt`, `model.tts.<lang>`, `turn.*`, `escalation.*`,
`engine`. Runtime reads the live version through a small cached reader (`brain/config.py`); a call
uses the versions live when it started. `configs/default.yaml` stays the seed and the fallback.

## 6. Listening

**Three tasks per call** (`pipeline/duplex.py`): hearing (voice-activity detection and recognition,
always on), thinking (section 5), speaking (a cancellable playback task). Today's single loop in
`process_audio_stream` is split into these.

**Barge-in:** while SHEFA speaks, caller speech that is real speech (above a raised threshold, at
least 300 ms of voice, not a known acknowledgement such as জি, হুম, আচ্ছা, and whose transcript does
not match SHEFA's own current words) cancels speaking and flushes playback (Asterisk and the browser
get a clear-audio message). The brain is told how much of its reply was heard, so it does not repeat
the part already heard or assume the rest was.

**Echo safety:** on a phone line there is no echo cancellation, so the threshold during playback
follows the playback level (delay-aligned), and transcripts matching SHEFA's words are dropped. In the
browser, echo cancellation is on; the silence-while-speaking trick becomes a setting
(`turn.half_duplex`, default off once the bench's echo cases pass on a loudspeaker test).

**End of turn:** silence window adapts to context (shorter after SHEFA asked a yes/no question, longer
while the caller is listing or mid-sentence), plus a completeness check on the running transcript;
a hard maximum stays.

**Acknowledgements and silence:** a caller who talks for a long time gets a short pre-recorded "জি…"
in a pause, without taking the turn. Silence: a gentle check after 6 s, another after 15 s, a polite
close after 25 s (all settings).

**Speed:** recognition runs on the growing utterance every second while the caller speaks, so only the
last piece is left at the end; the model starts at once; the first sentence is spoken as soon as it
passes the checker; "একটু দেখছি…" plays only when a tool takes longer than 700 ms. Target: first audio
within 1.2 s at p95.

## 7. Super admin console

**Who:** a new platform role `superadmin`, above clinic roles, held by the founder only. Its own sign-in
at `/console`, separate from the staff app's clinic sign-in, never reachable through the public link.
Every change is written to an audit log (who, what, before, after, when).

**Areas:**
- **Prompts:** persona, conduct rules, greeting style, tool rules. Drafts with a diff against live, a
  test chat that runs a draft without publishing, publish, roll back to any version.
- **Knowledge base:** platform entries (About SHEFA) and per-clinic entries; editor in Bangla and
  English; "ask a question" shows which entries would be retrieved and the reply a draft would give.
- **Models:** language model (from the installed list), its generation settings, recognition model,
  voice per language. A switch runs a short self-test (load, one Bangla and one English turn,
  memory check) before it can be made live.
- **Conversation settings:** silence windows, barge-in sensitivity, acknowledgements, silence
  check-ins, escalation limits, maximum call length, languages, engine (agent or guided).
- **Test bench:** run a bench, see and compare scorecards, mark real transcripts for the judge.
- **Calls:** live and past calls; per turn the mood label, retrieved entries, tool calls, checker
  verdicts, timing; flag a turn to turn it into a bench case.
- **System:** health, graphics memory, model status, the pause switch, feature switches, user accounts
  (clinic owners and staff), backups.

Built in the existing React app as its own area, served at `/console` by the same build, with the same
visual language; the main server serves it only on its local address, never through the public link.
Changes apply to new calls only.

## 8. Errors and fallbacks

- Model unavailable or too slow: the guided engine takes the call (it needs no model for most turns),
  and the console shows the failure.
- Checker fails twice: a safe fixed sentence for the situation; the turn is marked for review.
- Retrieval finds nothing: "not in the knowledge base" path (5.3).
- Tool error: the model is told in plain words and asks or offers the desk; no claim of success.
- Barge-in false triggers above a rate in a call: that call falls back to half-duplex and the call is
  marked.
- Config publish of a broken prompt or model: blocked by the test chat and self-test; rollback is one
  click.

## 9. Testing

Unit tests for each new module (state tracker, retrieval, prompt assembly, checker, tool validators,
duplex controller with simulated audio, config store, console API permissions). The bench is the
integration test; a bench run gates flipping the engine default and each published prompt. Existing
tests stay green; the guided engine keeps its tests.

## 10. Risks

- A 9 to 12B local model may still sound stiff in Bangla at times; the checker keeps it safe, and the
  bench shows where. Fine-tuning on collected data is the next lever.
- Recognition errors on real phone audio cap understanding; the mishearing model and the bench show
  how much, and recognition fine-tuning continues in parallel.
- Barge-in on phone lines without echo cancellation is the hardest part; it ships behind a setting and
  is proven on the bench and a real line before it is on by default.
- One graphics card limits concurrent calls; the bake-off measures it.
