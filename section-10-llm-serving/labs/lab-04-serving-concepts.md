# Lab 4 — Serving concepts (the interview lab)

**Goal:** the theory that separates "I ran a model" from "I understand serving." You'll *measure* continuous batching and the KV cache on your own machine, learn the napkin math for GPU capacity, and get a straight survey of vLLM / TGI / SGLang and why llama.cpp is the Apple-Silicon path. This is the lab that becomes a system-design interview answer.

## The mental map (read this first)

Four ideas, each a common interview question:

**1. Continuous batching — the throughput lever.** Recall from the section intro: generating one token means reading the *entire* weights array out of memory once. If one request is generating, that expensive read is "wasted" on a single user. **Batching** runs many requests through the *same* weight-read simultaneously — the bytes stream through the chip once and serve everyone in the batch. **Continuous** (a.k.a. in-flight) batching goes further: instead of waiting for a whole batch to finish before starting the next (static batching, where one slow request stalls everyone), it adds and removes requests from the running batch token-by-token. A finished request frees its slot instantly; a new one joins mid-flight.

```
 STATIC batching                        CONTINUOUS batching
 req A ████████░░░░ (waits for B)        req A ████████        (leaves, slot freed)
 req B ████████████                      req B ████████████
 req C ░░░░░░░░████ (waited for batch)   req C   ██████████    (joined mid-flight)
        └ slot idle while others run            └ no idle slots → higher utilization
```

The payoff: **aggregate tokens/sec goes UP with concurrency** (up to a limit), even though each *individual* request may get slightly slower. You'll watch this happen.

**2. KV cache — the memory that grows.** When the model generates token 200, it needs to "remember" tokens 1–199. Recomputing them every step would be quadratic and insane. Instead it caches the intermediate key/value tensors for every prior token — the **KV cache**. It grows linearly with context length *and* with the number of concurrent requests, and it's the thing that actually runs you out of memory. Napkin:

```
 KV cache per token ≈ 2 (K and V) × n_layers × kv_dim × bytes_per_elem
 total KV ≈ (per-token) × context_length × concurrent_requests
```

For a 0.6B model it's megabytes — invisible. For an 8B model it's the story (worked below). Weights are fixed; **KV is what your batch size trades against.**

**3. TTFT vs tokens/sec — two different clocks.** These get conflated constantly and interviewers separate the sheep from the goats on it:

- **TTFT (time to first token)** = prefill latency: the model reads your whole prompt (one big parallel pass) before emitting anything. Long prompt → long TTFT. Queue wait adds to it.
- **tokens/sec** = decode throughput: how fast tokens come *after* the first. Memory-bandwidth-bound (section intro).

A long document summarization has high TTFT but the tok/s can be fine. A short-prompt chat has tiny TTFT. You tune for different ones depending on the workload — and batching *helps tok/s but can hurt TTFT* (a joining request waits for the current step). Trade-offs everywhere.

**4. The engines.** vLLM / TGI / SGLath are the production GPU stacks; llama.cpp is the portable one. Survey in step 5.

## Steps

### 1. Restart the bare server with multiple slots

Use the bare (Metal) server so the numbers are clean. The new flags expose batching:

```bash
llama-server \
  -hf Qwen/Qwen3-0.6B-GGUF:Q8_0 \
  --host 127.0.0.1 --port 9110 \
  -c 8192 \
  -np 4 -cb \
  --metrics --jinja
```

#### The batching flags

- **`-np 4`** — **parallel slots**: the server can hold 4 requests in flight at once. Each slot gets `context ÷ np` of the KV budget, so `-c 8192 -np 4` = 2048 tokens of context per slot. (This is why context and parallelism are linked: more slots means less room per slot, unless you also raise `-c` — and raising `-c` costs KV-cache RAM.)
- **`-cb`** — **continuous batching**: enable the in-flight scheduler described above. Modern llama.cpp often defaults this on, but set it explicitly so you know it's active.
- **`--metrics`** — Prometheus `/metrics` (used here to read counters, and in Lab 5 to graph them).

### 2. Watch the slots

```bash
curl -s localhost:9110/slots | python3 -m json.tool | head -40
```

