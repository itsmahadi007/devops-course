# Lab 2 — Prometheus scraping + PromQL basics

**Goal:** run Prometheus in an observability **overlay** on the compose stack, watch it scrape the capstone's `/metrics` every 15s, read the Targets UI, and write the two PromQL functions you'll use forever: `rate()` and `histogram_quantile()`.

## The mental map (read this first)

Lab 1 built the *source* — a `/metrics` page the app renders on demand. Prometheus is the *reader and the memory*. On a fixed interval it walks a list of **targets**, does `GET /metrics` on each, parses every line, and appends each number as a timestamped **sample** into its local time-series database (TSDB). Over hours that TSDB becomes the history you graph and alert on.

```
   your Mac (host)
        │  ONE new door this lab
        ▼
   localhost:9090  ── Prometheus UI (Targets, Graph, query box)
        │
  ┌─────┴──────────── compose network ────────────────────────┐
  │  ┌────────────┐   every 15s:  GET api:8000/metrics         │
  │  │ prometheus │ ──────────────────────────────────────▶ ┌──────┐
  │  │  :9090     │ ◀── plain-text metrics page ──────────── │ api  │
  │  │            │                                          │:8000 │
  │  │  TSDB      │  parses each line → stores a sample      └──────┘
  │  │ (promdata  │  {name, labels, value, timestamp}
  │  │  volume)   │
  │  └────────────┘
  └────────────────────────────────────────────────────────────┘
```

Two things to hold onto:

1. **Prometheus reaches the api by its compose service name `api`, on the container-side port `8000`** — the same service DNS from Section 1, Lab 4. Not `localhost`, not `9000`. `9000` is the *host* door; inside the network everyone still uses `8000`. Getting this wrong is the #1 first-scrape failure, so it's called out again below.
2. **A target is a URL Prometheus was *told* to scrape.** The list lives in `prometheus.yml` — a file Prometheus owns, not the apps. This is the pull model's payoff: to monitor a new service you edit Prometheus's config, you don't touch the service.

## Steps

### 1. Write the Prometheus config

Create `capstone/observability/prometheus.yml`:

```yaml
global:
  scrape_interval: 15s        # how often to read every target's /metrics (the default cadence)
  evaluation_interval: 15s    # how often to re-check alert rules (Lab 3 uses this)

scrape_configs:               # the list of things to scrape — Prometheus OWNS this list
  - job_name: prometheus      # a "job" = a group of like targets; this one is Prometheus itself
    static_configs:
      - targets: ["localhost:9090"]   # yes, Prometheus scrapes its own /metrics too

  - job_name: capstone-api
    static_configs:
      - targets: ["api:8000"]   # compose DNS: service name "api", CONTAINER port 8000
    # metrics_path defaults to /metrics — no need to state it
```

Read it as: *"every 15 seconds, GET `http://api:8000/metrics` and `http://localhost:9090/metrics`, parse them, store every sample."* A **job** groups targets that mean the same thing (all replicas of one service). Prometheus auto-attaches two labels to everything it scrapes: `job` (from `job_name`) and `instance` (the target address) — you'll use `job="capstone-api"` to filter in queries.

### 2. Write the observability overlay compose file

You could paste Prometheus into your existing `docker-compose.yml`, but that file is the *app*. Observability is a separate concern you'll want to bring up and tear down independently — so use a compose **overlay**: a second file that *adds* services on top of the base. Create `capstone/docker-compose.observability.yml`:

```yaml
services:                     # these MERGE onto the base file's services

  prometheus:
    image: prom/prometheus:v3.8.1   # PIN v3 — the plain :latest tag still points at the old 2.x line
    ports:
      - "9090:9090"           # host:container — Prometheus UI on your Mac at localhost:9090
    volumes:
      - ./observability/prometheus.yml:/etc/prometheus/prometheus.yml:ro   # our config, read-only
      - promdata:/prometheus  # named volume for the TSDB — history survives `down` (see step 6)
    command:                  # override the image's default args to point at OUR config + data dir
      - --config.file=/etc/prometheus/prometheus.yml
      - --storage.tsdb.path=/prometheus

volumes:
  promdata:                   # declare the TSDB volume
```

Line-by-line worth reading:

