"""Capstone service — deliberately tiny. The DevOps around it is the course."""

import os

import redis
from fastapi import FastAPI

app = FastAPI(title="capstone")

REDIS_URL = os.environ.get("REDIS_URL", "")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/ask")
def ask(q: str = "") -> dict:
    # Canned answer for now. Section 10 replaces this with a self-hosted LLM.
    return {"question": q, "answer": "I am a placeholder. A real LLM arrives in Section 10."}


@app.get("/visits")
def visits() -> dict:
    if not REDIS_URL:
        return {"visits": None, "detail": "REDIS_URL not set"}
    r = redis.Redis.from_url(REDIS_URL, socket_connect_timeout=2)
    return {"visits": r.incr("visits")}
