# Lab 4 — Loki + Alloy: central logs that survive `down`, and the metric↔log pivot

**Goal:** ship every container's logs into **Loki** using **Alloy** (Grafana's log agent), query them with **LogQL** in Grafana, and do the move that defines incident response — pivot from a metric spike ("errors up") to the exact log lines that explain it. This pays the Section 1, Lab 4 debt in full: **logs that outlive `docker compose down`.**

## The mental map (read this first)

Section 1, Lab 4 taught the limit: a container's log line is a JSON object on disk written by the `json-file` driver; `docker logs` just reads that file; **`docker compose down` is an `rm` of every container, so the file — the evidence — dies with it.** The postgres-18 error lecture from that day is unrecoverable. The fix, promised back then, is *ship logs off the box as they happen* into a central store. That store is **Loki**. The shipper is **Alloy**.

```
   each container writes stdout → docker's json-file (Section 1)
        │
        ▼
   ┌─────────┐  reads docker.sock, discovers containers,
   │  Alloy  │  tails their logs, attaches labels, PUSHES ──────┐
   │ (agent) │  (note: logs PUSH; metrics PULL — opposite!)     │
   └─────────┘                                                  ▼
                                                          ┌──────────┐
   Grafana ──LogQL query──▶  loki:3100  ◀──── stores ──── │   Loki   │
   (same UI as metrics)                                   │ (no host │
                                                          │  port!)  │
                                                          └──────────┘
```

Three ideas do the heavy lifting:

1. **Logs push, metrics pull — and that's not arbitrary.** Metrics are a small fixed set of numbers you can re-read any time, so Prometheus pulls on a schedule. Logs are an unbounded stream of events that must be captured *the instant they happen* (a crashed container can't be scraped later) — so an agent tails them and pushes immediately. Same reason a black-box flight recorder writes continuously rather than waiting to be asked.
2. **Loki indexes labels, not text — "like Prometheus, but for logs."** Elasticsearch (the ELK "E") indexes every word of every log — powerful, and expensive (huge storage, heavy infra). Loki's bet: index only a *few labels* (which container, which job) and store the raw log lines compressed and un-indexed. You find the right *stream* by labels, then `grep` within it. Cheaper by an order of magnitude, and the label discipline is *exactly the cardinality rule from metrics* — high-cardinality stuff (request IDs, user IDs) goes in the log **line**, never in a Loki **label**.
3. **Alloy, not Promtail.** Every older tutorial ships logs with `promtail`. **Promtail reached end-of-life in March 2026.** Grafana's replacement is **Alloy** (their distribution of the OpenTelemetry Collector) — same job, actively maintained, config in "River"/Alloy syntax. If a StackOverflow answer says `promtail`, mentally translate to Alloy.

Notice Loki and Alloy get **no host ports** — reinforcing Section 1's "fewer doors" lesson. Alloy reads the Docker socket and talks to Loki over the compose network; Loki is queried by Grafana over the compose network. Nothing outside the stack ever needs to reach them, so they publish nothing.

## Steps

### 1. Write the Loki config

Create `capstone/observability/loki-config.yml` — the standard single-binary local config (filesystem storage, no auth, fine for one node):

```yaml
auth_enabled: false            # single-tenant local lab; no multi-tenant headers

server:
  http_listen_port: 3100       # Loki's API port (container-side; we publish NO host port)

common:
  instance_addr: 127.0.0.1
  path_prefix: /loki           # everything lives under here (mounted volume)
  storage:
    filesystem:                # store chunks on local disk — no S3/cloud for the lab
      chunks_directory: /loki/chunks
      rules_directory: /loki/rules
  replication_factor: 1        # one copy; single node
  ring:
    kvstore:
      store: inmemory          # the cluster "ring" is just in memory (one node)

schema_config:
  configs:
    - from: 2020-10-24
      store: tsdb              # modern Loki index format
      object_store: filesystem
      schema: v13
      index:
        prefix: index_
        period: 24h

limits_config:
  allow_structured_metadata: true
  volume_enabled: true         # lets Grafana show the "log volume" bar over queries
```

You don't need to memorize this — it's Loki's documented local starter config. The one line to *understand* is `filesystem` storage under `/loki`: in production this would be S3/GCS, but the shape is identical, and pointing `/loki` at a named volume is what makes logs **survive `down`**.

### 2. Write the Alloy config (the pipeline)

Create `capstone/observability/config.alloy`. Alloy config is a set of **components** wired together — each block reads from the one it names in `forward_to`/`targets`. Read it top-to-bottom as a pipeline: *discover containers → clean up their labels → tail their logs → write to Loki.*

