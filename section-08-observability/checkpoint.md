# Checkpoint — Section 08: Observability

Pass every task **from memory** — no peeking at the labs. If you have to peek, the section isn't done yet; redo that lab tomorrow and try again.

## Practical tasks

- [ ] **1.** From scratch, add a `/metrics` endpoint to a FastAPI app with `prometheus-fastapi-instrumentator`, and — without running Prometheus — `curl` it and point to the counter, the histogram, and the two labels the library grouped for cardinality safety (status class, `handler="none"`).
- [ ] **2.** Write a `prometheus.yml` that scrapes a compose service by DNS name, bring Prometheus up as a compose overlay, and get the target to **UP** in the Targets UI. Deliberately break the target (use the host port), read the exact error, and fix it.
- [ ] **3.** In the Prometheus expression box, write from memory: total req/s, req/s per handler, the error ratio, and p95 latency (`histogram_quantile` over rate'd buckets summed `by (le)`).
- [ ] **4.** In Grafana, add the Prometheus data source and build a 3-panel RED dashboard, then export it to JSON. Target: under 15 minutes.
- [ ] **5.** Create an alert on the error ratio, then make it fire by stopping Redis and hammering `/visits` — narrate Normal→Pending→Firing and what the `for` duration is doing. Restore Redis and watch it clear.
- [ ] **6.** Ship container logs to Loki via Alloy, and in Grafana Explore run a LogQL query that (a) selects the api stream, (b) filters for the Redis error, and (c) counts those errors over time. Then `stop` the api and prove the logs are still queryable.

## Explain aloud (interview drill — answer in 60–90 seconds each)

- [ ] The three pillars — metrics, logs, traces: what question does each answer, and how do you *pivot* between them during an incident?
- [ ] Why does Prometheus **pull** instead of push? Give three concrete advantages, and the one case where you'd push instead (and how).
- [ ] What is a time series, and what is **cardinality**? Tell the story of the label that takes a Prometheus down, and the one-line PromQL you'd run to find the culprit.
- [ ] Counter vs gauge vs histogram vs summary — one sentence each, with an example metric, and *why you never graph a raw counter*.
- [ ] A histogram never stored a single request's duration. Walk through how `histogram_quantile()` produces a p95, and what caps its accuracy.
- [ ] Read this aloud and explain every piece: `histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket[5m])))`. Why `rate` first, why `sum by (le)`, what breaks if you drop the `le`.
- [ ] The RED method — what are the three signals, what kind of service is it for, and how does it differ from USE? Which golden signal does RED *not* cover?
- [ ] Why is an error **ratio** the right alert metric, not an error count? Why alert on the ratio being high **`for` a duration** instead of instantly?
- [ ] Logs push, metrics pull — defend the asymmetry from the data's shape.
- [ ] What does Loki index, what does it *not* index, and why is that cheaper than ELK? What cardinality rule does it force on your log labels?
- [ ] How does this section make Section 1's "`docker compose down` deletes the logs" no longer true — name the agent, the store, and the reason the volume survives.
- [ ] SLI vs SLO vs error budget: define each, compute the budget in minutes for 99.9%/30d, and give the ship-or-freeze rule the budget dictates.
- [ ] What is a burn rate, and why do fast burn and slow burn get different responses (page vs ticket)? What does multi-window multi-burn-rate buy you?
- [ ] The one-sentence rule for what to page on, and the failure mode of paging on causes instead of symptoms.
- [ ] Why is `up == 0` for a few minutes always page-worthy even though it's an "infrastructure" signal, not a user symptom?
- [ ] Why did Promtail get replaced, and by what? (If someone hands you a `promtail` config in 2026, what do you say?)
- [ ] Why does mounting `/var/run/docker.sock` into the Alloy container make a security reviewer wince, and what mitigations exist?

### If you did Lab 6 (kube-prometheus-stack)

- [ ] On Kubernetes you don't edit `prometheus.yml` — what replaces it, what watches it, and why is a static target list unworkable in a cluster?
- [ ] What does `kube-prometheus-stack` bundle beyond Prometheus + Grafana, and what did you *give up* by using it instead of building the stack by hand?

## Gate

- [ ] `notes.md` filled in my own words
- [ ] Everything committed (capstone `/metrics` diff + `pyproject.toml`/`uv.lock`, `docker-compose.observability.yml`, `observability/prometheus.yml`, `observability/loki-config.yml`, `observability/config.alloy`, `dashboards/capstone-red.json` — no secrets; admin passwords are local-lab placeholders only)

When all boxes are checked, say so — the next section (GitOps with Argo CD) gets written against your notes.

## LinkedIn post ideas (this section)

When the section's done, these are ready-to-write posts for the "AI Engineer / running AI in production" challenge:

1. **"Pull, not push: the one Prometheus idea backend engineers get backwards."** — every API you've built pushes; monitoring is the inverse, and here's why that's the better design (unreachable = signal, config in one place, debuggable with curl).
2. **"The label that takes down your monitoring."** — cardinality explained from a real `/metrics` page: why `status="2xx"` not `"200"`, why they split latency into two histograms, and the one query that finds the culprit when Prometheus OOMs.
3. **"I made Section 1's dead logs come back to life."** — the `docker compose down` = logs deleted problem, and how Loki + Alloy ship them off the box so a stack trace survives the container that produced it. Metric spike → log pivot, shown.
4. **"What I actually page on (and the 3am CPU alert I deleted)."** — golden signals, SLO/error budget as a ship-or-freeze tool, symptom-vs-cause alerting. The senior-vs-junior monitoring interview answer.