- **`:ro`** on the config bind-mount — read-only. Prometheus never writes its config; mounting it read-only means a bug can't corrupt your source-of-truth file. Good habit for every config mount.
- **`command:`** — the `prom/prometheus` image has a sensible default command; we override it to (a) use our config file and (b) put the TSDB at `/prometheus`, which is where our named volume is mounted. Without the volume, every `down` would wipe your metric history.
- **No healthcheck needed** here — this is a lab; add one in a real deployment (`wget -q --spider http://localhost:9090/-/healthy`).

### 3. Bring up the merged stack

Two `-f` flags = "merge these files, later ones win on conflicts" — exactly the mechanism you'd use for a `docker-compose.prod.yml` override in real life:

```bash
cd capstone
docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d
```

Typing both `-f` flags on every command gets old fast. Set them once for this shell so plain `docker compose` picks up both:

```bash
export COMPOSE_FILE=docker-compose.yml:docker-compose.observability.yml   # colon-separated on macOS/Linux
docker compose ps      # now sees api, redis, db, AND prometheus — no -f needed
```

`COMPOSE_FILE` is the standard env var compose reads to find its files; setting it is how teams avoid the `-f` soup. (It lasts only for this terminal session — re-export it in a new tab, or add it to a project `.env`.)

You should see four services `Up`, with `prometheus` published on `9090`.

> **If `prometheus` exits immediately** — `docker compose logs prometheus`. Almost always a YAML error in `prometheus.yml` (Prometheus refuses to start on a bad config — loud failure over silent drift, same principle as `postgres:18` and `--frozen`). The log names the exact line.

### 4. Read the Targets UI — the first thing you check, always

Open **http://localhost:9090/targets** in a browser. This page answers "is Prometheus actually reading my app?" — it's the first place you look when a dashboard is empty.

You'll see two jobs. Under `capstone-api`:

```
Endpoint                   State   Labels                              Last Scrape   Scrape Duration
http://api:8000/metrics    UP      job="capstone-api" instance="api…"  4.2s ago      3.1ms
```

- **`State: UP`** (green) = the last scrape succeeded. This is what you want.
- **`Last Scrape` / `Scrape Duration`** = when it last read the page and how long that read took. A scrape duration creeping toward your 15s interval is itself a warning (the target is slow to render metrics).
- **`Labels`** = the `job` and `instance` labels Prometheus stamped on. Every sample from this target carries these.

> **If State is `DOWN` (red):**
> - `connection refused` → wrong host/port. You almost certainly wrote `localhost:9000` (the *host* door) instead of `api:8000` (the *service name + container port*). Prometheus is a neighbor on the compose network — it dials the service name. Fix `prometheus.yml`, then either restart prometheus (`docker compose restart prometheus`) or hit **http://localhost:9090/-/reload** to hot-reload the config.
> - `context deadline exceeded` → the target didn't answer within the scrape timeout (10s default). The api is overloaded or wedged.
> - `no such host` → the service name is misspelled or that service isn't up.

### 5. PromQL: from raw samples to answers

Open **http://localhost:9090/graph**. First generate some load so rates aren't flat — run this in a terminal and leave it going while you query:

```bash
while true; do curl -s localhost:9000/health >/dev/null; curl -s localhost:9000/visits >/dev/null; sleep 0.2; done
```

Now type each query into the expression box (Table tab for instant values, Graph tab to see it over time). Read what each *means*, not just what it returns.

**a) The raw counter — and why it's useless as-is:**

```promql
http_requests_total
```

Returns each counter's current total. Useless for a dashboard: "31402 requests" since *when*? It only ever climbs. You almost never graph a raw counter.

**b) `rate()` — turn a climbing counter into "per second":**

```promql
rate(http_requests_total[1m])
```

`rate(counter[1m])` = "average per-second increase, measured over a 1-minute sliding window." *This* is how you read a counter. Two things `rate()` does for you that a naive `(now - then)/seconds` wouldn't: it **automatically handles counter resets** (app restarts to 0 → `rate()` sees the drop and corrects, so a deploy doesn't create a fake negative spike), and it needs at least **two** samples in the window (hence a window ≥ 2× your scrape interval — with 15s scrapes, use `[1m]` minimum, never `[15s]`).

**c) `sum()` and `sum by (...)` — aggregate away the labels you don't care about:**

```promql
sum(rate(http_requests_total[1m]))                    # total requests/sec across ALL handlers
sum by (handler) (rate(http_requests_total[1m]))      # requests/sec, split per endpoint
```

