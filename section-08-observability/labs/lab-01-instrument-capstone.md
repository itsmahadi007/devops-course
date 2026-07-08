# Lab 1 — Instrument the capstone: `/metrics` line by line

**Goal:** add a `/metrics` endpoint to the capstone with `prometheus-fastapi-instrumentator`, generate a little traffic, and read the output **line by line** until every metric family, label, and cardinality decision makes sense. No Prometheus yet — this lab is about the *source* of the numbers. Prometheus comes to read them in Lab 2.

## The mental map (read this first)

Right now your app answers questions from *outside* — `GET /visits` returns a number to a caller. Instrumentation adds a second kind of endpoint that answers questions about *itself*: "how many requests have I served? how long did they take? how many failed?" That endpoint is `/metrics`, and it's just a plain-text web page.

The trick is that you don't write any of the counting code. The library installs a piece of **ASGI middleware** — a wrapper that sits between the network and your route functions, so *every* request passes through it on the way in and out. On the way out it does two things: bumps a counter ("+1 request, this handler, this status") and records how long the request took into a histogram. All of that lives in an in-memory table (the "registry"). `/metrics` just renders that table as text.

```
                       the capstone container
   incoming request
        │
        ▼
  ┌───────────────────────────────────────────────┐
  │  Instrumentator middleware  (wraps everything)  │
  │        │  on the way OUT of every request:      │
  │        │   • http_requests_total  += 1          │
  │        │   • http_request_duration observe(t)   │
  │        ▼                                         │
  │   your routes:  /health  /visits  /ask          │
  └───────────────────────────────────────────────┘
        │                        ▲
        │ writes counts          │ renders as text
        ▼                        │
   ┌─────────────────┐    GET /metrics
   │ in-memory        │◀────────────────  (Prometheus will
   │ registry (table) │                    scrape this in Lab 2)
   └─────────────────┘
```

Key idea to carry: **the app never sends metrics anywhere.** It accumulates numbers in memory and exposes them on demand. Something else (Prometheus, or your `curl`) has to come and read. If the app restarts, the counters reset to zero — that's fine and expected; Prometheus handles resets (Lab 2). Metrics are a *current snapshot of counters since start*, not a durable log.

## Steps

### 1. Add the dependency (updates the lockfile — this matters)

Your `Dockerfile` installs deps with `uv sync --frozen` — "the lockfile is law, fail if it drifts" (Section 1, Lab 3). So you can't just import a new package; you must update `uv.lock` first. `uv add` does all three things at once — edits `pyproject.toml`, re-resolves and updates `uv.lock`, and installs into `.venv`:

```bash
cd capstone
uv add prometheus-fastapi-instrumentator
```

Expected output (abridged):

```
Resolved N packages in ...ms
 + prometheus-client==0.2x.x
 + prometheus-fastapi-instrumentator==8.0.2
...
```

Two things to notice. First, it pulled in **`prometheus-client`** as well — that's the low-level Python metrics library (the counters/histograms themselves); the `instrumentator` package is the FastAPI-flavored wrapper that auto-wires the middleware. Second, `pyproject.toml` now lists `prometheus-fastapi-instrumentator>=8.0.2` and `uv.lock` has new entries. Confirm:

```bash
git diff pyproject.toml    # one added dependency line
```

> **If you see** `error: no such command 'add'` — your `uv` is old; `brew upgrade uv`. **If** `uv add` fails to resolve against Python 3.14, pin a slightly older instrumentator (`uv add 'prometheus-fastapi-instrumentator>=7.1'`) and note it in `notes.md`.

### 2. Wire it into the app — a 2-line diff

Edit `capstone/app/main.py`. Add the import near the top, and one line right after `app = FastAPI(...)`. Full context so you place it exactly:

```python
"""Capstone service — deliberately tiny. The DevOps around it is the course."""

import os

import redis
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator   # ← add

app = FastAPI(title="capstone")

Instrumentator().instrument(app).expose(app)   # ← add: wire middleware + serve /metrics

REDIS_URL = os.environ.get("REDIS_URL", "")
```

Leave every route (`/health`, `/ask`, `/visits`) exactly as it is. Read the one new line as two verbs:

- **`.instrument(app)`** — installs the counting middleware around every route. This is the part that *collects*.
- **`.expose(app)`** — adds a `GET /metrics` route that *renders* the registry as Prometheus text. Default path is `/metrics`; default content type is the Prometheus exposition format.

That's the whole change. No per-route decorators, no manual counters — the middleware sees everything by virtue of sitting in the request path.

### 3. Rebuild the api and generate traffic

Bring the base stack up with the new image (Redis + Postgres come along so `/visits` actually works and produces a `2xx`, not an error):

```bash
docker compose up -d --build
```

Only `api` should say `Recreated` (its image changed); `redis`/`db` stay `Running` — the reconcile-only-the-drift behavior you saw in Section 1, Lab 4. Now make some varied traffic so the counters have something interesting in them — different handlers, different status classes:

