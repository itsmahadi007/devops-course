# Section 10 — LLM Serving Infrastructure

**Status:** in progress · **Time:** ~1.5 weeks at 2–4h/day · **Labs:** 6

This is the flagship. Section 9 left you with a full platform: a chart in git, Argo CD syncing it onto kind, CI bumping image tags through PRs. Every section so far built the *machinery*. This section puts the payload inside it — the capstone's `/ask` endpoint, a canned placeholder since Section 1, finally gets a **real, self-hosted language model**, served the same way you'd serve any other stateful backend: as a process with a port, a health probe, resource limits, and metrics.

Nothing here is about prompt engineering or model quality. This is the **serving layer** — the part a backend/infra engineer owns. It's also the part that makes this repo read as *AI-infrastructure*, not "another DevOps portfolio." (Why that matters for the job hunt: `docs/why-this-course.md`.)

## The mental model (read first)

**An LLM server is three things: a weights file, a compute loop, and a queue.** Strip away the mystique and that's the whole machine.

```
        ┌──────────────────────── the model server (one process) ────────────────────────┐
        │                                                                                 │
 HTTP   │   ┌────────┐   requests    ┌──────────────┐   one token at a time   ┌────────┐  │
 client ├──▶│ QUEUE  │ ───────────▶  │ COMPUTE LOOP │ ─────────────────────▶  │ tokens │ ──┼──▶ response
 (curl, │   │(slots) │               │  matrix mults│                          │ stream │  │
 capstone)  └────────┘               │  over WEIGHTS│                          └────────┘  │
        │                            └──────┬───────┘                                      │
        │                                   │ reads                                        │
        │                          ┌────────▼─────────┐   loaded once at startup           │
        │                          │  WEIGHTS in RAM  │   (the .gguf file, quantized)      │
        │                          │  + KV cache      │   ← grows with context length      │
        │                          └──────────────────┘                                    │
        └─────────────────────────────────────────────────────────────────────────────────┘
```