```alloy
// 1. discover every container the Docker daemon knows about
discovery.docker "containers" {
  host = "unix:///var/run/docker.sock"
}

// 2. turn Docker's raw metadata into a clean "container" label
//    (__meta_docker_container_name arrives as "/capstone-api-1" — strip the leading slash)
discovery.relabel "containers" {
  targets = discovery.docker.containers.targets
  rule {
    source_labels = ["__meta_docker_container_name"]
    regex         = "/(.*)"
    target_label  = "container"
  }
}

// 3. tail the logs of those containers and forward to the writer below
loki.source.docker "containers" {
  host       = "unix:///var/run/docker.sock"
  targets    = discovery.relabel.containers.output
  labels     = { job = "docker" }              // a fixed label on every line — low cardinality
  forward_to = [loki.write.default.receiver]
}

// 4. push everything to Loki over the compose network (service DNS, container port)
loki.write "default" {
  endpoint {
    url = "http://loki:3100/loki/api/v1/push"
  }
}
```

The labels you'll query on: `container` (e.g. `capstone-api-1`) and `job="docker"`. Both are low-cardinality — a handful of containers, one job. The actual log *text* (stack traces, request paths, IDs) stays in the line body, not in labels. That's the discipline that keeps Loki cheap.

### 3. Add Loki + Alloy to the overlay

Edit `capstone/docker-compose.observability.yml` — add two services and one volume. **Neither gets `ports:`** — compose DNS only:

```yaml
  loki:
    image: grafana/loki:3.7.3
    command: -config.file=/etc/loki/loki-config.yml
    volumes:
      - ./observability/loki-config.yml:/etc/loki/loki-config.yml:ro
      - lokidata:/loki                    # THE volume that makes logs survive `down`
    # no ports: — only Grafana (in-network) and Alloy (in-network) talk to it

  alloy:
    image: grafana/alloy:v1.17.1
    command:
      - run
      - /etc/alloy/config.alloy
      - --server.http.listen-addr=0.0.0.0:12345   # Alloy's own UI/debug port (in-network only)
    volumes:
      - ./observability/config.alloy:/etc/alloy/config.alloy:ro
      - /var/run/docker.sock:/var/run/docker.sock:ro   # READ the daemon socket to discover+tail logs
    depends_on:
      - loki
    # no ports: — it pushes OUT to loki; nothing needs to reach it
```

Add `lokidata` to the bottom `volumes:` block:

```yaml
volumes:
  promdata:
  grafanadata:
  lokidata:
```

**The `docker.sock` mount deserves a pause.** `/var/run/docker.sock` is the Docker daemon's control socket — mounting it gives Alloy the ability to *see and read every container*. That's how it discovers and tails logs without you configuring each one. It's also **a lot of trust**: read-write access to that socket is effectively root on the host (you can create privileged containers through it). We mount it **`:ro`** to narrow that, and in production you'd prefer a socket-proxy that allows only the read calls Alloy needs. On Docker Desktop the socket is safely brokered by the VM, so this is fine for the lab — but know *why* a security reviewer flags a `docker.sock` mount.

Bring it up:

```bash
export COMPOSE_FILE=docker-compose.yml:docker-compose.observability.yml
docker compose up -d
```

`loki` and `alloy` are `Created`. Give Alloy ~15s to discover containers and start tailing.

> **If Alloy logs show** `permission denied` on the socket — on Docker Desktop this is rare; ensure the mount path is exactly `/var/run/docker.sock`. **If Loki logs show** `too far behind` / timestamp errors — clock skew inside the Docker VM; a `docker compose restart loki` after the VM settles clears it.

### 4. Query logs with LogQL in Grafana

Grafana already knows Prometheus; add Loki the same way:

1. **Connections → Data sources → Add data source → Loki.**
2. **URL:** `http://loki:3100` (service DNS, container port — not localhost). **Save & test** → "Data source successfully connected."
3. Left menu → **Explore** → pick the **Loki** data source (top-left dropdown).

Now LogQL. A LogQL query is **a stream selector `{}` (which logs) + optional line filters (grep within them):**

```logql
{container="capstone-api-1"}
```
All lines from the api container. The `{}` part is matched against **labels** (the indexed, cheap part) — this is "pick the stream." You'll see your uvicorn access logs streaming in.

```logql
{container="capstone-api-1"} |= "500"
```
`|=` = "line contains this substring." Now only lines mentioning `500`. Filter operators: `|=` contains, `!=` doesn't contain, `|~` regex-matches, `!~` regex-doesn't-match. **This is the split that makes Loki cheap:** labels (`{}`) are indexed so selecting the stream is instant; the filter (`|=`) is a brute-force scan *within* the already-narrowed stream — like `grep` over just the right files instead of the whole disk.

Turn logs into a *number* (this is the bridge to metrics):

