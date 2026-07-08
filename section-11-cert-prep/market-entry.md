# Market entry — turning six months into the first offer

**Goal:** convert this repo, the two certs, and six years of backend/AI shipping into a running pipeline — CVs out, freelance profiles live, LinkedIn engine on, interviews booked. This starts **day 1 of this section, in parallel with cert prep**, and never stops. A cert that lands in week 8 upgrades a pipeline that's already moving; it doesn't start one.

## The mental map (read this first)

```
                 ┌─────────────────────────────────────────┐
                 │   ONE skill base (this repo + 6 yrs)      │
                 └───────────────┬───────────────┬───────────┘
                                 │               │
                    ┌────────────▼───┐   ┌───────▼────────────┐
                    │ CV-A backend   │   │ CV-B DevOps /       │
                    │  -led (+DevOps)│   │  platform (+AI-infra)│
                    └────────┬───────┘   └───────┬────────────┘
                             │                   │
          full-time apps ────┤                   ├──── full-time apps
                             │                   │
                    ┌────────▼───────────────────▼────────┐
                    │  freelance infra gigs (income NOW)   │
                    └──────────────┬───────────────────────┘
                                   │
                    ┌──────────────▼───────────────────────┐
                    │  LinkedIn engine → distribution        │
                    │  (every post points at ONE repo file)  │
                    └────────────────────────────────────────┘
```

**The founding insight, in one line:** the skills were never why you were underpaid — **access and distribution were** (`docs/why-this-course.md`). At ~$1,000/month on a senior US-remote title, the binding constraint is a *credible offer above threshold, soon* — not a salary ceiling. So this file optimizes for **funnel width and speed**, not for the highest theoretical number. A concrete modest offer in month 2 beats a theoretical high one in month 9.

**Two CVs, one you.** You are not two people. You are one engineer who can be *read* two ways, and you send whichever reading fits the job post. Backend role → CV-A. DevOps/platform role → CV-B. AI-infra/MLOps role → CV-B with the AI-infra summary swapped to the front (that's the premium combination, and it's the one nobody else in the rebranding lane can fake). Same GitHub link on both; same truth; different order of emphasis.

**The repo does a job no bullet can.** Anyone can *write* "experienced with Kubernetes." Almost nobody can hand an interviewer a public repo where a self-hosted LLM answers requests behind their own GitOps-managed, observable, Helm-packaged cluster — built in the open, commit by commit. That artifact is what separates you from the flooded rebranding lane. Every CV, every proposal, every post drives to a **specific file** in it.

---

## CV variant A — Backend-led (with DevOps depth)

**Send this for:** Senior/Staff Backend, Python, API, platform-backend, and AI-application roles. This is your home turf with a widened moat.

**Header line:**
> **Senior Backend Engineer** · Python / Django / DRF / FastAPI · Production AI systems · Docker · Kubernetes · CI/CD
> github.com/itsmahadi007/devops-course · [your email] · Bangladesh (remote, US hours flexible)

**Summary (2 lines):**
> Senior backend engineer, ~6 years, shipping production Python services and AI/LLM systems (multi-model routing, cost metering, eval harnesses). Now operate the full delivery path myself — containerized, CI/CD'd, Kubernetes-deployed, observable — so my services ship and stay up without waiting on a separate ops team.

