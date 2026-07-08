# Lab 3 — Grafana: a RED dashboard by hand + one alert that fires

**Goal:** add Grafana to the overlay, connect it to Prometheus, build a three-panel **RED** dashboard *by hand* (so you understand every query), then create one alert and **watch it fire for real** by breaking Redis. Export the dashboard as JSON into the section folder — that's the artifact this section leaves behind.

## The mental map (read this first)

Prometheus stores numbers and can draw a rough graph, but it's not where humans live. **Grafana is the eyes:** it connects to a **data source** (your Prometheus), runs PromQL on your behalf, and renders panels you arrange into a dashboard. It's read-only over Prometheus — it never stores metrics, it just queries and draws.

The dashboard you build follows the **RED method** (Tom Wilkie, Grafana): for any request-driven service, three signals tell you almost everything:

```
   RED — the three questions a dashboard must answer at a glance
   ┌────────────────────────────────────────────────────────────┐
   │  R  Rate      how many requests/sec?   (traffic / load)       │
   │  E  Errors    what fraction are failing? (as a RATIO, not #)  │
   │  D  Duration  how slow is the tail?      (p95 / p99 latency)  │
   └────────────────────────────────────────────────────────────┘
       every one of these comes from metrics you already have:
       R,E ← http_requests_total (counter)   D ← ..._duration_seconds (histogram)
```

RED is for **request-driven services** (your api). Its cousin **USE** (Utilization, Saturation, Errors — Brendan Gregg) is for **resources** (CPU, disk, a queue). You'll meet USE in Lab 5's saturation signal. For an HTTP service, RED is the fastest credible dashboard and the one an interviewer wants to hear you name.

```
   localhost:9091 ── Grafana UI ─┐
        (host door)              │ queries PromQL over the network
                                 ▼
                          prometheus:9090  (container-side port, service DNS)
                                 │
                                 ▼  scrapes
                          api:8000/metrics
```

Note the two ports again: Grafana's host door is **9091**, but *inside the container* Grafana listens on **3000** (its native port) — that's why the mapping is `9091:3000`. And Grafana reaches Prometheus at `prometheus:9090` (service name + container port), never `localhost`.

## Steps

### 1. Add Grafana to the overlay

Edit `capstone/docker-compose.observability.yml` — add a `grafana` service and its volume:

```yaml
  grafana:
    image: grafana/grafana:13.0.2   # the grafana/grafana repo (grafana-oss stopped updating after 12.4)
    ports:
      - "9091:3000"                 # host 9091 → container 3000 (Grafana's native port)
    environment:
      GF_SECURITY_ADMIN_USER: admin       # first-login creds — LOCAL LAB ONLY, never a real secret
      GF_SECURITY_ADMIN_PASSWORD: admin
      GF_AUTH_ANONYMOUS_ENABLED: "false"  # keep the login (quoted — driver wants a string, like the S1 log config)
    volumes:
      - grafanadata:/var/lib/grafana # dashboards/alerts you create persist across `down`
```

And add `grafanadata` under the existing `volumes:` block at the bottom:

```yaml
volumes:
  promdata:
  grafanadata:
```

Bring it up (your `COMPOSE_FILE` from Lab 2 is still teaching compose about both files — re-export it if this is a new terminal):

```bash
export COMPOSE_FILE=docker-compose.yml:docker-compose.observability.yml
docker compose up -d
```

Only `grafana` is `Created`; everything else stays put — the reconcile-only-the-drift behavior again.

### 2. Connect Grafana to Prometheus (the data source)

1. Open **http://localhost:9091** → log in `admin` / `admin` → it'll ask you to set a new password (any local value; skip is fine).
2. Left menu → **Connections → Data sources → Add data source → Prometheus**.
3. **Prometheus server URL:** `http://prometheus:9090` — the service name and container port, *not* `localhost:9090`. Grafana is a container; from inside the network `localhost` is Grafana itself.
4. Scroll down → **Save & test**. You want: **"Successfully queried the Prometheus API."**

> **If you see** `dial tcp ...:9090: connect: connection refused` or `no such host` — you used `localhost:9090` or misspelled the service. Same class of mistake as Lab 2's scrape target: containers talk by service DNS. Change to `http://prometheus:9090`.

