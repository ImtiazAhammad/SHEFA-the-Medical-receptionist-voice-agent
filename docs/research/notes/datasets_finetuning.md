# Bangla Speech/Dialogue Datasets and Fine-Tuning Recipes on a Single 12 GB GPU (as of Nov 2026)

> Method note: This session's network allowed only web search and GitHub. Direct fetches of openslr.org, huggingface.co, arxiv.org, kaggle.com, commonvoice.mozilla.org, ai4bharat.iitm.ac.in and docs.unsloth.ai were blocked by the sandbox egress policy. Most figures below come from search-result snippets of the primary pages (HF dataset cards, arXiv papers, OpenSLR pages), plus two GitHub pages fetched directly (rhasspy/piper TRAINING.md, ylacombe/finetune-hf-vits README). Items marked **[UNVERIFIED]** come from prior knowledge or a single secondary source and were not confirmed against a primary page in this session. Check every licence on the live dataset card before you ship.

## 1. Bangla TTS datasets (hours, speakers, quality, accent, licence)

### Takeaway
No public, commercially licensed, studio-quality, single-speaker *Bangladeshi* receptionist-style corpus exists. Here is what is available:
- **Commercially usable (CC BY 4.0):** AI4Bharat corpora that are mostly Indian-Bengali. Rasa has about 57 h of expressive studio speech from 2 speakers. IndicVoices-R has about 112 h from 617 speakers, cleaned from ASR data.
- **Best Bangladesh-relevant studio corpus:** BanglaKontho, 20 h of audiobook speech, but it is **non-commercial**.
- **Customer-care style:** a new 26.8 h *synthetic* Bengali telecom set under CC BY 4.0.
- **Not suitable for TTS:** Common Voice bn and OpenSLR 53, which are crowd-sourced phone recordings.

