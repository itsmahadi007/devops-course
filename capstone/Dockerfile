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