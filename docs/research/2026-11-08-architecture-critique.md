# SHEFA architecture critique, 2026-11-08

Why the agent feels like a form-filler instead of a receptionist, checked against the code, the
console logs of 2026-11-07, and how production voice agents are built.

## Verdict

The pieces are real and they run locally: Bangla Whisper, gemma2, Piper, a booking engine,
Asterisk. What is missing is the layer that makes a call feel like a conversation: **a dialogue
manager that holds state and knowledge**. Today the language model is used as a one-shot
classifier. It reads the history, emits one JSON tool call, and code replaces its wording with a
template. Nothing reasons about what the caller is trying to achieve, so any request that is not
phrased like a command ("book Dr Rahman tomorrow at 9") falls through to the nearest tool or to
`transfer_to_human`.

Several of those choices were mine, made earlier in this project (see "My reasoning errors").

## What I verified before writing this

| Question | Result |
|---|---|
| Is Ollama truncating the prompt? (`ollama ps` shows a 4096 context) | **No.** The router prompt is ~1,200 tokens; a 10-turn call is ~1,600. Truncation would only start near 40 turns. `num_ctx` can be raised to 8192 for headroom. |
| Why is the first syllable lost ("শিশু" -> "িশু", "ইমতিয়াজ" -> "িয়াজ")? | **The browser, not the VAD.** `console.html` zeroes the microphone while the agent speaks and for 0.25 s after (`agentUntil+0.25`), so a caller who answers at once is muted for their first syllable. The VAD keeps every sample since the last flush, so a VAD pre-roll would not help. Yesterday's plan task 3 is wrong. |
| Why are VAD flushes 10-21 s long with 60-90% discarded? | The buffer includes the digital silence sent while the agent speaks plus the caller's thinking time; Whisper's own VAD strips it. Harmless to accuracy, wasteful, and it hides real endpointing. A 21.6 s flush at rms=29 was room noise that became an empty transcript and counted toward the 3-failure escalation. |
| Can the caller ask "do I have an appointment?" | **No tool exists for it.** `verify_patient` returns only id/name/phone. The router had no correct option and chose `transfer_to_human`; the free-form reply then claimed "আপনার নামে একটি অ্যাপয়েন্টমেন্ট আছে" with nothing behind it. |
| Does `verify_patient` guard identity? | **No.** It registers any string as a phone number (`0787374` became patient 3). |
| Does the router invent arguments? | Yes: `reschedule_appointment` with `appointment_id: "unknown"` and a made-up 14:30; `doctor_name: "ডাক্তর সুলতানা"` (a spelling that is in no list). |

## How a production voice agent works (from the research)

