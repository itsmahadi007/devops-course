# Lab 2 — Containerize the capstone (the naive way)

**Goal:** containerize `capstone/` the way most tutorials do — then measure why it's bad. The pain here is the setup for Lab 3.

## Steps

**1. Sanity-check the app bare-metal first:**

```bash
cd capstone
uv sync && uv run uvicorn app.main:app &
curl -s localhost:8000/health
kill %1
```

**2. Write the naive Dockerfile** — `capstone/Dockerfile.naive`, by hand:

```dockerfile
FROM python:3.14
WORKDIR /app
COPY . .
RUN pip install .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**3. Build it and feel the problems:**

```bash
docker build -f Dockerfile.naive -t capstone:naive .
docker images capstone:naive
```

Note the size (expect ~1 GB+). Three sins: full `python:3.14` base (a whole Debian with compilers), `COPY . .` **before** installing (any code change nukes the dependency cache layer — rebuild everything), and no `.dockerignore` (your `.venv/`, `.git`, caches all went into the build context and possibly the image).

**4. Prove the cache sin:**

```bash
touch app/main.py
time docker build -f Dockerfile.naive -t capstone:naive .
```

One meaningless file touch → `pip install` runs again from scratch. Imagine that in CI on every commit.

**5. Write `.dockerignore`** — `capstone/.dockerignore`:

```
.venv/
__pycache__/
*.pyc
.git/
Dockerfile*
```

Rebuild and check the "sending build context" size drop.

**6. Run and test:**

```bash
docker run -d --name capstone-naive -p 8000:8000 capstone:naive
curl -s localhost:8000/ask?q=hello
```

## Verify

- `curl localhost:8000/health` returns `{"status":"ok"}` from the container.
- You can state the naive image's size and name its three sins without notes.

## Clean up

```bash
docker rm -f capstone-naive
```

Keep `capstone:naive` (the image) — Lab 3 compares against it. Commit `Dockerfile.naive` and `.dockerignore`.
