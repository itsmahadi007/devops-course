# Lab 3 — Multi-stage, slim, non-root, healthy

**Goal:** the production-grade image — multi-stage with uv, slim base, correct cache order, non-root user, healthcheck. This exact Dockerfile pattern is reusable for every Python service you'll ever ship.

## Steps

**1. Lock dependencies (uv needs a lockfile for reproducible builds):**

```bash
cd capstone
uv lock
```

**2. Write the real `capstone/Dockerfile`:**

```dockerfile
# ---- build stage: has uv, resolves and installs deps into .venv ----
FROM python:3.14-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app

# Deps first — this layer survives code changes
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Code last — only this layer rebuilds on a commit
COPY app ./app

# ---- runtime stage: no uv, no build tools, just the venv and the code ----
FROM python:3.14-slim
RUN useradd --create-home --uid 1000 appuser
WORKDIR /app
COPY --from=builder --chown=appuser:appuser /app /app
ENV PATH="/app/.venv/bin:$PATH"
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Read it line by line and make sure every line has a *reason* you could defend in review.

**3. Build and compare:**

```bash
docker build -t capstone:0.1.0 .
docker images | grep capstone
```

Expect roughly 5–6× smaller than `capstone:naive`. Optional deeper look: `brew install dive && dive capstone:0.1.0`.

**4. Prove the cache order is fixed:**

```bash
touch app/main.py
time docker build -t capstone:0.1.0 .
```

The `uv sync` layer should say `CACHED` — only the code layer rebuilt. Compare with Lab 2 step 4.

**5. Run and watch the healthcheck work:**

```bash
docker run -d --name capstone -p 8000:8000 capstone:0.1.0
docker ps --filter name=capstone        # STATUS: (health: starting) → (healthy)
docker inspect --format '{{.State.Health.Status}}' capstone
docker exec capstone whoami             # appuser — not root
```

## Verify

- Image at least ~5× smaller than naive; `whoami` inside = `appuser`; health status reaches `healthy`.
- Explain out loud: why deps-then-code ordering; why two stages instead of one slim stage; what `--frozen` protects against; why non-root matters.

## Clean up

```bash
docker rm -f capstone
docker rmi capstone:naive   # done comparing — the naive image has served its purpose
```

Commit `Dockerfile` and `uv.lock`. Update `capstone/README.md` evolution log: "Section 1: production image — multi-stage uv, non-root, healthcheck."
