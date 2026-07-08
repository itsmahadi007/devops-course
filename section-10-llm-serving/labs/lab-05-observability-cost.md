# Lab 5 — Observability & cost metering for LLM serving

**Goal:** put real eyes on the model. The model server already exposes Prometheus `/metrics` (you turned it on with `--metrics` in Lab 3); you'll scrape it into the Section 8 stack, then add **capstone-side** token counters, a latency histogram, and a **cost meter** — the infrastructure version of the per-request cost metering you built at ApplyFuel. By the end you can answer "how many tokens/sec, what's my TTFT, and what is this costing" from a dashboard.

## The mental map (read this first)

Section 8 gave the capstone golden-signal observability (RED: rate, errors, duration). LLM serving adds **three metrics nobody else has to think about**, and they're exactly what an AI-infra interview probes:

```
 the LLM-serving golden signals (on top of RED)
 ┌────────────────────────────────────────────────────────────────┐
 │ 1. TOKENS       tokens_in + tokens_out  → the unit of work AND   │
 │                 the unit of COST (everything bills per token)    │
 │ 2. TTFT         time to first token      → the latency users feel│
 │ 3. THROUGHPUT   tokens/sec (decode rate)  → capacity utilization │
 └────────────────────────────────────────────────────────────────┘
        two vantage points, and you want BOTH:

  llama-server /metrics          capstone /metrics (per-request, per-endpoint)
  ── the ENGINE's view ──        ── the APPLICATION's view ──
  raw decode rate, prompt/       tokens & cost attributed to /ask,
  gen token totals, KV usage     latency histogram, error rate
```

Why two vantage points? The **engine** metrics tell you if the server is healthy and fast (is the GPU saturated? is decode rate dropping?). The **application** metrics attribute cost and latency to *your* endpoints and *your* users — which is what a business actually asks about. ApplyFuel's cost metering lived at the app layer for exactly this reason: you can't bill a customer from the engine's global counters; you meter per request, per model, and sum.

**The cost-metering insight for self-hosted models.** A hosted API has an obvious price ($X per 1M tokens). Self-hosted has *no per-token invoice* — but it still costs money (the GPU/box, amortized). The professional move is to **model a synthetic cost rate** ("this box costs $Z/hour, it does W tokens/hour, so $Z/W per token") and meter against it. The huge payoff: the *same dashboard and the same code* work whether `/ask` points at your `llama-server` or at OpenAI — you just change the price constant. That's the 12-factor thesis extended to cost. It's also the single most portfolio-worthy sentence in this course: *"I meter LLM cost at the serving layer, self-hosted or hosted, on one dashboard."*

## Steps

### 1. Confirm the engine's metrics