`rate()` gives you one line per (handler, method, status) series. Usually you want fewer lines. `sum(...)` collapses them all into one total; `sum by (handler)(...)` keeps a line *per handler* and merges the rest. This is your throughput ("Rate" in RED, Lab 3).

**d) `histogram_quantile()` — the p95 you set up in Lab 1:**

```promql
histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket[5m])))
```

Read it inside-out — this composition is the standard idiom and worth memorizing:

1. `http_request_duration_seconds_bucket` — the cumulative bucket series (the `le="..."` rows from Lab 1).
2. `rate(...[5m])` — per-second rate of *each bucket*, so old data ages out and you get *current* behavior. (You always `rate()` the buckets first — the buckets are counters too.)
3. `sum by (le) (...)` — add up the buckets across handlers/methods/instances, **grouped by `le`**. Keeping `le` is mandatory — it's the axis the quantile walks; sum by anything and you must keep `le`. (Want per-endpoint p95? `sum by (le, handler)`.)
4. `histogram_quantile(0.95, ...)` — walk the cumulative buckets, find where the 95th percentile lands, interpolate. Result: p95 latency in seconds.

Change `0.95` to `0.50` for the median, `0.99` for p99. Remember Lab 1's caveat: the answer's precision is capped by the bucket boundaries — if your `_bucket` output has no boundary near where the tail actually sits, the estimate is coarse.

**e) A cardinality X-ray (keep this one in your pocket):**

```promql
count by (__name__) ({__name__=~".+"})
```

Counts how many time series exist per metric name. On a healthy small app, small numbers. The day someone adds a `user_id` label, one metric's count explodes and this query points straight at the culprit. This is the diagnostic behind "our Prometheus is OOMing."

## Verify

```bash
curl -s 'http://localhost:9090/api/v1/query?query=up{job="capstone-api"}' | python -m json.tool
```

`up` is a synthetic metric Prometheus writes for every target: `1` = last scrape succeeded, `0` = failed. **Proof it worked:** the JSON shows `"value": [<timestamp>, "1"]` for `job="capstone-api"` — Prometheus is successfully scraping your app. (`up` is also the simplest possible alert: `up == 0` means "the thing is unreachable.")

Answer aloud:

**Q1. Why does `prometheus.yml` say `api:8000` and not `localhost:9000`? What error do you get if you use the host address, and why?**
<details><summary>Answer (read after attempting aloud)</summary>
Prometheus is a container on the compose network, so it reaches the api the same way the api reaches redis: by **service DNS name + container-side port** — `api:8000`. `localhost` inside the prometheus container is prometheus *itself*, and `9000` is a door published on your Mac's host, invisible from inside the network. Using it gives `connection refused` (nothing is listening at prometheus-localhost:9000). Fix the target and hot-reload with `/-/reload`.
</details>

**Q2. Why never graph a raw counter? What exactly does `rate()` fix that a hand-rolled delta wouldn't?**
<details><summary>Answer (read after attempting aloud)</summary>
A counter only climbs and resets to 0 on restart, so its raw value ("47000 requests") has no meaning without a reference point — you want the *rate of change*. `rate()` gives per-second increase over a window and, crucially, **handles resets**: when it sees the value drop (a deploy restarted the process), it treats it as a reset rather than a huge negative delta, so deploys don't create fake spikes. It also requires ≥2 samples in the window, so your range must be ≥2× the scrape interval (`[1m]` for 15s scrapes).
</details>

**Q3. In the p95 query, why must the `sum` keep `by (le)`? What happens if you drop it?**
<details><summary>Answer (read after attempting aloud)</summary>
`le` is the bucket-boundary axis — `histogram_quantile` walks the cumulative counts across `le` values to find the percentile. If you `sum` without `by (le)` you collapse all buckets into one number and destroy the distribution; `histogram_quantile` has nothing to interpolate over and returns garbage/NaN. You may sum away `handler`, `method`, `instance` — but `le` must survive into the function.
</details>

## Clean up

Leave everything **up** — Lab 3 puts Grafana in front of this Prometheus. Kill the load loop with Ctrl-C. If stopping for the day:

```bash
docker compose down        # COMPOSE_FILE still set → tears down all four services; promdata volume kept
```

Commit the new files:

```bash
git add capstone/observability/prometheus.yml capstone/docker-compose.observability.yml
git commit -m "feat(capstone): prometheus scrape overlay for the observability stack"
```
