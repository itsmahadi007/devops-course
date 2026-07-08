# Checkpoint — Section 10: LLM Serving Infrastructure

Pass every task **from memory** — no peeking at the labs. If you have to peek, the section isn't done yet; redo that lab tomorrow and try again.

## Practical tasks

- [ ] **1.** From nothing, launch `llama-server` with a GGUF pulled from Hugging Face, on a port in this section's block, with the chat template enabled — and hit `/v1/chat/completions` with curl, reading `usage` and tokens/sec out of the response. Under 5 minutes, no references.
- [ ] **2.** Given only a GGUF filename and quant tag (e.g. `...-Q4_K_M.gguf`), state the approximate parameter count and file size, and explain the arithmetic.
- [ ] **3.** Point capstone's `/ask` at a model server via an env var, then re-point it at a *different* base URL — with zero code changes — and prove both work.
- [ ] **4.** Write, from scratch, the timeout/retry policy for an LLM HTTP call and defend every choice (connect vs read timeout, what you retry and what you never retry).
- [ ] **5.** Add a model server to the compose stack using the init-download pattern (cache volume), wire the api to it by service DNS, and prove the full `/ask` chain works.
- [ ] **6.** Add a token + cost + latency metric to `/ask`, drive load, and read tokens/sec, p95 latency, and cost burn from PromQL.
- [ ] **7.** Deploy the model server to kind as a Deployment with resource limits, trigger an `OOMKilled`, read the exit code and reason, then fix it.

## Explain aloud (interview drill — answer in 60–90 seconds each)

- [ ] What are the three parts of an LLM server (weights / compute loop / queue), and what does each do?
- [ ] Predict a model's file size from its parameter count and quant, and vice-versa. Q8 vs Q4_K_M vs FP16 — bytes per param and what you trade.
- [ ] Why is single-stream tokens/sec a *memory-bandwidth* story? Give the napkin estimate and why a 2× bigger model is ~half as fast.
- [ ] TTFT vs tokens/sec: define each, name what dominates it, and give a workload where they diverge.
- [ ] What is continuous batching? Why does aggregate throughput rise with concurrency, and what caps it?
- [ ] What is the KV cache, what does it grow with, and why does it — not the weights — decide how many concurrent users fit on a GPU?
- [ ] GPU capacity napkin: how much VRAM to serve an 8B model at N concurrent requests? Walk the terms.
- [ ] vLLM / TGI / SGLang / llama.cpp / Ollama — one line each on what it's for, and why llama.cpp is the Apple-Silicon path.
- [ ] Why is "self-hosted vs hosted" a config decision and not a code rewrite? What makes the OpenAI-compatible API the key to that?
- [ ] For an LLM HTTP call: why asymmetric timeouts, and why retry a connect error but never a read timeout?
- [ ] Bake vs mount vs init-download for model weights — the trade-off of each and when you'd pick it.
- [ ] Why is a containerized model slower than the bare one on a Mac? What's the real-server fix, and why doesn't it apply to Docker Desktop?
- [ ] How do you meter cost for a *self-hosted* model that has no per-token invoice, and why does that approach make hosted vs self-hosted comparable on one dashboard?
- [ ] For a model pod on Kubernetes: `requests` vs `limits`, and exactly what happens (and what you'd see) when it exceeds the memory limit.
- [ ] Why an initContainer for weights, and why does the model pod sit at `0/1 Running` before it's `READY`?

## Gate

- [ ] `notes.md` filled in my own words
- [ ] Everything committed (updated `main.py`, `pyproject.toml`, `uv.lock`, `docker-compose.yml`, chart changes, Prometheus scrape config — no keys, no baked model weights in git)
- [ ] The flagship writeup drafted (Lab 6's closing task) — the paragraph that becomes LinkedIn + CV material

When all boxes are checked, say so — this is the last building section. Section 11 (Cert Prep + Market Entry) turns everything into CKA/SAA readiness and two CV variants.
