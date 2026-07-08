# Checkpoint — Section 11: Cert Prep + Market Entry

No labs to verify this time — **readiness gates instead.** A box gets ticked when it's *genuinely* true, not when it's close. These gates are strict on purpose: SAA has no free retake, CKA's free retake is for real emergencies not skipped prep, and a CV sent before it's ready burns a first impression you don't get back.

## CKA readiness gate — do not book the exam until every box is honestly true

- [ ] **Speed baseline.** A full pass of the imperative-reflexes list (`cka-plan.md`) from the prompt, no docs, under 10 minutes — and it feels like typing, not thinking.
- [ ] **Every gap drill (1–12) done once, then re-done from memory under its target time.** The ones that matter most, blind: RBAC (SA→Role→Binding→can-i, +CSR user), NetworkPolicy default-deny + allow, etcd snapshot save/restore ≤10 min, taints/affinity + "why Pending?", static PV↔PVC binding, HPA.
- [ ] **The two VM drills done** (kubeadm init/join, upgrade + drain/uncordon) — you've felt every step kind was hiding.
- [ ] **Break-and-fix gauntlet passed blind:** kubelet down, bad apiserver static-pod manifest, CoreDNS scaled to 0, empty-endpoints selector typo — each found and fixed without peeking.
- [ ] **killer.sh session 1 taken under exam conditions**, every miss redone, every solution read (even for tasks you got right).
- [ ] **killer.sh session 2 ≥ 80%** on the (seen) questions, in the remote-desktop-style environment. Below 80% → reschedule, no shame.
- [ ] **Exam-day muscle memory:** the first-60-seconds env setup (`alias k`, `export do`/`now`, vimrc) is automatic, and you copy the `use-context` line on *every* task by reflex.
- [ ] **Triage internalized:** you can look at a task list, order it cheapest-first, and you *believe* you can abandon a third of the exam and still clear 66%.
- [ ] **Logistics ready:** PSI system check passed on the exact machine + room, ID ready, desk-clear / single-monitor / copy-paste keys all rehearsed.

## SAA readiness gate — no free retake, so this bar is the strict one

- [ ] **Exam guide PDF read fully**, and every **GAP** row in `saa-plan.md`'s domain tables has been studied (FAQ or Tutorials Dojo cheat sheet).
- [ ] **The superlative → reflex table is instant** — cover the right column, and the reflex fires without thinking for every row.
- [ ] **The five cost/scenario reasoning drills done cold, aloud** (S3 class picker, NAT arithmetic, RTO/RPO ladder, pricing-model assignment, cross-AZ tax).
- [ ] **Error log alive** — every missed practice question logged with *why* (knowledge gap vs misread superlative vs distractor) and a one-line rule.
- [ ] **≥ 80% on a FRESH full 65-question timed set** (TD #6 or equivalent — never a repeated set; a jump on a seen set is memorization, not readiness).
- [ ] **Stamina proven:** you've sat multiple full 130-minute sets and the last third didn't fall apart.
- [ ] **Logistics ready:** Pearson VUE system test passed (or test-center booked), ID ready, room rules understood.

## Market readiness gate — this one starts on day 1 and is never "done", but here's the bar

- [ ] **Both CV variants drafted** from real artifacts (`market-entry.md` §CV-A / §CV-B) and reviewed once by a native-English reader or a strong LLM pass.
- [ ] **AI-infra summary written and swappable** — you can retarget CV-B to an AI-infra/MLOps post in under a minute.
- [ ] **LinkedIn profile updated** to match the CVs; repo pinned; open-to-work + available-for-contract signals on.
- [ ] **At least one freelance profile live** (Upwork or a vetted platform) with the repo front-and-centre and at least one productized-gig listing.
- [ ] **Capstone README written** — architecture diagram, the numbers, the flagship paragraph — so a stranger gets the story in 90 seconds.
- [ ] **Story bank: 12–15 STAR cards written**, each rehearsed aloud at least twice, including the behavioral must-haves.
- [ ] **Application engine running:** tracker live, weekly volume target hit two weeks in a row, both lanes (backend + DevOps/AI-infra) in the funnel.
- [ ] **At least one section post published** and pointing at a specific repo file (per `TODO.md` hooks).

## Explain aloud (the interview warm-up — 60–90 seconds each, spoken not read)

These double as your first STAR cards. If any answer isn't fluent, that's a card to sharpen, not a box to tick.

- [ ] "Walk me through your repo." — the 90-second flagship tour: container → CI → K8s → Helm → GitOps → observability → self-hosted LLM, ending on *why* it's one coherent platform.
- [ ] Why did you add DevOps as a *second lane* rather than pivoting away from backend/AI? (Your real answer, from `docs/why-this-course.md`.)
- [ ] What does it tell you about a company when they have *dedicated* DevOps headcount vs backend devs absorbing ops? (Your own BD-market insight.)
- [ ] The AI-infra pitch in 45 seconds: why is "I run models in production *and* the platform under them" a rarer combination than either alone?
- [ ] Pick your sharpest debugging story from S1 or S4 and tell it as Situation→Task→Action→Result, with the actual command and the number.
- [ ] "Tell me about a time you were wrong" — the `:latest` or postgres:18 assumption that bit you, and what you now do differently.
- [ ] A time you chose *not* to use a tool (S6 "when NOT to use Terraform"). Senior signal — practice it.
- [ ] CKA in one breath: what kind of exam is it, and what's the single skill it rewards (typing/triage, not elegance)?
- [ ] SAA in one breath: what kind of exam is it, and what's the single skill it rewards (superlative → eliminate → decide)?

## Gate

- [ ] `notes.md` filled in my own words
- [ ] **CKA passed** — cert line added to both CVs the same day, announcement post drafted
- [ ] **AWS SAA passed** — cert line added to both CVs, added to CV-A's cloud story too
- [ ] Repo polished for strangers: root `README.md` 11/11 boxes ticked, capstone README written, repo pinned
- [ ] Story bank complete and rehearsed; application engine running

When all boxes are checked, say so. This is the last section — the gate doesn't open onto another section. **It opens onto interviews.**