1. **The weights file** is a big array of numbers (the model's learned parameters) sitting in memory. For a 0.6-billion-parameter model that's ~0.6–1.2 GB depending on how you compress it (that compression is **quantization** — Lab 1). It loads once at startup and just *sits there*; every request reads from the same copy.

2. **The compute loop** is autoregressive: to generate text it produces **one token at a time**, and each new token requires one full pass over the weights. "Generate 200 tokens" = 200 passes. This is why generation feels like typing, not like a database query returning instantly.

3. **The queue** is how one process serves many callers. Each in-flight request occupies a **slot**; the server interleaves their compute passes (**batching** — Lab 4) so the expensive weights get read once and amortized across everyone waiting. This is the single biggest lever in serving throughput, and the thing interviews probe.

**Serving economics live in two numbers, and RAM is the wall.**

- **tokens/sec** — throughput. How fast it generates. On Apple Silicon with Metal, a 0.6B model does *hundreds* of tokens/sec; an 8B model, tens. This number is mostly bounded by **memory bandwidth**, not raw compute — decoding one token means streaming the entire weights array through the chip once, so `tokens/sec ≈ memory_bandwidth ÷ model_size_in_bytes` is a shockingly good napkin estimate (Lab 4). Bigger model = slower, linearly.
- **TTFT (time to first token)** — latency. How long before the *first* word appears. This is what a user feels. It's dominated by prompt length (the model must read your whole prompt before writing anything) and by whether your request had to wait in the queue.

And the wall behind both: **the model plus its KV cache must fit in RAM.** Weights are fixed; the **KV cache** grows with how much context each concurrent request is holding. Run out of RAM and the process is OOM-killed — exit 137, the same signal you met in Section 1 when a container blew its memory limit. Capacity planning for LLM serving is, at heart, RAM arithmetic you can do on a napkin (Labs 1 and 4).

**Why llama.cpp, and why local is the whole point.** The famous serving stacks — vLLM, TGI, SGLang — are CUDA-first: they assume an NVIDIA GPU and won't accelerate on a Mac. **llama.cpp** is the project that made CPU-and-Metal inference practical, so it's *the* Apple-Silicon path and it runs at $0 on this machine. It ships `llama-server`, which speaks the **OpenAI-compatible API** (`/v1/chat/completions`) — the same schema every hosted provider uses. That's the key infra insight: **the API is a commodity interface.** Your capstone will call `http://model:8080/v1/chat/completions` exactly as it would call OpenAI — only the base URL (an env var — 12-factor, again) changes. Self-hosted vs hosted becomes a config decision, not a code rewrite. No API keys anywhere in this section: the point is that *you* own the server.

## Why this matters for jobs

- **AI-infra / MLOps is 2026's hardest-to-fill role** (`docs/why-this-course.md`): backend + this serving layer is exactly the premium combination. Most "DevOps" candidates have never served a model; most "ML" candidates have never owned a deployment. This section is where your two lanes fuse.
- **"Walk me through serving an LLM in production"** is now a standard system-design question. Quantization trade-offs, KV cache, continuous batching, tokens/sec vs TTFT, GPU capacity math — Labs 1 and 4 are that interview, done with your hands.
- **Cost metering** — you built multi-model routing and per-request cost metering at ApplyFuel. Lab 5 rebuilds the *infra* version of that: token counters and latency histograms into the Prometheus/Grafana stack from Section 8. "I instrument LLM cost at the serving layer" is a sentence very few candidates can say truthfully.
- The flagship demo at the end: **"a self-hosted LLM, containerized, deployed to Kubernetes via my own GitOps pipeline, with token/latency dashboards and resource limits."** That single sentence is a portfolio.

## Labs

| Lab | What you build | Proves |
|---|---|---|
| [1 — GGUF, quantization & the bare server](labs/lab-01-quantization-and-bare-server.md) | `llama-server` running Qwen3-0.6B, hit by curl | quantization math, RAM napkin, OpenAI API schema |
| [2 — Wire capstone `/ask` to the model](labs/lab-02-wire-capstone-ask.md) | real `/ask`, env base URL, streaming, timeouts/retries | 12-factor config, slow-IO backend instincts for LLM calls |
| [3 — Containerize the model server](labs/lab-03-containerize-model-server.md) | model server as a compose service beside the api | bake vs mount vs init-download, image-size reality, Metal-in-container truth |
| [4 — Serving concepts (the interview lab)](labs/lab-04-serving-concepts.md) | measurements of batching, KV cache, TTFT vs tok/s | continuous batching, KV cache, vLLM/TGI/SGLang survey, GPU capacity math |
| [5 — Observability & cost metering](labs/lab-05-observability-cost.md) | token/latency metrics into the S8 stack + `/ask` cost log | LLM-serving golden signals, the ApplyFuel cost story as infra |
| [6 — Model server on Kubernetes](labs/lab-06-model-on-kind.md) | model Deployment on kind + chart grows an `llm` piece | resource limits, the flagship end-to-end demo |

Do them in order. Each ends with **Verify** (proof it worked) and **Clean up**.

## Tooling & versions (latest stable, verified 2026-07)

- **llama.cpp** via Homebrew: `brew install llama.cpp` — gives you `llama-server` and `llama-cli`, built with **Metal** (Apple's GPU framework) on Apple Silicon. The formula tracks upstream releases.
- **Container image:** `ghcr.io/ggml-org/llama.cpp:server` — official, multi-arch (amd64/arm64). Note up front: inside Docker Desktop's Linux VM there is **no Metal** — the container runs CPU-only inference (slower than the bare brew binary). Lab 3 makes you measure that gap honestly; it's a real production consideration, not a footnote.
- **Model (pinned):** `Qwen/Qwen3-0.6B-GGUF` — the official Qwen GGUF repo, an instruct/chat model with a built-in chat template, 32K context, ships `Qwen3-0.6B-Q8_0.gguf` (639 MB). For comparing quantization levels, `bartowski/Qwen_Qwen3-0.6B-GGUF` publishes `Q4_K_M` (397 MB) and others. **Swapping models is one flag** — Lab 1 shows how; any `<user>/<repo>-GGUF` on Hugging Face works. (If a newer tiny instruct GGUF is your preference by the time you run this — Qwen3.6, Llama, SmolLM, etc. — the entire section is model-agnostic; only the `-hf` value changes.)
- **Ollama** deserves a mention: it's a convenience wrapper *over the same llama.cpp engine* — nicer model management, same GGUF weights, same OpenAI-compatible API underneath. Once you understand `llama-server` directly (this section), Ollama holds no mysteries. We teach the layer below the convenience layer on purpose.
- **Host ports:** this section owns **9110–9119**. The model server is published on host **9110** (container-side stays the conventional `8080`). Anything else you publish stays inside this block.

## Reading (curated, ~1.5h total)

- [llama.cpp server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md) — the flag and endpoint reference you'll return to
- [llama.cpp Docker docs](https://github.com/ggml-org/llama.cpp/blob/master/docs/docker.md) — the image variants (server/full/light, and the accelerator flavors)
- [GGUF format & quantization (Qwen docs)](https://qwen.readthedocs.io/en/latest/quantization/gguf.html) — quant names decoded from the horse's mouth
- [OpenAI Chat Completions API](https://platform.openai.com/docs/api-reference/chat) — the schema `llama-server` mimics; read it as *the interface contract*, not an OpenAI ad
- [vLLM docs — architecture overview](https://docs.vllm.ai/en/latest/) — skim for Lab 4's survey: PagedAttention, continuous batching, why it's the GPU-serving default

## Done when

Every task in [checkpoint.md](checkpoint.md) passes from memory, and [notes.md](notes.md) is filled in your own words. This is the last building section — when it's done, Section 11 turns everything into CKA/SAA prep and two CVs.
