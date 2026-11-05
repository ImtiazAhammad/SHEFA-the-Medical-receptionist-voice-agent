# Locally runnable TTS for a bilingual (Bangla + English) medical-receptionist phone agent (as of Nov 2026)

Research conditions: this session's network blocked huggingface.co, arxiv.org and ar5iv.labs.arxiv.org (DNS/proxy refusal), so model cards and papers could not be fetched directly. Hugging Face and arXiv facts below come from search-result snippets of those pages or from mirrors and aggregators, and each one says so. GitHub (raw.githubusercontent.com, github.com) could be fetched. Claims that rest only on prior knowledge and were not re-checked this session are labelled **[unverified this session]**. To verify them, allow huggingface.co and arxiv.org in the session network settings and re-read the cards.

Hardware budget: RTX 4060 Ti 12 GB, shared with STT (~1.6 GB) and LLM (~7 GB), which leaves roughly 2-3 GB for TTS, or TTS on CPU. Output is streamed sentence by sentence at 8-24 kHz.

## Q1. Bangla TTS options: naturalness, accent, latency, streaming, VRAM, licence

### Takeaway
No Bangla voice I could verify combines a Bangladeshi accent, a commercial-safe licence and high naturalness in one small model. The most practical small local options are:
- **Single-speaker Bangla VITS models** (bangla-speech-processing; MIT on the card; self-reported MOS 4.1; about 22 kHz; trivial VRAM; can run on CPU).
- **Indic Parler-TTS** (reported Apache-2.0; 21 Indic languages including Bengali; heavier and slower; Indian-dataset accent).
- **IndicF5** (MIT weights, but needs a reference clip, is slow and is not streaming-friendly).
- **Svara-TTS v1** (Apache-2.0, a 3B Orpheus/Llama model with Bengali male and female voices; about 1.9 GB at 4-bit but heavy for the budget).

Meta MMS-TTS-ben is CC-BY-NC-4.0, so it is not commercial-safe. I could not confirm an official Piper Bangla voice.

