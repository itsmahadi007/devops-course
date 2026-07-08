# Lab 5 — SLOs, golden signals, and what to actually page on

**Goal:** no new infrastructure — this is a **thinking lab**, and it's the interview-gold one. You'll turn the numbers you've been graphing into *decisions*: the four golden signals, an SLI/SLO/error-budget for the capstone (computed in real PromQL against your own data), burn-rate alerting, and the judgment of what deserves to wake you at 3am. This is the chapter that separates "installed a dashboard" from "runs production."

## The mental map (read this first)

You now have metrics, dashboards, logs, and an alert. The missing piece is **judgment**: *which* numbers matter, *what* target to hold them to, and *when* a human must intervene. Google's SRE practice answers all three with a small stack of ideas:

```
   GOLDEN SIGNALS      the 4 numbers that describe any user-facing service
   ┌──────────────────────────────────────────────────────────────┐
   │  Latency     how long requests take   (esp. the tail, p95/p99)  │  ┐
   │  Traffic     how much demand           (req/s)                   │  │ RED
   │  Errors      how many requests fail     (ratio)                  │  ┘ covers
   │  Saturation  how "full" the resource is (CPU/mem/queue → USE)    │  ← the gap
   └──────────────────────────────────────────────────────────────┘
              │
              ▼  pick the user-facing ones, write them as ratios
   SLI   Service Level Indicator = good events / valid events   (a number, 0–1)
              │
              ▼  set a target
   SLO   Service Level Objective = "SLI ≥ 99.9% over 30 days"   (the promise)
              │
              ▼  the inverse is a budget you're allowed to spend
   ERROR BUDGET = 100% − SLO = 0.1% of 30 days ≈ 43 min of failure allowed
              │
              ▼  how fast you're spending it decides urgency
   BURN RATE → fast burn = page a human · slow burn = file a ticket
```

The through-line: **your RED dashboard already measures 3 of the 4 golden signals.** The fourth, **saturation**, is the resource view (USE method — Utilization, Saturation, Errors) that RED doesn't cover; you have raw material for it in the `process_*` metrics from Lab 1, and Lab 6 / the Kubernetes stack add proper node and container saturation. Everything else in this lab is turning those signals into a *contract* and an *escalation policy*.

## Steps

Bring the stack up if it's down (`docker compose up -d`) and generate steady traffic so the queries return real numbers — but the "work" here is reasoning, done at the Prometheus query box (**http://localhost:9090/graph**) and on paper.

```bash
while true; do curl -s localhost:9000/health >/dev/null; curl -s localhost:9000/visits >/dev/null; sleep 0.2; done
```

### 1. Name your four golden signals for the capstone

Write down, for *this* service, the concrete metric behind each signal. Then check yourself:

<details><summary>The four, mapped to your metrics (attempt yours first)</summary>

- **Latency** → `histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket[5m])))` — and split "good" vs "bad" latency; a fast error isn't "good latency."
- **Traffic** → `sum(rate(http_requests_total[1m]))` — req/s.
- **Errors** → `sum(rate(http_requests_total{status="5xx"}[5m])) / sum(rate(http_requests_total[5m]))` — the ratio.
- **Saturation** → the one RED misses. Closest signal you have: `process_resident_memory_bytes` (a gauge from Lab 1) and, in a container/cluster, CPU throttling and memory-vs-limit. Saturation predicts *future* failure ("we're at 90% memory, we'll OOM soon") where the other three describe *current* pain. This is why the Kubernetes stack (Lab 6) is worth it — it adds node/pod saturation you can't easily see from inside one process.
</details>

### 2. Define an SLI, then an SLO, for the capstone

An **SLI** is always a **ratio of good to valid events** — that shape makes it a clean 0–1 number you can average, target, and alert on. Two SLIs matter for an HTTP service:

**Availability SLI** — fraction of requests that didn't server-error:

```promql
sum(rate(http_requests_total{status!="5xx"}[30d]))
/
sum(rate(http_requests_total[30d]))
```

