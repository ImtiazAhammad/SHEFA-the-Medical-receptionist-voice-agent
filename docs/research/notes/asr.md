# Locally runnable ASR for Bangla (Bangladesh) + English + code-switched Banglish (as of Nov 2026)

Research context: one 12 GB NVIDIA GPU shared with an LLM of about 7 GB and a TTS model, so the ASR budget is about 1.5-3 GB. Audio is telephone-band (8 kHz, noisy) or browser mic (16 kHz). The current baseline is `OmiKhan/bangla-asr-whisper-medium` converted to CTranslate2 and run with faster-whisper. The project measured it at about 16.5% WER on clean FLEURS bn and about 22.7% with phone simulation plus noise. Stock whisper large-v3 measured about 70% WER on Bengali.

Access note: huggingface.co and arxiv.org were blocked from this research session, so the WebFetch tool could not read those pages. Model-card facts were taken from GitHub READMEs (fetched directly), search-engine snippets and mirrors. Anything I could not confirm is marked "unverified".

## Q1. Best Bangla ASR models, their WER, VRAM, speed, streaming and licence

### Takeaway
The most rigorous current comparison is the community benchmark ehzawad/bengali-asr-benchmark (Oct 2026): 12 models, 11 test sets, NFC normalisation and bootstrap confidence intervals. On it, fine-tuned Whisper-turbo, Qwen3-ASR, Canary, Voxtral and FastConformer models all reach about 11.6-12.8% WER on FLEURS bn, but they are private and under a non-commercial licence. Among public models, `hishab/titu_stt_bn_conformer_large` (121M-parameter NeMo CTC model) has the best FLEURS WER at 10.83%, the best CER at 2.20%, and is about 3.5x faster than Whisper-medium. Its weakness is spontaneous and conversational speech (29-33% WER on IndicVoices and Vaani), where Whisper-style models do better. Its licence is unverified. Meta's Omnilingual ASR (Apache-2.0) has a CTC-300M/1B model that fits the VRAM budget, but the only Bengali number found is for the 7B model (2.8% CER).

### Cited Findings

