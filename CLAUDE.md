# CLAUDE.md — DevOps Course (self-contained)

This file carries ALL context. Sessions open directly in this folder — do not assume access to any parent repo, memory, or prior chat.

## Who is learning, and why

**Mahadi Hassan** (github: itsmahadi007) — ~6 years backend engineer (Python/Django/DRF/FastAPI), currently Senior Backend Engineer at CosmosID (US remote). Already comfortable with: Docker basics, Linux/SSH/bash, DNS configuration, AWS basics (S3/EC2/deployments), CI/CD basics, Postgres/Redis tuning, deploying his own systems. Has shipped production AI/LLM systems (ApplyFuel — Chrome Web Store, multi-model LLM orchestration, cost metering).

**The decision (2026-07-06):** DevOps is an **added second career lane, not a pivot** — he keeps backend/AI and takes whichever opportunity fires first. Kill-first assessment found vanilla DevOps pays less than AI-eng at every US level BUT: (a) living in Bangladesh, actual income is the binding constraint — speed to the first credible offer beats salary-ceiling comparisons; (b) DevOps has an accessible freelance/contract market (infra gigs) that can pay DURING the course; (c) BD companies with dedicated DevOps engineers are consistently better employers (company-quality filter); (d) the AI-infra/MLOps hybrid — his backend+AI plus these DevOps skills — is 2026's hardest-to-fill role and the premium framing whenever a role allows it. Full context: `docs/why-this-course.md`.

**Constraints:** aggressive 3–6 month timeline, main focus. All labs **$0 and local** (macOS, Apple Silicon, zsh, Docker Desktop, uv installed). End state: two CV variants (backend-led, DevOps-led) + CKA + AWS SAA + this repo as public portfolio evidence.

## What this repo is

A progressive, hands-on course. Each section: **read** (`README.md` lesson) → **practice** (`labs/`, on this machine) → **note** (`notes.md`, his own words) → **prove** (`checkpoint.md`).

- `capstone/` — small FastAPI service that EVOLVES through every section: S1 containerize → S2 CI → S3 deploy to vps-lab over SSH → S4/5 Kubernetes + Helm → S6/7 infra as code → S8 observability → S9 GitOps → S10 its `/ask` endpoint gets a real self-hosted LLM. By the end, this repo IS the flagship portfolio artifact.
- `vps-lab/` — a Docker container acting as a fake VPS (Debian + sshd, key-only auth). Built by Mahadi himself in Section 1, Lab 5. All "server" labs (Section 3 especially) SSH into it like a real box.

## Section status

| # | Section | Status |
|---|---------|--------|
| 01 | docker-deep | **written — in progress** |
| 02 | github-actions | stub |
| 03 | linux-networking | stub |
| 04 | kubernetes-core | stub |
| 05 | helm | stub |
| 06 | terraform | stub |
| 07 | aws-core | stub |
| 08 | observability | stub |
| 09 | gitops-argocd | stub |
| 10 | llm-serving | stub |
| 11 | cert-prep | stub |

**Update this table** when a section is completed or written.

## Progressive protocol (MANDATORY for every session)

1. A section is **done** only when every `checkpoint.md` task is genuinely completed (ask him — don't assume) AND `notes.md` is filled in his own words.
2. When a section is done: **read his `notes.md` from ALL completed sections first** (what confused him, what he flagged), then write the NEXT section fully — lesson, labs, notes template, checkpoint — adapted to that. Deeper where he struggled, faster where he flew.
3. **Never write sections ahead of need.** One fully-written, not-yet-done section at a time.
4. Keep every lab **$0 and local**. Real-cloud labs may exist only as clearly-marked OPTIONAL extras with same-day teardown instructions.
5. Update the status table above + the progress checkboxes in `README.md` on every transition.

## Live-session protocol (how labs actually run — established Labs 1–2)

Mahadi works through labs in-terminal and pastes output into the chat. The rhythm:

1. **He pastes terminal output** → explain what it shows in **easy words**: annotate the actual lines he saw, connect them back to earlier labs' concepts, use analogies (e.g. `docker stop` = "knock on the door, wait 10s, break it down"; cache = "ladder — break one rung, everything above rebuilds"). Plain language beats jargon; introduce the technical term after the intuition.
2. **"update step N with this"** → fold that explanation back into the lab file as a `####` subsection at the relevant step, with good flow, so the lab is self-contained for future re-reads.
3. **Something misbehaves during a lab** (races, stale processes, wrong assumptions in the lab itself) → treat it as a teachable moment, explain it, AND fix the lab file so future-him doesn't trip (e.g. added `sleep 2` + "two traps" note; replaced `touch` with a real content edit because Docker caches by checksum, not timestamp).
4. **Verify questions get collapsible answers**: each question followed by `<details><summary>Answer (read after attempting aloud)</summary>...</details>` in the same easy style — hidden so from-memory drilling still works.
5. **"lab N is done, update the checkpoints and notes"** → do BOTH:
   - `notes.md`: append a dated **"Lab N digest (session summary)"** — one-liner takeaways from what was actually covered in session (including detours). Never fill his own-words sections (what clicked / confused / etc.) — those are his, and the section gate requires them.
   - `checkpoint.md`: add explain-aloud items for material the session went deeper on than the original questions covered. Don't tick any boxes — he does that.
6. **New labs / rewrites**: mental model first ("The mental map (read this first)" with an ASCII diagram), then steps where each command's output is pre-explained, in the same easy-words style.

## Lab & lesson style rules

- Every lab: **Goal → Steps → Verify → Clean up.** Steps are copy-paste-able for macOS/zsh. Verify = a command whose output proves it worked.
- Lessons teach: mental model first → why it matters in DevOps jobs/interviews → curated official-docs links (no link dumps).
- Checkpoints: from-memory tasks (no peeking at labs) + explain-aloud interview questions.
- He is a senior backend engineer — never explain Python, APIs, or basic git. DO explain ops concepts from first principles (K8s, TLS internals, iptables, etc.).
- Each completed section is LinkedIn post material (he runs a posting challenge positioned "AI Engineer / running AI in production") — when a section is done, offer 2-3 post-topic ideas from it.

## Rules

- **NEVER add Co-Authored-By or any AI attribution to commits.** Commits are authored solely by Mahadi. Conventional commits: `type(scope): message`, lowercase, <72 chars.
- **Public repo — no secrets, ever.** No real keys, tokens, .env values, or SSH private keys in commits (`.gitignore` covers `vps-lab/keys/`, `.env`). Placeholder values only.
- Don't touch `capstone/` beyond what the current section's labs require — its evolution IS the curriculum.
- Latest stable versions by default for every tool introduced.
- **Host ports: use the 9000 series in all labs** (`-p 9000:8000` style). Mahadi's real dev stack (cashlessai, always running) occupies the 8000-series plus 5433, 5678–5690, 6379, 6432 on this machine. Container-side ports stay conventional (8000, 6379, 5432…) — only the host side of any published port moves to 9000+. Services that don't need host access get no `ports:` at all.
