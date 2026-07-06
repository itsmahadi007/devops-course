# capstone

A deliberately tiny FastAPI service. The point is never the app — it's everything the course builds AROUND it (containers, CI, deploys, K8s, IaC, observability, GitOps, LLM serving).

Endpoints: `GET /health` · `GET /ask?q=...` (canned answer until Section 10 gives it a real self-hosted LLM) · `GET /visits` (Redis counter; needs `REDIS_URL`).

Run bare-metal (pre-Section-1 sanity check):

```bash
cd capstone
uv sync
uv run uvicorn app.main:app --reload
curl localhost:8000/health
```

**Evolution log** (updated as sections complete):
- Section 0: born. Bare `uv run`.
