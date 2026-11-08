# vLLM against Ollama for several callers at once (measured 2026-11-09)

**Result: vLLM is the right engine for a clinic with more than one line. Ollama stays as the
zero-setup way to try SHEFA on a laptop.**

## What was measured

Same machine for both: RTX 4060 Ti, 16 GB. Same model family and size class: gemma2-9b in 4-bit
(Ollama's `gemma2:9b`; vLLM's `hugging-quants/gemma-2-9b-it-AWQ-INT4`). Same input: the real router
prompt with the sample clinic directory and five different caller sentences. Each simulated caller
asks, waits for the answer, pauses 0.4 s and asks again, 6 rounds. `scripts/bench_concurrency.py`.

| Callers at once | Engine | p50 | p95 | Answers per second |
|---|---|---|---|---|
| 1 | Ollama | 1.73 s | 2.35 s | 0.48 |
| 1 | **vLLM** | 0.96 s | 1.27 s | 0.75 |
| 3 | Ollama | 3.75 s | 4.86 s | 0.66 |
| 3 | **vLLM** | 0.97 s | 1.40 s | 2.08 |
| 5 | Ollama | 6.52 s | 7.80 s | 0.71 |
| 5 | **vLLM** | 1.03 s | 1.56 s | 3.24 |

- Ollama serialises requests: throughput stays near 0.5-0.7 answers a second whatever the number of
  callers, so the fifth caller waits behind four others. A phone caller gives up on a 6 s silence.
- vLLM batches them: the 95th percentile barely moves from 1 to 5 callers and throughput grows
  almost with the callers. The target from the engineering review (p95 under 2.5 s at 3 callers) is
  met by vLLM (1.40 s) and missed by Ollama (4.86 s).

## Accuracy is not the same, and not clearly worse

`scripts/bench_dialogue.py`, 29 multi-turn cases:

| Engine | Right tool and arguments | Median reply | Worst |
|---|---|---|---|
| Ollama gemma2:9b | 24/29 | 1.48 s | 5.25 s |
| vLLM gemma2-9b AWQ | 22/29 | 0.97 s | 1.94 s |

vLLM did better on follow-ups (8/9 against 6/9) and worse on dictated phone numbers (0/2 against
2/2) and on two cases that the code layer already catches before the model is asked (a "thank you"
and an emergency, both decided by `social.py` and the keyword layer). It is a different 4-bit
quantisation with a different chat template, so a small gap is expected; n=29 cannot separate them.
End to end, the full pipeline on vLLM answered a Bangla and an English booking correctly, refused
a dosing question, and escalated a chest-pain call (see the commit that added this note).

## What it costs

- 75 s to start with the weights cached (about 6 minutes the first time, which includes the
  5.5 GB download on a 4.4 MB/s line).
- 8.4-10 GB of the 16 GB card at `gpu_memory_utilization: 0.60`. **vLLM and Ollama cannot hold the
  card together**; stop Ollama's model (`ollama stop gemma2:9b`) first. With speech recognition
  (about 2.5 GB) there is little room to spare on 16 GB; a 24 GB card is more comfortable.
- The KV cache at 0.60 holds about 5,000 tokens, about 1.2 full-length requests, but the long
  system prompt is shared by prefix caching, which is why 5 callers were served.
- Operational note: vLLM's sampler tries to compile a FlashInfer kernel at start-up and dies
  without the CUDA toolkit and `ninja`. The launcher sets `VLLM_USE_FLASHINFER_SAMPLER=0`.
- Gemma 2's own chat template rejects a system message; `configs/chat_templates/gemma2.jinja`
  folds it into the first user turn.

## Limits of this measurement

One GPU, one model size, 6 rounds per caller count, router requests only. Speech recognition and
the voice were NOT running at the same time, and they share the GPU in production; the real load
test has to run with them (3 simultaneous scripted calls through AudioSocket for 30 minutes,
tracking p95 and VRAM). Treat 5 callers as the upper bound until that is done; the default
`telephony.max_concurrent_calls` is 4.

## How to use it

```bash
uv venv .venv-vllm --python 3.12 && VIRTUAL_ENV=.venv-vllm UV_HTTP_TIMEOUT=900 uv pip install vllm
uv run shefa setup --profile vllm      # writes configs/local.yaml
uv run shefa serve                     # starts vLLM too, waits for the model
```