**Experience bullets (fold the infra depth into existing roles — don't invent a job):**
- Shipped a production Chrome-Web-Store AI product (ApplyFuel): multi-model LLM orchestration with per-request cost metering and an evaluation harness — the "AI runs in production, and someone pays the bill" discipline.
- Tuned Postgres and Redis under real load (connection pooling, cache-eviction policy, query hot-paths) — the same knowledge that maps directly onto managed-service tradeoffs (RDS Multi-AZ vs read replicas, ElastiCache) on AWS.
- Owned deploys end to end on AWS (EC2/S3), DNS, and SSH-based release flows for my own services.

**Portfolio project block (this repo — the widened moat):**
> **Self-hosted AI platform (public, built end-to-end)** — github.com/itsmahadi007/devops-course
> - Packaged a FastAPI service into a **multi-stage image, 1.67 GB → 220 MB** (47 MB compressed to ship), non-root (UID 1000), with a container healthcheck driving orchestration gates.
> - Built the delivery pipeline in GitHub Actions: test → lint → **multi-arch build (amd64+arm64)** → push to GHCR, with a self-hosted runner deploying over SSH.
> - Ran the same stack on Kubernetes (kind): probes, ConfigMap/Secret wiring, PVC-backed Postgres, ingress — packaged as a **Helm chart** and deployed via **Argo CD GitOps** (git as the source of truth, auto-sync + self-heal).
> - Instrumented it with Prometheus/Grafana/Loki (RED-method dashboards, one alert rule), and stood up a **self-hosted LLM** (llama.cpp) behind the platform to power the service's `/ask` endpoint.

**Keep it to one page.** The backend experience leads; the repo block sits directly under it as proof the ops claims are real. Cert line at the top once earned: `CKA · AWS SAA (SAA-C03)`.

---

## CV variant B — DevOps / Platform-led (with AI-infra framing)

**Send this for:** DevOps Engineer, Platform Engineer, SRE, Cloud Engineer, and — the premium target — **MLOps / AI-Infrastructure** roles. Here the repo leads and the backend depth becomes the differentiator, not the headline.

**Header line:**
> **DevOps / Platform Engineer** · Kubernetes · CI/CD · Terraform · AWS · Observability · **AI-serving infrastructure**
> CKA · AWS SAA · github.com/itsmahadi007/devops-course

**Summary — two versions, pick by the job post:**

*Standard DevOps summary:*
> Platform engineer who ships the whole path: container → CI/CD → Kubernetes → GitOps → observability. Certified (CKA, AWS SAA) with a public, end-to-end repo proving each layer. Backed by ~6 years as a production backend engineer — I've been on the other side of the pipeline, so I build platforms developers actually want to use.

*AI-infra / MLOps summary (swap this to the front for AI-infra posts — this is the hardest-to-fill 2026 role, and your unfair advantage):*
> AI-infrastructure engineer: I run models in production *and* the platform under them. ~6 years backend (Python/FastAPI), production LLM systems (multi-model routing, cost metering, eval harnesses), plus the full delivery stack — Kubernetes, GitOps, observability, self-hosted model serving. My public repo ends with a self-hosted LLM served behind my own GitOps-managed cluster: the MLOps loop, built end-to-end and in the open.

**Skills line (ATS keyword bait — put it high, it's what recruiter searches and matchers scan):**
> Docker · Kubernetes (CKA) · Helm · Argo CD / GitOps · GitHub Actions · Terraform · AWS (SAA) · Prometheus · Grafana · Loki · Linux · Nginx · Python · FastAPI · LLM serving (llama.cpp/vLLM concepts)

**Project bullets (the repo IS the experience — lead with the flagship, then decompose):**
- **Flagship:** designed and built a self-hosted AI platform end-to-end — a self-hosted LLM answering live requests behind a GitOps-managed, observable, Helm-packaged Kubernetes cluster. Public, commit-by-commit: github.com/itsmahadi007/devops-course.
- **CI/CD:** GitHub Actions pipeline — test/lint → multi-arch image build (amd64+arm64) → GHCR push → deploy; self-hosted runner reaching a private target over SSH.
- **Kubernetes:** deployments with liveness/readiness/startup probes, ConfigMaps/Secrets, PVC-backed stateful services, ingress; RBAC, NetworkPolicy, and etcd backup/restore drilled for CKA.
- **IaC:** Terraform (Docker + Kubernetes/Helm providers) managing the stack as code with real state-file handling and drift detection.
- **Observability:** Prometheus + Grafana (RED-method dashboards, alerting) + Loki log aggregation; SLO/golden-signals reasoning.
- **Container engineering:** multi-stage build cutting image 1.67 GB → 220 MB, non-root, healthchecked — the layer/cache/signal fundamentals, not just `docker build`.

**Positioning note — say "AI-infra" out loud whenever the role allows.** Vanilla DevOps is a flooded, lower-paid lane. The moment a job post mentions ML, models, GPUs, inference, data pipelines, or "AI" anywhere — lead with the AI-infra summary. That combination (production AI *plus* the platform under it) is what recruiters call 2026's hardest-to-fill technical role, and it's the one framing where your six years of backend/AI is a moat instead of a footnote.

---

## Freelance / contract infra-gig entry playbook (income *during* the course)

**Why now, not "when I'm finished":** infra work has a real small-gig market you can already serve — dockerizing an app, setting up a CI/CD pipeline, a Docker→K8s migration, a server/nginx/TLS setup, a Terraform starter. These are exactly Sections 1–6. Start listing in month 1. The first paid gig is worth more than the tenth practice lab — it's proof, income, and a testimonial in one.

### Platforms (pick 2, don't spread thin)

| Platform | Fit for you | Reality |
|---|---|---|
| **Upwork** | Primary. Deep pool of "need someone to set up CI/CD / dockerize / fix our K8s" gigs | New-account cold-start is real — first 3–5 gigs are about *reviews*, not rate. Price to win them, then climb |
| **Toptal / Gun.io / Arc.dev** | Higher-quality, vetted, better pay; screening is stiff | Worth applying once CV-B + repo are polished — your senior title + public portfolio pass screens most rebranders fail |
| **Contra / Fiverr Pro** | Productized gigs ("I will dockerize your app + write CI in 3 days") | Good for packaging a repeatable deliverable at a fixed price |
| **LinkedIn / direct** | Warmest, no platform cut | Your posting engine feeds this — a good post *is* a lead-gen ad. BD network + US-remote title is credible |

### Profile positioning (freelance ≠ CV — it's an outcome, not a résumé)

- **Headline = the outcome, not the stack:** "I set up production-grade CI/CD and Kubernetes for backend teams" beats "DevOps Engineer skilled in Docker, K8s, Terraform." Buyers buy the result.
- **Lead with the repo.** Your public, end-to-end repo is a portfolio 90% of freelance-infra profiles simply don't have. Pin it, screenshot the Grafana dashboard and the Argo sync view, link specific files.
- **Turn each finished section into a productized gig:** S1→"Dockerize your app (multi-stage, secure, small)", S2→"GitHub Actions CI/CD pipeline", S3→"Nginx reverse proxy + TLS", S4/5→"Deploy your app to Kubernetes with Helm", S6→"Terraform starter for your infra". Fixed scope, fixed price, fast delivery.
- **The AI-infra edge here too:** "Self-host an LLM for your app (private, cost-controlled)" is a gig almost nobody credibly offers and demand is climbing. That's your S10 turned into a premium listing.

### First-gig strategy

1. **Win the first 3 reviews deliberately.** Price them to be an easy yes for the buyer (a small dockerization or a CI setup). You're buying social proof, not maximizing this invoice.
2. **Over-deliver visibly:** a short Loom walkthrough of what you set up + a one-page README hand-off. Reviews that say "explained everything clearly" are what convert future higher-paying buyers.
3. **Small fixed-scope over open-ended hourly** at the start — buyers trust a defined deliverable from an unproven profile more than an hourly meter.
4. **Then raise rates every 2–3 reviews** until proposals stop converting; that ceiling is your real market rate.

### Rate guidance (honest, for your profile — BD-based, senior, new-to-platform)

- **Anchor to your reality, not US ceilings.** Your binding constraint is beating ~$1,000/month, not matching a US freelancer's $120/hr. Even conservative freelance rates clear that bar fast.
- **Cold-start hourly (0 reviews):** ~$25–35/hr — deliberately low to win the first gigs. This is a *marketing cost*, time-boxed to the first few jobs, not your worth.
- **After ~5 solid reviews:** ~$40–60/hr is defensible for a senior with a public portfolio and (soon) CKA.
- **With CKA + SAA + a testimonial wall:** $60–90/hr on Upwork, higher on vetted platforms — and now you're choosing gigs, not chasing them.
- **Fixed-price small gigs (better than hourly early on):** dockerize an app ~$150–400; a CI/CD pipeline ~$300–800; nginx+TLS setup ~$150–350; a Terraform starter ~$400–1,000; K8s deploy + Helm chart ~$600–1,500. Scope tightly, quote a range, deliver fast.
- **Rule:** never anchor low *because* you're from Bangladesh — anchor low *only* to buy your first reviews, then climb on the strength of the portfolio. The repo is your permission to charge like the senior engineer you are.

---

## Interview story bank — every checkpoint becomes a STAR story

**Why this exists:** interviews are won on *specific stories told well*, not on knowledge recited. You've already built the raw material — every section's `checkpoint.md` "explain aloud" item is a story waiting to be shaped. This turns six months of learning into ~15 rehearsed, repeatable answers.

**The method:** walk every completed section's `checkpoint.md`. Each "explain aloud" / "session went deeper" item becomes one STAR card:

- **S**ituation — the concrete moment (a real thing that happened in a lab: ":latest moved overnight and my build broke", "postgres:18 refused to start with the old volume path", "the app ran but every request was refused").
- **T**ask — what had to be true.
- **A**ction — what you actually did, in first-person specifics (the command, the diagnosis chain, the fix).
- **R**esult — what it proved / the number / the lesson that now transfers.

**Write them in a single file (`notes.md` here, or a private doc) and rehearse each aloud at least twice.** Spoken, not read — the goal is fluent recall under pressure, not a perfect paragraph.

### The story bank shopping list (aim for 12–15 cards)

| Section | Strongest story seeds (from its checkpoint) |
|---|---|
| S1 Docker | 1.67 GB → 220 MB multi-stage shrink (numbers!) · ":latest bit me — mutable tags vs digests" · "port published, every request refused" → 0.0.0.0 vs 127.0.0.1 · 10-second `docker stop` → PID 1 & signals · authn vs authz on the GHCR push |
| S2 CI/CD | arm64-only image → `exec format error` → multi-arch fix · self-hosted runner: *why* a hosted runner can't reach your laptop (NAT reality) · least-privilege `GITHUB_TOKEN` scoping |
| S3 Linux/net | reverse proxy + TLS from first principles (chain of trust) · "why is nothing listening on that port" debugging with ss/dig/curl · iptables/Docker chains |
| S4 K8s | killed a pod, watched the reconcile loop self-heal · liveness/readiness/startup probes mapped from the Docker healthcheck · Secrets "aren't secret without extra work" |
| S5 Helm | parameterized raw manifests into a chart · a release rollback and what a revision actually stores |
| S6 Terraform | drift detection (hand-deleted a container, plan caught it) · "who owns what: TF vs Helm vs Argo" |
| S7 AWS | least-privilege IAM policy reading · SG vs NACL mapped to iptables · a cost/scenario decision |
| S8 Observability | built a RED-method dashboard + one alert · "logs die with the container → why we ship them centrally" (the S1 debt paid) · SLO/golden-signals reasoning |
| S9 GitOps | hand-edited the cluster, watched Argo revert it (drift as a first-class citizen) · why prod credentials leave CI |
| S10 LLM serving | self-hosted an LLM, wired `/ask` to it · quantization/RAM napkin math · TTFT vs tokens/sec, batching · cost metering (connect to ApplyFuel) |
| Career | "why DevOps as a second lane, not a pivot" · "what does dedicated DevOps headcount tell you about a company" (your own BD insight) |

**Behavioral must-haves (write these too — they're asked every loop):** a time you debugged something under pressure (pick the sharpest S1/S4 one), a time you decided *not* to use a tool (S6 "when NOT to use Terraform" — senior signal), a time you shipped despite ambiguity (ApplyFuel), and the honest "tell me about a time you were wrong" (a lab assumption that bit you — the postgres:18 or :latest one, told with what you now do differently).

---

## LinkedIn engine — hooks pointing at the repo (see repo `TODO.md`)

**The rule (from the course style contract):** every completed section is post material, and **every post points at a *specific file* in the repo, not the repo root** — specificity is what converts a scroll into a click. Positioning: *"AI Engineer / running AI in production."* Repo `TODO.md` already parks the Section-1 candidates ("do these later") — this is where you pick them up.

**Ready-to-write hooks (one per section, each ends by driving to a repo file):**

- **S1** — "I shrank a container image 1.67 GB → 220 MB. Here's the one reordering that did most of it." → link the multi-stage `Dockerfile`. *(Already in `TODO.md` as a strong candidate.)*
- **S1** — "`:latest` broke my build overnight and I hadn't changed a line of code. Mutable tags vs digests, live." *(In `TODO.md`.)*
- **S1** — "'Login Succeeded' — then the push was denied. Authentication is not authorization." *(In `TODO.md`.)*
- **S2** — "My image ran on my Mac and crashed on a $5 VPS with one cryptic error. `exec format error`, and the multi-arch fix." → the CI workflow file.
- **S4** — "I killed a pod on purpose and watched Kubernetes bring it back. The reconcile loop, in 40 seconds." → the deployment manifest.
- **S9** — "I hand-edited my cluster. 30 seconds later Argo CD silently undid it. That's the whole point of GitOps." → the Argo Application manifest.
- **S10 (flagship)** — "I built a self-hosted LLM behind my own GitOps-managed Kubernetes platform — in public, one commit at a time. Here's the repo." → the repo, with the architecture diagram.
- **Cert posts** — a pass announcement is the single highest-engagement format on the platform. "Passed the CKA." / "Passed AWS SAA." Each points back at the course repo. Post the *same week* you pass.
- **Capstone / finish post** — "11 sections, 2 certs, one public repo: a self-hosted AI platform built end-to-end." The 11/11 progress boxes are the visual.

**Cadence that's sustainable:** one substantive post per completed section, plus the two cert announcements and the finish post. Consistency over volume — a post a week that each drives to a file beats a daily firehose that drives nowhere.

**Feed the freelance funnel with it:** every good post is also a lead-gen ad. When a post lands, the profile it drives traffic to should already say "available for infra/DevOps/AI-infra contract work" — so distribution and income share one engine.

---

## The application engine (the part that actually produces offers)

Certs and CVs are ammunition; this is pulling the trigger, at volume, consistently.

- **A tracker from day 1** (a spreadsheet is fine): company · role · which CV variant sent · date · channel (job board / referral / LinkedIn / freelance) · status · next action. What you can't measure you can't tune.
- **Volume target, both lanes:** apply as backend *and* DevOps/AI-infra — you're widening the funnel, not choosing. Whichever lane produces a credible offer first wins; that was the founding decision.
- **BD-accessible channels first** (funnel width beats prestige): remote-first job boards, LinkedIn "open to work" + recruiter DMs, BD companies with *dedicated* DevOps headcount (your own quality filter — those are the better employers), and the freelance platforms feeding both income and testimonials.
- **Referral > cold apply, always.** Every LinkedIn post that lands is a warm-intro opportunity; every freelance client is a potential referral. Distribution compounds.
- **The weekly loop:** N applications + 1 post + freelance-proposal quota + tracker review. Steady beats sporadic — a pipeline running for eight weeks by exam day is worth more than the cert itself.