### Cited Findings
**OpenSLR 37 (Google crowd-sourced high-quality Bengali TTS, bn_BD + bn_IN)**
- It is multi-speaker data for Bangladesh (bn-BD) and Indian Bengali (bn-IN), hosted at openslr.org/37 — [coqui-ai/open-speech-corpora](https://github.com/coqui-ai/open-speech-corpora); [OpenSLR via HF](https://huggingface.co/datasets/openslr/openslr)
- One HF LoRA adapter card used 2.9 h of OpenSLR-37. That is one user's subset, not the official total — [SayedShaun/Qwen3-ASR-0.6B-Bengali-LoRA](https://huggingface.co/SayedShaun/Qwen3-ASR-0.6B-Bengali-LoRA)
- **[UNVERIFIED]** Prior knowledge says the licence is CC BY-SA 4.0 (commercial use allowed, share-alike on the *dataset*), with a few hours per locale from volunteer speakers. Confirm on [openslr.org/37](https://www.openslr.org/37/).

**IndicTTS (IIT Madras TTS Consortium, Bengali)**
- The project says the datasets are free for researchers, and "start-ups and businesses that want to use the data can sign a Memorandum Of Understanding with Indic TTS." In practice, commercial use needs a separate agreement — [CIS-India Indic TTS page](https://voice.cis-india.org/indic-tts.html)
- Sources conflict on the licence. One project lists the IIT Madras IndicTTS voice as "Non-commercial / Academic." An HF card describes a "permissive license that allows derivative works" but also reproduces a TTS Consortium copyright notice — [localclaw IndicTTS](https://localclaw.io/tts/indic-tts); [voxaura-labs/vaakya-open README](https://huggingface.co/voxaura-labs/vaakya-open/blob/2f78aefb54fbbae59c84abfec4c6a63e57f417a4/README.md)
- The BanglaKontho paper calls the Bengali IndicTTS corpus "12-hour IndicTTS-Bn." The same MB-iSTFT-VITS architecture reached 16.0 % WER / MOS 3.16 on it — [BanglaKontho arXiv 2609.29146](https://arxiv.org/abs/2609.29146)
- The Indic Parler-TTS card lists a Bengali training subset of 140.04 h / 70,305 utterances and says "the underlying IndicTTS data is listed under CC BY 4.0." This conflicts with the MoU statement above — [ai4bharat/indic-parler-tts](https://huggingface.co/ai4bharat/indic-parler-tts)
- Accent: Indian Bengali (IIT Madras recordings). **[UNVERIFIED]** It is generally 1 male + 1 female studio speaker per language.

**IndicVoices-R (AI4Bharat, NeurIPS 2024 Datasets & Benchmarks)**
- Overall: 1,704 h of "high-quality speech from 10,496 speakers across 22 Indian languages," 9–175 h per language. It was derived (enhanced and filtered) from the IndicVoices ASR data — [arXiv 2409.05356](https://arxiv.org/pdf/2409.05356); [NeurIPS paper](https://proceedings.neurips.cc/paper_files/paper/2024/file/7dfcaf4512bbf2a807a783b90afb6c09-Paper-Datasets_and_Benchmarks_Track.pdf)
- **Bengali: 111.99 h, 617 speakers, 40,943 utterances** (paper table; may differ from the current HF release) — [arXiv 2409.05356](https://arxiv.org/pdf/2409.05356)
- Licence: **CC BY 4.0** (HF card, GitHub and paper agree) — [HF ai4bharat/indicvoices_r](https://huggingface.co/datasets/ai4bharat/indicvoices_r); [GitHub AI4Bharat/IndicVoices-R](https://github.com/AI4Bharat/IndicVoices-R); download portal [datasets.ai4bharat.org/IndicVoices-R](https://datasets.ai4bharat.org/IndicVoices-R/)
- Accent: speakers recruited across Indian districts, so West Bengal / Indian Bengali (inferred from IndicVoices' India-wide collection).

**Rasa (AI4Bharat expressive TTS)**
- Bengali: **Female 29.69 h (15,570 utt) + Male 27.06 h (15,639 utt), about 56.75 h**. Licence tag **CC BY 4.0** — [HF ai4bharat/Rasa](https://huggingface.co/datasets/ai4bharat/Rasa)
- **[UNVERIFIED]** It is studio-recorded, with emotion/style labels (e.g. happy, sad, anger, fear, surprise, disgust, neutral, command, news, conversational). The speakers are Indian.

**Common Voice Bengali (Mozilla)**
- v9.0: 231,120 samples, **399 h from 19,817 contributors, but only about 56–57 h validated (14 %)** — [arXiv 2206.14053](https://arxiv.org/pdf/2206.14053)
- A forum thread says CV-14 had 1,268 h of Bengali *recorded* audio, while validated audio stays small — [Mozilla Discourse](https://discourse.mozilla.org/t/600-hours-of-audio-is-missing-in-bengali/121240)
- Licence: CC0 — [arXiv 2206.14053](https://arxiv.org/pdf/2206.14053)
- Suitability for TTS: poor. It is crowd-sourced browser/phone microphones with many short clips per speaker, so noise and channel vary (inferred from the collection method). It suits ASR, or at most speaker-diverse pre-training after heavy filtering/enhancement. IndicVoices-R shows that kind of enhancement pipeline.

**BanglaKontho (2026)**
- **20 h, single speaker, professional audiobook recordings, 7,050 utterances, 24 kHz.** Licence **CC BY-NC 4.0 (non-commercial)**. Released with a Bangla text normaliser at github.com/mizba-grad/BanglaKontho — [arXiv 2609.29146](https://arxiv.org/abs/2609.29146); [HTML](https://arxiv.org/html/2609.29146)
- MB-iSTFT-VITS trained on it: **9.5 % WER, 4.46 MOS**, against 16.0 % / 3.16 for the same model on 12 h IndicTTS-Bn — [arXiv 2609.29146](https://arxiv.org/abs/2609.29146)
- Speaker accent (BD vs IN) was not stated in the snippets — see Gaps.

**Synthetic Bengali telecom customer-care speech (2026)**
- 10,000 audio–text pairs, **about 26.82 h at 24 kHz**, released on HF under **CC BY 4.0**. Authors: Kawshik Kumar Paul, Md. Nafiul Alam Fuji — [arXiv 2608.20346](https://arxiv.org/abs/2608.20346)
- It is synthetic (TTS-generated), so it is useful for ASR domain adaptation and dialogue phrasing. It does not make a TTS voice sound more natural.

**Other / commercial**
- SUBESCO (SUST Bangla Emotional Speech Corpus) is an audio-only Bangla emotional speech corpus (Bangladesh, SUST). It is useful for an emotion/prosody reference — [PMC8087046](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8087046/)
- Commercial vendors sell Bangladesh-Bengali TTS monologue sets and telecom scripted monologues (price and licence on request) — [FutureBeeAI BD TTS](https://www.futurebeeai.com/dataset/speech-dataset/tts-monolgue-bengali-bangladesh); [FutureBeeAI BD telecom](https://www.futurebeeai.com/dataset/monologue-speech-dataset/telecom-scripted-speech-monologues-bengali-bangladesh)
- A Springer 2025 paper built a custom Bangla VITS dataset. It shows that groups have recorded their own voices — [Springer 10.1007/s10791-025-09701-3](https://link.springer.com/article/10.1007/s10791-025-09701-3)

### Inferences
- For a **commercial** Bangladeshi clinic agent, these are the legally clean public TTS sources:
  - Rasa (CC BY 4.0, expressive, 2 speakers)
  - IndicVoices-R (CC BY 4.0, many speakers)
  - OpenSLR 37 (likely CC BY-SA 4.0, partly bn_BD)
  - The synthetic telecom set (CC BY 4.0)
- All of them except OpenSLR 37 bn_BD are Indian-accented. Training on them alone will likely give a Kolkata-leaning prosody and lexicon (e.g. "jol" vs "pani", different politeness forms).
- BanglaKontho has the best measured quality (MOS 4.46), but its NC licence blocks commercial deployment. It is fine for research and A/B prototyping only.
- CC BY-SA on OpenSLR 37 may impose share-alike on derived *datasets*. Whether trained model weights are "adapted material" is legally unsettled. Treat it as a risk to flag, not a blocker.

### Gaps
- OpenSLR 37 exact hours/speakers/licence could not be fetched (openslr.org blocked).
- IndicTTS Bengali licence is unresolved: MoU-for-commercial (project page) vs "CC BY 4.0" (Indic Parler-TTS card). Read the licence PDF on the IIT Madras download page.
- BanglaKontho speaker origin (Bangladesh vs India) is not confirmed.
- "SUBAK.KO" is an **ASR** corpus (see §2), not TTS. I found no SUST studio *TTS* corpus with a public licence.
- I found no public conversational/spontaneous Bangladeshi TTS corpus (expressive dialogue between two people, studio-grade).

## 2. Bangla ASR datasets (hours, licence, accent, domain, telephone, code-switching)

### Takeaway
Bangladesh-accent ASR data is plentiful:
- **SUBAK.KO:** 241 h, CC BY 4.0
- **OpenSLR 53:** about 196k utterances, CC BY-SA 4.0
- **OOD-Speech / Bengali.AI:** about 1,200 h, 22k speakers, CC BY-SA 3.0 US per paper
- **Common Voice bn:** CC0, but only a small validated share
- **Indian-Bengali sets:** Kathbath (about 116 h) and IndicVoices (conversational, CC BY 4.0)

Real 8 kHz telephone Bangla and real Bangla–English code-switched conversational speech are almost absent. The large new **DocTalkBN** (558 h of telemedicine audio and text) is the closest domain match, but its licence is unknown. Telephone conditions will have to be simulated.

### Cited Findings
**OpenSLR 53 – Large Bengali ASR training data (Google, Bangladesh)**
- About 196K utterances. Licence **CC BY-SA 4.0** — [openslr.org/53](https://www.openslr.org/53/) (via search snippet)
- Hours conflict: 181.46 h (2026 arXiv paper) vs 211.2 h / 214,324 utterances (HF adapter card). The official page gives no hour total — [arXiv 2601.09710](https://arxiv.org/pdf/2601.09710); [HF SayedShaun adapter](https://huggingface.co/SayedShaun/Qwen3-ASR-0.6B-Bengali-LoRA)
- HF mirror: [SKNahin/open-large-bengali-asr-data](https://huggingface.co/datasets/SKNahin/open-large-bengali-asr-data)
- **[UNVERIFIED]** The often-quoted "~229 h" figure comes from the task brief and was not confirmed. It may be confused with SUBAK.KO's 229 h read-speech portion (below). Recordings are crowd-sourced on Android phones in Bangladesh, read speech.

**SUBAK.KO (SUST CSE, Bangladeshi Bangla)**
- **241 h total: 229 h read speech in a noise-proof studio + 12 h broadcast speech from YouTube** — [ScienceDirect, Speech Communication 2021](https://www.sciencedirect.com/science/article/abs/pii/S0167639321001370); [ResearchGate](https://www.researchgate.net/publication/356919063_Bangladeshi_Bangla_Speech_Corpus_for_Automatic_Speech_Recognition_Research)
- HF card metadata: **licence cc-by-4.0**, 10K<n<100K samples — [HF SUST-CSE-Speech/SUBAK.KO README](https://huggingface.co/api/resolve-cache/datasets/SUST-CSE-Speech/SUBAK.KO/78ec55bd4207a9268df6bf13ef0cd9303817f62a/README.md?download=true&etag=%22955413af27c96f3cd4e8b88b082e327a7f7e8476%22). The 2022 CV paper marked it "Not Publicly Available," which predates the HF release — [arXiv 2206.14053](https://arxiv.org/pdf/2206.14053)
- Note: the read portion is studio-recorded Bangladeshi speech with many speakers. It could also serve as a secondary multi-speaker TTS pre-training source (inference).

**Bengali.AI OOD-Speech (basis of the Kaggle "Bengali.AI Speech Recognition" 2023 competition)**
- **About 1,177.94 h training + about 23 h test (total about 1,201 h), 22,645 native Bengali speakers in South Asia**, massively crowdsourced. The test set is designed for out-of-distribution benchmarking across domains (e.g. drama, sermons, parliament) — [arXiv 2305.09688](https://arxiv.org/pdf/2305.09688); [bengaliai.github.io/asr](https://bengaliai.github.io/asr)
- Licence per paper table: **CC BY-SA 3.0 US**. The Kaggle competition terms were not verified and may restrict use to the competition — [arXiv 2305.09688](https://arxiv.org/pdf/2305.09688)
- Related Kaggle dialect competition "ভাষা-বিচিত্রা: ASR for Regional Dialects" (ben10) — [Kaggle ben10](https://www.kaggle.com/competitions/ben10). Regional spontaneous corpus RegSpeech12 (12 dialects) — [arXiv 2510.24096](https://arxiv.org/pdf/2510.24096)

**Common Voice bn** — see §1. 399 h recorded / 56–57 h validated (v9), CC0. Later versions have >1,200 h recorded but little validated — [arXiv 2206.14053](https://arxiv.org/pdf/2206.14053); [Discourse](https://discourse.mozilla.org/t/600-hours-of-audio-is-missing-in-bengali/121240)

**Kathbath (AI4Bharat, IndicSUPERB)**
- Bengali **about 115.8 h**, read speech (text from IndicCorp), Indian speakers. Includes a noisy test variant — [GitHub AI4Bharat/IndicSUPERB](https://github.com/AI4Bharat/indicSUPERB)
- Licence conflict: HF card says the packaging is **CC0**. A mirror says MIT. The HF page is gated — [HF ai4bharat/Kathbath](https://huggingface.co/datasets/ai4bharat/Kathbath); [modeldatabase mirror](https://modeldatabase.com/datasets/ai4bharat/kathbath.html)

**IndicVoices (AI4Bharat)**
- 23.7K h total (11.2K transcribed): read 8 %, extempore 76 %, **conversational 15 %**, 51K speakers. **CC BY 4.0** — [HF ai4bharat/IndicVoices](https://huggingface.co/datasets/ai4bharat/IndicVoices); [IndiaAI article](https://indiaai.gov.in/article/iit-madras-ai4bharat-and-sarvam-ai-launch-indicvoices-a-milestone-in-indian-speech-recognition)
- A Bengali folder exists on HF (56 train parquet shards) — [HF commit listing](https://huggingface.co/datasets/ai4bharat/IndicVoices/commits/f9c48ae48f689c98e5a58de988b47bf949345efb/bengali/train-00017-of-00056.parquet). Bengali hours were not found.
- **[UNVERIFIED]** Prior knowledge says part of the IndicVoices conversational data was recorded over telephone, which would make it the main *real* narrowband Indic source.

**MUCS 2021 (Interspeech) – Bengali-English code-switched**
- Bengali–English data is extracted from **spoken technical tutorials**, so code-switching comes from technical vocabulary. Sources conflict on sampling rate (16 kHz vs "8 kHz for most sets") — [arXiv 2104.00235](https://arxiv.org/pdf/2104.00235); [OpenSLR 104](https://www.openslr.org/104/)
- **[UNVERIFIED]** It is roughly 50–100 h per code-switched pair, licence CC BY-SA 4.0 on OpenSLR.

**Code-switched / clinical speech (new)**
- **MediBeng**: a *synthetic* Bengali–English code-switched doctor–patient conversation dataset for ASR/translation/TTS. It was used to fine-tune Whisper-tiny — [medRxiv 2025.04.25.25326406](https://www.medrxiv.org/content/10.1101/2025.04.25.25326406v1.full)
- **BEHE-CMDisfl (WILDRE 2026)**: a synthetic Bengali–English and Hindi–English code-mixed corpus with disfluency annotations. The Bengali–English subset is 1.3 h — [ACL Anthology 2026.wildre-1.5](https://aclanthology.org/2026.wildre-1.5.pdf)
- **DocTalkBN (2026)**: **557.63 h of paired audio and text** from nationally broadcast **telemedicine programmes with board-certified physicians**, real spoken Bengali. The licence was not stated in the snippets ("publicly available at an anonymous link") — [arXiv 2608.27110](https://arxiv.org/abs/2608.27110)
- A GitHub project does Bengali/English code-switched LoRA on whisper-medium / large-v3. It notes large-v3 did not fit a T4 (no bf16, 15 GB), so it fell back to whisper-medium fp16 — [Asrarul-BS23/whisper-finetuning](https://github.com/Asrarul-BS23/whisper-finetuning)

**Telephone / call-centre**
- I found no public *real* 8 kHz Bangla call-centre corpus. Closest options:
  - synthetic telecom set (26.8 h, CC BY 4.0) — [arXiv 2608.20346](https://arxiv.org/abs/2608.20346)
  - commercial vendor sets — [FutureBeeAI](https://www.futurebeeai.com/dataset/monologue-speech-dataset/telecom-scripted-speech-monologues-bengali-bangladesh)
  - generic Bengali conversational speech sample sets on HF — [SpeechDataAI/bengali-conversational-speech](https://huggingface.co/datasets/SpeechDataAI/bengali-conversational-speech)

**Shrutilipi** — **[UNVERIFIED]** AI4Bharat, about 6,400 h of All India Radio news audio and transcripts across 12 Indic languages incl. Bengali, CC BY 4.0. Indian broadcast (news-reader) style. Not confirmed this session.

### Inferences
- **Most useful for Bangladesh accent:** SUBAK.KO (studio read, CC BY 4.0), OpenSLR 53 (phone-recorded read, CC BY-SA 4.0), OOD-Speech (diverse, CC BY-SA 3.0 — check share-alike implications) and Common Voice (CC0).
- **Most useful for clinic domain realism:** DocTalkBN (if its licence permits) and MediBeng/IndicMedDialog for terminology.
- A practical Whisper fine-tune mix could be 100–300 h drawn from SUBAK.KO + OpenSLR 53 + CV-validated + a DocTalkBN slice. That fits a 12 GB LoRA budget in a few days, with all audio downsampled to 8 kHz → 16 kHz and codec-augmented.

### Gaps
- Bengali-specific hours in IndicVoices; telephone portion confirmation.
- Kaggle Bengali.AI competition data terms (could be competition-only).
- DocTalkBN and MUCS licences; Shrutilipi Bengali hours.
- Current (CV 20+/2025–26) Common Voice bn validated hours.

## 3. Text / dialogue data: medical, appointment-booking, instruction-tuning, synthetic generation

### Takeaway
No public Bangla appointment-booking dialogue set exists. Medical dialogue resources appeared in 2025–26: DocTalkBN (real telemedicine), IndicMedDialog (synthetic, native-verified, multi-turn), MediBeng (synthetic code-switched) and BanglaHealth-NER. General Bangla instruction sets are available (Bangla-Instruct 100K, but with licence conflicts). Receptionist style data will have to be **synthesised** from a strong LLM and reviewed by native Bangladeshi speakers.

### Cited Findings
- **DocTalkBN** — real Bengali expert telemedicine conversations with paired audio. Unlike prior forum/synthetic resources, it keeps the spoken character of real interaction. 557.63 h — [arXiv 2608.27110](https://arxiv.org/abs/2608.27110)
- **IndicMedDialog** — a parallel multi-turn medical dialogue dataset in English + 9 Indic languages incl. Bengali. Built by LLM synthesis with native-speaker verification. The paper LoRA-fine-tunes **LLaMA-3.2-3B-Instruct** on it. Licence not found — [arXiv 2605.13292](https://arxiv.org/pdf/2605.13292)
- **BanglaHealth-NER** (EsferSami/BanglaHealthNER) — Bangla medical conversations with BIO tags. 25,426 / 3,178 / 3,179 train/val/test — via search summary of [arXiv 2609.29101](https://arxiv.org/pdf/2609.29101)
- **BanglaHealth paraphrase** (behind BanglaT5-mHealth) — Bengali health sentences with paraphrase pairs — [HF faisal4590aziz/bangla-t5-mHealth](https://huggingface.co/faisal4590aziz/bangla-t5-mHealth)
- Bangla medical VQA benchmark (2026) — [arXiv 2605.18111](https://arxiv.org/pdf/2605.18111)
- **Bangla-Instruct** (TigerLLM): 100K native Bangla instruction–response pairs made with self-instruct and teacher models. Licences conflict: the HF card says MIT, the TigerLLM repo says GPL-3.0, and the paper page says CC BY-NC-ND 4.0 — [HF md-nishat-008/Bangla-Instruct](https://huggingface.co/datasets/md-nishat-008/Bangla-Instruct/resolve/main/README.md?download=true); [GitHub mraihan-gmu/TigerLLM](https://github.com/mraihan-gmu/TigerLLM); [ResearchGate TigerLLM](https://www.researchgate.net/publication/389894110_TigerLLM_--_A_Family_of_Bangla_Large_Language_Models)
- Bangla-Code-Instruct (300K, CC BY 4.0) is code-focused and not relevant to dialogue — [HF TigerCoder-9B](https://huggingface.co/md-nishat-008/TigerCoder-9B/blob/main/README.md)
- Curated index of Bengali AI datasets/models — [GitHub Iamsdt/awesome-bengali-ai](https://github.com/Iamsdt/awesome-bengali-ai)
- **[UNVERIFIED]** Cohere **aya_dataset** (Apache 2.0) and **aya_collection** contain human-written and translated Bengali prompt/completion pairs. The Bengali count was not found.
- The synthetic telecom paper shows that LLM-written Bengali customer-care scripts + TTS can produce a CC BY 4.0 resource — [arXiv 2608.20346](https://arxiv.org/abs/2608.20346)

### Inferences
- Recommended synthetic pipeline:
  1. Write a schema for clinic intents (book / reschedule / cancel, doctor availability, fees, directions, reports, emergencies → escalate).
  2. Generate 2–5K multi-turn dialogues with a frontier LLM in Bangladeshi colloquial Bangla, with Banglish code-switching (e.g. "appointment", "report", "doctor" kept in English).
  3. Have 1–2 native Bangladeshi reviewers fix register: আপনি-form politeness, Dhaka colloquial forms.
  4. Seed realism with DocTalkBN transcripts (licence permitting).
  5. Use the same scripts as the reading prompts for custom voice recording (§5) and as ASR text-LM adaptation data.
- IndicMedDialog's 3B LoRA result suggests small models (3–4B) can be domain-tuned for medical dialogue. Those fit comfortably on 12 GB.

### Gaps
- Licences of IndicMedDialog, DocTalkBN, MediBeng not confirmed.
- No Bangla appointment-booking or receptionist dataset found anywhere.
- aya_dataset Bengali row count not found.

## 4. Fine-tuning recipes feasible on 12 GB (RTX 4060 Ti-class) with time/gain estimates

### Takeaway
Everything on the list fits on 12 GB with modest batch sizes:
- **Piper / VITS / MMS fine-tuning:** about 83M params. Easy, hours to a day.
- **Whisper-medium LoRA:** easy. Whisper-large-v2/v3 LoRA with 8-bit weights also fits; PEFT says under 8–10 GB.
- **7–9B QLoRA with Unsloth:** fits at about 6–10 GB with seq ≤2048 and batch 1–2.
- **F5-TTS / IndicF5:** the only tight one. Community runs use 24 GB; 12 GB needs small frame batches. Treat it as risky.

Licences decide more than VRAM. MMS-TTS weights are CC BY-NC. IndicF5's licence is unclear. Indic Parler-TTS is Apache 2.0.

### Cited Findings
**Piper (VITS) voice fine-tuning**
- Fine-tuning from an existing checkpoint is the normal path. The base checkpoint must match quality and sample rate but **need not be the same language**. Quality levels:
  - low = 16 kHz
  - medium = 22.05 kHz
  - high = 22.05 kHz, larger model, "much slower"
- From scratch: about 2,000 epochs. Fine-tuning: about **+1,000 epochs**. Stop when `loss_disc_all` plateaus.
- Reference setting: batch 32 with max-phoneme-ids 400 on 24 GB. A 12 GB card implies roughly batch 8–16 (inferred).
- Requires **espeak-ng** with a `--language` voice, or a "text" phoneme alphabet.
- No time estimates or minimum dataset size are given.
- Source: [rhasspy/piper TRAINING.md](https://raw.githubusercontent.com/rhasspy/piper/master/TRAINING.md)
- Community guidance on data:
  - "even just an hour of speech will get you a voice that sounds great in most scenarios"
  - about 1,300 phrases is often recommended
  - demos with <50 s or a single phrase (via synthetic augmentation) exist but have limited quality
  - Sources: [ZachB100 Piper guide](https://github.com/ZachB100/Piper-Training-Guide-with-Screen-Reader/blob/main/README.md); [CodingKiwi](https://blog.coding.kiwi/training-a-custom-piper-tts-voice/); [Cal Bryant](https://calbryant.uk/blog/training-a-new-ai-voice-for-piper-tts-with-only-4-words/); [Hackaday](https://hackaday.com/2025/07/09/how-to-train-a-new-voice-for-piper-with-only-a-single-phrase/)
- An existing Bengali Piper-style voice ("Rohan") trained on IIT Madras IndicTTS is tagged non-commercial/academic — [localclaw IndicTTS](https://localclaw.io/tts/indic-tts)
- **[UNVERIFIED]** espeak-ng ships a Bengali (`bn`) voice. Its G2P quality for Bangla (inherent vowel deletion, conjuncts) is mediocre, so a custom phonemiser or the "text" grapheme mode may sound better.

**MMS / HF VITS fine-tuning (finetune-hf-vits)**
- "As little as **80 to 150 samples**" can give a good result, "in **20 minutes**." The model is about 83M params, so one GPU is enough. A discriminator is required: use a `-with-discriminator` checkpoint or run the conversion script once per language.
- **MMS checkpoints are CC BY-NC 4.0, and fine-tunes inherit that licence.**
- Source: [ylacombe/finetune-hf-vits README](https://raw.githubusercontent.com/ylacombe/finetune-hf-vits/main/README.md)

**F5-TTS / IndicF5**
- F5 maintainers say a new language needs "a substantial amount" of hours — [F5-TTS issue #5](https://github.com/SWivid/F5-TTS/issues/5)
- Community data points:
  - Polish: 142 h
  - Vietnamese: about 100 h for specific voices, about 1,000 h for broad cloning
  - Single-speaker clone: 14 min / 224 clips on F5 v1 Base
  - Sources: [Discussion #1168](https://github.com/SWivid/F5-TTS/discussions/1168); [F5-TTS-Vietnamese](https://github.com/nguyenthienhy/F5-TTS-Vietnamese); [Ferrari-72 child-voice](https://github.com/Ferrari-72/F5TTS-Child-Voice-Finetune)
- VRAM:
  - LoRA run verified on 24 GB; 12 GB only "with conservative batch settings" — [Instavar guide](https://instavar.com/research/tts/f5-tts-fine-tuning)
  - child-voice project used 8 GB at batch 4, dropping to 2 on OOM — [Ferrari-72](https://github.com/Ferrari-72/F5TTS-Child-Voice-Finetune)
- **IndicF5 licence is unclear.** Mirrors say MIT plus "obtain explicit permission before cloning any voice." A GitHub issue notes the repo has no LICENSE file and asks about training-data commercial terms — [F5-TTS issue #1341](https://github.com/SWivid/F5-TTS/issues/1341); [AIKosh IndicF5](https://aikosh.indiaai.gov.in/home/models/details/aibharat_indicf5.html)
- A community Bengali IndicF5 fine-tune (ehzawad/indicf5-bangla-tts) is **research-only, non-commercial** — [HF ehzawad/indicf5-bangla-tts](https://huggingface.co/ehzawad/indicf5-bangla-tts/tree/main/checkpoints)

**Parler-TTS / Indic Parler-TTS**
- Indic Parler-TTS: **Apache 2.0**, Bengali training subset 140.04 h. A community Bengali fine-tune (Tanmoyshome/bn-parler-tts) already exists — [HF ai4bharat/indic-parler-tts](https://huggingface.co/ai4bharat/indic-parler-tts); [HF Tanmoyshome/bn-parler-tts](https://huggingface.co/Tanmoyshome/bn-parler-tts)
- **[UNVERIFIED]** The model is about 0.9B params (Mini-based), so full fine-tuning on 12 GB needs bf16 + gradient checkpointing + small batch. It is feasible but slower than VITS.

**Whisper LoRA / PEFT**
- With PEFT + INT8, **Whisper-large-v2 trains in under 8 GB VRAM** (under 10 GB in another phrasing) on a Colab T4. The adapter is about 63 MB vs 6.7 GB for the full model — [openai/whisper discussion #988](https://github.com/openai/whisper/discussions/988); [LinkedIn S. Mangrulkar](https://www.linkedin.com/posts/sourab-m_attention-asr-developers-and-researchers-activity-7034051494240821249-edTr?trk=public_profile_like_view)
- Marathi CV11 result: **13.64 WER full fine-tune vs 14.01 WER with PEFT LoRA**, so LoRA is roughly on par — [discussion #988](https://github.com/openai/whisper/discussions/988); [HF anuragshas/whisper-large-v2-mr](https://huggingface.co/anuragshas/whisper-large-v2-mr)
- LoRA-INT8 Whisper for low-cost Cantonese edge ASR (peer-reviewed) — [PMC12431075](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12431075/)

**Telephone augmentation evidence**
- Codec-simulation augmentation (16 kHz → 8 kHz + diverse codecs) when no real telephone data is available, tested on real call-centre speech — [APSIPA 2019](https://www.apsipa.org/proceedings/2019/pdfs/216.pdf)
- 2026 narrowband study on 8 kHz customer-support audio:
  - fine-tuned in-house model about 12.3 % English WER vs Whisper-large-v3 zero-shot about 28.7 %
  - Whisper Hindi WER about 49 %
  - Source: [arXiv 2606.18659](https://arxiv.org/pdf/2606.18659)
- Vendor blog (not peer-reviewed): fine-tuning on codec-degraded audio from your own traffic "recovers 3 to 5 points of WER." It recommends training on the actual codec path rather than additive noise — [caller.digital 8 kHz benchmark](https://caller.digital/blog/8khz-narrowband-telephony-asr-tts-benchmark-india-2026)
- Korean telemedicine Whisper fine-tune with SpecAugment, speed perturbation and noise showed a significant WER gain — [ResearchGate](https://www.researchgate.net/publication/403885801_Optimizing_whisper_for_Korean_telemedicine_Fine-tuning_domain-specific_ASR_for_clinical_telephone_transcription)

**LLM QLoRA (Unsloth)**
- Unsloth lists minimums of **8B: about 6 GB QLoRA (4-bit) / about 22 GB LoRA (16-bit)**, and says these are absolute minimums — [Unsloth requirements](https://unsloth.ai/docs/get-started/fine-tuning-for-beginners/unsloth-requirements); [Vast.ai mirror](https://docs.vast.ai/examples/ai-ml-frameworks/unsloth-studio)
- Measured: 6.6 GB peak for 8B QLoRA at 2,048 seq on an RTX 4090 — [ComputingForGeeks](https://computingforgeeks.com/fine-tune-llm-unsloth-qlora/). Estimates: about 7–8 GB at r=16 batch 1, about 9–10 GB at batch 2, with 12 GB as the stated minimum GPU — [InsiderLLM](https://insiderllm.com/guides/lora-training-consumer-hardware/)
- **[UNVERIFIED]** Unsloth also has notebooks for Whisper and for LLM-based TTS (Orpheus, Sesame CSM, Spark-TTS, Llasa). These are an alternative route to an expressive Bangla voice, but those base models have little Bangla pre-training.

### Inferences (time estimates are engineering estimates, not sourced)
- **Piper medium fine-tune**, from an English or existing Bengali checkpoint, 1–3 h of single-speaker 22 kHz audio, about 1,000 extra epochs on a 4060 Ti: roughly 12–36 h wall-clock. Real-time on CPU at inference, which suits a phone agent.
- **MMS-ben VITS fine-tune**: under 1 h of training on about 150 clips (per the README's "20 minutes"), but non-commercial. Use it only to prototype voice/timbre.
- **Whisper-medium LoRA (or large-v3-turbo LoRA in 8-bit)** on 100–200 h Bangladeshi Bangla + 8 kHz/codec augmentation: about 1–3 days for 2–3 epochs at batch 8–16 with gradient accumulation.
  - Expected gain: large on Bangla (zero-shot Whisper Bangla is weak). A further 3–5 WER points from telephone-matched augmentation (vendor figure).
- **Unsloth QLoRA 7–9B** on 2–5K synthetic receptionist dialogues (seq 2k, r=16): about 1–4 h per epoch. Gains are mostly style/register/consistency (short turns, polite আপনি forms, structured booking slots), not new knowledge.
- **F5/IndicF5 fine-tune on 12 GB**: possible at batch 2–4 frame batches, but slow (days) and fragile. Its licence risk makes it a poor first choice.

### Gaps
- No published Bangla-specific numbers for Piper fine-tune hours→MOS, Whisper-medium Bangla LoRA WER, or Bangla telephone gains.
- Parler-TTS fine-tune VRAM on 12 GB was not verified.
- Unsloth docs could not be fetched directly (domain blocked); figures come from a mirror and search snippets.

## 5. Recommendation: most realism per effort; custom voice talent vs public data; consent/licence

### Takeaway
Ranked by realism per effort:
1. **Synthetic-dialogue QLoRA of the LLM** (cheap, hours, biggest effect on "sounds like a receptionist")
2. **Whisper LoRA on Bangladeshi data with 8 kHz/codec augmentation** (biggest effect on "understands")
3. **Custom-voice Piper (or VITS) fine-tune on 1–3 h of a consenting Bangladeshi voice talent**

Recording your own talent beats the public datasets on accent, register and licence cleanliness. Public CC BY corpora are Indian-accented or non-commercial, and none is receptionist-style. Fine-tune from an Apache/CC BY base so the result is commercially clean.

### Cited Findings
- The largest measured Bangla TTS jump came from **data quality**: the same architecture went from MOS 3.16 (12 h IndicTTS-Bn) to 4.46 (20 h professional single speaker) — [arXiv 2609.29146](https://arxiv.org/abs/2609.29146)
- Piper needs only about 1 h for a good single-speaker voice when fine-tuned from a checkpoint, and the base can be another language — [ZachB100 guide](https://github.com/ZachB100/Piper-Training-Guide-with-Screen-Reader/blob/main/README.md); [Piper TRAINING.md](https://raw.githubusercontent.com/rhasspy/piper/master/TRAINING.md)
- Licence traps:
  - MMS-TTS CC BY-NC (inherited by fine-tunes) — [finetune-hf-vits](https://raw.githubusercontent.com/ylacombe/finetune-hf-vits/main/README.md)
  - BanglaKontho CC BY-NC — [arXiv 2609.29146](https://arxiv.org/abs/2609.29146)
  - IndicTTS needs an MoU for commercial use — [CIS-India](https://voice.cis-india.org/indic-tts.html)
  - IndicF5 unclear; voice cloning requires explicit permission — [F5-TTS #1341](https://github.com/SWivid/F5-TTS/issues/1341); [AIKosh](https://aikosh.indiaai.gov.in/home/models/details/aibharat_indicf5.html)
  - ehzawad Bangla IndicF5 research-only — [HF](https://huggingface.co/ehzawad/indicf5-bangla-tts/tree/main/checkpoints)
  - Bangla-Instruct licence conflicting — [GitHub TigerLLM](https://github.com/mraihan-gmu/TigerLLM)
- Clean commercial bases:
  - Indic Parler-TTS Apache 2.0 — [HF](https://huggingface.co/ai4bharat/indic-parler-tts)
  - IndicVoices-R / Rasa / IndicVoices CC BY 4.0 — [HF IndicVoices-R](https://huggingface.co/datasets/ai4bharat/indicvoices_r); [HF Rasa](https://huggingface.co/datasets/ai4bharat/Rasa)
  - SUBAK.KO CC BY 4.0 — [HF](https://huggingface.co/api/resolve-cache/datasets/SUST-CSE-Speech/SUBAK.KO/78ec55bd4207a9268df6bf13ef0cd9303817f62a/README.md?download=true&etag=%22955413af27c96f3cd4e8b88b082e327a7f7e8476%22)
  - Common Voice CC0 — [arXiv 2206.14053](https://arxiv.org/pdf/2206.14053)
  - synthetic telecom CC BY 4.0 — [arXiv 2608.20346](https://arxiv.org/abs/2608.20346)
- Telephone-matched fine-tuning beats generic noise augmentation — [caller.digital](https://caller.digital/blog/8khz-narrowband-telephony-asr-tts-benchmark-india-2026); [APSIPA 2019](https://www.apsipa.org/proceedings/2019/pdfs/216.pdf)

### Inferences
- **Order of work on one 4060 Ti:**
  1. LLM QLoRA on 2–5K reviewed synthetic Bangladeshi receptionist dialogues (1–2 days including data).
  2. Whisper-medium or large-v3-turbo LoRA on SUBAK.KO + OpenSLR 53 + CV-bn + a DocTalkBN slice if licensed. Add an 8 kHz resample + G.711/AMR/Opus codec chain + packet-loss augmentation, and a few hours of real calls recorded with consent (3–5 days).
  3. Custom TTS (1–2 weeks including recording).
- **Custom voice talent plan:**
  - Hire one Bangladeshi (Dhaka-standard) receptionist-style speaker.
  - Record **1–3 h (about 1,000–2,500 utterances)** of the actual clinic script domain at 22.05/24 kHz in a treated room. Include numerals, dates, times, doctor names, Banglish terms and question/confirmation prosody.
  - Fine-tune Piper-medium (fast CPU inference, permissive MIT code) from an English or other medium checkpoint.
  - Optionally pre-adapt first on Rasa/IndicVoices-R Bengali (CC BY, attribution needed) or SUBAK.KO studio read speech to teach Bangla phonetics, then fine-tune on the talent.
  - This should beat any public-dataset voice on accent and register. Public-only voices will sound Indian or audiobook-like.
- **Consent/licence:**
  - Get a written voice-talent agreement covering commercial synthetic-voice use, duration and territory, a right to revoke or not, no use for other clients, and payment.
  - Comply with Bangladesh's evolving data-protection rules and the clinic's patient-privacy obligations if real call audio is recorded for ASR. Get explicit caller notice/consent, de-identify, and do not train on PHI without approval.
  - Keep attribution notices for CC BY data, and flag share-alike (OpenSLR 53/37, OOD-Speech) for legal review.
  - Avoid NC-licensed bases (MMS, BanglaKontho, ehzawad IndicF5) in the production path.
- Where the voice must be expressive, not just clear, consider Indic Parler-TTS (Apache 2.0, Bengali seen in pre-training) fine-tuned on the same talent recordings as a second candidate. A/B it against Piper on latency, because Parler is much heavier at inference.

### Gaps
- No controlled study compares "1–3 h custom talent" against public multi-speaker data for Bangla specifically. The recommendation rests on the BanglaKontho quality result plus general TTS practice.
- Bangladesh-specific voice-likeness/biometric consent law details were not researched (out of scope / not found).
- No Bangla receptionist LLM fine-tuning results found; expected gains are inferred from IndicMedDialog's 3B LoRA work and general practice.
