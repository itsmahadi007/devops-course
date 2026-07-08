# Lab 1 — GGUF, quantization, and the bare model server

**Goal:** understand what a `.gguf` weights file actually *is* (and the RAM math you can do on a napkin), then run `llama-server` bare-metal on your Mac, and hit its OpenAI-compatible API with `curl`. By the end you have a real language model answering HTTP requests on host port `9110` — the thing Lab 2 wires the capstone into.

## The mental map (read this first)

Two ideas before you run anything: **what a GGUF file holds**, and **why quantization is the lever that makes tiny models runnable**.

A model's "weights" are just a huge list of numbers — the parameters it learned during training. A 0.6-billion-parameter model has 0.6 billion of them. Store each number as a full 16-bit float (`FP16`, 2 bytes) and the file is `0.6e9 × 2 ≈ 1.2 GB`. **Quantization** shrinks each number to fewer bits — trading a little accuracy for a lot of RAM:

```
 one weight, stored three ways        bytes/param     0.6B model      what you lose
 ───────────────────────────────      ───────────     ──────────      ─────────────
 FP16  (training precision)           2.0             ~1.2 GB         nothing (baseline)
 Q8_0  (8-bit)                        ~1.06           ~0.64 GB        almost nothing
 Q4_K_M (4-bit, "K-quant medium")     ~0.56           ~0.40 GB        a little, rarely noticeable
 Q2_K  (2-bit)                        ~0.33           ~0.24 GB        real, often too much
```

The rule of thumb interviewers want to hear: **`file_size ≈ params × bytes_per_param`.** Q8 is ~1 byte/param, Q4 is ~0.5 byte/param. That's why the official `Qwen3-0.6B-Q8_0.gguf` is 639 MB (≈ 0.6e9 × 1.06) and the Q4_K_M is 397 MB — you can predict both from the params and the quant name. The `_K_` variants ("K-quants") are smarter than plain `Q4_0`: they spend more bits on the layers that matter and fewer on the rest, so `Q4_K_M` punches above its size. For a small model, **Q4_K_M or Q8_0 is the sweet spot** — go below Q4 only when RAM is truly scarce.

**GGUF** is the file format that packs all this into one file: the quantized weights *plus* the metadata (architecture, tokenizer, and the **chat template** — the exact string format the model was trained to expect turns/roles in). That last part is why `llama-server` can accept OpenAI-style `messages: [{role, content}]` and render them correctly: the template travels *inside* the file.

Now the RAM napkin — total footprint is **weights + KV cache + a little overhead**:

```
 TOTAL RAM ≈  weights (fixed, from the file)
            + KV cache (grows with context × concurrent requests)
            + ~a few hundred MB runtime overhead

 KV cache is the model's "short-term memory" of the conversation so far.
 For a 0.6B model it's tiny (megabytes). For an 8B model at long context
 it can rival the weights themselves — which is why Lab 4 comes back to it.
```

For this lab the whole thing fits in well under 1 GB — trivial on your Mac. Lab 4 scales the same arithmetic up to "why an 8B model wants a GPU."

Where the server sits:

```
 your Mac (Apple Silicon, Metal GPU)
      │
 localhost:9110  ── you publish here (this section's port block)
      │
 ┌────▼─────────────────────────────────────────┐
 │ llama-server (one native process, brew-built) │
 │  • loaded: Qwen3-0.6B-Q8_0.gguf  (~640 MB)    │
 │  • Metal: offloads compute to the GPU         │
 │  • serves /v1/chat/completions  (OpenAI API)  │
 └───────────────────────────────────────────────┘
```

## Steps

### 1. Install llama.cpp

```bash
brew install llama.cpp
```

This installs `llama-server` and `llama-cli`, compiled with **Metal** — on Apple Silicon that means inference runs on the GPU cores, not just the CPU. Verify:

```bash
llama-server --version
```

#### What you'll see

A version/build line like `version: 6xxx (…)` and a build target mentioning your platform. You don't need to memorize the number — the point is the binary exists and is on your PATH (Homebrew's `/opt/homebrew/bin`, which you met in Section 1's PATH anatomy). If `command not found`, `brew link llama.cpp` or open a new shell so PATH refreshes.

### 2. Launch the server — it downloads the model for you

`llama-server` can pull a GGUF straight from Hugging Face with `-hf`, so you don't hand-manage files:

```bash
llama-server \
  -hf Qwen/Qwen3-0.6B-GGUF:Q8_0 \
  --host 127.0.0.1 --port 9110 \
  -c 4096 \
  --jinja
```

Leave this running in its own terminal (it holds the foreground — like `daemon off;` from Section 1, a server process belongs in the foreground). Open a **second** terminal for the curl calls in step 3.

#### Every flag, decoded

- **`-hf Qwen/Qwen3-0.6B-GGUF:Q8_0`** — "download this repo's `Q8_0` file from Hugging Face and load it." The part after `:` is the quant tag; swap it to `Q4_K_M` (from a repo that has it, e.g. `-hf bartowski/Qwen_Qwen3-0.6B-GGUF:Q4_K_M`) to load the smaller one. First run downloads to `~/.cache/llama.cpp`; later runs reuse it (same content-addressed caching idea as Docker layers). **This one flag is your model swap** — any `<user>/<repo>-GGUF:<quant>` works.
- **`--host 127.0.0.1`** — bind to loopback only; nothing outside your Mac can reach it. (In Lab 3's container you'll switch to `0.0.0.0` for the same reason CMD did in Section 1: traffic must cross the container's network wall. Bare on your laptop, loopback is the safer default.)
- **`--port 9110`** — this section's published port. The brew binary defaults to 8080; we move it to 9110 to stay in the block and off your real dev stack.
- **`-c 4096`** — context size: the max tokens (prompt + generated) the server will hold per request. Bigger = more KV-cache RAM. 4096 is plenty for `/ask` and keeps memory tiny; the model itself supports 32K.
- **`--jinja`** — use the chat template baked into the GGUF (a Jinja template) to format `messages` into the exact prompt string the model was trained on. Without it, `/v1/chat/completions` may format turns generically and you'll get worse answers. For a chat/instruct model, **always `--jinja`**.

#### What the startup log tells you

Read it like Section 1's build logs — every line is evidence:

```
llama_model_loader: loaded meta data ... Qwen3 ...
print_info: file size = 639.xx MiB              ← the weights, exactly the number you predicted
llama_kv_cache: size =  xx.xx MiB               ← KV cache reserved for -c 4096
ggml_metal_init: found device: Apple M...       ← Metal is active — GPU offload, not CPU-only
main: server is listening on http://127.0.0.1:9110  ← ready
```

- **`file size = 639 MiB`** — confirms the Q8 napkin math live. That RAM is now resident and stays put.
- **`ggml_metal_init: found device`** — the proof you're on the GPU path. In Lab 3's container this line disappears (no Metal in the VM) and you'll feel it in tokens/sec.
- **`server is listening`** — only *now* is the port open. If you curl before this line prints, you'll get connection-refused — the "started ≠ ready" race from Section 1, at model scale (a big model can take tens of seconds to load; this tiny one is near-instant).

#### If it fails

- **`error while loading ... / failed to load model`** or a download error → usually a typo in the repo id or quant tag, or no network on first pull. The repo is `Qwen/Qwen3-0.6B-GGUF` and the tag is `Q8_0` (case matters). Re-run; the partial download resumes.
- **`bind: address already in use` (errno 48)** → something else holds 9110. `lsof -ti :9110` to find it; pick another port in 9110–9119. (Same host-port lesson as Section 1.)
- **Killed / OOM** on a bigger model → you asked for more RAM than free. This 0.6B model won't do it, but it's the exit-137 wall the mental model warned about — remember it for Lab 4.

### 3. Hit the OpenAI-compatible API

In the second terminal. First the trivial health check (a *native* endpoint, not OpenAI):

```bash
curl -s localhost:9110/health
```

Expect `{"status":"ok"}` — the same shape as your capstone's `/health`, and the thing Kubernetes will probe in Lab 6.

Now the real call — the **OpenAI Chat Completions** schema, byte-for-byte what you'd send a hosted provider:

```bash
curl -s localhost:9110/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen",
    "messages": [
      {"role": "user", "content": "In one sentence, what is a reverse proxy?"}
    ],
    "max_tokens": 100
  }' | python3 -m json.tool
```

#### Reading the response

You'll get the familiar OpenAI envelope:

```json
{
  "choices": [
    { "message": { "role": "assistant", "content": "A reverse proxy is ..." },
      "finish_reason": "stop" }
  ],
  "usage": { "prompt_tokens": 18, "completion_tokens": 42, "total_tokens": 60 },
  "timings": { "predicted_per_second": 210.4, ... }
}
```

- **`choices[0].message.content`** — the answer. This exact path is what capstone's `/ask` will pull out in Lab 2.
- **`model: "qwen"`** — note it can be *any* string. A self-hosted server serves whatever it loaded; the field is ignored for routing. (Hosted APIs use it to pick a model — the interface is identical, the semantics differ.)
- **`usage`** — token counts. This is the raw material for cost metering in Lab 5 — the infra version of what you built at ApplyFuel.
- **`timings.predicted_per_second`** — llama.cpp's own **tokens/sec** measurement. On Apple-Silicon Metal, a 0.6B model typically lands in the **~150–300 tok/s** range (varies by chip — an M1 is slower than an M4). That's your baseline; Lab 3's CPU container will be markedly lower, and Lab 4 explains why the number is what it is.

### 4. Feel streaming (optional but worth 30 seconds)

Add `"stream": true` and the server sends tokens as **Server-Sent Events** (`data: {…}` chunks) instead of one final blob:

```bash
curl -s -N localhost:9110/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen","messages":[{"role":"user","content":"Count to five slowly."}],"stream":true}'
```

`-N` disables curl's buffering so you see chunks arrive live. You'll watch `data: {"choices":[{"delta":{"content":"one"}}]}` lines stream in, ending with `data: [DONE]`. This is *why* chatbots type word-by-word — and Lab 2 makes capstone choose between streaming and waiting for the whole answer. The key infra insight: streaming trades a single slow response for many fast chunks, which drops perceived latency (TTFT) even though total time is the same.

## Verify

- `curl -s localhost:9110/health` returns `{"status":"ok"}`, and a chat-completions call returns an `assistant` message with a `usage` block.
- You can answer, out loud, without looking:

- Your model file is 639 MB. How many parameters, roughly, and how did you know from the filename?

  <details><summary>Answer (read after attempting aloud)</summary>

  The quant is `Q8_0` ≈ 1 byte per parameter, so `file_size ≈ params × 1 byte` → ~640 million params → 0.6B, matching `Qwen3-0.6B`. Q8 is roughly 1 byte/param, Q4 roughly 0.5, FP16 exactly 2. `file_size ≈ params × bytes_per_param` predicts the size from the name (and vice-versa) — the napkin every serving interview wants.

  </details>

- What does `--jinja` do, and what does the chat template have to do with the GGUF file?

  <details><summary>Answer (read after attempting aloud)</summary>

  The chat template is the exact string format (special tokens marking system/user/assistant turns) the model was trained on. It's stored *inside* the GGUF as metadata. `--jinja` tells the server to render incoming OpenAI `messages` through that template so the model sees prompts in its native format. Skip it on a chat model and you get generically-formatted prompts and worse answers.

  </details>

- The `model` field in the request was `"qwen"` — a made-up string. Why did it work?

  <details><summary>Answer (read after attempting aloud)</summary>

  A self-hosted `llama-server` serves exactly one model — whatever GGUF it loaded at startup. The `model` field is part of the OpenAI schema for *routing* on multi-model hosted APIs; a single-model server ignores its value. The endpoint is API-compatible, so the field must be *present*, but its content doesn't matter here.

  </details>

- Why is tokens/sec mostly a memory-bandwidth story, not a compute story?

  <details><summary>Answer (read after attempting aloud)</summary>

  Generating each token requires one pass reading the *entire* weights array out of memory. Single-stream decoding is therefore bounded by how fast the chip can stream those bytes — memory bandwidth — far more than by arithmetic throughput. So `tokens/sec ≈ memory_bandwidth ÷ model_size_bytes` is a good estimate, and a model twice as big is ~half as fast. (Batching many requests amortizes that read — Lab 4.)

  </details>

## Clean up

Stop the server with `Ctrl-C` in its terminal (it's PID 1 of nothing — just a foreground process; SIGINT stops it cleanly). The downloaded model stays cached in `~/.cache/llama.cpp` — leave it; Labs 2–5 reuse it. To reclaim the ~640 MB later: `rm -rf ~/.cache/llama.cpp`.

Nothing to commit this lab — it's all local runtime. Lab 2 is where code changes begin.
