# Open-weight LLMs for Bangla + English clinic receptionist dialogue on a 12 GB GPU (as of Nov 2026)

Research method note: this session could only use web search. Direct fetches of huggingface.co, ollama.com and ai.google.dev failed (those hosts are not in the session's allowed network list), so model-card numbers below come from search snippets, mirrors and third-party pages. Anything taken from those sources is marked. Items marked "[training knowledge, unverified]" come from the researcher's background knowledge (cutoff mid-2026) and were not re-checked this session.

Project context, from the repo's own files:
- The project's LLM bench (2026-10-31) measured: gemma2:9b 12/12 valid JSON, 12/12 right tool, 11/12 right args, 95.1% Bangla purity, median 1.04 s / p95 2.05 s, 7,238 MiB; qwen2.5:7b 9/12 tool, 98.2% purity, 4,878 MiB; aya-expanse:8b 6/12 tool, 80.3% purity, 6,014 MiB; TigerLLM-9B-it Q4_K_M 9/12 tool, 74.5% purity, 9,996 MiB; gemma-3-12b-it Q4_K_M 11/12 tool, 99.6% purity, 0.9 s / 2.5 s, 10.3 GB; Qwen3-8B with thinking on 10/12 tool, 7% purity, 4.4 s median — [docs/model-selection.md](../../docs/model-selection.md), [docs/history/bench-llm-2026-10-31.json](../../docs/history/bench-llm-2026-10-31.json)
- **Discrepancy to flag:** that bench doc says it ran on an "RTX 4060 Ti 16 GB", but the brief assumes a 12 GB card. (The RTX 4060 Ti comes in 8 GB and 16 GB versions; "12 GB" points to a different card, such as an RTX 3060 12 GB or RTX 4070 [training knowledge, unverified].) The VRAM figures were measured with plenty of free memory, so Ollama may have chosen a larger context or kept the vision projector loaded. On a real 12 GB card they need re-measuring — [docs/model-selection.md](../../docs/model-selection.md)
- The same doc says "a no-think run [of Qwen3] is untested" and Gemma 3 12B was "worth re-testing on more cases before switching" — [docs/model-selection.md](../../docs/model-selection.md)

## Which 2025-2026 open models have the best Bangla generation quality at <=9B params / <=8 GB quantized?

### Takeaway
No published benchmark ranks the current small models (Gemma 4 E4B, Qwen3.5-9B, Gemma 3 4B/12B) against each other on Bangla *generation*. Bangla benchmarks that cover these generations test larger models (Qwen3-32B, Gemma-3-27B) or older ones (Gemma-2, Llama-3.1). The two strongest new candidates are **Gemma 4 E4B** (Apache 2.0, April 2026, pretrained on 140+ languages, about 5.3 GB at Q4_K_M) and **Qwen3.5-9B** (Apache 2.0, March 2026, 201 languages, thinking off by default on small sizes). Neither has been tested in the project. Bangla-specific fine-tunes (TigerLLM, TituLLM) and Indic models (Sarvam, Krutrim) either lack instruction and tool skills or are too large. The project's own measurements are still the best evidence: Gemma 3 12B had the cleanest Bangla, and gemma2:9b the best tool routing.

### Cited Findings
**Gemma 4 (new since the Oct 2026 bench list; replaces the "any Gemma 4?" question)**
- Gemma 4 came out around 1-2 April 2026 in four sizes: E2B, E4B (effective 2B/4B), a 26B Mixture-of-Experts (26B A4B) and a 31B dense model. One outlier site lists a 12B size; the other sources do not, so treat a "Gemma 4 12B" as unconfirmed — [The Register](https://www.theregister.com/2026/04/02/googles_gemma_4_open_weights/); [AlternativeTo](https://alternativeto.net/news/2026/4/google-releases-gemma-4-open-weight-ai-models-with-apache-2-0-license); [theairankings (outlier, 12B claim)](https://theairankings.com/google/gemma-4/)
- Gemma 4 is released under **Apache 2.0**, the first Gemma family under an OSI licence. Gemma 2 and Gemma 3 used Google's own Gemma Terms — [AlternativeTo](https://alternativeto.net/news/2026/4/google-releases-gemma-4-open-weight-ai-models-with-apache-2-0-license); [Daily AI News](https://dailyainews.manus.space/article/google-s-gemma-4-is-now-available-with-apache-20-licensing-for-the-first-time-mni3izlw)
- Gemma 4 covers 140+ languages, with context up to 256K. The 31B ranked 3rd and the 26B MoE 6th among open models on the Arena text leaderboard at launch — [Geo TV](https://www.geo.tv/latest/658294-google-launches-gemma-4-open-models-with-140-languages-400m-downloads); [Google Blog via search summary](https://pixelmind-ai-delta.vercel.app/news/google-gemma-4-open-source-models-2026)
- From mirrored copies of the Gemma 4 model card (unverified, and column alignment uncertain): MMMLU is 76.6% for E4B and 67.4% for E2B, against 88.4% / 86.3% for the larger models. The card says "out-of-the-box support for 35+ languages, pre-trained on 140+ languages". E4B scores 42.2% on Tau2 (agentic) vs 68.2% for 26B A4B — [HF mirror alekshandru/gemma-4-E4B](https://huggingface.co/alekshandru/gemma-4-E4B); [HF mirror Iambackup/gemma-4-E4B-it](https://huggingface.co/Iambackup/gemma-4-E4B-it)

**Qwen3.5**
- Qwen3.5 was released 1 March 2026. The small series is 0.8B, 2B, 4B and 9B, plus Base versions. Ollama tags `qwen3.5:9b`, `qwen3.5:4b`, etc. exist according to third-party guides (not checked on ollama.com). A Toolhalla article listing `qwen3.5:8b` / `qwen3.5:14b` contradicts the official lineup and looks wrong — [DEV Community](https://dev.to/preecha/how-to-use-qwen-35-with-ollama-20a0); [Product Hunt](https://www.producthunt.com/p/qwen3/qwen3-5-small); [Toolhalla (conflicting)](https://toolhalla.ai/blog/qwen-3-5-small-best-llm-for-phone-2026)
- **Thinking mode is disabled by default on the Qwen3.5 small models (0.8B-9B)**. This directly addresses the Qwen3-8B English-leak failure in the project bench — [Emelia review](https://emelia.io/hub/qwen-35-9b-review)
- Third-party hosts list Qwen3.5-9B at 201 languages and dialects, 262K context, tool calling and multi-token prediction. They report MMMLU 81.2 and MMLU-ProX 76.3, not verified against Qwen's card — [DeepInfra](https://deepinfra.com/Qwen/Qwen3.5-9B); [Featherless](https://featherless.ai/models/unsloth/Qwen3.5-9B)

**Bangla benchmarks that exist (2025-2026)**
- **BnMMLU** (Findings of ACL 2026; arXiv 2505.18951) has 134,375 question-option pairs across 41 domains and tests 24 model variants from 11 families — [ACL Anthology](https://preview.aclanthology.org/ingest-acl/2026.findings-acl.593/); [GitHub samanjoy2/bnmmlu](https://github.com/samanjoy2/bnmmlu)
  - v1 (2025): Gemini 2.0 Flash 75.80%, GPT-4o 69.38%, Llama 3.3-70B 59.30%, Gemma 2-27B 53.45% — [arXiv 2505.18951](https://arxiv.org/abs/2505.18951v1)
  - v2 (2026), 0-shot direct: Qwen3-32B about 65.34 and Gemma-3-27B-IT about 61.27 (Gemini 2.5 Flash 69.85). The snippet's table headers were garbled, so these numbers are approximate — [arXiv 2505.18951v2](https://arxiv.org/html/2505.18951v2)
  - No <=12B Gemma 3 / Gemma 4 / Qwen3.5 rows were visible in the snippets.
- **TigerLLM** (ACL 2025 Main, short paper) is a 9B model built on Gemma-2. It reports about 72 on MMLU-bn vs about 35 for Gemma 2 27B and 55 for GPT-3.5, and claims it beats all open-source alternatives — [arXiv 2503.10995](https://arxiv.org/html/2503.10995v3); [emergentmind summary](https://www.emergentmind.com/topics/tigerllm)
  - The HF card for the 9B mirror says "These are not the final checkpoints for the 9B model. Contact us if you need them." — [HF dipta007/TigerLLM-9B-it](https://huggingface.co/dipta007/TigerLLM-9B-it)
  - The TigerLLM paper says titu-Gemma continual pretraining and distillation efforts "have yielded low and non-reproducible results, often performing worse than their base models" — [ACL 2025 short.69](https://preview.aclanthology.org/landing_page/2025.acl-short.69.pdf)
- **TituLLMs** (Hishab, arXiv 2502.11187) are 1B and 3B models adapted from Llama 3.2 on about 37B tokens, with five Bangla benchmarks (Bangla MMLU, CSQA, OBQA, PIQA, ...). The 3B beats Llama-3.2-3B and Qwen-2.5-1.5B on commonsense but lags on knowledge and long-context tasks. Llama-3.2-3B scores about 0.33-0.34 on Bangla MMLU. Per a secondary summary, the extended tokenizer cuts Bangla tokens-per-word from 7.84 to 1.90 — [arXiv 2502.11187](https://web3.arxiv.org/abs/2502.11187); [Moonlight review](https://themoonlight.io/review/titullms-a-family-of-bangla-llms-with-comprehensive-benchmarking)
- **BenHalluEval** (arXiv 2605.31483, 2026) tests Bengali hallucination on Gemma-2-27B, Llama-3.1-8B, Qwen2.5-32B and TigerLLM-9B. Results vary by task, and no current small model is included — [arXiv 2605.31483](https://arxiv.org/pdf/2605.31483)
- The BengaliAI bn-llm-benchmark (2025) finds that models perform worse when Bangla input is over-tokenized, so tokenizer efficiency matters — [newx summary](https://newx.sg/paper/detail/a7380c10-f823-11f0-b84c-00163e10baa7)
- Gemma-3 12B scores lower on Bangla than English on BanglaMedVQA (a medical VQA benchmark) — [benchmarklist Gemma-3 12B Bangla](https://benchmarklist.com/models/gemma-3-12b-bangla-zero-shot/)
- Artificial Analysis runs a Bengali multilingual leaderboard page. Its content was not retrieved — [Artificial Analysis Bengali](https://artificialanalysis.ai/models/multilingual/bengali)

**Indic models**
- Sarvam-1 is a 2B model covering Bengali plus nine other Indic languages and English, with tokenizer fertility of 1.4-2.1. Its licence is disputed: the HF card says Sarvam non-commercial, while India's AIKosh lists CC BY-SA 4.0 — [HF sarvamai/sarvam-1](https://huggingface.co/sarvamai/sarvam-1); [AIKosh](https://aikosh.indiaai.gov.in/home/models/details/sarvam1.html); [Sarvam blog](https://www.sarvam.ai/blogs/sarvam-1)
- Sarvam-M is a 24B hybrid-reasoning model built on Mistral-Small. AIKosh lists it as Apache 2.0. It leads Sarvam's MMLU-IN / ARC-C-IN / MILU tests (secondary blog), but no Bengali-specific number was found — [AIKosh Sarvam-M](https://aikosh.indiaai.gov.in/home/models/details/sarvamm.html); [blog summary](https://amanchhetry.bearblog.dev/sarvam-ai/)

### Inferences
- **Gemma 4 E4B is the most important untested candidate.** It is the Gemma-line successor at a size that leaves a lot of VRAM headroom. Its licence is now Apache 2.0, which removes the Gemma Terms concern noted in model-selection.md. The project's numbers show each Gemma generation improving Bangla purity (gemma2 95% to gemma3-12B 99.6%). But E4B is an "effective 4B" model, and its MMMLU (about 76.6) is well below the larger Gemma 4 models. It could match gemma2:9b on purity and still lose on tool routing (Tau2 42% is weak). It has to be benchmarked.
- **Qwen3.5-9B with thinking off** should fix the 7%-purity failure, since that failure came from thinking mode. Qwen models historically trail Gemma on Bangla fluency (qwen2.5:7b: 98% purity but 9/12 tools in the project bench), so expect a strong tool caller with less natural Bangla. This is an inference, not measured.
- Aya Expanse's low score is expected. Its 23 supported languages include Hindi but not Bengali, and its licence is CC-BY-NC 4.0, which rules it out for a commercial clinic product [training knowledge, unverified].
- Llama 3.1/3.2 officially support 8 languages, Bengali not among them, under the Llama Community Licence (700M-MAU clause plus acceptable-use policy). Llama 4 Scout/Maverick are 109B/400B-total MoEs and cannot fit in 8 GB [training knowledge, unverified]. Llama is not a fit.
- Sarvam-1 is a 2B base model, not a chat or tool model, and Sarvam-M (24B) needs about 13-14 GB at Q4. Neither fits the role. Krutrim-2 (about 12B, Mistral-NeMo based, Krutrim community licence) would need about 7-8 GB at Q4 but has no tool-calling evidence [training knowledge, unverified].
- TigerLLM and TituLLM are not usable as tool-calling receptionists: no published final 9B checkpoint, 75% purity in the project bench, and TituLLM is only 1-3B. BanglaLLaMA / BongLLaMA are older Llama-2/3 fine-tunes with no 2025-26 evaluations found.
- Phi-4-mini and Ministral 3 (3B/8B/14B, Apache 2.0, reportedly Dec 2025) are multilingual, but no Bangla evidence was found. They are low priority [training knowledge, unverified].

### Gaps
- No head-to-head Bangla *generation* or human-naturalness evaluation (register, politeness, Bangladeshi vs Kolkata style) for any <=12B 2025-26 model was found. IndicGenBench, MILU, BenNumEval and BanglaBench results for Gemma 4 / Qwen3.5 were not found in the time available.
- BnMMLU v2 small-model rows (Gemma-3-4B/12B, Qwen3-8B, etc.) were not visible in snippets. Read Table 2 of arXiv 2505.18951v2 directly.
- Gemma 4 E4B official multilingual numbers were not checked on Google's model card (host blocked).
- Whether Gemma 3n (E2B/E4B, mid-2025) does better than Gemma 4 E4B on Bangla is unknown.

## Tool/JSON calling reliability, Ollama availability, and quantization impact on Bangla

### Takeaway
Grammar-constrained decoding makes JSON *validity* a non-issue for any model: every model in the project bench hit 12/12 or 11/12 valid. What separates models is choosing the *right tool and args*, which only a local bench can measure. Gemma 4 and Qwen3.5 both advertise native tool use, and Qwen3.5-9B has public BFCL/TAU2 numbers. No source quantifies how 4-bit quantization affects Bangla specifically.

### Cited Findings
- Qwen3.5-9B scores BFCL-V4 66.1 and TAU2-Bench 79.1 (host-reported). DeepInfra's card shows serving with a tool-call parser — [DeepInfra](https://deepinfra.com/Qwen/Qwen3.5-9B); [Featherless](https://featherless.ai/models/hamishivi/Qwen3.5-9B)
- The Gemma 4 card (mirror) lists "native support for structured tool use, enabling agentic workflows". E4B scores Tau2 42.2% vs 68.2% for 26B A4B — [HF mirror](https://huggingface.co/alekshandru/gemma-4-E4B)
- Gemma 4 benchmark figures are reported with thinking mode enabled. An Ollama registry page for a 26B Gemma 4 variant lists "vision tools thinking audio" capabilities — [cheatsheets.zip](https://cheatsheets.zip/gemma4); [Ollama registry blob](https://registry.ollama.ai/huihui_ai/gemma-4-abliterated:26b-qat/blobs/4b4f9d4b448f)
- `ollama pull gemma4:e4b` is the edge-4B tag according to a cheat sheet (not checked on ollama.com) — [cheatsheets.zip](https://cheatsheets.zip/gemma4)
- Project bench: JSON valid 12/12 for every model except Qwen3-8B with thinking (11/12). Tool accuracy ranged 6/12 to 12/12. The harness also found that `parse_action` used to reject JSON wrapped in Markdown fences — [docs/model-selection.md](../../docs/model-selection.md)
- Gemma 3 QAT (April 2025) shrinks the 12B from 24 GB (bf16) to 6.6 GB (int4) while keeping quality close to bf16. QAT tags such as `gemma3:12b-it-qat` exist in Ollama — [Simon Willison](https://simonwillison.net/2025/Apr/19/gemma-3-qat-models/)

### Inferences
- Use the server's schema-constrained mode (Ollama `format: <JSON schema>`, llama.cpp `json_schema`/GBNF, vLLM guided decoding) rather than free-form tool calling. Put the spoken reply inside the action object, for example `{"tool": "...", "args": {...}, "say": "..."}`. This avoids two round-trips and makes validity grammar-guaranteed. These features exist in all three servers [training knowledge, unverified; Ollama structured outputs date from v0.5, Dec 2024].
- Keep thinking **off** for every candidate. With Gemma 4 and Qwen3.5 this means explicitly disabling it (Ollama `think: false`, or the chat-template flag `enable_thinking=False` for Qwen). Thinking costs seconds and, as the bench showed, leaks English into replies.
- Quantization: Bangla is token-hungry (TituLLM's 7.84 tokens/word on a Llama tokenizer). Low-resource languages are generally assumed to degrade more under aggressive quantization, but no Bangla-specific measurement was found. Prefer QAT int4 checkpoints (Gemma 3 QAT, and Gemma 4 QAT if Google ships them for E4B) or Q4_K_M/Q5_K_M over Q3/IQ quants. Measure purity at each quant level.

### Gaps
- No public tool-calling benchmark results in Bangla (BFCL-style) were found for any model.
- No study of Bangla quality vs quantization level (Q4 vs Q5 vs Q8) was found.
- Gemma 4 E4B BFCL score not found.

## Realistic VRAM budget (Q4_K_M + ~4k-context KV cache); does gemma3:12b QAT fit beside 1.6 GB ASR in 12 GB?

### Takeaway
Gemma 4 E4B (about 5.3 GB file) and Qwen3.5-9B (about 6 GB, estimated) fit comfortably. gemma2:9b (7.2 GB measured) fits. **Gemma 3 12B fits in 12 GB only in a stripped-down setup**: QAT Q4_0 text-only weights (about 6.6 GB) with no vision projector, a 4k context, flash attention, q8_0 KV cache, and the TTS running on CPU. The project's measured 10.3 GB setup plus 1.6 GB ASR is about 11.9 GB, which does not fit with CUDA contexts and desktop overhead.

### Cited Findings
- `gemma3:12b-it-qat` is an 8.9 GB Ollama download. Google gives the 12B int4 weights as 6.6 GB. A third-party calculator estimates about 8.4 GB VRAM at Q4_K_M and recommends 11+ GB for headroom — [Simon Willison](https://simonwillison.net/2025/Apr/19/gemma-3-qat-models/); [Novita](https://blogs.novita.ai/gemma-3-12b-it-vram-can-your-gpu-handle-it/)
- For the 27B QAT tag, Ollama used about 22 GB at runtime vs a much smaller file, so runtime overhead is substantial — [Simon Willison](https://simonwillison.net/2025/Apr/19/gemma-3-qat-models/)
- Gemma 4 E4B Q4_K_M GGUF is 5.3-5.34 GB. Another site gives about 4.6 GB VRAM at Q4_K_M — [HF AlexAtomic/gemma4-e4b-it-GGUF](https://huggingface.co/AlexAtomic/gemma4-e4b-it-GGUF); [HF prithivMLmods/gemma-4-E4B-it-GGUF](https://huggingface.co/prithivMLmods/gemma-4-E4B-it-GGUF); [canirun.ai](https://canirun.ai/model/gemma4-e4b-it/)
- The Gemma 4 26B A4B variant is about 17 GB, too big — [Ollama registry blob](https://registry.ollama.ai/huihui_ai/gemma-4-abliterated:26b-qat/blobs/4b4f9d4b448f)
- Project measurements: gemma2:9b 7,238 MiB; qwen2.5:7b 4,878 MiB; aya-expanse:8b 6,014 MiB; Qwen3-8B Q4_K_M 5.3 GB; gemma-3-12b Q4_K_M 10.3 GB; TigerLLM-9B Q4_K_M 9,996 MiB. ASR (OmiKhan whisper-medium, CTranslate2) is 1.6 GB — [docs/model-selection.md](../../docs/model-selection.md)

### Inferences
KV-cache arithmetic below uses architecture figures from training knowledge [unverified]: KV bytes per token = 2 × layers × KV heads × head_dim × bytes per element.
- **Gemma 2 9B** (42 layers, 8 KV heads, head_dim 256): about 344 KB/token at fp16, so about 1.4 GB at 4k. That fits the measured 7.2 GB: about 5.4 GB Q4_0 weights + 1.4 GB KV + buffers.
- **Gemma 3 12B** (48 layers, 8 KV heads, head_dim 256, 5:1 local:global with a 1,024-token sliding window): about 1.6 GB at 4k without SWA-aware caching. With SWA caching (recent llama.cpp/Ollama) it is about 0.6 GB, and about 0.3 GB with q8_0 KV.
  - Budget: 6.6 GB QAT weights + about 0.3-0.6 GB KV + about 0.5 GB compute buffers + about 0.3 GB CUDA context gives **about 7.7-8.0 GB**. Leaving out the about 0.8 GB SigLIP vision projector is what brings it under 8.9 GB.
  - With ASR at 1.6 GB plus its own CUDA context (about 0.3 GB), the total is **about 9.6-10 GB of 12 GB**. That is feasible but tight, and an OS desktop on the same GPU takes another 0.3-1 GB.
  - The 10.3 GB measured in the project probably included the vision projector and/or a larger default context. Re-measure with `num_ctx 4096`, `OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_KV_CACHE_TYPE=q8_0`, and a text-only GGUF.
- **Gemma 4 E4B**: about 5.3 GB weights. E-models keep per-layer embeddings that can be offloaded, so the VRAM-resident footprint may be smaller. Total with KV is likely about 6-6.5 GB, which leaves about 3 GB spare [inference].
- **Qwen3.5-9B**: Q4_K_M about 5.5-6 GB (estimated from param count). If, as reported for the Qwen3.5 family, most layers use linear attention (Gated DeltaNet), the 4k KV cache is small [training knowledge, unverified].
- **Latency**: first token in under 1 s is realistic for all of the above on a 4060-Ti-class card. gemma2:9b's *full-reply* median is already 1.0 s. Keep prompts short and cache the system prompt (Ollama keep_alive; llama.cpp/vLLM prefix caching), because a long Bangla system prompt is expensive in tokens.

### Gaps
- No measured VRAM for gemma3:12b-it-qat text-only at 4k ctx on a 12 GB card. This needs a local `ollama ps` / `nvidia-smi` check.
- Official Gemma 4 E4B and Qwen3.5-9B Ollama tag sizes were not checked (ollama.com blocked).
- TTS VRAM is not given in the brief. Piper is CPU/ONNX-friendly; if a GPU TTS is adopted, the budget changes.

## Prompting techniques for natural spoken Bangla (register, short sentences, numbers as words, time/date)

### Takeaway
No published, sourced guidance for prompting LLMs into *Bangladeshi spoken* register was found. The techniques below are practitioner inference and should be validated with native Bangladeshi listeners. The project's purity metric and a "Kolkata-marker" lexical check can automate part of that.

### Cited Findings
- Tokenizer fertility drives Bangla cost and quality: 7.84 tokens/word on a Llama tokenizer vs 1.90 after extension (secondary summary). Over-tokenized inputs score worse — [Moonlight TituLLMs review](https://themoonlight.io/review/titullms-a-family-of-bangla-llms-with-comprehensive-benchmarking); [newx bn-llm-benchmark summary](https://newx.sg/paper/detail/a7380c10-f823-11f0-b84c-00163e10baa7)
- Piper bn_BD-google-medium is the project's TTS. Round-trip WER is 14.6%, but "nobody on the team has yet listened to the TTS output" — [docs/model-selection.md](../../docs/model-selection.md)

### Inferences (unsourced; native-speaker review needed)
- **Write the system prompt in Bangla**, with a short English section for routing rules. Give 3-5 few-shot turns in the exact target register, and match the reply language to the caller's last utterance (an explicit rule: "If the caller speaks English, reply only in English").
- **Register:** use the polite "আপনি" form and "জি" for yes, and avoid "তুমি".
- **Bangladeshi vs Kolkata markers:** list the preferred forms explicitly in the prompt.
  - Bangladeshi forms to prefer: "পানি" (not "জল"), "গোসল" (not "স্নান"), "চারটা" (not Kolkata "চারটে"), "আসবেন", "দাওয়াত".
  - A post-check can flag Kolkata markers (জল, -টে clock suffix, "করছি না তো" style) and Devanagari or Latin characters.
- **Short sentences:** one idea per sentence, at most about 2 sentences per turn, and a question at the end of the turn. Require the `say` field to be at most about 25 words.
- **Numbers as words for TTS:** have the LLM output words, not digits.
  - Times: "সকাল দশটা", "বিকেল সাড়ে চারটা", "পৌনে পাঁচটা".
  - Dates: "বারো নভেম্বর, বুধবার".
  - Phone numbers digit by digit: "শূন্য এক সাত ...".
  - Better still, have the LLM emit structured values (ISO date/time in `args`) and render the Bangla words *deterministically in code*. Do not trust the LLM to spell numbers correctly.
- **Doctor names and English medical terms:** allow a short allowlist (for example "ডাক্তার", "রিপোর্ট", "আল্ট্রাসনোগ্রাম" are normal in Bangladeshi speech, written in Bangla script). Ask for Bangla-script transliteration, never Latin script, and exclude allowlisted names from the purity check.
- **Purity guard:** if the `say` text has more than X% non-Bengali-script characters, regenerate once (temperature 0.3-0.5) or fall back to a templated reply.

### Gaps
- No academic or industry source found on Bangladeshi-register control for LLMs, or on human evaluations of Bangladeshi vs West Bengal style in LLM output.
- No Bangla text-normalization reference (numbers to words) for Piper bn_BD was found this session.

## Concrete recommendation for a 12 GB GPU

### Takeaway
**Keep gemma2:9b as the production default for now.** It has the only measured 12/12 tool accuracy and 7.2 GB. Run one focused bench (same 12 router cases plus about 30 more, in both Bangla and English, on the actual 12 GB card) against three candidates:
- (1) `gemma4:e4b` with thinking off, as the likely future default (Apache 2.0, about 5-6 GB);
- (2) `qwen3.5:9b` with thinking off, as the best-documented tool caller (Apache 2.0, BFCL-V4 66.1);
- (3) `gemma3:12b-it-qat` text-only with a 4k ctx and q8_0 KV, the best measured Bangla purity, if it fits in about 8 GB.

Switch only if a candidate matches at least 11/12 tool accuracy, at least 98% purity, and under 1 s first token.

### Cited Findings
- gemma2:9b: 12/12 tool, 95% purity, 7.2 GB. gemma-3-12b: 11/12, 99.6%, 10.3 GB. Qwen3-8B thinking: 7% purity — [docs/model-selection.md](../../docs/model-selection.md)
- Gemma 4 is Apache 2.0, has native tool use, and E4B is about 5.3 GB at Q4_K_M — [AlternativeTo](https://alternativeto.net/news/2026/4/google-releases-gemma-4-open-weight-ai-models-with-apache-2-0-license); [HF mirror](https://huggingface.co/alekshandru/gemma-4-E4B); [HF GGUF](https://huggingface.co/AlexAtomic/gemma4-e4b-it-GGUF)
- Qwen3.5-9B: thinking off by default on small models, 201 languages, BFCL-V4 66.1 — [Emelia](https://emelia.io/hub/qwen-35-9b-review); [DeepInfra](https://deepinfra.com/Qwen/Qwen3.5-9B)
- Gemma 3 12B QAT weights are 6.6 GB; the Ollama tag is 8.9 GB — [Simon Willison](https://simonwillison.net/2025/Apr/19/gemma-3-qat-models/)

### Inferences
- **Licence ranking for a commercial clinic product:**
  - Apache 2.0: Gemma 4, Qwen3.5, Qwen3; and Sarvam-M per AIKosh.
  - Gemma Terms (custom with a prohibited-use policy; gemma2 and gemma3): acceptable but not OSI.
  - Llama Community Licence: acceptable but restrictive.
  - CC-BY-NC (Aya Expanse) and Sarvam-1's disputed non-commercial licence: avoid.
  - Moving to Gemma 4 would also remove the Gemma Terms caveat in model-selection.md.
- **Two-model fallback option:** run gemma4:e4b (or gemma2:9b) for routing plus the reply in one call. Escalate to a cloud model only for hard free-text turns. Note: an LLM handling patient calls in a clinic raises privacy/consent obligations whether it runs locally or in the cloud.
- **Gemma 4 E4B and E2B accept audio input** per the Ollama capability tags for the family. Bangla ASR quality for that path is unknown, and the measured OmiKhan Whisper fine-tune (16.5-22.7% WER) should stay [inference from capability tags; unverified for E4B].
- **Settings on a 12 GB card:** `num_ctx 4096`, flash attention on, q8_0 KV cache, `keep_alive -1` (never unload), a single model resident (no swapping), and the ASR loaded first so VRAM fragmentation is predictable. Make sure the display/desktop is not on the same GPU, or budget 0.5-1 GB for it.

### Gaps
- No independent verification that `gemma4:e4b` / `qwen3.5:9b` Ollama tags support schema-constrained `format` together with `think: false` without template issues. Test locally.
- Whether Google released QAT checkpoints for Gemma 4 E4B is unknown (the registry shows a 26B QAT community variant only).
