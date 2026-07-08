# Lab 2 — Wire capstone `/ask` to the model server

**Goal:** replace the canned `/ask` placeholder with a real call to the model server from Lab 1. The base URL comes from an env var (12-factor, again), you'll add both non-streaming and streaming variants, and you'll set the timeout/retry policy that LLM calls demand — because an LLM call is the slowest, flakiest piece of IO your backend will ever make, and your backend instincts apply directly.

## The mental map (read this first)

Since Section 1, `/ask` has returned a hard-coded sentence. Now it becomes a **client of the model server** — capstone is just another HTTP caller of the OpenAI-compatible API you hit with curl in Lab 1.

```
 client ──▶ capstone /ask ──HTTP──▶ llama-server /v1/chat/completions ──▶ answer
                 │                        (Lab 1, on :9110)
                 │ base URL comes from an ENV VAR:
                 │   LLM_BASE_URL=http://localhost:9110/v1   (bare, this lab)
                 │   LLM_BASE_URL=http://model:8080/v1       (compose, Lab 3 — service DNS)
                 │   LLM_BASE_URL=https://api.openai.com/v1  (hosted — same code!)
                 ▼
        the ONLY thing that changes between self-hosted and hosted is this string
```

That env var is the whole thesis of the section: **self-hosted vs hosted is a config decision, not a code change.** The same `httpx` call works against your `llama-server`, a compose neighbor, a Kubernetes Service, or OpenAI — because they all speak the same schema (Section 1's 12-factor lesson, now paying off for AI infra).

Three things make LLM calls different from the Redis/Postgres calls capstone already makes, and each drives a design choice:

1. **They're slow — seconds, not milliseconds.** A DB query is ~1 ms; generating 200 tokens is ~1 second even on a fast local model, and much longer for big models or long outputs. So the **read timeout must be generous** (tens of seconds), while the **connect timeout stays short** (a dead server should fail fast, not hang).
2. **They're a stream, not an atomic result.** Generation is token-by-token (Lab 1). You can wait for the whole thing (simpler) or forward tokens as they arrive (better perceived latency). You'll build both.
3. **Retries are dangerous.** Retrying a *connection* failure is safe (nothing happened yet). Retrying a call that already started generating means you pay twice and may double-answer. So: **retry the connect, never the read.** This is the backend "idempotency vs side-effects" instinct, applied to tokens.

## Steps

### 1. Add the HTTP client dependency

`/ask` needs an HTTP client. Add `httpx` (async, the modern choice, and what FastAPI's own `TestClient` uses) to `capstone/pyproject.toml`:

```toml
[project]
name = "capstone"
version = "0.1.0"
description = "The app this course practices DevOps on — evolves every section"
requires-python = ">=3.14"
dependencies = [
    "fastapi>=0.115",
    "uvicorn>=0.34",
    "redis>=5.2",
    "httpx>=0.28",
]

[tool.uv]
package = false
```

Then re-lock so the build stays reproducible (Section 1's `--frozen` lesson — the lockfile is law):

```bash
cd capstone
uv lock
```

`uv.lock` now pins `httpx` and its transitive deps. Commit it alongside `pyproject.toml`.

### 2. Rewrite `capstone/app/main.py`

Full new file — replace the whole thing. Read the comments; the LLM-specific reasoning is unpacked below it.

```python
"""Capstone service — deliberately tiny. The DevOps around it is the course."""

import os

import httpx
import redis
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

app = FastAPI(title="capstone")

REDIS_URL = os.environ.get("REDIS_URL", "")

# ── LLM serving config (Section 10) — all 12-factor, no code change to swap backends ──
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:9110/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen")  # ignored by single-model llama-server
# Slow IO: short connect (fail fast on a dead server), long read (generation takes seconds).
LLM_TIMEOUT = httpx.Timeout(connect=3.0, read=60.0, write=10.0, pool=3.0)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/visits")
def visits() -> dict:
    if not REDIS_URL:
        return {"visits": None, "detail": "REDIS_URL not set"}
    r = redis.Redis.from_url(REDIS_URL, socket_connect_timeout=2)
    return {"visits": r.incr("visits")}


def _chat_payload(q: str, stream: bool) -> dict:
    return {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": q}],
        "max_tokens": 256,
        "stream": stream,
    }


@app.get("/ask")
async def ask(q: str = "") -> dict:
    """Non-streaming: wait for the full answer, return it as JSON."""
    if not q:
        return {"question": q, "answer": "", "detail": "pass ?q=your+question"}

    url = f"{LLM_BASE_URL}/chat/completions"
    # Retry the CONNECT (safe — nothing generated yet), never the read.
    last_err = None
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
                resp = await client.post(url, json=_chat_payload(q, stream=False))
                resp.raise_for_status()
                data = resp.json()
                return {
                    "question": q,
                    "answer": data["choices"][0]["message"]["content"],
                    "usage": data.get("usage", {}),
                }
        except httpx.ConnectError as e:  # server down/not ready — safe to retry
            last_err = e
            continue
        except httpx.HTTPError as e:  # read timeout, bad status — do NOT retry
            return {"question": q, "answer": "", "detail": f"model error: {e}"}
    return {"question": q, "answer": "", "detail": f"model unreachable: {last_err}"}


@app.get("/ask/stream")
async def ask_stream(q: str = "") -> StreamingResponse:
    """Streaming: forward tokens to the client as they are generated (low TTFT)."""

    async def token_stream():
        url = f"{LLM_BASE_URL}/chat/completions"
        async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
            async with client.stream("POST", url, json=_chat_payload(q, stream=True)) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        yield line[len("data: "):] + "\n"

    return StreamingResponse(token_stream(), media_type="text/event-stream")
```

#### Why this shape — the LLM-specific bits

- **`LLM_BASE_URL` default `http://localhost:9110/v1`** — points at Lab 1's bare server so this lab works with zero env setup. Lab 3 overrides it to `http://model:8080/v1` via compose; nothing in the code changes. That's the interface-is-a-commodity payoff.
- **`httpx.Timeout(connect=3.0, read=60.0, …)`** — the asymmetry *is* the lesson. A dead server should fail in 3 s, not hang. But a live server generating 256 tokens legitimately needs many seconds, so `read=60`. One flat timeout can't express "fail fast to connect, be patient once talking" — LLM IO needs the split.
- **The retry loop retries only `ConnectError`** — a connect failure means the request never reached the model, so re-sending is free and idempotent (the "started ≠ ready" race from Section 1 — the server may still be loading weights). A `read` timeout or a 5xx *after* generation began is **not** retried: you'd pay for tokens twice and might get a doubled answer. This is your backend side-effects instinct, translated to tokens.
- **`raise_for_status()`** — turns a 4xx/5xx from the model into an exception you handle, instead of blindly reading `choices` off an error body and `KeyError`-ing.
- **`/ask/stream` uses `client.stream(...)` + `StreamingResponse`** — capstone becomes a *pass-through* for the model's SSE chunks. The client sees the first token in ~TTFT instead of waiting for all 256. `aiter_lines()` reads the `data: {…}` events (Lab 1's stream format) as they arrive and forwards each. This is exactly how a chat UI types word-by-word through a backend.

### 3. Run it against the bare server

Terminal A — the model (from Lab 1):

```bash
llama-server -hf Qwen/Qwen3-0.6B-GGUF:Q8_0 --host 127.0.0.1 --port 9110 -c 4096 --jinja
```

Terminal B — capstone, run locally with uv (no container this lab — that's Lab 3):

```bash
cd capstone
uv run uvicorn app.main:app --port 9010
```

#### Why port 9010 and no REDIS_URL

You're running capstone bare for this lab, just to exercise `/ask`. `9010` keeps you off your dev stack; `/visits` will report `REDIS_URL not set` (harmless — no Redis running). `LLM_BASE_URL` isn't set either, so it falls back to the `localhost:9110` default — which is exactly where Terminal A is listening. Config defaults doing their job.

### 4. Ask it something

Terminal C:

```bash
curl -s "localhost:9010/ask?q=what+is+a+load+balancer%3F" | python3 -m json.tool
```

#### Reading the response

```json
{
  "question": "what is a load balancer?",
  "answer": "A load balancer distributes incoming traffic across ...",
  "usage": { "prompt_tokens": 15, "completion_tokens": 88, "total_tokens": 103 }
}
```

The `answer` is real model output, pulled from `choices[0].message.content`. The `usage` block rides along — you're already carrying the token counts that Lab 5 turns into cost metrics. The placeholder from Section 1 is gone.

Now the streaming variant — watch tokens arrive live:

```bash
curl -s -N "localhost:9010/ask/stream?q=list+three+load+balancing+algorithms"
```

`-N` again disables buffering. You'll see `{"choices":[{"delta":{"content":"Round"}}]}` chunks stream in, ending with `[DONE]`. Same total time as `/ask`, but the first token shows up almost immediately — that's TTFT winning the perceived-latency game.

#### If it misbehaves

- **`{"detail":"model unreachable: ..."}`** → Terminal A isn't listening on 9110 yet (still loading, or crashed). Check its log for `server is listening`. This is the retry loop correctly giving up on a connect that never succeeds.
- **`{"detail":"model error: ... Read timed out"}`** → generation took >60 s. Won't happen with a 0.6B model and `max_tokens: 256`, but if you crank `max_tokens` to thousands on a slow machine you'd hit it — and note the code *doesn't* retry it, on purpose.
- **`KeyError: 'choices'`** would mean the model returned an error body you tried to parse as success — `raise_for_status()` is there precisely to convert that into the clean `model error` path instead.

## Verify

- `/ask?q=...` returns a real, model-generated `answer` plus a `usage` block; `/ask/stream` streams tokens with visibly lower time-to-first-token.
- You can answer, out loud, without looking:

- Why is the connect timeout 3 s but the read timeout 60 s?

  <details><summary>Answer (read after attempting aloud)</summary>

  Different failure modes. A connection that can't be established means the server is down or unreachable — fail fast (3 s) so callers aren't left hanging. But once connected, the server is *legitimately* slow: generating tokens takes seconds to tens of seconds, so a short read timeout would kill healthy requests. LLM IO needs the asymmetry; one flat timeout can't serve both.

  </details>

- You retry on `ConnectError` but not on a read timeout. Why is that the correct rule?

  <details><summary>Answer (read after attempting aloud)</summary>

  A connect failure means the request never reached the model — nothing was generated, so re-sending is safe and idempotent (and covers the server-still-loading race). A read timeout or a post-start error means generation may have already begun — retrying pays for tokens twice and can produce a doubled/garbled answer. Same side-effect reasoning as never blindly retrying a non-idempotent POST.

  </details>

- Someone asks you to point capstone at OpenAI instead of the local server. What changes?

  <details><summary>Answer (read after attempting aloud)</summary>

  Only `LLM_BASE_URL` (to `https://api.openai.com/v1`) plus an auth header/key — no code change, because both speak the OpenAI Chat Completions schema. That's the whole point of an OpenAI-compatible server: self-hosted vs hosted is a config/env decision. (In this course we stay self-hosted — no keys — but the code is already portable.)

  </details>

- What does the streaming endpoint buy a user if total generation time is unchanged?

  <details><summary>Answer (read after attempting aloud)</summary>

  Lower *perceived* latency. Non-streaming makes the user wait for all 256 tokens before seeing anything; streaming shows the first token after ~TTFT and the rest as they generate. Total wall-clock is the same, but "words appear immediately" feels far faster than "spinner, then a wall of text" — which is why every chat UI streams.

  </details>

## Clean up

`Ctrl-C` both Terminal A (model) and Terminal B (capstone). Model cache stays for later labs.

Commit `app/main.py`, `pyproject.toml`, and `uv.lock`. Update the capstone evolution log: "Section 10: `/ask` calls a real self-hosted model (env base URL, streaming, timeout/retry policy)."