### 3. Build the RED dashboard, panel by panel

Left menu → **Dashboards → New → New dashboard → Add visualization → pick your Prometheus data source.** For each panel: paste the query into the query box, set the title and unit, then **Apply**. Add a new panel with **Add → Visualization** for the next.

Keep the load loop from Lab 2 running in a terminal so the panels have live data:

```bash
while true; do curl -s localhost:9000/health >/dev/null; curl -s localhost:9000/visits >/dev/null; sleep 0.2; done
```

**Panel 1 — R: Request rate (throughput)**

- Query: `sum by (handler) (rate(http_requests_total[1m]))`
- Title: `Request rate (req/s)` · Legend: `{{handler}}` (Options → Legend, custom → `{{handler}}`) · Unit: `requests/sec (reqps)`
- What you're seeing: one line per endpoint, requests per second. This is *load* — is traffic normal, spiking, or flatlined (flatline = maybe nothing can reach you)?

**Panel 2 — E: Error ratio**

- Query:
  ```promql
  sum(rate(http_requests_total{status="5xx"}[5m]))
  /
  sum(rate(http_requests_total[5m]))
  ```
- Title: `Error ratio (5xx)` · Unit: `Percent (0.0-1.0)` (so 0.02 renders as 2%) · set panel **min 0, max 1**.
- Why a **ratio**, not a count: 50 errors/sec is a catastrophe at 100 req/s and a rounding error at 100,000 req/s. Errors only mean something *relative to traffic*. Numerator = 5xx per second, denominator = all requests per second — the fraction failing. (Recall Lab 1: `status` is grouped, so it's `"5xx"`, not `"500"`.) Right now this should read ~0 — no errors yet. We'll change that in step 5.

**Panel 3 — D: Duration (p95 latency)**

- Query: `histogram_quantile(0.95, sum by (le, handler) (rate(http_request_duration_seconds_bucket[5m])))`
- Title: `p95 latency` · Legend: `{{handler}}` · Unit: `seconds (s)`
- The Lab 2 idiom, now per-handler (`by (le, handler)`). This is the **tail** — the slow 5% of requests, which is what users actually complain about. p50 can look fine while p95 is on fire; that gap is the whole reason you graph the tail, not the average.

**Save the dashboard** (disk icon, top right) — name it `Capstone — RED`. Set the time range (top right) to **Last 15 minutes** and the auto-refresh to **10s** so it's live.

### 4. Export the dashboard as JSON (the section artifact)

The spec's deliverable for this section is "dashboards-as-JSON in the section folder" — a dashboard you can version-control and re-import anywhere. Export it:

1. Open the dashboard → **Export / Share → Export → Save to file** (or **Dashboard settings (gear) → JSON Model → copy**).
2. Save the JSON to `section-08-observability/dashboards/capstone-red.json`:

```bash
mkdir -p section-08-observability/dashboards
# paste the copied JSON into the file, e.g. with your editor, then:
git add section-08-observability/dashboards/capstone-red.json
```

Now the dashboard is code. Anyone can **Dashboards → New → Import** this JSON and get your RED view instantly. (In a real setup you'd *provision* it from a file on startup so it's never hand-built twice — a good follow-up, but hand-building it once is how you learn what every panel means.)

### 5. Create one alert — and make it fire

An alert is a PromQL condition Grafana evaluates on a schedule; when the condition holds for long enough, the alert changes state. Build one on the error ratio.

**Alerting → Alert rules → New alert rule:**

1. **Query A** (the metric): `sum(rate(http_requests_total{status="5xx"}[1m])) / sum(rate(http_requests_total[1m]))` — 1-minute window so it reacts fast in the lab.
2. **Condition:** add an **Threshold** expression on A → **IS ABOVE `0.05`** (fire when >5% of requests are failing).
3. **Evaluation:** evaluate every `10s`; **`for: 1m`** — the condition must stay true for a full minute before it fires. This `for` duration is the single most important knob in alerting (see Q below) — it's what stops a one-scrape blip from paging you.
4. **Name:** `Capstone high error ratio`. Folder/group: create any (e.g. `capstone`). Save. (Skip contact points — the default is fine; you'll watch the state in the UI, no email needed for a local lab.)

Now break Redis and watch the machinery work. In Section 1, Lab 4 you learned `depends_on: service_healthy` gates **only startup** — if Redis dies later, the api keeps running and must cope. It doesn't cope: `/visits` calls Redis, Redis is gone, the call raises, FastAPI returns **500**. That's your error source:

```bash
docker compose stop redis        # kill the cache under the running api
# hammer the endpoint that needs redis — these now 500:
for i in {1..200}; do curl -s localhost:9000/visits >/dev/null; sleep 0.1; done
```

Watch **Alerting → Alert rules** (and Panel 2 on the dashboard). The rule marches through the states:

- **Normal** → (errors start) → **Pending** (condition true, but the `for: 1m` timer is counting) → **Firing** (stayed true for the full minute).
- The error-ratio panel climbs toward 1.0 (nearly every `/visits` is now a 500).

That **Pending → Firing** transition *is* the `for` duration doing its job: a two-second Redis hiccup would go Pending and fall back to Normal without ever paging you. Only a *sustained* problem fires.

Now heal it:

```bash
docker compose start redis       # cache back; /visits returns 2xx again
```

Within a minute or two the ratio falls back under 5% and the alert returns to **Normal** (Grafana calls the recovery a "resolved" notification in real setups). You just watched an alert detect a real failure and clear on recovery — the full loop.

> **If the alert never leaves Normal:** the error ratio didn't clear 5% for a full minute. Send more `/visits` traffic while Redis is stopped, or lower the threshold to `0.01` temporarily. **If it fires but the panel is empty:** the dashboard time range is behind — set it to "Last 5 minutes" and refresh.

## Verify

```bash
curl -s 'http://localhost:9090/api/v1/query?query=sum(rate(http_requests_total{status="5xx"}[1m]))' | python -m json.tool
```

Run this *while Redis is stopped and traffic is flowing* — a non-zero value proves the 5xx are real and Prometheus recorded them (the same number your alert evaluates). **Proof it worked:** you have a saved 3-panel RED dashboard exported to `dashboards/capstone-red.json`, and you watched the alert go Normal→Pending→Firing→Normal across the Redis break and recovery.

Answer aloud:

**Q1. Why is the error panel a ratio (5xx ÷ total) instead of just a count of 5xx?**
<details><summary>Answer (read after attempting aloud)</summary>
Because an error count is meaningless without knowing the traffic it's drawn from — 50 errors/sec is a disaster at 100 req/s and noise at 100k req/s. A ratio normalizes to "what fraction of users are being hurt," which is (a) comparable across traffic levels and time of day, and (b) exactly what an SLO is written against (Lab 5). Alert on the ratio, not the count.
</details>

**Q2. What is the `for: 1m` doing, and what would happen to your pager without it?**
<details><summary>Answer (read after attempting aloud)</summary>
`for` requires the condition to stay true continuously for that duration before the alert fires — that's the **Pending** state (condition true, timer running). Without it, every single evaluation that crosses the threshold pages you, so a one-scrape blip, a brief GC pause, or a two-second dependency hiccup wakes you at 3am. `for` filters transient noise and only escalates *sustained* problems. It's the main dial between "actionable alerts" and "alert fatigue."
</details>

**Q3. This alert fires on the *error ratio* — a thing users feel. Why is that better than an alert on "Redis is down"?**
<details><summary>Answer (read after attempting aloud)</summary>
It's a **symptom** alert, not a **cause** alert. You care that *users are getting 500s* — and that fires no matter what causes it (Redis down, a bad deploy, a network partition, a code bug). A "Redis is down" alert only catches one specific cause, misses every other way users can be hurt, and pages you even when Redis is down but nothing user-facing depends on it right now. Page on symptoms (errors, latency, availability); use causes for *diagnosis* once you're already looking. This is the core of Lab 5.
</details>

## Clean up

Restore Redis if you haven't: `docker compose start redis`. Kill the load loop (Ctrl-C). Leave the stack up — Lab 4 adds Loki and correlates *this exact Redis break* with the log lines. If stopping:

```bash
docker compose down        # grafanadata + promdata volumes kept → dashboard and alert survive
```

Commit:

```bash
git add capstone/docker-compose.observability.yml section-08-observability/dashboards/capstone-red.json
git commit -m "feat(observability): grafana RED dashboard and error-ratio alert"
```
