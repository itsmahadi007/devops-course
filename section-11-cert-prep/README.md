# Section 11 — Cert Prep + Market Entry

**Status:** written — in progress · **Time:** ~8 weeks for both certs, market work runs in parallel from day 1 · **Plans:** 3 (no labs)

Section 10 left you with the flagship: a self-hosted LLM answering `/ask` behind your own GitOps-deployed, observable, Helm-packaged Kubernetes platform — all of it in a public repo, all of it built by your hands. This section builds nothing new. It **converts** — six months of artifacts into interviews, and interviews into the first credible offer. Different shape than every section before it: no labs, no ports, no containers. Three plans and a set of gates.

## The mental model (read first)

**A cert is a door badge; the repo is the demo.** Two different artifacts doing two different jobs. HR filters, recruiter searches, and ATS keyword matchers can't read your Argo CD sync loop — they can read "CKA" and "AWS SAA" on a title line. The badge gets you *through the door*; the repo and the stories are what you *show once inside*. Neither substitutes for the other: a cert with no evidence looks like a rebranding applicant (the flooded lane `docs/why-this-course.md` warned about); a great repo with no badge never gets seen by half the funnel. You're finishing both.

**The certs were chosen backwards from the exams.** This course's sections weren't a random tour — S4/S5/S8/S9 map onto CKA domains, S7 onto SAA domains, deliberately. So cert prep here is *gap-filling and speed-training*, not learning Kubernetes or AWS from scratch. The two plan files are gap maps first, schedules second.

**Speed to the first credible offer beats everything** — that was the founding decision (2026-07-06). Which has a sharp consequence: **market entry does not wait for the certs.** CVs, freelance profiles, LinkedIn posts, and applications start the same week you start this section. A cert that lands in week 8 upgrades a pipeline that's already running; it doesn't start one.

```
Week →      1   2   3   4   5   6   7   8   9 ...
CKA lane:  [gap drills][lifecycle][speed][exam]
SAA lane:                              [gaps][grind][grind][exam]
Market:    [CVs + profiles live][stories][posting + applying →→→→→ ongoing]
```

## Sequencing: CKA first

- **Freshness.** You just spent sections 4, 5, 8, 9, 10 living in kubectl on kind. CKA is performance-based — a 2-hour timed terminal session. That muscle memory decays in weeks; use it now. S7 (AWS) was ~3 months ago and SAA is recall-based anyway — it needs its own refresh block regardless of order.
- **Differentiation.** For the DevOps lane and for K8s freelance gigs, CKA is the badge that separates you from rebranding applicants. SAA is the broader HR filter — more people have it, so it opens more doors but distinguishes less.
- **Exam style match.** CKA = doing things in a terminal under time pressure = literally what you've done for five sections. Start with the exam you're already 70% trained for.

**The money, honestly** (verified 2026-07): CKA is **$445**, SAA is **$150** — $595 total, the only real spend of this entire course. Softeners: the Linux Foundation runs sales constantly (30–40% off around holidays, KubeCon, year-end — never pay sticker; you have 12 months from purchase to schedule, so buy CKA the moment a sale appears). CKA includes **one free retake** and **two killer.sh simulator sessions** (36h access each) — the best CKA prep that exists, bundled in. SAA has **no free retake** (14-day wait, pay again), so you book it only when the readiness gate in `checkpoint.md` says so. If budget forces choosing exactly one right now: **CKA** — it differentiates more for your target roles, and six visible years of shipping on AWS partially substitutes for SAA in a way nothing substitutes for CKA.

## How this repo becomes the portfolio

The repo is already the evidence; this section makes it *legible* to a stranger with 90 seconds:

1. **Root `README.md` progress boxes all ticked** — an 11/11 public course is a story in itself.
2. **Capstone gets a proper README**: architecture diagram of the final stack, the numbers (1.67GB → 220MB image, the CI → GHCR → PR-bump → Argo sync loop), and the flagship paragraph: *self-hosted LLM served behind a GitOps-managed Kubernetes platform I built end-to-end.*
3. **Pin the repo** on your GitHub profile; both CVs link to it in the header, not buried at the bottom.
4. Every LinkedIn post and freelance proposal points at a *specific file* in it, not just the repo root — specificity is what converts.

## The three plans

| Plan | What it is | When |
|---|---|---|
| [cka-plan.md](cka-plan.md) | CKA domain map vs sections 1–10, gap drills, kubectl speed training, killer.sh strategy, 4-week schedule | Weeks 1–4 |
| [saa-plan.md](saa-plan.md) | SAA-C03 domain map vs section 7, gap list, question-bank grind, cost/scenario reasoning drills, 4-week schedule | Weeks 5–8 |
| [market-entry.md](market-entry.md) | Two CV variants (bullet drafts from real artifacts), AI-infra positioning, freelance entry playbook, STAR story bank, application engine | Day 1, parallel, ongoing |

## Milestones

No labs to tick this time — milestones instead. Same rule as always: a box gets ticked when it's *genuinely* true, not when it's close.

- [ ] **M1** — Both CV variants drafted (market-entry.md §CVs) and reviewed once by a native-English reader or a strong LLM pass
- [ ] **M2** — LinkedIn profile updated + freelance profile(s) live, repo pinned and polished (capstone README written)
- [ ] **M3** — CKA gap drills complete (cka-plan.md weeks 1–2), all drill verifies pass
- [ ] **M4** — killer.sh session 1 taken under exam conditions, misses dissected
- [ ] **M5** — CKA readiness gate passed (checkpoint.md) → exam booked → **CKA passed**
- [ ] **M6** — Story bank: 12+ STAR stories written, each rehearsed aloud at least twice
- [ ] **M7** — Application engine running: tracker live, weekly volume target hit two weeks in a row
- [ ] **M8** — SAA gap study complete (saa-plan.md weeks 1–2 of its schedule)
- [ ] **M9** — SAA readiness gate passed → exam booked → **SAA passed**
- [ ] **M10** — Both CVs updated with cert lines; one "I finished the course" flagship post published

## Reading (curated, ~1h total)

- [CKA — official page](https://training.linuxfoundation.org/certification/certified-kubernetes-administrator-cka/) — current price, policies, and the authoritative domain list
- [CKA candidate handbook + important instructions](https://docs.linuxfoundation.org/tc-docs/certification/lf-handbook2) — exam-day rules; read once early, once the week of
- [killer.sh FAQ](https://killer.sh/faq) — how the two included sessions work
- [AWS SAA-C03 official exam guide (PDF)](https://d1.awsstatic.com/training-and-certification/docs-sa-assoc/AWS-Certified-Solutions-Architect-Associate_Exam-Guide.pdf) — the domain/task breakdown the whole saa-plan maps against
- [AWS Well-Architected pillars](https://docs.aws.amazon.com/wellarchitected/latest/framework/the-pillars-of-the-framework.html) — the exam's scenario questions are these five pillars wearing costumes

## Done when

Every readiness checklist in [checkpoint.md](checkpoint.md) passes honestly, and [notes.md](notes.md) is filled in your own words. This is the last section — the gate doesn't open onto another section. It opens onto interviews.
