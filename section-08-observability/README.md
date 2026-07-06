# Section 08 — Observability (stub)

**Status:** stub — written when Section 07 completes.

**Goal:** make the capstone stack *observable* on kind: metrics, logs, dashboards, alerts, SLOs. The difference between "it's down" and "I knew before the user did."

**You'll be able to:** deploy the Prometheus/Grafana/Loki stack via Helm, instrument the capstone with a `/metrics` endpoint, write PromQL that answers real questions (rate, p95 latency, error ratio), build one honest dashboard, define an SLO and its alert, and write a small incident report.

**Planned labs:** kube-prometheus-stack install → instrument capstone (prometheus client) → PromQL drills → Loki + log queries → alert rules + SLO for /health → break the app, watch the alert fire, write the postmortem.

**Builds on:** the Section 4/5 cluster and chart.
