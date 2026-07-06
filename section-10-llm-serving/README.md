# Section 10 — LLM Serving Infrastructure (stub)

**Status:** stub — written when Section 09 completes.

**Goal:** the differentiator — the flagship. The capstone's `/ask` endpoint finally gets a real, self-hosted LLM, served on the cluster with observability and cost thinking. This is the section that turns "DevOps course" into "AI-infrastructure portfolio."

**You'll be able to:** serve a small open model locally (llama.cpp / vLLM CPU mode on Apple Silicon; GPU serving as theory + optional cloud extra), explain quantization trade-offs from experience, put an LLM behind an API gateway with routing/caching/cost metering (the infra version of what ApplyFuel does in app code), autoscale it, and monitor tokens/sec + latency in Grafana.

**Planned labs:** run a quantized model locally → wrap it in an OpenAI-compatible server on kind → point capstone `/ask` at it → add caching + per-request token/cost metrics → load-test and read the dashboards → the flagship writeup (the LinkedIn/portfolio case study).

**Builds on:** everything. This is why the course exists.
