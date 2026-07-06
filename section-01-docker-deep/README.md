# Section 01 — Docker Deep

**Status:** in progress · **Time:** ~1 week at 2–4h/day · **Labs:** 6

You've used Docker for years. This section closes the gap between *using* Docker and *owning* it — the difference interviewers probe and production incidents expose.

## The mental model (read first)

**An image is a stack of read-only layers.** Every `RUN`/`COPY`/`ADD` line in a Dockerfile produces one layer — a filesystem diff. Layers are content-addressed and shared: ten images `FROM python:3.14-slim` store that base once. A **container** is just one extra *writable* layer on top of an image, plus a process namespace. Delete the container, the writable layer dies; the image is untouched.

**The build cache works top-down, line by line.** Docker reuses a cached layer if the instruction AND everything it depends on are unchanged. First changed line invalidates every layer below it. This is why the classic pattern is: copy dependency manifests → install deps → *then* copy source code. Code changes daily; deps change weekly — order the Dockerfile so the expensive layer survives your commits.

**Slim images are a security and speed feature, not vanity.** Less in the image = fewer CVEs to patch, faster pulls/deploys/scaling, smaller attack surface. The levers: slim base images, `.dockerignore`, multi-stage builds (build tools stay in the builder stage, only artifacts reach the runtime stage), no cache/temp files in layers, non-root user.

**Networking in one paragraph:** every container joins a Docker network; on a user-defined network, containers reach each other **by service name** (built-in DNS) — `redis://redis:6379`, not an IP. `-p 8080:8000` publishes container port 8000 on host port 8080. Volumes outlive containers: named volumes for data (Postgres), bind mounts for dev.

**Healthchecks make orchestration possible.** A `HEALTHCHECK` turns "the process is running" into "the app actually answers." Compose (and later Kubernetes) can gate startup ordering and restarts on it.

## Why this matters for jobs

- "Why is your image 1.2 GB and how would you shrink it?" is a standard DevOps screening question — Lab 2 vs Lab 3 IS the answer.
- Layer-cache reasoning is how you cut CI build times from 8 min to 40 s — a bread-and-butter freelance infra gig.
- Non-root containers + slim bases are the first thing a security review checks.

## Labs

| Lab | What you build | Proves |
|---|---|---|
| [1 — Image anatomy](labs/lab-01-image-anatomy.md) | nothing new — you dissect nginx | layers, cache, inspect, logs |
| [2 — Naive containerize](labs/lab-02-containerize-capstone.md) | capstone in a container, the obvious way | why naive images are huge |
| [3 — Multi-stage slim](labs/lab-03-multi-stage-slim.md) | production-grade capstone image | multi-stage, non-root, healthcheck, cache ordering |
| [4 — Compose stack](labs/lab-04-compose-stack.md) | capstone + Redis + Postgres, one command | networks, service DNS, volumes, healthcheck gating |
| [5 — Build the fake VPS](labs/lab-05-build-vps-lab.md) | `vps-lab/` — your practice server | sshd, users, key-only auth; used by Sections 2–3 |
| [6 — Registry](labs/lab-06-registry-ghcr.md) | capstone image on GHCR, public | tagging, login, push/pull, registries |

Do them in order. Each ends with **Verify** (proof it worked) and **Clean up**.

## Reading (curated, ~1.5h total)

- [Dockerfile reference — best practices](https://docs.docker.com/build/building/best-practices/) — the canonical checklist
- [Multi-stage builds](https://docs.docker.com/build/building/multi-stage/)
- [Build cache](https://docs.docker.com/build/cache/) — read until the invalidation rules feel obvious
- [Compose: how it works](https://docs.docker.com/compose/intro/compose-application-model/)
- [uv in Docker](https://docs.astral.sh/uv/guides/integration/docker/) — the pattern Lab 3 uses

## Done when

Every task in [checkpoint.md](checkpoint.md) passes from memory, and [notes.md](notes.md) is filled in your own words. Then the next section gets written.