```bash
for i in {1..30}; do curl -s localhost:9000/health   > /dev/null; done   # 30× 2xx on /health
for i in {1..15}; do curl -s localhost:9000/visits   > /dev/null; done   # 15× 2xx on /visits (via redis)
for i in {1..5};  do curl -s localhost:9000/ask       > /dev/null; done   # 5×  2xx on /ask
for i in {1..8};  do curl -s localhost:9000/nope-404 > /dev/null; done   # 8×  4xx on a non-route
```

The last loop hits a path that doesn't exist — FastAPI returns 404. Watch what the library does with it in the next step: it does **not** create a `handler="/nope-404"` series (that would be unbounded cardinality — anyone typing random URLs could balloon your series count). It groups all unmatched paths under `handler="none"`. That's cardinality-safety you're getting for free.

### 4. Read `/metrics` line by line

```bash
curl -s localhost:9000/metrics | grep -A2 '^# HELP http'
```

You'll see five metric families. Here's each one, what it is, and — the important part — **why its labels are the way they are.** (Your exact numbers differ; the shapes match.)

#### a) `http_requests_total` — a **Counter**

```
# HELP http_requests_total Total number of requests by method, status and handler.
# TYPE http_requests_total counter
http_requests_total{handler="/health",method="GET",status="2xx"} 30.0
http_requests_total{handler="/visits",method="GET",status="2xx"} 15.0
http_requests_total{handler="/ask",method="GET",status="2xx"} 5.0
http_requests_total{handler="none",method="GET",status="4xx"} 8.0
```

- **`# HELP`** = human description, **`# TYPE`** = the metric kind. Prometheus reads these.
- **Counter** = a number that only ever goes **up** (or resets to 0 on restart). You never read a counter's raw value in a dashboard — it's meaningless ("47210 requests since… when?"). You read its **rate** (`rate()` in Lab 2): requests *per second*. A counter is the right type for "things that happen": requests, errors, bytes.
- **Three labels — `handler`, `method`, `status`** — and every distinct combination is its own row (its own time series). Count them here: 4 rows. That's this metric's cardinality.
- **`status="2xx"`, not `status="200"`** — the library **groups status codes into classes** on purpose. `200`/`201`/`204` would triple your series for no diagnostic gain; "was it a success, a client error, or a server error?" is the question that matters, and 3–5 classes keeps cardinality bounded.
- **`handler="none"` for the 404** — every unmatched URL folds into one bucket, so a scanner hitting random paths can't explode your series count. This is the cardinality rule from the lesson, enforced in code.

#### b) `http_request_duration_seconds` — a **Histogram** (this is where p95 comes from)

```
# HELP http_request_duration_seconds Duration of HTTP requests in seconds.
# TYPE http_request_duration_seconds histogram
http_request_duration_seconds_bucket{handler="/visits",method="GET",le="0.005"} 12.0
http_request_duration_seconds_bucket{handler="/visits",method="GET",le="0.01"}  14.0
http_request_duration_seconds_bucket{handler="/visits",method="GET",le="0.025"} 15.0
...
http_request_duration_seconds_bucket{handler="/visits",method="GET",le="+Inf"}  15.0
http_request_duration_seconds_count{handler="/visits",method="GET"}             15.0
http_request_duration_seconds_sum{handler="/visits",method="GET"}               0.087
```

This is the money metric and the one people misunderstand. **A histogram does not store your request times.** It stores a ladder of counters:

- **`_bucket{le="0.005"} 12`** means "12 requests to `/visits` finished in ≤ 5ms." **`le` = less-than-or-equal.** The buckets are **cumulative** — each `le` counts everything at or below it, so they climb monotonically up to `le="+Inf"` which equals the total count. That cumulative shape is exactly what lets `histogram_quantile()` interpolate a p95 later.
- **`_count`** = total observations (= the `+Inf` bucket). **`_sum`** = total seconds spent. `_sum / _count` = the *average* latency — useful, but averages hide the tail, which is why you'll compute p95 from the buckets instead.
- **Labels here: `handler` and `method` — but NO `status`.** Deliberate: adding `status` would multiply every bucket row by the number of status classes. They kept latency-per-endpoint but dropped status to hold cardinality down. (You get error info from the counter in (a), which *does* carry status. Division of labor.)
- **The `le` values are the resolution limit.** Look at the actual `le` numbers in *your* output — you can only ask for quantiles at that granularity. Note them; Lab 2's p95 query and Lab 5's latency-SLO both need an `le` boundary that actually exists in this list. (Default ladder is roughly `0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, +Inf`.)

#### c) `http_request_duration_highr_seconds` — a second **Histogram**, no `handler` label

```
# TYPE http_request_duration_highr_seconds histogram
http_request_duration_highr_seconds_bucket{le="0.01"} 40.0
...
http_request_duration_highr_seconds_bucket{le="+Inf"} 58.0
```

