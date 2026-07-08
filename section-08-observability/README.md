# Section 08 — Observability: Prometheus · Grafana · Loki

**Status:** in progress · **Time:** ~1–1.5 weeks at 2–4h/day · **Labs:** 6 (Lab 6 optional)

Back in Section 1, Lab 4, you learned a hard limit: a container's log line lives as a tiny JSON object on disk (`stdout → engine → json-file`), `docker logs` is just a reader of that file, and **`docker compose down` is an `rm` of every container — so the logs die with it.** The postgres-18 error lecture you hit that day is gone forever. We ended that lab with a promise: *real systems ship logs out to a central store as they happen — Section 8 builds exactly that.* This is Section 8. We're paying that debt, and going three steps further: not just logs, but **metrics**, **dashboards**, **alerts**, and the interview-grade skill of deciding **what to actually wake up for.**

This section instruments the same capstone stack you've carried since Section 1 and gives it eyes. The difference you're building is the difference between *"a user told me it's down"* and *"I knew before the user did, and I know why."*

## The mental model (read first)

**Observability = being able to answer questions about your system you didn't think to ask in advance.** It rests on three kinds of signal — the "three pillars." You need all three because each answers a different question:

```
                  the three pillars

  METRICS          "how MUCH / how FAST / how OFTEN?"
  (numbers over     e.g. 240 req/s, p95 latency 180ms, 0.3% errors
   time)            cheap to store forever · aggregate the whole fleet
                    → Prometheus (Labs 1-2), Grafana dashboards (Lab 3)

  LOGS             "what EXACTLY happened at 14:03:07?"
  (timestamped      e.g. the full stack trace of that one 500
   text events)     rich, per-event · expensive if you index every word
                    → Loki + Alloy (Lab 4)

  TRACES           "where in the request did the 400ms GO?"
  (one request      e.g. api 5ms → redis 2ms → db 390ms
   across services)  we name it (Lab 5) but don't build it — it's the
                    next depth, and single-service capstone doesn't need it yet
```

Metrics tell you **that** something is wrong and roughly where. Logs tell you **what** exactly. You pivot between them constantly during an incident — a metric spike ("errors up") sends you to the logs ("here's the exception"). Lab 4 makes you do that pivot for real.

**Metrics are pulled, not pushed — and that's a deliberate design choice.** This is the single most surprising idea for a backend engineer, because every API you've built *pushes* data out. Prometheus is the opposite: your app just *exposes* a plain-text page at `/metrics` showing its current numbers, and Prometheus **reaches out and reads that page every 15 seconds** (a "scrape"). The app doesn't know or care that Prometheus exists.

```
   PUSH model (what you're used to)        PULL model (Prometheus)
   app ──sends metrics──▶ collector        prometheus ──scrapes──▶ app:8000/metrics
   app must know the collector's address    app exposes a page; knows nothing
   app dies quietly if collector is down    a DOWN target is itself a signal
```

Why pull wins for metrics: (1) the list of what's-being-monitored lives in **one config Prometheus owns** — no app needs the collector's address; (2) a target that fails to scrape is *itself an alert* ("the thing is unreachable") — a pushing app that goes silent looks identical to a healthy-but-idle one; (3) you can hit `/metrics` with `curl` yourself to debug — the data is just a web page. (Push has its place — short-lived batch jobs that die before the next scrape use a "pushgateway" — but for long-running services, pull is the default and you should be able to defend why.)

**Label cardinality is the shape — and the failure mode — of the whole system.** A metric isn't one number; it's a family of numbers split by **labels** (key=value tags). `http_requests_total{handler="/visits", method="GET", status="2xx"}` is *one* time series; change any label value and it's a *different* series Prometheus stores separately. **Cardinality = the number of distinct label-value combinations = the number of time series.** This is the concept that separates people who've run Prometheus from people who've read about it:

- Good labels have **bounded** value sets: HTTP method (~5 values), status class (5), handler (however many routes you have — a dozen). Multiply them: 5 × 5 × 12 = 300 series. Fine.
- **The classic outage:** someone adds a label whose values are unbounded — `user_id`, `request_id`, a raw URL with IDs in it, an email. Now every unique request mints a new permanent time series. Millions of them. Prometheus's memory is roughly proportional to *active series count*, so it OOMs and takes your monitoring down exactly when you need it. This is why the instrumentation library you'll use in Lab 1 deliberately **groups status codes into `2xx`/`3xx`/…** (not `200`/`201`/`204`/…) and groups unmatched paths into a single `none` handler — and why it splits latency into *two* histograms, one with a `handler` label and one without. You'll read those design choices straight out of the `/metrics` output and understand *why* they made them.

Hold this rule: **a label value must come from a small, fixed set you could write on a whiteboard. If it can't, it's not a label — it's a log field.** (That's the metrics↔logs division of labor: high-cardinality detail belongs in logs, which Loki indexes cheaply by *not* indexing the text.)

**Histograms don't store your latencies — they store counts in buckets.** You'll want "p95 latency" and Prometheus never saw individual request times. Instead a histogram keeps a set of counters: "how many requests were faster than 5ms? faster than 10ms? …faster than 10s?" (the `_bucket` series, tagged by `le` = "less-than-or-equal"). From those cumulative counts, `histogram_quantile()` *interpolates* the 95th percentile. Two consequences you must internalize: (1) the answer is only as precise as the bucket boundaries — you can't get a quantile more accurate than the gaps between buckets; (2) you can only reason at boundaries that exist. This is the histogram trade: fixed cheap storage, approximate quantiles. Lab 2 makes you compute one by hand.