```logql
sum(count_over_time({container="capstone-api-1"} |= "Internal Server Error" [1m]))
```
`count_over_time(...[1m])` = "how many matching lines per 1-minute window." You just built a metric *out of logs* — the count of 500-errors over time. Switch Explore's visualization to a graph to see it as a line.

### 5. The pivot: metric spike → the exact log line (and the debt, paid)

This is the skill. Re-break Redis exactly as in Lab 3 and watch the two signals line up:

```bash
docker compose stop redis
for i in {1..100}; do curl -s localhost:9000/visits >/dev/null; sleep 0.1; done
```

- **In your RED dashboard (Lab 3):** the error-ratio panel spikes. Metrics told you *that* something's wrong and *roughly where* (5xx on `/visits`).
- **In Grafana Explore (Loki):** run `{container="capstone-api-1"} |= "ConnectionError"` (or `|= "Error"`). There are the actual Python tracebacks — `redis.exceptions.ConnectionError: Error connecting to redis:6379` — the *what and why* the metric could never tell you.

That pivot — spike on the dashboard, jump to the logs for the stack trace — is 80% of real incident response. Metrics point, logs explain.

Heal it: `docker compose start redis`.

**Now pay the debt explicitly.** Section 1's lesson was "`down` deletes the logs." Watch it *not* happen:

```bash
docker compose stop api          # stop the app — its json-file logs would normally be all you had
# in Grafana Explore, query the LAST 15 minutes:
#   {container="capstone-api-1"} |= "ConnectionError"
```

The error lines are **still there** — they're in Loki's `lokidata` volume, shipped the instant they were written, completely independent of whether the api container still exists. Even a full `docker compose down` (which `rm`s every container) leaves them queryable, because the named volume survives `down`. *"The postgres-18 lecture would have survived this."* That sentence from Section 1, Lab 4 is now literally true — restart the api (`docker compose start api`) and the record of its every past failure is intact in Loki.

## Verify

```bash
curl -s 'http://localhost:9091/api/datasources/proxy/uid/LOKI_UID/loki/api/v1/labels' 2>/dev/null || \
  echo "Use Grafana Explore: {container=\"capstone-api-1\"} should return lines."
```

Simplest honest proof (do it in the UI): in **Explore → Loki**, `{container="capstone-api-1"}` returns log lines, and after the Redis break `|= "ConnectionError"` returns the tracebacks — **and those tracebacks are still queryable after you `stop` the api container.** That last clause is the whole point of the section.

Answer aloud:

**Q1. Metrics are pulled; logs are pushed. Why the opposite direction for each?**
<details><summary>Answer (read after attempting aloud)</summary>
Metrics are a small, fixed set of current numbers that can be re-read at any moment, so a scheduled pull is efficient and a failed pull is itself a useful signal. Logs are an unbounded event stream that must be captured *the instant it's produced* — a container that crashes can't be scraped afterward, so an agent tails and pushes continuously (black-box recorder, not on-demand). Different data shape → different transport.
</details>

**Q2. Loki indexes labels but not the log text. Why is that cheaper, and what's the rule it forces on you?**
<details><summary>Answer (read after attempting aloud)</summary>
Indexing every word (ELK-style) means huge indexes and heavy infra. Loki indexes only a few low-cardinality labels (container, job) and stores the raw lines compressed and un-indexed; you select the right *stream* by label, then brute-force `grep` within it (`|=`). Far less storage/compute. The rule it forces: **high-cardinality data (request IDs, user IDs, raw paths) goes in the log line, never in a Loki label** — the exact cardinality discipline you learned for Prometheus metrics, on the logs side.
</details>

**Q3. How does this lab make Section 1's "`down` deletes the logs" no longer true?**
<details><summary>Answer (read after attempting aloud)</summary>
Alloy tails each container's stdout and pushes every line to Loki *as it happens*, into Loki's `lokidata` **named volume**. The log record is now decoupled from the container's lifetime and stored somewhere `down` doesn't touch (named volumes survive `down`; only `down -v` removes them). So you can `stop` or even `down` the api and still query its full history in Loki — the evidence is off the box before the box dies.
</details>

## Clean up

Restore anything you stopped: `docker compose start redis api`. Leave the stack up for Lab 5 (which reasons over these exact signals — no new infra). Full teardown:

```bash
docker compose down          # logs SURVIVE (lokidata volume kept) — that's the feature
docker compose down -v       # only this wipes lokidata/promdata/grafanadata — deliberate full reset
```

Commit:

```bash
git add capstone/observability/loki-config.yml capstone/observability/config.alloy capstone/docker-compose.observability.yml
git commit -m "feat(observability): ship container logs to loki via alloy"
```
