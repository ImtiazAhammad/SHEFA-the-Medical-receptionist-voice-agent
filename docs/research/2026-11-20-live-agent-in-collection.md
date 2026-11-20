# Can volunteers talk to the real agent while we collect? (2026-11-20)

Short answer: yes, and it is the most useful next step, because it turns the collection portal
into the **test harness for the booking product**. Recommended with the product's own local agent
(not a separate chatbot), with the limits below.

## What was measured (the real SHEFA text pipeline, sample clinic, gemma2:9b on Ollama, RTX 4060 Ti)
Typed turns, so speech recognition time is NOT included.

| Said | SHEFA (before today's fixes) | Time |
|---|---|---|
| নিউরোলজি বিভাগে একজন ডাক্তার দেখাতে চাই | offered a **Urology** doctor | 0.5 s |
| Neurology department এ কালকে সিরিয়াল হবে? | answered in English, wrong doctor | 0.0 s |
| আপনি কি মানুষ না রোবট? | "আমি একটি রোবট…" (fine) | 4.6 s |
| আমার বাবার হঠাৎ বুকে প্রচণ্ড ব্যথা, কী করব? | **listed departments; no emergency line** | 2.3 s |
| ডাক্তার সাহেব কি ভালো? … রোগ সারবে? | long department list (weak) | 10.3 s |
| পার্কিং আছে আপনাদের? | confused answer | 4.9 s |
| first turn after start | | 21.7 s (model warm-up) |

Six off-script sentences found three real product bugs (two fixed today: departments said the
mixed way, and emergency words with a word in between). Scripted reading never finds these. That
is the strongest argument for the live mode.

## How it would work
1. The volunteer picks "SHEFA-র সাথে কথা বলুন" and gets a situation (no hint wording).
2. Each turn is recorded as a normal clip (same consent, same review queue, slot `live`).
3. The server transcribes it (the Whisper model already loaded for drafts), passes the text to the
   product's own pipeline (`text_pipeline().handle_text`) on a SANDBOX clinic database, speaks the
   reply with the local voice and plays it. The page shows "SHEFA যা শুনেছে" so the volunteer
   sees mishearings.
4. After the call the volunteer taps "ঠিক ছিল / ভুল বুঝেছে / অদ্ভুত উত্তর". Every call is saved
   as a product test case (what was said, what SHEFA heard, what it did).

## What we gain
- Unscripted speech: corrections ("না না, কালকে না, পরশু"), repeats, frustration, off-topic
  questions, the things real calls contain and scripts do not.
- A growing set of real failures to fix and to re-test after every change (regression set).
- Volunteers stay interested (several asked for this).

## Risks and limits
- **Latency:** speech recognition (about 1-3 s) + agent (0-10 s on the LLM path) + voice. Turns of
  3-12 s will feel slow; the scripted path is instant. Show a "ভাবছে…" state.
- **One GPU:** Whisper + gemma2:9b fit in 16 GB; 2-3 talkers at a time, then "ব্যস্ত, একটু পরে".
  The laptop also has to stay on.
- **Agent mistakes reach volunteers.** That is the point, but brief them: it is a test, nothing is
  booked, and the emergency message ("৯৯৯-এ ফোন করুন") is expected if they act an emergency.
- **No hint means no expected answer:** every live clip must be transcribed by the reviewer (the
  machine draft helps).
- **A cloud LLM** (e.g. Claude) would give smoother, more varied answers, but it is not the product
  and sends text off the machine. Use the local product agent; try a cloud model later only as an
  experiment for exception handling.

## Effort
About 2-3 working sessions: a live-call page in the collector, a server endpoint that chains
draft model -> product pipeline -> local voice, a sandbox clinic, the feedback buttons, a
"failures" list on the admin page, and tests. The product already has a browser voice call
(`/ws/demo-call`); reusing it is a possible shortcut, to be checked first.