**Why this separates senior candidates.** Anyone can install a dashboard. The senior signal is judgment: knowing that you page on *symptoms users feel* (errors, latency) and not *causes* (CPU 90% while users are fine); knowing what an SLO and an error budget are and using the budget to decide whether to ship; knowing cardinality will bankrupt you before it bankrupts your cloud bill; knowing when a metric is lying and you need the logs. Labs 3 and 5 are where you build exactly that judgment.

## Why this matters for jobs

- "How does Prometheus get metrics from your app — and why pull instead of push?" is a standard SRE/DevOps screen. The mental-model section above IS the answer; Lab 2 makes it muscle memory.
- "Your Prometheus keeps OOMing" → cardinality. Being able to say *"someone put an unbounded value in a label"* and prove it (`count by (__name__)({__name__=~".+"})`) is a senior-level diagnostic.
- "Walk me through what you'd alert on for a web service" → golden signals + symptom-based alerting + error budgets (Lab 5). This is the question that sorts juniors from seniors, and most candidates fumble it.
- Building a RED dashboard by hand (Lab 3) is a real freelance infra deliverable — "add monitoring to my service" is a common gig, and the RED method is the fastest credible answer.

## Labs

| Lab | What you build | Proves |
|---|---|---|
| [1 — Instrument the capstone](labs/lab-01-instrument-capstone.md) | `/metrics` on the FastAPI app, read line by line | counters/gauges/histograms, labels, cardinality by design |
| [2 — Prometheus + PromQL](labs/lab-02-prometheus-promql.md) | Prometheus scraping the api, targets UI | the pull model, `rate()`, `histogram_quantile()` |
| [3 — Grafana RED dashboard + alert](labs/lab-03-grafana-red-alert.md) | a hand-built dashboard + one alert that fires | RED method, error ratio, alert states, symptom alerting |
| [4 — Loki + Alloy log shipping](labs/lab-04-loki-alloy-logs.md) | central logs surviving `down`, LogQL | logs push vs metrics pull, label-only indexing, metric↔log pivot |
| [5 — SLOs & golden signals](labs/lab-05-slo-golden-signals.md) | an SLO + error budget + page/ticket split (thinking lab) | SLI/SLO/error budget, burn rate, what to page on |
| [6 — kube-prometheus-stack (OPTIONAL)](labs/lab-06-kube-prometheus-stack.md) | the same stack on kind via Helm | operator/ServiceMonitor model, batteries-included contrast |

Do 1→5 in order — they chain (Lab 2 scrapes what Lab 1 exposes; Lab 3 graphs what Lab 2 stores; Lab 4 correlates against Lab 3's induced failure; Lab 5 reasons over all of it). Lab 6 is optional and heavier on the Mac — do it only if you want the Kubernetes-native version (it reuses your Section 4 kind + Section 5 Helm skills).

Everything is a **container image** — there is nothing to `brew install` this section (Prometheus, Grafana, Loki, Alloy all run from the compose overlay). That itself is a point: your whole observability plane is disposable and declared in YAML, exactly like the app it watches.

**Versions used (latest stable, July 2026 — pin these; bump deliberately):**

- `prometheus-fastapi-instrumentator` **8.0.2** — added to capstone via `uv add` in Lab 1
- `prom/prometheus:v3.8.1` — **pin `v3`**; the plain `:latest` tag still resolves to the old 2.x line
- `grafana/grafana:13.0.2` — use the `grafana/grafana` repo (`grafana/grafana-oss` stopped updating after 12.4.0; same images)
- `grafana/loki:3.7.3`
- `grafana/alloy:v1.17.1` — the log shipper. **Promtail reached end-of-life March 2026**; Alloy (Grafana's OpenTelemetry-Collector distribution) is its official successor, so every tutorial still showing `promtail` is teaching a dead tool. *(verify latest before pinning — tags move.)*

## Reading (curated, ~2h total)

- [Prometheus — overview & data model](https://prometheus.io/docs/introduction/overview/) — read "data model" until labels + cardinality feel obvious
- [Metric types](https://prometheus.io/docs/concepts/metric_types/) — counter vs gauge vs histogram vs summary, in one page
- [Querying basics + `rate()` / `histogram_quantile()`](https://prometheus.io/docs/prometheus/latest/querying/basics/) — the two functions you'll use most
- [The RED method (Grafana)](https://grafana.com/blog/2018/08/02/the-red-method-how-to-instrument-your-services/) — Lab 3's dashboard, explained by its inventor
- [Google SRE Book — Ch. 4 SLOs](https://sre.google/sre-book/service-level-objectives/) and [Ch. 6 Monitoring / golden signals](https://sre.google/sre-book/monitoring-distributed-systems/) — Lab 5 is these two chapters, applied
- [Loki — fundamentals](https://grafana.com/docs/loki/latest/get-started/overview/) — why indexing labels-not-text makes it cheap

## Done when

Every task in [checkpoint.md](checkpoint.md) passes from memory, and [notes.md](notes.md) is filled in your own words. Then the next section (GitOps with Argo CD) gets written against your notes.