Same idea, but **many more buckets (high resolution) and no `handler` label at all** — it's the whole-app latency distribution. This is the cardinality trade made visible: *fine-grained buckets but zero per-endpoint labels* here, vs *coarse buckets but per-endpoint* in (b). Two histograms so you can have both precision and per-route breakdown without multiplying `buckets × handlers` into a cardinality bomb. When you understand *why they split it*, you understand cardinality.

#### d) & e) `http_request_size_bytes` / `http_response_size_bytes` — **Summaries**

```
# TYPE http_response_size_bytes summary
http_response_size_bytes_count{handler="/visits"} 15.0
http_response_size_bytes_sum{handler="/visits"}   285.0
```

Request/response byte sizes. A **Summary** is a cousin of the histogram: it exposes `_count` and `_sum` (and sometimes pre-computed quantiles) but **no buckets you can re-aggregate across instances**. Rule of thumb: prefer histograms (you can compute quantiles server-side and combine across replicas); summaries are fine for simple sum/count like byte totals. You won't graph these — just know what they are.

#### The four metric types, in one breath

You've now seen three of the four Prometheus types in real output — lock them in:

- **Counter** — only goes up; read its `rate()`. (requests, errors)
- **Gauge** — goes up *and* down; read its current value. (in-flight requests, memory, temperature) — none in the default set, but you'll meet them everywhere (`process_resident_memory_bytes` further down the page is one).
- **Histogram** — bucketed counts + `_sum` + `_count`; `histogram_quantile()` gives approximate percentiles, combinable across instances.
- **Summary** — `_sum` + `_count` (± client-side quantiles); simpler, not re-aggregatable.

Scroll the full page (`curl -s localhost:9000/metrics | less`) and you'll also see `python_*` and `process_*` metrics — GC stats, resident memory (a gauge!), open file descriptors — shipped free by `prometheus-client`. Those are your **saturation** signals (Lab 5's fourth golden signal).

## Verify

```bash
curl -s localhost:9000/metrics | grep '^http_requests_total'
```

**Proof it worked:** you see one `http_requests_total{...}` line per (handler, method, status) combination you generated, including a `handler="none"` line for the 404 — the middleware is counting, and grouping for cardinality safety.

Answer these **aloud** before peeking:

**Q1. Nothing pushed these numbers anywhere. So how will Prometheus get them, and what has to be true about the app for that to work?**
<details><summary>Answer (read after attempting aloud)</summary>
Prometheus will **pull** them — it reaches out and does `GET /metrics` on a schedule (Lab 2). For that to work the app only has to (a) keep accumulating counts in its in-memory registry and (b) keep the `/metrics` route reachable. The app doesn't know Prometheus's address or that it exists. If the app restarts, counters reset to 0; Prometheus detects the reset and keeps `rate()` correct.
</details>

**Q2. Why is `status` a label on `http_requests_total` but deliberately NOT on `http_request_duration_seconds`? And why `status="2xx"` instead of `status="200"`?**
<details><summary>Answer (read after attempting aloud)</summary>
Cardinality. The duration histogram is already many rows per (handler, method) because of all the `le` buckets; adding `status` would multiply that by the number of status classes for little diagnostic value — so they kept it off latency and left it on the cheap counter, which is where you actually want to slice errors. And `2xx` instead of `200` collapses dozens of possible codes into ~5 classes: you lose nothing you'd query on ("success vs client-error vs server-error") and you cap the series count. Both are the "a label value must come from a small fixed set" rule, applied.
</details>

**Q3. A histogram never saw a single request's exact duration. How can it possibly give a p95?**
<details><summary>Answer (read after attempting aloud)</summary>
It stores cumulative bucket counters — "N requests were ≤ 5ms, M were ≤ 10ms, …". To get p95, `histogram_quantile()` finds which bucket the 95th-percentile observation falls into and **linearly interpolates** within that bucket. So the answer is only as precise as the bucket boundaries: with a boundary at 0.25 and the next at 0.5, a p95 that lands between them is an estimate. That's the histogram trade — fixed cheap storage, approximate (and re-aggregatable across replicas) quantiles.
</details>

**Q4. You hit `/nope-404` eight times but there's no `handler="/nope-404"` series. What did the library do, and what disaster did it prevent?**
<details><summary>Answer (read after attempting aloud)</summary>
It grouped all unmatched paths under `handler="none"`. If it had used the raw path, anyone hitting random URLs (a scanner, a broken client, a crawler) would mint a brand-new permanent time series per unique path — unbounded cardinality → Prometheus memory blows up → your monitoring dies exactly when you need it. Grouping untemplated paths is the built-in guard.
</details>

## Clean up

Leave the stack **running** — Lab 2 puts Prometheus in front of this exact `/metrics` endpoint. If you must stop for the day:

```bash
docker compose down          # containers + network gone; pgdata volume kept (safe habit)
```

Commit the change — it's a real capstone evolution:

```bash
git add capstone/app/main.py capstone/pyproject.toml capstone/uv.lock
git commit -m "feat(capstone): expose prometheus /metrics via instrumentator"
```

Update the capstone evolution log. Next: Prometheus reaches out and starts reading this page every 15 seconds.
