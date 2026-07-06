# DevOps Course — learning in public

My self-built, hands-on DevOps course: 11 sections, each one **read → practice locally → notes → checkpoint**. One small FastAPI service (the [capstone](capstone/)) evolves through every section — from a bare container to a GitOps-managed, observable, self-hosted-LLM-serving platform. Everything runs locally at $0.

Built and completed in public as part of my move into **backend + DevOps + AI-infrastructure** work.

## How I use it

1. Read the section `README.md` (the lesson).
2. Do the `labs/` in order on my machine (macOS + Docker Desktop).
3. Write what I actually learned in `notes.md`.
4. Pass `checkpoint.md` — from memory, no peeking.
5. Only then the next section gets written (adapted to my notes).

## Progress

- [ ] **Section 01 — Docker Deep** ← current
- [ ] Section 02 — CI/CD with GitHub Actions
- [ ] Section 03 — Linux & Networking (inside the fake VPS)
- [ ] Section 04 — Kubernetes Core
- [ ] Section 05 — Helm
- [ ] Section 06 — Terraform
- [ ] Section 07 — AWS Core
- [ ] Section 08 — Observability (Prometheus · Grafana · Loki)
- [ ] Section 09 — GitOps (Argo CD)
- [ ] Section 10 — LLM Serving Infrastructure
- [ ] Section 11 — Cert Prep (CKA · AWS SAA) + market entry

## The lab environment

| Piece | What it is |
|---|---|
| `capstone/` | FastAPI service — the app everything gets practiced ON |
| `vps-lab/` | Docker container as a fake VPS (Debian + sshd) — I SSH into it like a rented server. Built by me in Section 1, Lab 5 |
| kind | local Kubernetes (from Section 4) |
| LocalStack | local AWS emulation (Sections 6–7) |

## Why this course exists

Six years of backend work already came with Docker, Linux, SSH, DNS, and deployments — this course turns that implicit ops experience into an explicit, provable DevOps skill set. Background: [docs/why-this-course.md](docs/why-this-course.md).