### Cited Findings
**Piper (rhasspy / OHF-Voice)**
- The official Piper voice list (piper1-gpl `docs/VOICES.md`) has **no Bengali (bn) entry**. Its South Asian languages are Hindi (hi_IN), Malayalam (ml_IN), Nepali (ne_NP) and Telugu (te_IN). — [OHF-Voice/piper1-gpl VOICES.md](https://raw.githubusercontent.com/OHF-Voice/piper1-gpl/main/docs/VOICES.md)
- The older rhasspy/piper `VOICES.md` (v1.0.0 voices) also has no Bengali. Its Hindi voices are `hi_IN-pratham-medium` and `hi_IN-priyamvada-medium`. — [rhasspy/piper VOICES.md](https://raw.githubusercontent.com/rhasspy/piper/master/VOICES.md)
- A third-party Hugging Face mirror (PYTHAI/voaice) lists a `bn_BD-google-medium` entry with a CC-BY-4.0 licence. The table row is misaligned (its language cell reads "Kazakh"), so it is unreliable. A `ne_NP/google/medium` voice exists in a piper-voices PR branch, which suggests that Google-dataset South Asian voices were contributed via PRs. — [PYTHAI/voaice](https://huggingface.co/PYTHAI/voaice); [piper-voices refs/pr/6 ne_NP google](https://huggingface.co/rhasspy/piper-voices/tree/refs%2Fpr%2F6/ne/ne_NP/google/medium/samples)
- Piper says it is "intended for personal use and text to speech research only". Each voice's licence follows its training dataset, so the voice's MODEL_CARD must be checked. — [OHF-Voice/piper1-gpl VOICES.md](https://raw.githubusercontent.com/OHF-Voice/piper1-gpl/main/docs/VOICES.md)

**Meta MMS-TTS (facebook/mms-tts-ben)**
- Tagged `license: cc-by-nc-4.0`. MMS-TTS family models are VITS-based, cover about 1,100 languages, and cite arXiv:2305.13516. CC-BY-NC-4.0 limits use to non-commercial purposes. — [Mixpeek listing of facebook/mms-tts-ben](https://mixpeek.com/model/facebook/mms-tts-ben); [PromptLayer MMS-TTS](https://www.promptlayer.com/models/mms-tts)

**AI4Bharat Indic Parler-TTS (ai4bharat/indic-parler-tts)**
- Supports 21 languages including Bengali. The card says it was evaluated with a "MOS-like framework" by native and non-native speakers, but search snippets showed no numeric Bengali MOS. Card revisions disagree on training data: 8,385 h in an older version, 1,806 h now. — [Hugging Face card (snippet)](https://huggingface.co/ai4bharat/indic-parler-tts); [pretrained commit](https://huggingface.co/ai4bharat/indic-parler-tts-pretrained/commit/793b78ff9f7575577edd490ac9c3d1085db128e1)
- Licence is reported as Apache-2.0 and the model is gated on HF, but only third-party listings confirm this. Aggregator presets for Bengali are "Aditi" (female) and "Arjun" (male). The aggregator labels speed "slow" and caps requests at 500 characters. — [dev.co listing](https://dev.co/ai/llms/indic-parler-tts); [tts.ai Indic Parler](https://tts.ai/voices/indic-parler/?lang=as)
- The companion paper (Rasmalai dataset + IndicParlerTTS) is arXiv 2505.18609. Its Bengali MOS tables could not be fetched. — [arXiv 2505.18609](https://arxiv.org/html/2505.18609v2)

**AI4Bharat IndicF5**
- Licence is MIT (HF card and India's AIKosh catalogue). Languages are Assamese, Bengali, Gujarati, Hindi, Kannada, Malayalam, Marathi, Odia, Punjabi, Tamil and Telugu. Training data is Rasa, IndicTTS, LIMMITS and IndicVoices-R, and the dataset licences may differ from the MIT weights. — [ai4bharat/IndicF5](https://huggingface.co/ai4bharat/IndicF5); [AIKosh IndicF5](https://aikosh.indiaai.gov.in/home/models/details/aibharat_indicf5.html)
- An open HF community discussion asks AI4Bharat to confirm the MIT grant for commercial use and the pretraining data provenance. No reply was visible. — [IndicF5 discussion #43](https://huggingface.co/ai4bharat/IndicF5/discussions/43)

**Bangla VITS fine-tunes (bangla-speech-processing, "Saiful")**
- `bangla_tts_female`: single-speaker VITS trained with Coqui TTS. The card says **MIT** and self-reports **MOS 4.10** with no protocol given. Training data partly comes from Mozilla Common Voice. Sample rate is 22,050 Hz. — [bangla_tts_female README](https://huggingface.co/bangla-speech-processing/bangla_tts_female/blob/main/README.md); [aimodels.org listing (22,050 Hz)](https://aimodels.org/ai-models/text-to-speech-synthesis/bengali-female-tts-model-vits-female-encoding-trained-on-custom-dataset-at-22050hz)
- The male VITS model reportedly has a MOS of about 4.1 for naturalness. — [bangla-speech-processing org](https://huggingface.co/bangla-speech-processing)
- An independent paper, **BanglaTalk** (arXiv 2510.06188, Oct 2025, Bangladesh regional-dialect assistant), used "VITS-Bengali (male)" TTS and reports **MOS 4.49** on a BanSpeech subset. It also reports a 4.9 s average end-to-end delay at 24 kbps. Its dialect work is on the ASR side, not TTS. — [BanglaTalk arXiv](https://arxiv.org/html/2510.06188v1)
- The comprehensive-bangla-tts project (mobassir94) offers a Bangla VITS model that was added to Coqui TTS. — [GitHub mobassir94/comprehensive-bangla-tts](https://github.com/mobassir94/comprehensive-bangla-tts)
- A Dhaka University Journal of Science benchmark compares Bangla Tacotron2, FastSpeech2, VITS and Grad-TTS using objective metrics and native-speaker MOS. It concludes that phonetic accuracy and naturalness still need work. — [DUJS benchmark](https://banglajol.info/index.php/DUJS/article/view/84122)

**BnTTS (XTTS-based Bangla, NAACL Findings 2025)**
- Extends XTTS to Bangla. It is pretrained on about 3.85k h of Bangla speech and does few-shot adaptation with 20 min from four studio speakers. Authors claim better SMOS, naturalness and clarity than SOTA Bangla TTS. The snippets give no numbers and no weights licence. The paper is associated with the Hishab team (via catalyzex author listings). — [ACL Anthology 2025.findings-naacl.279](https://preview.aclanthology.org/new-sigs/2025.findings-naacl.279/); [arXiv 2502.05729](https://arxiv.org/abs/2502.05729v1); [catalyzex author page](https://www.catalyzex.com/author/Tareq%20Al%20Muntasir)
- I found no Hishab-branded open TTS release. — [search summary, Hishab](https://www.catalyzex.com/author/Tareq%20Al%20Muntasir)

**Orpheus-based Bangla**
- **Svara-TTS v1** (Kenpath): **Apache-2.0**, 19 languages including Bengali and Indian English, male and female voices per language.
  - Model: a Llama-3.2-3B fine-tune on Canopy Labs' Orpheus Hindi base with the SNAC 24 kHz codec.
  - Training data: 2,000+ h of SYSPIN, RASA, IndicTTS and SPICOR.
  - Builds: MLX 4-bit about 1.9 GB, 8-bit about 3.5 GB; OpenVINO INT4 and WebGPU ports exist.
  - Voice cloning on Orpheus-family fine-tunes is reported to be unreliable.
  — [mlx-audio Svara docs](https://blaizzy.github.io/mlx-audio/models/tts/svara/); [Prince-1/svara-tts-v1 mirror card](https://huggingface.co/Prince-1/svara-tts-v1); [kenpath/svara-tts-v1 (proxy mirror)](https://hf-ccm.pages.dev/kenpath/svara-tts-v1)
- A Jan 2026 ICECTE paper fine-tuned Orpheus on an open Bangla dataset and reports CER 5.8%, WER 11.1% and speaker similarity 99.96%. — [IEEE Xplore 11429426](https://ieeexplore.ieee.org/abstract/document/11429426/)
- `asif00/orpheus-bangla-tts` is a 3B Orpheus proof-of-concept trained on only 955 audiobook clips. — [asif00/orpheus-bangla-tts](https://huggingface.co/asif00/orpheus-bangla-tts)

**Other multilingual models and Bengali**
- **Kokoro-82M**: languages are en-US, en-GB, es, fr, hi, it, ja, pt-BR and zh, with **no Bengali**. — [hexgrad/kokoro GitHub](https://github.com/hexgrad/kokoro)
- **Chatterbox-Multilingual (Resemble AI)**: officially supports 23 languages (ar, da, de, el, en, es, fi, fr, he, hi, it, ja, ko, ms, nl, no, pl, pt, ru, sv, sw, tr, zh), with **no Bengali**. A community "chatterbox-indic-lora" adds Bengali and self-reports a Bengali CER of 0.245. — [Chatterbox supported languages (mirror docs)](https://www.mintlify.com/yocxy2/chatterboxyocxy/api/supported-languages); [reenigne314/chatterbox-indic-lora](https://huggingface.co/reenigne314/chatterbox-indic-lora)
- A GitHub desktop app, "kothon-52-bangla-tts", is tagged chatterbox-bangla and was updated Oct 2026. Not evaluated. — [GitHub topic bangla-tts](https://github.com/topics/bangla-tts)

### Inferences
- **Accent:** almost all open Bangla training data cited here is Indian-curated (IndicTTS, Rasa, IndicVoices-R, SYSPIN, SPICOR). Indic Parler-TTS, IndicF5 and Svara will therefore probably lean towards a standard or West-Bengal-style accent, although Indian datasets can include Bangladeshi speakers. The Bangladesh-originated options are the bangla-speech-processing VITS voices, BnTTS (Bangladeshi team, 3.85k h) and the BanglaTalk VITS. No source measured accent directly.
- **Speed and VRAM:** VITS models (MMS, Bangla VITS, Piper-style) are about 30-80M parameters, use well under 1 GB VRAM and run faster than real time on CPU. They are the only Bangla options that fit the 2-3 GB budget comfortably. **[unverified this session: exact RTFs]**
- **Svara:** 3B parameters, so even at 4-bit (about 1.9 GB of weights) plus SNAC and KV cache it would sit at the top of the budget. It also competes with the LLM for compute, which hurts latency.
- **Indic Parler-TTS:** about 0.9B parameters **[unverified this session]**, roughly 2-4 GB VRAM in fp16, and autoregressive. It is feasible, but labelled "slow".
- **IndicF5:** a flow-matching model that needs a reference audio clip and transcript per call. **[unverified this session]**
- **Licences:** MMS-TTS-ben (CC-BY-NC-4.0) should be excluded for a commercial clinic product.

**[Unverified this session, from prior knowledge]**
- F5-TTS base weights are CC-BY-NC-4.0 (Emilia data) and have no Bengali.
- Fish-Speech/OpenAudio weights are CC-BY-NC-SA-4.0, with no clear Bengali support.
- CosyVoice 2/3 (Apache-2.0) covers zh/en/ja/ko and some European languages, with no Bengali.
- XTTS-v2 covers 17 languages including Hindi but not Bengali, under the Coqui Public Model License (non-commercial).
- Sesame CSM-1B is English-only.
- Veena (Maya Research) is Hindi/English only.
- Orpheus multilingual releases do not include Bengali.

### Gaps
- I could not confirm whether `bn_BD-google-medium` exists in rhasspy/piper-voices main or only in a PR or fork, nor its MODEL_CARD licence. Likely source dataset: Google's crowdsourced Bangladeshi Bangla corpus (openslr SLR37, CC-BY-SA-4.0?) **[unverified]**. huggingface.co was blocked.
- I found no numeric Bengali MOS for Indic Parler-TTS, IndicF5 or MMS-TTS-ben. These are probably in arXiv 2505.18609 and the IndicF5 card, which were blocked.
- I found no BnTTS weights release or licence, and no MOS numbers.
- I found no evidence of a "Gemma-based" Google TTS with Bengali, nor of BengaliAI or SUST open TTS releases in 2025-2026. Searches surfaced nothing.
- I found no head-to-head RTF or VRAM benchmarks for Bangla models on a 4060 Ti.

## Q2. English: best small natural local voices

### Takeaway
**Kokoro-82M** (Apache-2.0, 82M parameters, 24 kHz, CPU-capable at about 5x real time) is the best small natural English voice that fits the budget. **Piper en_US voices** (lessac, ryan, amy, libritts_r and others) are a lighter, more robotic fallback. Larger models like Chatterbox and Orpheus sound more expressive but cost more VRAM and latency.

### Cited Findings
- Kokoro-82M: 82M parameters, Apache-licensed weights, 24,000 Hz output, `pip install kokoro` (>=0.9.4). It uses espeak-ng for English OOD fallback and some non-English languages, and supports US and UK English plus Hindi. — [hexgrad/kokoro GitHub](https://github.com/hexgrad/kokoro)
- Kokoro was #1 on the HF TTS Spaces Arena at its v0.19 launch. One blog reports v1.0 at about 32nd of 74 (Elo 1056) on the Artificial Analysis arena and first among browser-capable models. This is not confirmed from the primary leaderboard. — [Replicate kokoro-82m](https://replicate.com/kjjk10/kokoro-82m); [offlinetts.pages.dev Kokoro guide](https://offlinetts.pages.dev/blog/kokoro-tts-complete-guide/)
- Kokoro CPU RTF: about 0.205 (about 5x real time) on an 8-core CPU in a community benchmark (2026), and 6.9-8.3x real time on an Apple M4 Pro CPU. There is no official RTF. — [reddit snapshot (Apr 2026)](https://reddit.sentinel-team.org/posts/1sqkrqp/snapshots/2026-04-21T06%3A28%3A59.170586Z); [NobodyWho/Kokoro-82M](https://huggingface.co/NobodyWho/Kokoro-82M)
- Piper English voices (v1.0.0):
  - en_US: lessac (low, medium, high), libritts (high), libritts_r (medium), ljspeech (medium, high), norman (medium), reza_ibrahim (medium), ryan (low, medium, high), sam (medium) and others.
  - en_GB: alan, alba, aru, cori (medium, high), jenny_dioco, northern_english_male, semaine and others.
  — [rhasspy/piper VOICES.md](https://raw.githubusercontent.com/rhasspy/piper/master/VOICES.md)
- Each Piper voice keeps the licence of its dataset, so check its MODEL_CARD. — [OHF-Voice/piper1-gpl VOICES.md](https://raw.githubusercontent.com/OHF-Voice/piper1-gpl/main/docs/VOICES.md)
- **South-Asian-accented English:**
  - Svara-TTS v1 includes **Indian English** voices (Apache-2.0). — [mlx-audio Svara docs](https://blaizzy.github.io/mlx-audio/models/tts/svara/)
  - Indic Parler-TTS lists English among its languages. **[accent unverified]** — [Hugging Face card (snippet)](https://huggingface.co/ai4bharat/indic-parler-tts)

### Inferences
- **Kokoro on the GPU:** under 1 GB VRAM, 24 kHz output that downsamples cleanly to 8/16 kHz for telephony. It suits sentence-by-sentence streaming because it generates a short sentence in a fraction of a second. **[VRAM figure unverified this session]**
- **Piper:** medium voices are 22.05 kHz ONNX, run on CPU and use no GPU. They are useful for a zero-VRAM English path.
- **[Unverified this session, from prior knowledge]**
  - Chatterbox (English, MIT, 0.5B) and Orpheus 3B (Apache-2.0) are more expressive but take about 2-6 GB VRAM.
  - StyleTTS2 (MIT code; LibriTTS-trained weights carry a synthetic-speech disclosure requirement) is high quality but less maintained.
  - F5-TTS weights are non-commercial.
  - Kokoro's "h" Hindi voices could give an Indian-accented English flavour, but this is not documented as a feature.

### Gaps
- I found no primary 2026 TTS Arena leaderboard data, because huggingface.co was blocked.
- I found no verified VRAM numbers for Chatterbox, Orpheus or StyleTTS2 on a 4060 Ti.
- I could not check whether `en_US-reza_ibrahim` has a South Asian accent (MODEL_CARD inaccessible).

## Q3. Single model covering both Bangla and English well

### Takeaway
The candidates are **Indic Parler-TTS** (Apache-2.0 reported; 21 Indic languages plus English) and **Svara-TTS v1** (Apache-2.0; Bengali plus Indian English). Both carry an Indian accent and are heavier than the dedicated small models. A two-model setup (Bangla VITS or Indic Parler, plus Kokoro for English) is likely better for latency and English naturalness.

### Cited Findings
- Svara-TTS v1 covers 19 languages including Bengali and Indian English, under Apache-2.0, and is a 3B Orpheus/Llama model. — [mlx-audio Svara docs](https://blaizzy.github.io/mlx-audio/models/tts/svara/)
- Indic Parler-TTS covers 21 languages including Bengali, and its licence is reported as Apache-2.0. — [dev.co listing](https://dev.co/ai/llms/indic-parler-tts); [tts.ai Indic Parler](https://tts.ai/voices/indic-parler/?lang=as)
- The zabir-nabil/bangla-tts GitHub project claims multilingual Bangla plus English. It was last updated Oct 2024 and is not evaluated. — [GitHub topic bangla-tts](https://github.com/topics/bangla-tts)
- Kokoro and stock Chatterbox-Multilingual lack Bengali. — [hexgrad/kokoro](https://github.com/hexgrad/kokoro); [Chatterbox supported languages](https://www.mintlify.com/yocxy2/chatterboxyocxy/api/supported-languages)

### Inferences
- One model avoids loading two voices and gives the same speaker identity in both languages, which matters for code-switched Bangla sentences containing English medical terms ("appointment", "CBC test").
- Svara and Indic Parler can read English loanwords inside Bangla text. Kokoro cannot read Bangla script.

### Gaps
- I found no code-switching (Banglish) quality evaluation for any model.

## Q4. Practical integration notes

### Takeaway
VITS-family Bangla models load through Coqui TTS (`TTS` / `coqui-tts` package) or `transformers.VitsModel` (MMS). Kokoro uses `pip install kokoro` plus espeak-ng at 24 kHz. Bangla number and date normalisation must happen in the application before TTS. No cited source provides a ready Bangla number verbaliser.

### Cited Findings
- Kokoro: `pip install kokoro`, 24 kHz, espeak-ng installed via apt for fallback phonemisation. — [hexgrad/kokoro](https://github.com/hexgrad/kokoro)
- bangla_tts_female/male are Coqui-TTS VITS models; female is 22,050 Hz. — [bangla_tts_female README](https://huggingface.co/bangla-speech-processing/bangla_tts_female/blob/main/README.md); [aimodels.org listing](https://aimodels.org/ai-models/text-to-speech-synthesis/bengali-female-tts-model-vits-female-encoding-trained-on-custom-dataset-at-22050hz)
- Svara outputs through the SNAC 24 kHz codec. Inference code is at github.com/Kenpath/svara-tts-inference, and OpenVINO INT4 and WebGPU ports exist. — [mlx-audio Svara docs](https://blaizzy.github.io/mlx-audio/models/tts/svara/); [svara-tts-webgpu](https://awesome.ecosyste.ms/projects/github.com%2Fshreyaskarnik%2Fsvara-tts-webgpu)
- Piper voices are an `.onnx` plus `.onnx.json` pair. — [OHF-Voice/piper1-gpl VOICES.md](https://raw.githubusercontent.com/OHF-Voice/piper1-gpl/main/docs/VOICES.md)

### Inferences
- **[Unverified this session]**
  - MMS-TTS loads via `transformers` `VitsModel` + `AutoTokenizer` at 16 kHz and works on raw Bengali characters (uroman romanisation is only needed for some non-Latin MMS languages).
  - The Bangla VITS models are character-based and do not need espeak-ng. espeak-ng does have a Bengali (`bn`) voice for phonemisation if a Piper-style model is trained.
  - Indic Parler-TTS uses the `parler_tts` package with a text "description" prompt (speaker name, pace, pitch, recording quality) and supports streaming via `ParlerTTSStreamer`.
- **Sample rates:** downsample 22.05 or 24 kHz to 8 kHz for PSTN or 16 kHz for WebRTC.
- **Numbers and dates:** the LLM or an app-side normaliser must expand Bangla digits (০-৯), times ("সকাল ১০টা"), dates and doctor names into words before synthesis. Character-based VITS models trained on read speech often skip or misread raw digits.

### Gaps
- I found no verified open-source Bangla text-normalisation library for TTS (numbers, dates, currency). Worth a dedicated search, for example the "bnnumerizer" or "bangla" PyPI packages **[unverified]**.
- I found no verified streaming (chunked) support for Bangla VITS. Sentence-level synthesis is the practical approach.

## Q5. Concrete recommendation

### Takeaway
**(a) Commercial-safe licence:**
- Bangla: **bangla-speech-processing VITS male/female** (MIT on card; Bangladesh-origin; MOS 4.1 self-reported, 4.49 for a VITS-Bengali male in BanglaTalk; tiny; CPU-capable). Upgrade path: **Indic Parler-TTS** (Apache-2.0 reported) if it fits 2-3 GB, or Svara (Apache-2.0) if VRAM allows.
- English: **Kokoro-82M** (Apache-2.0), with a Piper en_US voice (after checking its MODEL_CARD) as a CPU fallback.

**(b) Best quality regardless of licence:**
- Bangla: likely **IndicF5** (MIT but data provenance questioned) or **Svara/Orpheus-Bangla** fine-tunes for expressiveness. MMS-TTS-ben (NC) is not better than the dedicated Bangla VITS models on any evidence found.
- English: Kokoro for the budget. Orpheus or Chatterbox if VRAM allows **[unverified VRAM]**.

### Cited Findings
- bangla_tts_female MIT, MOS 4.10 — [README](https://huggingface.co/bangla-speech-processing/bangla_tts_female/blob/main/README.md)
- VITS-Bengali male MOS 4.49 (BanglaTalk) — [arXiv 2510.06188](https://arxiv.org/html/2510.06188v1)
- Kokoro Apache-2.0, 82M, 24 kHz — [hexgrad/kokoro](https://github.com/hexgrad/kokoro)
- MMS-TTS-ben CC-BY-NC-4.0 — [Mixpeek](https://mixpeek.com/model/facebook/mms-tts-ben)
- IndicF5 MIT, with an open commercial-use question — [IndicF5 discussion #43](https://huggingface.co/ai4bharat/IndicF5/discussions/43)
- Svara Apache-2.0, Bengali plus Indian English — [mlx-audio Svara docs](https://blaizzy.github.io/mlx-audio/models/tts/svara/)

### Inferences
- **Common Voice data:** the MIT label on bangla_tts_female sits on top of partly Common Voice (CC0) data, which is commercially friendly. Confirm the remaining "custom dataset" provenance before production.
- **Before choosing:** run a quick blind A/B with Bangladeshi staff on 20 receptionist prompts across the candidates. Score accent, numerals and English loanwords, because published MOS figures are self-reported or not comparable.

### Gaps
- I found no independent, comparable Bangla MOS across all candidates.
- I found no measured RTF or VRAM on an RTX 4060 Ti for Indic Parler, IndicF5 or Svara.
