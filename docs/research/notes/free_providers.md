# Free / free-tier cloud APIs as a fallback for a Bangla (Bangladesh) + English voice agent demo

Date seen for all items: 2026-11-04.

**Method caveat (read first):** In this session, direct page fetches to azure.microsoft.com, learn.microsoft.com, ai.google.dev and console.groq.com failed (the hosts were blocked by the session's network allowlist). Every figure below therefore comes from web-search results. Where the search result came from the vendor's own page, the vendor URL is cited. Where it came from an aggregator or blog, that is stated. Treat every quota as "verify in the console on the day of the demo". Items marked UNVERIFIED come from background knowledge with no source found this session.

---

## TTS: which free tiers produce acceptable Bangladeshi Bangla and English speech?

### Takeaway
Azure AI Speech (F0) is the only official free tier I could confirm that has true bn-BD neural voices: Nabanita (female) and Pradeep (male). It also includes 0.5M neural characters per month, which covers a 30-minute demo many times over. Gemini TTS also lists bn-BD and is the most expressive option. Google Cloud's Chirp 3 HD voices are bn-IN only. ElevenLabs v3 supports Bengali, but its free plan is non-commercial and needs attribution. edge-tts is an unofficial, undocumented endpoint, so it should not be relied on in front of a client.

### Cited Findings
**Microsoft Azure AI Speech**
- The official pricing page lists Text to Speech **Neural: 0.5 million characters free per month** on the Free (F0) tier. The "5 audio hours free per month" applies to speech-to-text and speech translation, not TTS. (One tutorial wrongly says the 5 hours are for TTS.) — [Azure Speech pricing (en-au)](https://azure.microsoft.com/en-au/pricing/details/cognitive-services/speech-services/); [Azure pricing (en-in)](https://azure.microsoft.com/en-in/pricing/details/speech)
- On the F0 tier, "usage is throttled if the transaction limit is reached". You cannot run up overages; F0 stops working at the cap. — [Microsoft Q&A quoting the pricing page](https://learn.microsoft.com/en-us/answers/questions/5566384/azure-ai-speech-what-happens-after-free-tier-t0-ex)
- A Microsoft Q&A community answer says the product terms grant commercial-use rights to the output only on paid tiers. This is a community answer, not the Product Terms text. — [Microsoft Q&A](https://learn.microsoft.com/en-us/answers/questions/5805156/please-clarify-the-conflicting-information-regardi)
- The bn-BD voices are **bn-BD-NabanitaNeural (female)** and **bn-BD-PradeepNeural (male)**. Both are listed on Microsoft's language-support page, and Microsoft's Neural TTS announcement covers them. — [MS Tech Community announcement](https://techcommunity.microsoft.com/t5/azure-ai/azure-speech-s-neural-tts-empowers-organizations-to-serve-users/ba-p/2920882); [MS language support](https://learn.microsoft.com/en-my/AZURE/ai-services/speech-service/language-support)
- A third-party page gives Nabanita a 48 kHz output and roughly 123 words per minute. It is in use in a "Bangladesh diabetes assistant" agent on Gooey.ai, which shows real health-related use in Bangladesh. — [Gooey.ai](https://gooey.ai/agent/bangladesh-diabetes-assistant-u6r9mu5b116e/); [json2video Pradeep](https://json2video.com/ai-voices/azure/voices/bn-bd-pradeepneural)

**Google Cloud Text-to-Speech**
- Chirp 3 HD supports **Bengali (India) bn-IN**, added in a March 2025 expansion. Voices are named `bn-IN-Chirp3-HD-<Name>` (for example Kore, Puck, Enceladus, Erinome). Regions: global, us, eu, asia-southeast1 and others, all GA. Streaming output supports ALAW, MULAW, OGG_OPUS and PCM. — [Chirp 3 HD docs](https://docs.cloud.google.com/text-to-speech/docs/chirp3-hd); [Voices list](https://docs.cloud.google.com/text-to-speech/docs/voices)
- I found no bn-BD Chirp 3 HD voice in Cloud TTS. Search results showed only bn-IN for Chirp 3 HD. — [Voices list](https://docs.cloud.google.com/text-to-speech/docs/voices)

**Gemini TTS**
- Google Cloud's Gemini-TTS docs list **Bengali (Bangladesh) bn-BD** among the supported languages. One version of the page marks bn-BD as pre-release. The Cloud model ID is `gemini-2.5-flash-tts` (preview). — [Cloud TTS Gemini-TTS (pt)](https://docs.cloud.google.com/text-to-speech/docs/gemini-tts?hl=pt); [pt-br version](https://cloud.google.com/text-to-speech/docs/gemini-tts?hl=pt-br)
- A third-party help article (updated April 2026) says **Gemini 3.1 Flash TTS** is now the recommended TTS model. It says 24 locales are fully supported, including bn-BD. — [Scenario help](https://help.scenario.com/articles/5604258483-gemini-tts-the-essentials); [Picsart blog (87 languages, 24 GA)](https://picsart.com/blog/what-is-gemini-2-5-flash-tts/)
- No source was found for free-tier access to TTS models in the Gemini API (AI Studio).

**ElevenLabs**
- **Eleven v3** lists Bengali (`bn`) as a supported language. The docs now describe **Eleven v4** as the most advanced model, with its language coverage on a separate page that I did not check. — [ElevenLabs languages](https://elevenlabs.io/docs/help-center/other/what-languages-do-you-support); [Models](https://elevenlabs.io/docs/help-center/technical/what-models-do-you-offer-and-what-is-the-difference-between-them)
- Flash v2.5 supports 32 languages. Bengali did not appear in the excerpts I saw, so it is unconfirmed. — [ElevenLabs models](https://help.elevenlabs.io/hc/en-us/articles/17883183930129-What-models-do-you-offer-and-what-is-the-difference-between-them)
- Free plan (third-party sources only): **10,000 credits per month**, roughly 10 minutes of Multilingual v2 audio. Credits do not roll over. API access is included. Output is **non-commercial only and needs attribution** ("Voice generated by ElevenLabs"). Commercial rights start at the Starter plan, about $5–6 per month (sources disagree on the price). — [Costbench](https://costbench.com/software/ai-voice-tools/elevenlabs/free-plan); [BigVU](https://bigvu.tv/blog/elevenlabs-pricing-2026-plans-credits-commercial-rights-api-costs/); [HappyRobot](https://www.happyrobot.ai/hub/elevenlabs-pricing)

**edge-tts (unofficial)**
- Community client projects describe the Edge Read Aloud endpoint as **undocumented**. When Microsoft rotates the `Sec-MS-GEC` token/version constant, every request returns HTTP 403 until the client library is updated. Clock skew also causes 403s. — [msedge-tts crate notes](https://docs.rs/crate/msedge-tts/latest/source/AGENTS.md); [kothok-edge-tts](https://docs.rs/crate/kothok-edge-tts/0.2.2)
- User reports describe 403s from network or region blocking of speech.platform.bing.com, 403s attributed to request volume (rate limiting), and intermittent 401s on api.msedgeservices.com. — [pyvideotrans forum 2828](https://bbs.pyvideotrans.com/show/2828); [pyvideotrans 1358](https://bbs.pyvideotrans.com/show/1358)
- No source was found in which Microsoft authorizes third-party programmatic use of the Edge Read Aloud service.

### Inferences
- For "most natural Bangladeshi Bangla" on a free tier: Azure bn-BD Nabanita/Pradeep give the correct locale accent and are reliable but somewhat flat. Gemini TTS (bn-BD) is likely the most natural and steerable by prompt, but its free-tier status is unconfirmed and it is a preview model. Google Chirp 3 HD bn-IN will sound West Bengal/Kolkata-accented, which a Bangladeshi client may notice.
- A 30-minute demo at about 150 spoken characters per agent turn and about 60 turns uses roughly 10k characters. That is about 2% of Azure F0's 0.5M per month, and about 1 credit per character, or the whole ElevenLabs free month.
- edge-tts gives the same Nabanita/Pradeep voices for free, but it can break with no warning (a token rotation means 403s mid-demo), it has no SLA, and its terms status is unclear. Use Azure F0 for the same voices legitimately.
- The ElevenLabs free plan is non-commercial, so a client demo arguably counts as commercial use. Use a paid Starter plan if ElevenLabs is chosen.

### Gaps
- Azure F0 TTS concurrency or transactions-per-60-seconds limit: not verified (I recall 20 transactions per 60 s; UNVERIFIED). Real-time streaming via the Speech SDK or WebSocket and the REST endpoint `https://<region>.tts.speech.microsoft.com/cognitiveservices/v1` (SSML) are from background knowledge (UNVERIFIED this session).
- Azure English voice names (for example en-US-AvaMultilingualNeural, en-IN voices), and whether any multilingual voice handles Bangla: not checked.
- Google Cloud TTS free monthly character allowance per voice tier (Chirp 3 HD, WaveNet, Standard): not found. My recollection is about 1M characters per month for premium tiers (UNVERIFIED).
- Gemini API (AI Studio) free tier for TTS models: no source found.
- OpenAI gpt-4o-mini-tts Bangla quality and pricing: no source found this session. Background knowledge: it is paid-only, and voices are tuned for English with accented output in other languages (UNVERIFIED).
- Latency figures (time to first byte) for any of these TTS services: none found.

---

## STT: which free tiers can transcribe Bangladeshi Bangla plus English code-switching?

### Takeaway
Google Cloud Speech-to-Text V2 with Chirp 2/3 is the only major STT service I found that lists bn-BD explicitly, but bn-BD on Chirp 3 is in preview and may support batch recognition only (no streaming). Azure STT appears to support only bn-IN. Groq's free Whisper large-v3-turbo (7,200 audio seconds per hour) is the easiest free fallback with an OpenAI-compatible API, though Whisper's Bangla accuracy is weaker than that of specialist models. ElevenLabs Scribe v2 supports Bengali, with accuracy figures that vary widely depending on who published them.

### Cited Findings
**Groq (Whisper)**
- Free plan, `whisper-large-v3-turbo`: **20 RPM, 2,000 RPD, 7,200 audio seconds per hour (ASH), 28,800 audio seconds per day (ASD)**. This was reported as Groq's own rate-limits table; the official page itself was not readable this session. — [Groq rate limits (md)](https://console.groq.com/docs/rate-limits.md); [dev.to comparison](https://dev.to/build996/free-whisper-api-groq-deepgram-assemblyai-compared-562m)
- Requests shorter than 10 seconds are billed or counted as 10 seconds. For short voice-agent turns, the request and audio-second caps can bind before the nominal hourly allowance does. — [Spokenly](https://spokenly.app/blog/free-speech-to-text-apis); [developersdigest](https://www.developersdigest.tech/models/speech/groq)
- Paid or Developer-tier figures (about 400K ASH for turbo; about 200K ASH and 300 RPM for large-v3) differ from the free tier and should not be confused with it. — [MorphLLM Groq pricing (Oct 2026)](https://www.morphllm.com/groq-pricing)

**Google Cloud Speech-to-Text**
- Chirp 3 lists **Bengali (Bangladesh) bn-BD** and bn-IN. It is available **only in the Speech-to-Text API V2**. — [Chirp 3 docs](https://docs.cloud.google.com/speech-to-text/docs/models/chirp-3)
- Several doc versions mark bn-BD as **Preview**. The Japanese page says Chirp 3 supports Bengali (Bangladesh) through **BatchRecognize only**, not streaming. Word timestamps, word confidence and speech adaptation are not supported. — [Chirp 3 (ja)](https://docs.cloud.google.com/speech-to-text/v2/docs/chirp-model?hl=ja); [Chirp 3 v2 page](https://cloud.google.com/speech-to-text/v2/docs/chirp_3-model?hl=en)
- The V2 supported-languages page lists bn-BD with the chirp_2 and chirp_3 models. — [STT V2 languages](https://docs.cloud.google.com/speech-to-text/docs/languages?authuser=5)

**Azure STT**
- The language table shows **bn-IN (Bengali, India)** with real-time and fast transcription support. I saw no bn-BD row in the search excerpts (not conclusive). — [MS Learn language support (STT)](https://learn.microsoft.com/en-gb/azure/ai-services/speech-service/language-support?tabs=stt)
- F0 includes **5 audio hours per month** of standard STT. — [Azure Speech pricing](https://azure.microsoft.com/en-au/pricing/details/cognitive-services/speech-services/)

**ElevenLabs Scribe**
- ElevenLabs' own Bengali page claims a low Bengali WER, but the two versions of the page conflict: one says 8.1% FLEURS and 4.5% Common Voice, the other says 3.1% FLEURS and 5.5% Common Voice. — [ElevenLabs Bengali STT](https://elevenlabs.io/speech-to-text/bengali)
- Competitor benchmarks: Convozen (Feb 2026) puts Scribe v2 at **30.39% WER** on a 1.05-hour combined Bengali set, behind Akshara (17.96%) and Sarvam Saaras v3 (22.09%). Soniox reports 1.25% (Soniox) vs 3.16% (ElevenLabs) on its Bengali streaming test. Both are vendors with a stake in the result. — [Convozen](https://convozen.ai/products/bengali-speech-to-text); [Soniox vs ElevenLabs](https://soniox.com/compare-stt/soniox-vs-elevenlabs/bengali)
- Artificial Analysis ranks Scribe v2 first overall at 2.3% WER. This is a cross-language score, not Bengali-specific. — [Artificial Analysis](https://artificialanalysis.ai/speech-to-text/models/elevenlabs-scribe-v2)

**Gemini Live / audio understanding**
- The Vertex AI Live API (`gemini-live-2.5-flash-native-audio`, GA) lists **bn-BD** among its 24 supported languages. — [Vertex Live API configure language](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/live-api/configure-language-voice); [2.5 Flash Live API](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/2-5-flash-live-api)
- Google's OpenAI-compatibility docs show audio input sent as an `input_audio` (base64 WAV) content part with a "Transcribe this audio" prompt. — [Vertex OpenAI compat (ko)](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/start/openai?hl=ko)

### Inferences
- A 30-minute demo has about 15 minutes of caller speech, or about 900 audio seconds. Even with the 10-second minimum on about 60 turns (≥600 s billed), that is far below Groq's 7,200 ASH. The 20 RPM cap is also fine for one live call.
- Google Chirp 3 bn-BD supporting batch only rules it out as a streaming STT for a live demo. Per-turn synchronous or batch calls add latency. Check whether `Recognize` (sync) works for bn-BD before relying on it.
- Azure bn-IN STT will probably transcribe Bangladeshi speech reasonably well, since the script and most vocabulary are the same, but vocabulary such as Dhaka place names and BD terms for medicines may be less accurate.
- Gemini multimodal transcription (sending audio to the LLM) could merge STT and LLM into one call, which is attractive for code-switched Bangla and English.

### Gaps
- Google Cloud STT V2 free tier: no source found. I recall 60 minutes per month free (UNVERIFIED), and it may not apply to Chirp models.
- Deepgram Nova-3 Bengali: no source found confirming support. Treat it as unsupported until checked on Deepgram's language page.
- ElevenLabs free-plan quota for Scribe: not found.
- Whisper large-v3 / turbo WER on Bangladeshi Bangla: no independent figure found this session.
- Latency (RTF / time to first token) for Groq Whisper and the others: not found.

---

## LLM: free dialogue-model tiers (Gemini, Groq, OpenRouter, Cerebras)

### Takeaway
The Gemini API free tier is the strongest free option for Bangla dialogue and has an OpenAI-compatible endpoint, but its daily caps have been cut repeatedly and vary by project (reports range from 20 to 250 RPD for 2.5 Flash). Free-tier prompts may be used for training and read by human reviewers. Groq's free tier (llama-3.3-70b, gpt-oss-120b; about 30 RPM and 1,000 RPD) is fast and fine for a 30-minute demo. OpenRouter's free models have tight limits (50 RPD without a purchase). Cerebras no longer has an open free tier.

### Cited Findings
**Gemini API**
- Free-tier limits for gemini-2.5-flash conflict across sources. One January 2026 guide says **10 RPM, 250K TPM, 250 RPD**, cut from about 1,500 RPD in December 2025. Developer forum posts report hitting limits at **about 20 RPD**, plus quotas that do not reset. A May 2026 guide says the "20 RPD" figure is a project-level snapshot. — [YingTu guide](https://yingtu.ai/en/blog/google-gemini-api-free-tier); [Google AI dev forum](https://discuss.ai.google.dev/t/limits-on-gemini-api-free-tier-not-resetting/135026); [laozhang blog](https://blog.laozhang.ai/en/posts/gemini-api-free-tier)
- **Data use:** under the Gemini API Additional Terms, for **unpaid services** (AI Studio and free API quota), Google uses submitted content and responses "to provide, improve, and develop Google products and services and machine learning technologies". **Human reviewers may read, annotate, and process** inputs and outputs, after Google disconnects the data from the account. Paid-tier data is not used for product improvement and falls under the DPA. In the **EEA, Switzerland and the UK**, the paid-service data terms apply even to free use. — [Gemini API terms](https://ai.google.dev/gemini-api/terms); [terms preview](https://ai.google.dev/gemini-api/terms_preview); [archive 11/20/25](https://ai.google.dev/gemini-api/terms-archive/terms_11_20_25)
- OpenAI compatibility: Google's docs show `response_format` with a Pydantic model returning structured JSON (Vertex example), and audio input via `input_audio`. — [Vertex OpenAI compat](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/start/openai?hl=ja)

**Groq**
- Free tier, third-party sources: **llama-3.3-70b-versatile about 30 RPM, 1,000 RPD, 12,000 TPM, 100,000 TPD**. **openai/gpt-oss-120b 30 RPM, 8,000 TPM, 1,000 RPD**. Limits apply per organization, not per key. — [eesel.ai](https://eesel.ai/blog/groq-pricing); [fast.io](https://fast.io/resources/groq-rate-limit/); [localaimaster](https://localaimaster.com/blog/groq-api-free-guide)

**OpenRouter**
- Free (`:free`) models: **20 requests per minute**. **50 requests per day** if the account has never bought credits; **1,000 per day** after a lifetime purchase of $10 or more. A negative balance returns 402 even on free models, and failed requests may count against the daily cap. — [TrueFoundry](https://www.truefoundry.com/de/blog/openrouter-rate-limits-your-free-tier-depends-on-what-youve-already-paid); [developersdigest](https://www.developersdigest.tech/rate-limits/openrouter)

**Cerebras**
- The old open free tier (about 1M tokens per day, no card) ended around July 21, 2026. It was replaced by a one-time **$5 trial credit** that requires a payment method and expires after 30 days, with reported limits of 5 RPM, 90K TPM and 1M tokens per day. In October 2026 the trial and Developer tiers reportedly merged into pay-as-you-go with a $5 starter credit. — [usagepricing](https://www.usagepricing.com/blueprint/activity/cerebras-2026-07-21-free-tier-credit-trial); [MorphLLM Cerebras](https://www.morphllm.com/cerebras-pricing); [agentdeals](https://agentdeals.dev/vendor/cerebras)

### Inferences
- A 30-minute demo needs about 60–90 LLM calls. At about 1.5k input and 150 output tokens each, that is about 100–150k tokens. That exceeds Groq llama-3.3-70b's 100K TPD (an aggregator figure) if prompts are long, so trim the system prompt or rotate models. It fits within 1,000 RPD. The 12K TPM cap allows about 8 calls per minute at 1.5k tokens each, which is enough for one call.
- If the Gemini free tier on the day is really 20–250 RPD, 60–90 calls could exhaust a 20-RPD project. Have a paid key, or Groq, as the fallback.
- Bangla quality ranking (inference, not benchmarked this session): Gemini 2.5/3 Flash > gpt-oss-120b ≈ Llama 3.3 70B. Llama and gpt-oss tend to produce more stilted or romanized Bangla. Test with real prompts.
- Medical data: because the Gemini free tier allows training use and human review, use only synthetic patients and no real PHI in demos. Bangladesh is not in the EEA, so the protective EEA terms do not apply.

### Gaps
- The official Gemini rate-limit table for current models (Gemini 3 / 3.1 Flash, 2.5 Flash-Lite, TTS, Live) was not readable because ai.google.dev was blocked. No verified current figures.
- Whether the Gemini API, including its free tier, is available in Bangladesh: no source found this session.
- Exact JSON mode or `json_schema` behavior on `generativelanguage.googleapis.com/v1beta/openai/`: not confirmed from official Gemini API docs (only the Vertex equivalent).
- Groq, OpenRouter and Cerebras data-retention and training terms: not checked. Groq's official model list (whether Qwen or Llama 4 are still on the free tier): not verified.
- Independent Bangla benchmarks for these LLMs: none found.

---

## Best free combination and the limits that matter for a 30-minute live demo

### Takeaway
The recommended free stack: **Groq whisper-large-v3-turbo (STT) + Gemini Flash free tier, with Groq llama-3.3-70b / gpt-oss-120b as backup (LLM) + Azure F0 bn-BD-NabanitaNeural / PradeepNeural (TTS)**. As an alternative "most natural" path, use Gemini TTS bn-BD, or the Gemini Live native-audio model (bn-BD listed) if free access is confirmed. Every component fits a 30-minute demo within its quota. The real risks are Gemini's shrinking and unreliable daily caps, Azure F0 throttling, and the commercial-use and data-training terms of free tiers.

### Cited Findings
- Azure F0: 0.5M neural TTS characters per month and 5 STT hours per month; throttled at the limit; free-tier output reportedly has no commercial rights. — [Azure pricing](https://azure.microsoft.com/en-au/pricing/details/cognitive-services/speech-services/); [MS Q&A](https://learn.microsoft.com/en-us/answers/questions/5805156/please-clarify-the-conflicting-information-regardi)
- Groq Whisper turbo: 20 RPM, 2,000 RPD, 7,200 ASH, 28,800 ASD. — [Groq rate limits](https://console.groq.com/docs/rate-limits.md)
- bn-BD is explicitly supported by Azure TTS (Nabanita/Pradeep), Gemini TTS, the Gemini Live API and Google Chirp 3 STT (preview, batch). — sources above.
- Gemini free-tier data can be used for training and human review. — [Gemini API terms](https://ai.google.dev/gemini-api/terms)

### Inferences
- Limits that bind in a 30-minute demo: (1) Gemini free RPD (possibly as low as 20), the most likely to fail; (2) Groq TPD (about 100K) if the system prompt is large; (3) Groq Whisper 20 RPM, which is fine for one caller but breaks with parallel testing; (4) Azure F0 TTS transactions per minute (unverified figure). Run rehearsals on a different project or key from the live demo, so the rehearsals do not use up the demo key's daily quota.
- Latency budget (estimates, unmeasured): Groq Whisper about 0.3–1 s per turn, Groq LLM sub-second, Azure TTS streaming first audio around a few hundred ms. That is likely under 2 s per turn end to end. Gemini 2.5 Flash adds more latency than Groq.
- For a medical receptionist demo: use only synthetic patient data. No real patient audio or PHI should go through any free tier (Gemini free allows training and human review; Azure, Groq and OpenRouter free terms are unverified).

### Gaps
- No measured latency figures were found for any provider.
- No source was found on Bangladesh-specific restrictions (service availability or export) for Azure, Groq, ElevenLabs or Gemini.
- No source found on whether a client demo counts as "commercial use" under the Azure F0 or ElevenLabs Free terms. A cautious reading is to treat it as commercial.