The model server is already emitting Prometheus metrics (Lab 3's `--metrics`). Look:

```bash
curl -s localhost:9110/metrics | grep -E "^llamacpp:" | head -20
```

#### What you'll see

Lines in Prometheus exposition format, prefixed `llamacpp:`:

```
llamacpp:prompt_tokens_total 1234        ← total prompt (input) tokens processed
llamacpp:tokens_predicted_total 5678     ← total generated (output) tokens
llamacpp:tokens_predicted_seconds_total  ← time spent decoding → rate = predicted/seconds
llamacpp:n_decode_total ...              ← decode steps
llamacpp:kv_cache_usage_ratio ...        ← how full the KV cache is (0–1) — capacity signal
llamacpp:requests_processing ...         ← in-flight requests (your -np slots in use)
```

These are the engine's truth. `rate(llamacpp:tokens_predicted_total[1m])` in PromQL = live output tokens/sec; `llamacpp:kv_cache_usage_ratio` climbing toward 1 means you're about to hit the capacity wall from Lab 4.

### 2. Scrape the model into the Section 8 Prometheus

Add a scrape job to the Prometheus config from Section 8 (`capstone/observability/prometheus.yml` or wherever S8 put it — adjust the path to match). The model service is reachable by compose DNS as `model:8080`:

```yaml
scrape_configs:
  # ... your existing capstone job from Section 8 ...

  - job_name: "llama-server"          # ← NEW: the model engine's metrics
    metrics_path: /metrics
    static_configs:
      - targets: ["model:8080"]        # compose DNS — Prometheus and model share the network
```

Reload Prometheus (`docker compose restart prometheus`, or hit its `/-/reload` if S8 enabled it). In the Prometheus targets UI (`localhost:9090/targets` from S8) the `llama-server` target should go **UP**. If it's DOWN, the usual suspect is that Prometheus and `model` aren't on the same compose network — same service-DNS reachability rule as every service since Section 1.

### 3. Add capstone-side token + cost metrics

Now the application vantage point. Add `prometheus-client` to `capstone/pyproject.toml` (Section 8 may already have added `prometheus-fastapi-instrumentator`, which bundles it — if so, this is a no-op, but keep the explicit dep):

```toml
dependencies = [
    "fastapi>=0.115",
    "uvicorn>=0.34",
    "redis>=5.2",
    "httpx>=0.28",
    "prometheus-client>=0.21",
]
```

`uv lock` again. Then extend `capstone/app/main.py` — add the metrics definitions near the top and instrument `/ask`. Here are the pieces to fold into the Lab 2 file:

```python
# ── add near the top, after the LLM config ──
from prometheus_client import Counter, Histogram

# Cost model: a synthetic price so self-hosted and hosted share one dashboard.
# "This box costs ~$0.50/hr and does ~1M output tokens/hr" → ~$0.50 per 1M tokens.
# Override per environment (12-factor); set to a hosted provider's real price when you swap.
USD_PER_1M_INPUT = float(os.environ.get("LLM_USD_PER_1M_INPUT", "0.10"))
USD_PER_1M_OUTPUT = float(os.environ.get("LLM_USD_PER_1M_OUTPUT", "0.50"))

LLM_TOKENS = Counter(
    "capstone_llm_tokens_total", "LLM tokens processed", ["direction"]  # input | output
)
LLM_COST = Counter("capstone_llm_cost_usd_total", "Estimated LLM spend in USD")
LLM_LATENCY = Histogram(
    "capstone_llm_request_seconds", "End-to-end /ask latency",
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
)
```

Then wrap the successful branch of `/ask` so every answer records tokens, cost, and latency:

```python
@app.get("/ask")
async def ask(q: str = "") -> dict:
    if not q:
        return {"question": q, "answer": "", "detail": "pass ?q=your+question"}

    url = f"{LLM_BASE_URL}/chat/completions"
    last_err = None
    for attempt in range(2):
        try:
            with LLM_LATENCY.time():                       # ← histogram: times the whole call
                async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
                    resp = await client.post(url, json=_chat_payload(q, stream=False))
                    resp.raise_for_status()
                    data = resp.json()

            usage = data.get("usage", {})
            tin = usage.get("prompt_tokens", 0)
            tout = usage.get("completion_tokens", 0)
            LLM_TOKENS.labels(direction="input").inc(tin)   # ← token counters
            LLM_TOKENS.labels(direction="output").inc(tout)
            cost = tin / 1e6 * USD_PER_1M_INPUT + tout / 1e6 * USD_PER_1M_OUTPUT
            LLM_COST.inc(cost)                              # ← the cost meter (ApplyFuel, infra edition)

            return {
                "question": q,
                "answer": data["choices"][0]["message"]["content"],
                "usage": usage,
                "cost_usd": round(cost, 8),
            }
        except httpx.ConnectError as e:
            last_err = e
            continue
        except httpx.HTTPError as e:
            return {"question": q, "answer": "", "detail": f"model error: {e}"}
    return {"question": q, "answer": "", "detail": f"model unreachable: {last_err}"}
```

#### Why these specific metrics

- **`Counter` with a `direction` label** — input and output tokens are counted separately because they're **priced separately** (output usually costs more — reflected in the two constants). A label, not two metric names, so PromQL can sum or split at query time. (Watch label cardinality — Section 8's warning — `direction` has exactly two values, safe. Do *not* label by user-id or prompt text: unbounded cardinality kills Prometheus.)
- **`LLM_COST` as a monotonic `Counter`** — spend only goes up; `increase(capstone_llm_cost_usd_total[1h])` gives hourly burn, `sum` over time gives total. Modeling cost as a counter is what lets you graph "$/hour" and alert on a budget.
- **The synthetic price constants are env vars** — self-hosted default is a made-up amortized rate; point `/ask` at OpenAI and you set the real published price, and *every dashboard keeps working*. That's the portable-cost thesis, in code.
- **`Histogram` for latency** — buckets let you compute p50/p95/p99 with `histogram_quantile()` (Section 8's PromQL). LLM latency is *very* long-tailed (a big generation is 100× a small one), so a histogram, never an average.

### 4. Generate load and read the dashboard

Bring the stack up (`docker compose up -d`), then drive some traffic — reuse `bench.py` from Lab 4 pointed at capstone, or a quick loop:

```bash
for i in $(seq 1 20); do curl -s "localhost:9000/ask?q=explain+idempotency+$i" >/dev/null; done
```

Now in Prometheus (`localhost:9090`) try these queries:

```promql
rate(llamacpp:tokens_predicted_total[1m])                    # engine: live output tok/s
sum(rate(capstone_llm_tokens_total[5m])) by (direction)      # app: input vs output token rate
increase(capstone_llm_cost_usd_total[1h])                    # app: dollars burned this hour
histogram_quantile(0.95, rate(capstone_llm_request_seconds_bucket[5m]))  # p95 /ask latency
```

In Grafana (`localhost:9091`, from S8) build one panel per line — that's your **LLM-serving dashboard**: throughput, token split, cost burn, p95 latency. This is the flagship screenshot for the portfolio writeup.

#### What good looks like

- Output token rate tracks your load; when you stop, it decays to zero.
- Cost climbs in tiny increments (fractions of a cent — a 0.6B model on a cheap synthetic rate). The *number* is small; the *capability* — attributing spend to an endpoint from a dashboard — is the point.
- p95 latency sits at a few hundred ms to low seconds for `max_tokens: 256`. If it spikes, cross-reference `llamacpp:kv_cache_usage_ratio` and `requests_processing` — a full KV cache or maxed slots (Lab 4) is usually why.

## Verify

- Prometheus shows the `llama-server` target UP and your `capstone_llm_*` metrics populated; a Grafana panel shows token throughput and cost burn under load.
- You can answer, out loud, without looking:

- Why meter tokens/cost at the application layer when the engine already exposes token counters?

  <details><summary>Answer (read after attempting aloud)</summary>

  The engine's counters are global — they can't attribute tokens or cost to a specific endpoint, model, or customer. Billing and per-feature cost analysis need per-request attribution, which only the application sees. You want both: engine metrics for serving health (decode rate, KV usage), app metrics for cost/latency attribution — exactly the ApplyFuel split (meter per request, sum for the invoice).

  </details>

- Self-hosted models have no per-token invoice. How do you still meter cost, and why is that valuable?

  <details><summary>Answer (read after attempting aloud)</summary>

  Model a synthetic rate: amortize the box/GPU cost over its token throughput ($/hour ÷ tokens/hour = $/token) and meter against it as env-configured price constants. Valuable because the same code and dashboard then work for self-hosted *and* hosted — swapping `/ask` to OpenAI is just changing the price constant. You get consistent cost visibility and can compare "self-host vs API" on identical graphs.

  </details>

- Why a histogram for `/ask` latency instead of a gauge or average?

  <details><summary>Answer (read after attempting aloud)</summary>

  LLM latency is heavily long-tailed — output length varies wildly, so a big generation can be 100× a small one. An average hides the tail; a gauge captures only the last value. A histogram bins observations so `histogram_quantile()` gives p50/p95/p99 — the percentiles SLOs are written against and the ones that reveal the users actually suffering.

  </details>

- Why label tokens by `direction` but never by user id or prompt?

  <details><summary>Answer (read after attempting aloud)</summary>

  `direction` has two bounded values (input/output) and they're priced differently, so the label is both cheap and useful. User id or prompt text is unbounded cardinality — each unique value creates a new time series, which explodes Prometheus's memory and index (Section 8's cardinality warning). High-cardinality attribution belongs in logs/traces, not metric labels.

  </details>

## Clean up

`docker compose down` (keep volumes so the model cache and any dashboards persist). Commit the updated `main.py`, `pyproject.toml`, `uv.lock`, and the Prometheus scrape-config change. Export your Grafana dashboard JSON into this section's folder if you want it as a portfolio artifact. Update the capstone evolution log: "Section 10: token/latency/cost metrics for `/ask` + engine metrics scraped into the observability stack."