**Main benchmark: ehzawad/bengali-asr-benchmark (decoded 13-23 Oct 2026, A100, greedy decoding, batch 1, no LM, audio resampled to 16 kHz, cut into chunks of 25 s or less at pauses)**
- Clips are removed if they are under 0.5 s or if the reference contains digits. 10,291 of 10,920 clips remain. Text is normalised by stripping punctuation and applying Unicode NFC. 95% CIs are reference-clustered bootstrap. — [ehzawad/bengali-asr-benchmark](https://github.com/ehzawad/bengali-asr-benchmark)
- **NFC normalisation matters a lot.** Without NFC, Whisper Medium's FLEURS WER goes from 16.2% to 27.9%, because য়/ড়/ঢ় can be stored precomposed or decomposed. The project should check that its own 16.5% and 22.7% figures used NFC. — [same](https://github.com/ehzawad/bengali-asr-benchmark)
- WER on cleaned sets, in %. Columns: FLEURS / Vaani / IndicVoices-conversational / SUBAK.KO (Bangladeshi standard) / BanSpeech (Bangladeshi broadcast) / CV17 / Ben-10 (Bangladeshi regional dialects). — [same](https://github.com/ehzawad/bengali-asr-benchmark)
  - `ehzawad/whisper-large-v3-turbo-bn-BD` (private, 809M): 12.39 / 21.38 / 12.99 / 8.60 / 20.08 / 9.59 / 62.21
  - `ehzawad/Qwen3-ASR-1.7B-bn-BD` (private, 2.0B): 11.86 / 22.68 / 11.91 / 7.16 / 19.37 / 9.88 / 63.39
  - `ehzawad/canary-1b-v2-bn-BD` (private, 957M): 11.58 / 21.92 / 12.65 / 5.57 / 21.19 / 9.51 / 76.42
  - `ehzawad/Voxtral-Mini-3B-2507-bn-BD` (private, 4.7B): 12.08 / 22.08 / 13.34 / 5.42 / 19.24 / 10.32 / 69.97
  - `ehzawad/fastconformer-hybrid-rnnt-ctc-large-bn-BD` (private, 115M): 12.83 / 22.53 / 12.63 / 8.35 / 22.03 / 10.51 / 60.91
  - `hishab/titu_stt_bn_conformer_large` (public, 121.5M, NeMo CTC): **10.83** / 33.10 / 29.30 / 7.85 / 25.44 / **7.35** / 63.54
  - `ehzawad/granite-speech-5.0-2b-bn-BD` (private, 2.3B): 13.49 / 22.52 / 14.04 / 6.23 / 22.91 / 10.99 / 69.39
  - `SayedShaun/bengali-whisper-medium` (public, 764M): 13.90 / 26.35 / 24.43 / 16.48 / 21.93 / 10.12 / 74.79
  - `ehzawad/stt_bn_fastconformer_ctc` (public, 115.6M, CC-BY-SA-4.0): 14.63 / 24.67 / 12.26 / 13.67 / 26.66 / 12.14 / 76.92
  - `SayedShaun/bangla-wave2vec2-unigram` (public, 315M): 18.25 / 31.28 / 32.72 / 21.55 / 31.33 / 16.70 / 80.50
- FLEURS CER (%): hishab Conformer Large 2.20, Canary-bn 2.68, Qwen3-ASR-bn 2.78, Voxtral-bn 2.83, FC-hybrid 2.98, Whisper Medium 3.17, Whisper-turbo-bn 3.19, Wav2Vec2 4.08. Average WER over 11 sets: Whisper-turbo-bn 21.9, Qwen3-bn 21.9, FC-hybrid 22.4, Voxtral-bn 22.8, Canary-bn 23.1, Granite-bn 23.6, hishab Conformer 25.5, ehzawad CTC 25.9, Whisper Medium 26.1, Wav2Vec2 33.2. — [same](https://github.com/ehzawad/bengali-asr-benchmark)
- Speed, as mean ms per FLEURS clip at batch 1 on an A100 for the full pipeline: Wav2Vec2 56, hishab Conformer 87, ehzawad CTC 88, FC-hybrid 102, Whisper Medium 304, Voxtral 438, Canary 485, Qwen3-ASR 656, Whisper-turbo 700, Granite 961. **The README reports no VRAM figures.** — [same](https://github.com/ehzawad/bengali-asr-benchmark)
- Licences: the private ‡ fine-tunes use the "ehzawad Non-Commercial Model License". Base-model licences: Voxtral Apache-2.0, Canary CC-BY-4.0, Qwen3-ASR Apache-2.0, Whisper turbo MIT, FastConformer CC-BY-4.0, Granite Apache-2.0. The public `ehzawad/stt_bn_fastconformer_ctc` is CC-BY-SA-4.0. Seven of the 11 test sets are Indian Bengali, and the suite has **no telephony and no long-form audio**. — [same](https://github.com/ehzawad/bengali-asr-benchmark); [PR #6, merged 14 Oct 2026](https://github.com/ehzawad/bengali-asr-benchmark/pull/6)
- Whether the "private" ‡ checkpoints can be downloaded at all is unclear. The README says readers cannot run them. — [same](https://github.com/ehzawad/bengali-asr-benchmark)

**Hishab models**
- `hishab/titu_stt_bn_conformer_large`: licence not found (HF blocked). The sibling `hishab/titu_stt_bn_fastconformer` is listed as **CC-BY-NC-4.0**, which suggests Hishab may use non-commercial terms. Verify before shipping. — [search result for HF discussions page](https://huggingface.co/hishab/titu_stt_bn_fastconformer/discussions)
- In long-form DL Sprint 4.0 (2026) evaluation, "HisabTitu-BN" performed poorly (50.67% WER) and the BengaliAI tugstugi Whisper-medium reached 34.07%. — [Bangla-WhisperDiar, arXiv 2605.08214](https://arxiv.org/html/2605.08214v1). This conflicts with Hishab's strong short-utterance FLEURS result above. The likely cause is long-form or segmentation behaviour of CTC models, but that is my inference.

**bengaliAI/tugstugi_bengaliai-asr_whisper-medium (from the 2023 Bengali.AI Kaggle competition)**
- In 2026 DL Sprint 4.0 long-form papers it was the strongest off-the-shelf model. Results: 34.07% WER baseline on Bengali-Loop ([Bengali-Loop, arXiv 2602.14291](https://arxiv.org/html/2602.14291)); 0.36771 public WER with Silero VAD; 0.37738 private / 0.36137 public WER with Demucs plus silence chunking ([arXiv 2602.21741](https://arxiv.org/html/2602.21741v1)); fine-tuned further to 23.58% public / 24.75% private ([Bangla-WhisperDiar](https://arxiv.org/html/2605.08214v1)).
- I could not retrieve the original 2023 Kaggle 1st-place write-up or its FLEURS numbers in this session.

**OmiKhan/bangla-asr-whisper-medium** (the current baseline)
- It does not appear in the ehzawad benchmark. The only numbers available are the project's own measurements (16.5% clean FLEURS, 22.7% phone plus noise). These are in the same range as `SayedShaun/bengali-whisper-medium` (13.90% FLEURS WER, with NFC). No independent source found.

**AI4Bharat IndicConformer / IndicWhisper (Vistaar)**
- `ai4bharat/indic-conformer-600m-multilingual`: about 600M parameters, covers 22 Indic languages including Bengali, **MIT licence** (per GitHub and the AIKosh catalog). The HF repo is gated (contact-info agreement). Community ONNX/sherpa-onnx and quantised ports exist. — [search results: AI4Bharat GitHub, AIKosh, HF mirrors](https://aikosh.indiaai.gov.in/home/models/details/aibharat_indicconformer_600m_multi.html)
- I could not find a per-language Bengali WER for IndicConformer on Vistaar (HF and arXiv were blocked).
- Vistaar is 59 benchmarks across 12 languages (Kathbath, FLEURS, CommonVoice, IndicTTS, MUCS, GramVaani). IndicWhisper (a Whisper fine-tune) was best on 39 of 59, with an average WER reduction of 4.1. Data is mostly Indian Bengali. **2023, older.** — [AI4Bharat/vistaar](https://github.com/AI4Bharat/vistaar); [Interspeech 2023 paper](https://www.isca-archive.org/interspeech_2023/bhogale23_interspeech.pdf)

**Meta Omnilingual ASR (Nov 2025; v2 checkpoints later)**
- Code and models are **Apache-2.0**, and the corpus is CC-BY-4.0. — [omnilingual-asr README](https://github.com/facebookresearch/omnilingual-asr)
- Per-language CSV for the 7B LLM-ASR model: **ben_Beng CER 2.8 with 342.1 training hours**; eng_Latn CER 3.0 with 63,591 h. It also covers Bangladeshi regional languages: ctg_Beng (Chittagonian) 1.5, rkt_Beng (Rangpuri) 1.1, bng_Beng 1.5. — [per_language_results_table_7B_llm_asr.csv](https://github.com/facebookresearch/omnilingual-asr/blob/main/per_language_results_table_7B_llm_asr.csv). The CSV does not say which test set these come from, and the figures are for the 7B model only.
- VRAM and real-time factor (BF16, A100, 30 s audio, batch 1): CTC_300M(_v2) about 2 GiB, RTF 0.001; CTC_1B about 3 GiB, RTF 0.002; CTC_3B about 8 GiB; LLM_300M about 5 GiB, RTF 0.09; LLM_1B about 6 GiB; LLM_7B about 17 GiB. **Inputs are limited to 40 s or less** for CTC/LLM models; "Unlimited" LLM variants handle long audio. — [README](https://github.com/facebookresearch/omnilingual-asr)
- Paper headline: the 7B LLM model averages 6.2% CER on FLEURS-102 against 6.5% for USM. — [review of arXiv 2511.09690](https://www.themoonlight.io/review/omnilingual-asr-open-source-multilingual-speech-recognition-for-1600-languages)
- I found no Bengali WER or CER for the CTC-300M or CTC-1B models, which are the sizes that fit 3 GB.

**Older MMS-1B (2023)**: I found no current Bengali number in this session. Omnilingual ASR supersedes it.

**NVIDIA Parakeet / Canary**
- Canary-1B-v2 and Parakeet-TDT-0.6B-v3 cover **25 mostly European languages, with no Bengali**. — [arXiv 2509.14128](https://arxiv.org/pdf/2509.14128)
- A Bengali fine-tune of Canary-1B-v2 does very well (11.58% FLEURS), which shows the architecture adapts well to Bengali. — [ehzawad benchmark](https://github.com/ehzawad/bengali-asr-benchmark)
- Unverified: the licences are CC-BY-4.0 per the NVIDIA model cards (HF not reachable). The benchmark README also lists Canary as CC-BY-4.0.

**Qwen3-ASR (Jan 2026, Apache-2.0, 0.6B and 1.7B)**
- It supports 30 languages plus 22 Chinese dialects. **Bengali is not in the list; Hindi is.** It does streaming and offline inference in one model, with a vLLM backend. — [QwenLM/Qwen3-ASR README](https://github.com/QwenLM/Qwen3-ASR)
- A community Bengali fine-tune exists, `SayedShaun/Qwen3-ASR-0.6B-Bengali`, but no WER was found. — [HF card (search result)](https://huggingface.co/SayedShaun/Qwen3-ASR-0.6B-Bengali)

**Stock Whisper and SeamlessM4T**
- Fleurs-SLU appendix, FLEURS ben_Beng CER: Whisper-large-v3 33.9, SeamlessM4Tv2-Large 9.0. — [Fleurs-SLU, arXiv 2501.06117](https://arxiv.org/pdf/2501.06117)
- Unverified: SeamlessM4T v2's licence is CC-BY-NC-4.0, which is non-commercial. I could not check this in this session. It is a 2.3B model, too big for the budget.

**Other 2026 Bangla releases**
- BuzzASR, "A Swarm of 100+ Monolingual Speech Recognition Models" (arXiv 2609.09554, Sep 2026), has a `BuzzASR/bengali` HF repo. I could not fetch either, so its size, WER and licence are unknown. — [search result](https://huggingface.co/BuzzASR/bengali)
- "Whistle" bn-BD (57M, private) reaches 16.36% FLEURS WER on CPU. — [ehzawad benchmark](https://github.com/ehzawad/bengali-asr-benchmark)

### Inferences
- In VRAM terms, a 120M-parameter Conformer-CTC (hishab or FastConformer) needs well under 1 GB. A Whisper-medium in CTranslate2 int8 likely needs about 1.5-2 GB, because faster-whisper large-v2 int8 used about 2.9 GB ([faster-whisper](https://github.com/SYSTRAN/faster-whisper)) and medium has about half the parameters. Whisper-turbo (809M) in int8 likely needs about 1.5-2 GB. Omnilingual CTC-300M needs about 2 GiB in BF16 (README). All of these fit, but none of these per-model figures except Omnilingual's were measured.
- Switching base model is unlikely to beat the current Whisper-medium fine-tune by much on FLEURS. Published public alternatives score 10.8-14% against the project's 16.5% (watch out for NFC differences). The bigger lever is in-domain fine-tuning on Bangladeshi conversational and telephone speech.

### Gaps
- The licence for hishab/titu_stt_bn_conformer_large, and a Bengali WER for IndicConformer-600M.
- Bengali WER for Omnilingual CTC-300M/1B and MMS-1B.
- A FLEURS WER for OmiKhan's model under NFC normalisation.
- Measured VRAM figures for any Bangla model.

## Q2. English inside a Bangla fine-tuned Whisper, code-switching, and routing

### Takeaway
I found no direct study of the OmiKhan or tugstugi models on English. The evidence points to forgetting: Bangla fine-tunes rarely output Latin-script English. In SPRING-INX, about half of references contain Latin-script English words, and **no model in the 12-model benchmark reproduced them**. Fine-tuning on one language makes Whisper forget English. A practical design is a per-utterance language-ID step (Whisper's own LID, or a dedicated LID) that routes to a Bangla model or an English model. Code-switched English terms (medicine names, "appointment", "report") will come out in Bangla script and need post-processing or LLM tolerance.

### Cited Findings
- "About half of SPRING's references contain English words in Latin script. No model reproduced them". Measured SPRING WER (36-47%) overstates the real error rate. Whistle, by contrast, "leaks English fragments from its English base model." — [ehzawad benchmark](https://github.com/ehzawad/bengali-asr-benchmark)
- Fine-tuning Whisper only on code-switched data degrades its other languages (catastrophic forgetting). Training on a mix of monolingual and code-switched data beats sequential fine-tuning. — [Code-switching ASR survey, arXiv 2509.24310](https://arxiv.org/pdf/2509.24310)
- When Whisper is fine-tuned on a low-resource language alongside English, it forgets English after a small amount of fine-tuning. Adding auto-labelled English spans to training substantially reduces this. — [ComputEL 2025](https://preview.aclanthology.org/landing_page/2025.computel-main.18.pdf)
- Freezing Whisper and tuning soft prompts, or Bayesian adaptation, reduces forgetting. The Bayesian method reports a 54% backward-gain improvement over LoRA. — [summarised from search results for arXiv 2510.18723 / 2412.16507](https://arxiv.org/abs/2510.18723v1)
- Bengali-English code-switched data:
  - MUCS 2021: about 46 h of Bengali-English code-switched training data, from CS lecture recordings. It has a wav2vec2 result of 28.27% WER ([arXiv 2203.16578](https://arxiv.org/pdf/2203.16578)) and a hybrid result of 23.2% transliterated WER on the dev set ([Wiesner et al., Interspeech 2021](https://www.isca-archive.org/interspeech_2021/wiesner21_interspeech.pdf)).
  - BEHE-CMDisfl (2026): a synthetic LLM plus TTS corpus of disfluent code-mixed Bengali-English and Hindi-English speech. LoRA fine-tuning reached 21.37% WER. — [ACL Anthology author page](https://aclanthology.org/people/anuran-mitra/)
  - MediBeng Whisper Tiny: fine-tuned on synthetic clinical Bengali-English code-switched audio, but for **translation to English** (BLEU 0.98), not transcription. — [medRxiv 2025](https://www.medrxiv.org/content/10.1101/2025.04.25.25326406v3)
- No standard public pretrained Bengali-English code-switched ASR checkpoint was identified. — (search across the sources above)
- Whisper LID reliability: Whisper-small's default LID was about 87% correct for Bengali (366 of 418) and about 81% for Hindi. Clip length was not controlled. — [arXiv 2403.17314 appendix (Project MOSLA)](https://arxiv.org/pdf/2403.17314)
- A frozen FastConformer encoder gets over 90% macro LID accuracy on FLEURS and Kathbath and beats Whisper out of domain. Hindi-Urdu is the dominant confusion. — [arXiv 2606.09317](https://arxiv.org/abs/2606.09317)
- Omnilingual LLM-ASR supports "optional language conditioning", and Qwen3-ASR does joint LID plus ASR (but without Bengali). — [Omnilingual README](https://github.com/facebookresearch/omnilingual-asr); [Qwen3-ASR README](https://github.com/QwenLM/Qwen3-ASR)

### Inferences
- Bn-vs-en is a much easier LID task than bn-vs-hi. Whisper's main error risk for a Bengali caller is mislabelling as Hindi or Assamese, so restrict LID to {bn, en} by taking the argmax of only those two probabilities. Short utterances (under about 1-2 s, such as "হ্যাঁ" or "ok") are the hardest case. For those, keep the language used in the previous turn unless the new turn is confident.
- A stock Whisper model can provide LID before routing. Note that a fine-tuned Bangla Whisper may have a damaged LID head, so use the English model's or a separate LID's probabilities.
- For Banglish, the LLM downstream can usually understand English words written in Bangla script (for example "অ্যাপয়েন্টমেন্ট"). Prompting the LLM about this is cheaper than building code-switched ASR. A hotword or initial_prompt list of clinic and medicine terms can also help.

### Gaps
- No measurement of English WER, or of the transliteration rate, for OmiKhan or tugstugi on English speech. This needs an in-house test: about 50 English clinic utterances run through the Bangla model.
- No Whisper bn/en LID accuracy as a function of utterance length on telephone audio.

## Q3. Small English ASR to run alongside

### Takeaway
On faster-whisper, the strongest local English options that fit about 1.5-2 GB are distil-large-v3 (English-only, about 756M) and large-v3-turbo (809M, multilingual, MIT), both run in int8. small.en and medium.en are older, cheaper fallbacks. Parakeet-TDT-0.6B-v3 is fast and accurate for English but needs NeMo, and its VRAM is not verified here.

### Cited Findings
- faster-whisper on an RTX 3070 Ti 8 GB with large-v2, beam 5: fp16 used 4,525 MB VRAM, **int8 used 2,926 MB**, and int8 with batch_size=8 used 4,500 MB. — [faster-whisper README (v1.1.0 benchmark)](https://github.com/SYSTRAN/faster-whisper)
- Whisper "small" on CPU in faster-whisper int8 used 1,477 MB RAM. — [same](https://github.com/SYSTRAN/faster-whisper)
- distil-large-v3 is compatible with faster-whisper. With batch 16 it got 13.53 WER on YT Commons, against 14.80 under transformers. faster-whisper also exposes `WhisperModel("turbo")`. — [same](https://github.com/SYSTRAN/faster-whisper)
- Whisper turbo is MIT-licensed and 809M parameters, and it ran at 700 ms per clip in the vLLM Bangla benchmark. — [ehzawad benchmark](https://github.com/ehzawad/bengali-asr-benchmark)
- Parakeet-TDT-0.6B-v3 is 600M parameters and covers 25 European languages, including English. — [arXiv 2509.14128](https://arxiv.org/pdf/2509.14128)
- Omnilingual CTC-300M also covers English (eng CER 3.0 for the 7B model in the CSV), so one checkpoint could cover both languages. — [Omnilingual CSV](https://github.com/facebookresearch/omnilingual-asr/blob/main/per_language_results_table_7B_llm_asr.csv)

### Inferences
- Rough VRAM, scaled from the large-v2 int8 figure of 2.9 GB and not measured: medium.en int8 about 1.5 GB, distil-large-v3 int8 about 1.5-2 GB, large-v3-turbo int8 about 1.5-2 GB (turbo has the full 32-layer encoder and a 4-layer decoder), small.en int8 under 1 GB.
- Running the Bangla Whisper-medium int8 and an English turbo int8 together would cost about 3-4 GB, which is over budget. Options:
  - (a) Use large-v3-turbo for both LID and English, plus a Bangla CTC Conformer of 0.5 GB or less for Bangla, for about 2-2.5 GB in total.
  - (b) Use a single Bangla-and-English fine-tune of turbo, trained on mixed data to avoid forgetting.

### Gaps
- Verified VRAM, licence and Open ASR Leaderboard WER for parakeet-tdt-0.6b-v3, distil-large-v3 and medium.en (HF was blocked). From memory and unverified: parakeet-tdt-0.6b-v2 and v3 are CC-BY-4.0, and distil-large-v3 is MIT.

## Q4. Telephone (8 kHz) and noise robustness for Bangla

### Takeaway
There is very little public data. The one controlled Bangla study shows 8 kHz audio raises WER substantially (0.338 at 8 kHz against 0.232 at about 18.75 kHz), because telephone band-limiting cuts the energy of Bangla sibilants. No public benchmark of open Bangla models on 8 kHz exists, and the ehzawad benchmark explicitly excludes telephony. Plan to fine-tune with telephone-channel augmentation and evaluate on in-house calls.

### Cited Findings
- Bangla doctor-patient telehealth audio resampled from 8 to 32 kHz and passed through one cloud ASR: WER was about 0.338 at 8 kHz and about 0.232 at 18.75 kHz, with gains plateauing above that. 8 kHz truncates the high-frequency energy of /s/ and /ʃ/. (March 2026 preprint.) — [MDPI Signals 7(3):44](https://www.mdpi.com/2624-6120/7/3/44); [preprint](https://www.preprints.org/frontend/manuscript/6b50f05dfb4281166ab07eb8430f9af4/download_pub)
- Telephone Bangla corpora: Socian, about 300 h, not public; IARPA Babel Bangla, 215 h, West Bengal accent, licensed through LDC. — [arXiv 2210.12921](https://arxiv.org/pdf/2210.12921.pdf)
- A synthetic Bengali telecom customer-care speech corpus (2026) exists for ASR training and evaluation. — [arXiv 2608.20346](https://arxiv.org/pdf/2608.20346)
- Vendor claims, unverified: Convozen "Akshara" reports 26.55% telephonic Bengali WER against 38.01% and 71.89% for competitors ([Convozen](https://convozen.ai/products/bengali-speech-to-text)). Sarvam Saaras is marketed for 8 kHz Bengali including Bangladeshi accents ([Sarvam](https://www.sarvam.ai/apis/speech-to-text/bengali)). Both are cloud services, not local.
- A 2021 Bangladeshi call-centre system (AIMS TALK) reported 42.15% WER. **Older.** — [UIU IRIIC](https://iriic.uiu.ac.bd/?p=12029)
- Long-form noisy Bangla: Demucs source separation plus silence-boundary chunking helped Whisper-medium in DL Sprint 4.0. — [arXiv 2602.21741](https://arxiv.org/html/2602.21741v1)

### Inferences
These are augmentation tips based on standard practice. No Bangla-specific ablation was found.
- Simulate the telephone channel: 16 kHz → 300-3400 Hz band-pass → 8 kHz → G.711 μ-law or a-law and AMR-NB or Opus-narrowband codec round-trip → resample back to 16 kHz.
- Add MUSAN or real clinic and street noise at an SNR of 0-20 dB, room impulse responses, packet-loss and dropout simulation, and SpecAugment.
- Fine-tune on a mix of about 50% telephone-augmented and 50% clean data so browser-mic accuracy is kept.
- Feed every model 16 kHz-upsampled audio, since all the models above expect 16 kHz. Upsampling does not restore the lost band, so fine-tuning is the real fix.
- The project's measured jump from 16.5% to 22.7% is about +6 points absolute. That fits the about +10-point 8-vs-18 kHz gap in the telehealth study.

### Gaps
- No open-model Bangla WER on real 8 kHz calls. Babel Bangla (LDC) or in-house recordings would be needed.

## Q5. Concrete recommendation for this setup (12 GB GPU, about 1.5-3 GB ASR budget)

### Takeaway
Keep the current faster-whisper Bangla Whisper-medium (int8) as the production baseline. Add stock `large-v3-turbo` int8 only if VRAM allows; otherwise use stock `small` or `medium` for {bn, en} LID plus English. Run a quick A/B against `hishab/titu_stt_bn_conformer_large` (check its licence first) and Omnilingual `CTC_300M_v2`/`CTC_1B_v2` (Apache-2.0) on in-house phone audio. The most valuable next step is to fine-tune on telephone-augmented Bangladeshi conversational and clinic data mixed with English, so a single model handles both.

### Cited Findings (supporting facts, see above)
- The public hishab Conformer-CTC has the best FLEURS WER (10.83%) and CER, at 87 ms per clip, but is weak on spontaneous speech (IndicVoices 29.30%). — [ehzawad benchmark](https://github.com/ehzawad/bengali-asr-benchmark)
- Whisper-medium-class Bangla fine-tunes score about 13.9-16.5% on FLEURS and about 22-26% on conversational sets, at 304 ms per clip. — [same](https://github.com/ehzawad/bengali-asr-benchmark)
- Omnilingual CTC_300M_v2 needs about 2 GiB VRAM, runs at RTF 0.001, is Apache-2.0, and is limited to clips of 40 s or less. — [Omnilingual README](https://github.com/facebookresearch/omnilingual-asr)
- Fine-tuned 0.8-2B models (Whisper-turbo, Qwen3-ASR, Canary) are the best overall (about 21.9% average WER), but the available checkpoints are non-commercial. The same recipe with public base models (Whisper-turbo MIT, Canary CC-BY-4.0, Qwen3-ASR Apache-2.0) is something the project could replicate. — [same](https://github.com/ehzawad/bengali-asr-benchmark)
- Faster-whisper int8 cuts VRAM by about 35% compared with fp16 (large-v2: 2.9 GB against 4.5 GB). — [faster-whisper](https://github.com/SYSTRAN/faster-whisper)

### Inferences (recommended plan)
1. **Now:** keep OmiKhan Whisper-medium in CTranslate2 int8_float16 on faster-whisper, with Silero VAD and beam 1-2 for latency.
   - Always NFC-normalise both hypothesis and reference.
   - Add a domain `initial_prompt` or hotwords (doctor names, departments, common medicines).
   - Re-measure FLEURS WER with NFC.
2. **English path:** route by {bn, en} LID.
   - Cheapest option: run stock Whisper `small` for LID on the first about 2-3 s of the utterance, then send English utterances to `distil-large-v3` or `large-v3-turbo` int8 (about 1.5-2 GB, unmeasured).
   - If VRAM is too tight, use turbo int8 for both LID and English, and swap Bangla to a CTC Conformer (well under 1 GB).
   - Use turn-level hysteresis: keep the previous turn's language when LID confidence is low.
3. **Benchmark candidates on 100-300 in-house phone utterances** (8 kHz μ-law, upsampled):
   - OmiKhan Whisper-medium
   - bengaliAI tugstugi Whisper-medium (licence unverified)
   - hishab titu Conformer-large (licence unverified, possibly NC)
   - Omnilingual CTC_1B_v2 (Apache-2.0, about 3 GiB)
   - ai4bharat indic-conformer-600m (MIT, gated)
   Note that CTC models output no punctuation. Long-form results differ from short-clip results: the hishab model scored 50.67% WER long-form in DL Sprint 4.0 ([arXiv 2605.08214](https://arxiv.org/html/2605.08214v1)).
4. **Fine-tune (biggest expected gain):**
   - Base: Whisper-large-v3-turbo (MIT) or Whisper-medium.
   - Data: Bangladeshi sets (SUBAK.KO, BanSpeech, Ben-10, Common Voice bn, OpenSLR 53) plus English (for example LibriSpeech or Common Voice en) at about 20-30% share to prevent forgetting, plus synthetic code-switched clinic dialogues (LLM text + TTS, as BEHE-CMDisfl and MediBeng do).
   - Apply telephone-channel augmentation as in Q4.
   - LoRA or a frozen encoder reduces forgetting.
   - Target: a single model of about 1.5-2 GB int8 that handles bn, en and Banglish, removing the need for routing.
5. **Licence hygiene:**
   - Avoid ehzawad ‡ models (non-commercial).
   - Avoid Hishab models until their licence is confirmed (the fastconformer is CC-BY-NC-4.0).
   - Avoid SeamlessM4T (NC, unverified) for commercial use.
   - Safe permissive bases: Whisper (MIT), Omnilingual (Apache-2.0), IndicConformer (MIT), Qwen3-ASR (Apache-2.0, no bn out of the box), NVIDIA Canary/Parakeet (CC-BY-4.0, unverified, no bn out of the box).

### Gaps
- No measured VRAM for the candidate models on this GPU. Profile with `nvidia-smi` while the LLM and TTS are loaded.
- Streaming: faster-whisper and Whisper are chunked or pseudo-streaming. Qwen3-ASR has native streaming but no Bengali. I found no information on streaming support for NeMo Conformer-CTC Bangla models (cache-aware streaming needs specific FastConformer checkpoints), so it is unverified.
- OpenSLR 53 (Large Bengali ASR, Google Bangladesh/India crowdsourced) and Bengali.AI "OOD-Speech" WERs for current models were not found in this session.