- **Cascaded pipeline is still the default**: streaming STT -> LLM -> streaming TTS, with each
  stage starting before the previous one finishes. Reported end-to-end latencies range from
  ~0.6 s to ~3 s depending on the source; most come from vendors, so treat them as directional.
  Speech-to-speech models are gaining ground for latency but are harder to audit and to run
  locally. ([Cartesia](https://www.cartesia.ai/learn/speech-to-speech-vs-cascaded),
  [Gradium](https://gradium.ai/content/cascaded-voice-agent-vs-speech-to-speech-2026),
  [LiveKit](https://livekit.com/blog/sequential-pipeline-architecture-voice-agents),
  [Softcery](https://softcery.com/lab/ai-voice-agents-real-time-vs-turn-based-tts-stt-architecture))
- **Turn detection is learned, not a silence timer.** A fixed 700 ms timer costs 700 ms every
  turn; production stacks combine VAD with a semantic end-of-turn model.
  ([LiveKit](https://docs.livekit.io/agents/v1/build/turn-detection),
  [LiveKit blog](https://livekit.com/blog/turn-detection-and-interruption-handling))
  Whether any of these models cover Bangla is **not established**; check before depending on one.
- **Barge-in**: keep listening while the agent speaks; on interruption stop playback, flush
  queued audio, restart from STT. For irreversible tool calls, disable interruption.
- **Booking pattern**: the model converses and fills arguments; a deterministic tool checks
  availability and writes (transactionally); the agent reads back date/time/clinic and books only
  on an explicit yes; relative dates are grounded by a "today" tool; missing information is
  re-asked rather than guessed; the agent says "let me check" before a slow tool. These are
  practitioner write-ups, not standards.
  ([AssemblyAI hackathon entry](https://lablab.ai/ai-tutorials/assemblyai-voice-agent-http-tools),
  [OmniDim example](https://www.omnidim.io/docs/examples/health-appointment-booking-agent))
- **Verbex / the iFarmer example**: I cannot hear that audio, so I will not critique the call
  itself. Public facts: Verbex (formerly Hishab) builds Bangla voice agents on an in-house stack;
  an ASR paper from the group reports over 20,000 hours of labelled Bangla speech
  ([TBS News](https://www.tbsnews.net/features/panorama/voice-possibility-how-verbexai-giving-ai-bangladeshi-accent-1138101)).
  Their page names no models or engine. The gap to SHEFA is therefore partly **data and models**
  (ASR hours, a proprietary voice) that architecture cannot close, and partly **dialogue design**
  that it can.

## Critique by layer

| Layer | Today | Problem | Direction |
|---|---|---|---|
| Audio in | Browser mic -> 16 kHz PCM; half-duplex gate; Asterisk 8 kHz | Gate clips the first syllable; callers cannot interrupt; echo handled by muting | Drop the tail gate; rely on browser echo cancellation; server-side barge-in |
| Turn-taking | Energy VAD, 0.8 s end silence | Noise counts as speech; no notion of "finished sentence" vs "pause"; empty transcripts count as call failures | Silero VAD (already inside faster-whisper) plus a semantic end-of-turn check; noise segments do not count toward escalation |
| STT | Bangla Whisper medium CT2 + English small, routed by detected language | Strong on clean Bangla; short utterances mis-detected as English; digits and names garbled | Keep; bias with a clinic vocabulary prompt (doctor and department names); digit parsing in code |
| LLM | gemma2:9b through Ollama chat, JSON mode, no native tools | Used as a classifier; no state; re-reads history each turn; the free-form path hallucinates | Converse with tool calling over a dialogue state (below); benchmark any model change on the router and lab sets |
| Inference engine | Ollama | Serial requests, prefix caching not under our control, gemma2 rejects tools, one call at a time | Fine for a demo. Production candidates (vLLM, SGLang, llama.cpp server) bring prefix caching, schema-constrained output and concurrency; **not benchmarked here, and the model dictates what can run** (Qwen3 garbled Bangla, Gemma 3 12B missed a tool in earlier tests) |
| Dialogue / booking | Route first, run tool, speak a template | No slots, no clarification, no read-back, no offer of alternatives, no memory of what was established | Dialogue state machine (below) |
| Doctor knowledge | name, Bangla name, department, qualification, fee, weekly schedule, leave | Nothing links a symptom, a service or a person's description to a doctor | Enriched directory in the prompt (below) |
| TTS / wording | Piper bn; Kokoro en; fixed templates | Templates are correct but robotic; one reply shape for every situation | Short generated replies grounded on tool results, with facts (dates, times, fees) still rendered in code |
| Telephony | Asterisk AudioSocket built, **never run against real Asterisk** | Unknown codec, DTMF, NAT, caller-ID behaviour | Test with a softphone before any carrier |

## Why indirect questions fail

"I have chest pain, who should I see?", "my child has a fever", "is there a lady doctor?",
"who is the best for the heart?" all need **knowledge of the doctors**, which the directory does
not hold, and **a conversation**, which the router does not have. Static lookups (who, where,
when, how much) are being treated as tool calls with an LLM round-trip each, when for a clinic of
3-50 doctors the whole directory fits in the prompt (~500-1,500 tokens against 4,096, or more
with `num_ctx` 8192) and can be answered directly. Tools should be kept for what changes: live
availability, booking, cancelling.

## Target design

```
mic/phone -> VAD + end-of-turn -> STT (+ clinic vocabulary) -> turn text
                                                       |
   caller id / session identity ---->  DIALOGUE MANAGER (code)
                                          state: intent, department, doctor, date, time,
                                                 patient, pending-confirmation
                                          |            |                 |
                                  LLM with directory   deterministic     safety rules
                                  in cached prompt     booking engine    (emergency, no advice)
                                  + native tool calls  (slots, write)
                                          |
                          grounded reply -> facts rendered in code -> TTS (streamed)
```

1. **State, not guesses.** A small `DialogueState` per call (department, doctor, date, time,
   patient, `pending`). The model proposes; code checks every argument against the directory and
   the state before acting. Missing slot -> a targeted question. Complete slot -> read back and
   require an explicit yes.
2. **Offer, don't interrogate.** Offer 2-3 concrete slots ("Dr Rahman has 4:00 or 4:15 on Sunday,
   which one?") instead of asking an open question.
3. **Caller ID first.** "Is this 01782-737074?" instead of dictating digits; digit words parsed in
   code when a number is needed.
4. **Directory in the prompt**, cached, so "who treats a child's fever?" is answered from the data.
5. **Interruptible agent**, with turn detection that tolerates thinking pauses.
6. **Eval-gated changes.** No model or prompt change ships without the lab (`shefa lab run
   --audio`) and `scripts/bench_router.py`, both extended with indirect phrasings and with
   **real-microphone runs** (see below).

## Doctor information to enrich

Current fields: name (en/bn), department, qualification, fee, weekly schedule, leave.
Proposed additions (confirm with a real clinic which it can supply):

| Field | Why a caller asks |
|---|---|
| `conditions` / `services` (list, en + bn) | "my child has a fever", "back pain", "pregnancy check" -> the right department and doctor (routing aid, not medical advice) |
| `designation`, `experience_years`, `bmdc_no` | "how senior is the doctor", trust |
| `gender`, `languages` | "is there a lady doctor?", "speaks Bangla only?" |
| `room`, `floor`, `chamber` | "where do I go?" |
| `fee_new`, `fee_followup`, `fee_report` | fee depends on the visit type |
| `visit_types`, `slot_minutes`, `booking_notes` | follow-up within N days, fasting, bring reports |
| `aliases` (spoken and mis-heard spellings) | "ডাক্তর সুলতানা", "হাসান" -> the right doctor |
| `blurb_bn`, `blurb_en` (one sentence) | a natural spoken introduction |
| `available_for_phone_booking` | some doctors are walk-in only |

## What architecture cannot fix

- Bangla ASR on real phone audio: needs data (Verbex has ~20k hours). Options: collect and
  fine-tune on clinic calls with consent; a clinic vocabulary prompt helps in the meantime.
- A natural Bangla voice: needs a recorded voice talent or a licensed model; see the listening
  test (`shefa lab voices`).
- Model quality in Bangla: gemma2 holds the language, but a stronger open model would help.

## My reasoning errors

- Each fix was local: a prompt hint, a word-count rule, a template. The 3-word language rule
  caused the phone-number regression in the next call.
- "Route first, then speak a template" removed hallucinated facts and also removed the
  conversation. I treated robotic wording as an acceptable cost.
- I tested with Piper-generated speech through `scripts/simulate_call.py`. That hides microphone
  noise, clipping from the browser gate and real endpointing, so the first real-microphone call
  exposed problems the tests could not. Real-microphone runs must become the acceptance test.
- I proposed a VAD pre-roll without checking where the audio was actually lost.

## Sequence

Yesterday's plan (`docs/superpowers/plans/2026-11-07-conversation-quality.md`) is **superseded**
in order and scope, but these tasks survive as quick wins: 1 (missing arguments), 5 (phone
parsing and validation), 7 (digits and language switching). Task 3 (VAD pre-roll) is replaced by
removing the browser tail gate. The rest is re-sequenced under the dialogue manager.

## Open questions

1. Which enrichment fields can a real clinic supply, and who maintains them?
2. Is a human callback acceptable when no one answers a transfer, or is a live number required?
3. Does any open turn-detection model handle Bangla? Needs a test on recorded calls.
4. Do we move off Ollama before the first clinic, or after measuring concurrency needs?