**Latency SLI** — fraction of requests served fast enough. This uses the histogram buckets directly. **Pick an `le` boundary that actually exists in your `/metrics` output** (Lab 1 — you can only slice at a real bucket edge). Say your target is "≤ 500ms" and `0.5` is a boundary:

```promql
sum(rate(http_request_duration_seconds_bucket{le="0.5"}[30d]))
/
sum(rate(http_request_duration_seconds_count[30d]))
```

The numerator is "requests that finished in ≤ 0.5s" (the cumulative bucket), the denominator is all requests. (You won't have 30 days of data in the lab — shrink to `[1h]` to see a live number. The *shape* is what matters.)

Now the **SLO** is a target over a window: *"99.9% of requests succeed over 30 days"* and *"95% of requests complete in under 500ms over 30 days."* Two judgment calls you must be able to defend:

- **Why not 100%?** 100% is the wrong target — it's infinitely expensive, and it leaves no room to *ever* deploy, since every change risks the number. The gap below 100% is deliberate slack.
- **Why 99.9% and not 99.99%?** Each extra nine is roughly 10× the cost (redundancy, on-call rigor, slower change). You pick the *lowest* number users are still happy with. For an internal/portfolio service, 99.9% is plenty; a payment rail might need 99.99%.

### 3. Turn the SLO into an error budget — and use it

The inverse of the SLO is your **error budget**: how much failure you're *allowed* before you've broken the promise.

```
   SLO 99.9% over 30 days
   → budget = 0.1% of 30 days
   → 30 days = 43,200 min → 0.1% ≈ 43 minutes of "down" allowed per 30 days
```

The budget isn't a threat — it's a **decision tool that ends the dev-vs-ops fight**:

- **Budget remaining?** Ship. Take the risky deploy, run the load test, do the migration. You've *earned* the risk.
- **Budget exhausted?** Freeze features, spend engineering on reliability until the budget recovers. No debate, no politics — the number decides.

Compute yours live (shrunk window): budget-remaining as a fraction is `1 - (errors / total) / (1 - SLO)`:

```promql
1 - (
  sum(rate(http_requests_total{status="5xx"}[1h])) / sum(rate(http_requests_total[1h]))
) / (1 - 0.999)
```

`> 0` means budget left; `< 0` means you've blown the SLO for that window.

### 4. Burn rate — one alert doesn't fit all failures

**Burn rate = how many times faster than "sustainable" you're spending the budget.** A burn rate of 1 means you'll use exactly the whole budget over the SLO window (30 days). A burn rate of 14.4 means you'll exhaust the *entire 30-day* budget in ~50 hours. This single number lets you scale urgency:

```
   burn rate = (error ratio right now) / (1 − SLO)

   FAST burn  (e.g. ≥14.4× over 1h → 2% of the 30d budget gone in an hour)
        → PAGE a human now. This is an outage in progress.
   SLOW burn  (e.g. ~3× over 6h → a persistent low-grade problem)
        → open a TICKET. Someone looks at it during business hours.
```

The mature pattern (SRE workbook) is **multi-window, multi-burn-rate**: fire the page only when a *short* window (say 5m) AND a *long* window (1h) both show a high burn rate — the short window makes it react fast, the long window stops a brief blip from paging. You don't need to implement it here; you need to be able to *explain* it, because it's a common senior-interview question. The Lab 3 alert you built (`error ratio > 5% for 1m`) is the single-window starter version of this idea.

### 5. The page/ticket/ignore decision — drills

For each scenario, decide **page / ticket / ignore** and *why*, then check. This is the muscle interviewers probe.

**Drill A.** At 3am you're paged: *"api container CPU at 92%."* Users report nothing wrong; latency and errors are normal.
<details><summary>Verdict</summary>
**Bad alert — should not have paged (at most a ticket).** CPU is a *cause/saturation* signal, not a *symptom*. High CPU with healthy latency and errors means the service is doing its job efficiently — that's utilization, not a problem. Paging on causes = alert fatigue = the real 3am alert gets ignored. Convert it to a *ticket/dashboard* signal, or a *page only if it predicts imminent symptom* (e.g. saturation trending to 100% with latency already rising). Page on what users feel.
</details>

**Drill B.** SLO is 99.9%/30d. Current 30-day availability is 99.97%. Product wants to ship a risky migration.
<details><summary>Verdict</summary>
**Ship it.** You're comfortably above the SLO — budget remaining. That budget *exists to be spent* on exactly this kind of change. Refusing to ship while you have budget is as wrong as shipping recklessly while you're out of it. (If it were 99.88% — already below SLO — you'd freeze and fix reliability first.) The number decides, not opinions.
</details>

**Drill C.** p95 latency jumped to 900ms but p50 is still 40ms. Error ratio is 0.
<details><summary>Verdict</summary>
**Ticket now, page if it's user-facing and sustained / breaching the latency SLO.** The p50/p95 gap means *most* requests are fine but the *tail* is suffering — a subset of requests (one slow endpoint, a cold cache, a locking query, one bad replica) got slow. No errors, so nothing's failing outright, but users hitting the tail are hurting. The *shape* (tail up, median flat) is the diagnostic signal: don't chase the average, investigate what's special about the slow 5% — that's exactly why you graph p95, not the mean.
</details>

**Drill D.** Prometheus's own `up{job="capstone-api"}` has been `0` for 3 minutes.
<details><summary>Verdict</summary>
**Page.** Either the app is down or monitoring can't see it — both are "you are now blind to a production service," which is itself an emergency (all your other symptom alerts silently can't fire). `up == 0` for more than a scrape-or-two is one of the few *infrastructure* signals that always warrants a page. (This is the meta-lesson: monitor the monitoring.)
</details>

## Verify

No command — the proof is that you can, from memory, state for the capstone:

1. Its four golden signals and the PromQL behind each.
2. One availability SLO and one latency SLO, with a defense of the specific numbers (why not 100%, why not one more nine).
3. The error budget those SLOs imply in minutes, and the ship/freeze rule.
4. One **page-worthy** condition (a symptom, sustained) and one **ticket-worthy** condition (slow burn / cause), and why each is sorted where it is.

Answer aloud:

**Q1. Why is every SLI written as a ratio of good/valid events instead of a raw count?**
<details><summary>Answer (read after attempting aloud)</summary>
A ratio is dimensionless (0–1), so it's comparable across traffic levels, time windows, and services; it can be directly compared to an SLO target; and it maps cleanly onto an error budget (1 − SLO). A raw count ("500 errors") means nothing without the traffic it came from and can't be turned into a percentage-based promise.
</details>

**Q2. You have budget to spare but a nervous PM wants to freeze all deploys "to be safe." What does the SLO framework say?**
<details><summary>Answer (read after attempting aloud)</summary>
Freezing while you have budget wastes it — the budget exists precisely so you *can* take deploy risk. The framework replaces gut feeling with a number: budget remaining → ship; budget gone → freeze and fix reliability. It defuses the eternal dev(velocity)-vs-ops(stability) fight by making the error budget, not either team's anxiety, the arbiter.
</details>

**Q3. Give the one-sentence rule for what to page on, and the failure mode of getting it wrong.**
<details><summary>Answer (read after attempting aloud)</summary>
Rule: **page a human only for sustained symptoms that users feel and that require immediate action** (errors, latency SLO breach, availability / `up == 0`) — everything else is a ticket or a dashboard. Failure mode of getting it wrong: paging on causes (CPU, memory, "Redis restarted") and on blips floods the pager with non-actionable noise → alert fatigue → the on-call engineer starts ignoring alerts → the one real 3am page gets missed. Fewer, symptom-based, actionable pages beat a wall of cause-based ones.
</details>

## Clean up

No infra to tear down. Kill the load loop (Ctrl-C). Leave the stack up if you're going straight to the optional Lab 6; otherwise `docker compose down` (volumes and dashboards kept). Nothing to commit for this lab unless you jotted your SLO decisions somewhere in the repo — a good idea to capture them in `notes.md`.