`/slots` shows each of the 4 slots and its state (`idle`/`processing`), how many prompt tokens it's holding, etc. Right now all idle. Keep this handy — you'll re-run it under load.

### 3. Measure batching: 1 request vs 8 concurrent

Save this helper as `bench.py` (a throwaway measurement script — not part of capstone):

```python
"""Fire N concurrent chat requests, report wall time and aggregate tokens/sec."""
import asyncio, sys, time, httpx

N = int(sys.argv[1]) if len(sys.argv) > 1 else 1
URL = "http://localhost:9110/v1/chat/completions"
PAYLOAD = {"model": "q", "messages": [{"role": "user", "content": "Write two sentences about TCP."}], "max_tokens": 120}

async def one(client):
    r = await client.post(URL, json=PAYLOAD)
    d = r.json()
    return d["usage"]["completion_tokens"]

async def main():
    async with httpx.AsyncClient(timeout=120) as client:
        t0 = time.time()
        counts = await asyncio.gather(*[one(client) for _ in range(N)])
        dt = time.time() - t0
    total = sum(counts)
    print(f"N={N}  wall={dt:.2f}s  total_tokens={total}  aggregate_tok/s={total/dt:.1f}")

asyncio.run(main())
```

Run it at increasing concurrency (needs `httpx` — use the capstone venv: `cd capstone && uv run python ../section-10-llm-serving/bench.py 1`, adjusting the path, or `pip install httpx` in a throwaway venv):

```bash
uv run python bench.py 1
uv run python bench.py 4
uv run python bench.py 8
```

While the `8` run is going, in another terminal spam `curl -s localhost:9110/slots | grep -c processing` and you'll see multiple slots busy at once.

#### Reading the numbers

```
N=1  wall=0.55s  total_tokens=118  aggregate_tok/s=214.5
N=4  wall=0.98s  total_tokens=470  aggregate_tok/s=479.6   ← ~2.2× the single-stream rate
N=8  wall=1.9s   total_tokens=940  aggregate_tok/s=494.7   ← plateaus past the slot count (-np 4)
```

(Exact numbers vary by chip — the *shape* is the lesson.) Three things to read:

- **Aggregate tok/s rose well above the single-request rate** — that's continuous batching amortizing the weight-read across concurrent requests. The single expensive memory pass now serves 4 users.
- **It plateaued past `-np 4`** — you only have 4 slots. Request 5–8 queue and wait, so throughput stops climbing and *per-request* latency rises. Raise `-np` (and `-c` to keep per-slot context) to push the plateau higher — until you run out of RAM for KV cache. That ceiling is the capacity-planning wall.
- **Per-request wall time got a little worse at N=4 than N=1** — the TTFT-vs-throughput trade: batching maximizes total tokens/sec at the cost of some individual latency. Which you optimize depends on whether you're serving one interactive user or a fleet.

### 4. KV cache napkin — why 0.6B is free and 8B is not

Your 0.6B model's KV cache is a few MB — you never noticed it. Scale the formula to a real model. Take **Llama-3-8B** (32 layers, hidden 4096, GQA with kv_dim ≈ 1024), FP16 KV:

```
 per-token KV = 2 × 32 layers × 1024 kv_dim × 2 bytes ≈ 131 KB / token
 at   8,192 context, 1 request  → 131KB × 8192      ≈ 1.07 GB
 at   8,192 context, 16 requests → × 16             ≈ 17.2 GB   ← now KV rivals the 8GB of weights
```

That's the whole "why serving is a memory problem" story in three lines: **weights are fixed, KV cache is what your concurrency buys you, and it can dwarf the model.** vLLM's famous trick (**PagedAttention**) is literally a virtual-memory-style pager for the KV cache so it doesn't fragment and waste this scarce space — that's why it serves far more concurrent requests per GPU than naive implementations.

### 5. GPU capacity napkin + the engine survey

**Capacity napkin** — total VRAM needed to serve a model:

```
 VRAM ≈ weights + (KV per request × max concurrent requests) + ~1-2GB overhead

 e.g. Llama-3-8B, Q8 weights (~8GB), 8k ctx, 16 concurrent:
      8GB + (1GB × 16) + 2GB ≈ 26GB  → needs a 24GB card with modest batch, or a 40/80GB card
      70B model, FP16 (~140GB)       → does NOT fit one GPU; needs tensor-parallel across several
```

This is the exact reasoning a hiring manager wants when they ask "how many GPUs to serve model X at Y concurrent users." Now the engines:

| Engine | Hardware | Best at | Why you'd pick it |
|---|---|---|---|
| **vLLM** | NVIDIA GPU (CUDA) | high-throughput serving | PagedAttention + continuous batching; the default production choice for GPU serving |
| **TGI** (Text Generation Inference, HF) | NVIDIA GPU (+ others) | HF-ecosystem serving | tight Hugging Face integration, production-hardened, good streaming |
| **SGLang** | NVIDIA GPU | complex/structured generation | fast for multi-turn, tool-use, structured output (RadixAttention prefix caching) |
| **llama.cpp** | **CPU / Metal / anything** | portability, edge, Apple Silicon | runs where CUDA can't — the reason it's *this course's* engine |
| **Ollama** | wraps llama.cpp | dev convenience | model management UX over the same engine — not a new serving tech |

The honest framing for interviews: **vLLM/TGI/SGLang are CUDA-first and won't accelerate on a Mac** — that's *why* llama.cpp is the Apple-Silicon path and the right call for a $0 local course. On a real GPU box you'd reach for vLLM for raw throughput. Knowing *when each applies* (and that Ollama is a wrapper, not a competitor) is the signal that you've actually done serving, not just read about it.

## Verify

- Your `bench.py` shows aggregate tokens/sec rising with concurrency up to `-np`, then plateauing; `/slots` shows multiple slots `processing` under load.
- You can answer, out loud, without looking:

- What is continuous batching, and why does aggregate tokens/sec rise with concurrency?

  <details><summary>Answer (read after attempting aloud)</summary>

  Each decode step reads the entire weights array once. Batching runs multiple requests through that single read, so the expensive memory pass is amortized across all of them — aggregate throughput rises. *Continuous* (in-flight) batching adds/removes requests from the running batch token-by-token instead of waiting for a whole batch to drain, so slots never sit idle. Throughput climbs until you hit the slot count / KV-cache RAM ceiling.

  </details>

- What is the KV cache, what does it grow with, and why does it matter more than the weights at scale?

  <details><summary>Answer (read after attempting aloud)</summary>

  It caches the key/value tensors for every already-generated token so the model doesn't recompute the whole sequence each step. It grows linearly with context length and with concurrent requests. Weights are a fixed cost; KV is variable and, at long context × high concurrency, can exceed the weights themselves — so it's the real driver of "how many concurrent users fit on this GPU." (PagedAttention exists to use it efficiently.)

  </details>

- TTFT vs tokens/sec — define each and name what dominates it.

  <details><summary>Answer (read after attempting aloud)</summary>

  TTFT (time to first token) is prefill latency: the model must read the whole prompt before emitting the first token, so it's dominated by prompt length plus any queue wait. Tokens/sec is decode throughput after the first token, dominated by memory bandwidth (and helped by batching). A long prompt hurts TTFT but not necessarily tok/s; batching helps tok/s but can hurt an individual request's TTFT.

  </details>

- Why can't you just run vLLM on your Mac, and what does that imply about llama.cpp?

  <details><summary>Answer (read after attempting aloud)</summary>

  vLLM (and TGI, SGLang) are CUDA-first — they target NVIDIA GPUs and won't use Apple's Metal GPU, so on a Mac they'd be CPU-only or not run at all. llama.cpp was built for portability (CPU, Metal, CUDA, Vulkan…), which makes it *the* Apple-Silicon path and the correct engine for a $0 local course. On a real GPU box you'd pick vLLM for throughput; the skill is knowing which fits the hardware.

  </details>

## Clean up

`Ctrl-C` the server. Delete the throwaway `bench.py` (`rm bench.py`) — or keep it around for Lab 5's load generation. Nothing to commit (this lab is measurement + theory). If you want a portfolio artifact, jot your machine's N=1/4/8 numbers into `notes.md`.
