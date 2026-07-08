# Section 02 — CI/CD with GitHub Actions

**Status:** written — not started · **Time:** ~1 week at 2–4h/day · **Labs:** 7 (7 is a short optional)

Section 1 ended with three loose threads, on purpose: your GHCR image is **arm64-only** (a rented x86 VPS would die with `exec format error`), you're **logged out of ghcr.io** ("Section 2's CI authenticates with its own short-lived token"), and `vps-lab` is sitting there listening on 9022 with nothing deployed to it. This section pays all three debts. By the end, a `git push` runs tests, builds a multi-arch image, pushes it to GHCR, and ships it into vps-lab over SSH — with no human in the loop. That pipeline is the single most-asked-about artifact in DevOps interviews.

## The mental model (read first)

**GitHub Actions is a doorbell wired to disposable computers.** Four words carry the whole system — learn them as a hierarchy:

```
EVENT      the doorbell — a push, a PR, a click, a schedule
  └─ WORKFLOW    one YAML file in .github/workflows/ that answers that doorbell
       └─ JOB         one to-do list, executed on ONE fresh machine (a "runner")
            └─ STEP        one item on the list: a shell command, or a packaged action
```

Jobs in a workflow run **in parallel by default, each on its own machine** — they share *nothing* unless you explicitly wire them together (`needs:` for ordering, `outputs:` for data). Steps inside a job run in sequence on the same machine, so they DO share a filesystem. Getting this split wrong is the #1 beginner confusion, which is why Lab 1 makes you watch two jobs land on two different machines.

**A runner is a hotel room.** GitHub-hosted runners are fresh VMs: made up before your job, demolished after it. Nothing survives between jobs — not even your own repo (that's why every job starts with `checkout`; the room is *empty* until you carry your stuff in). A **self-hosted runner** (Lab 5) is your own guest room instead: it's your hardware, your network, and nobody cleans it between guests — powerful and dangerous in equal measure.

**`uses:` is `FROM` for pipeline steps.** `uses: actions/checkout@v7` pulls a *packaged, versioned step* from a registry of steps (the marketplace) — the same reuse move as pulling an image instead of writing a Dockerfile from scratch. And the `@v7` is a **sticky-note tag**, exactly like `:latest` in Lab 6: a mutable pointer someone else can move. Paranoid production setups pin actions by commit SHA (`@08c6903…`) for the same reason you learned to pull by digest.

**`GITHUB_TOKEN` is a hotel keycard.** Every job gets a credential minted *for that job*: it works only on this repo, only with the permissions the workflow grants (`permissions:` block), and it dies when the job ends. Compare that to the personal token you used in Lab 6 — a master key that opens everything you own, forever, until revoked. Lab 3 uses the keycard to push to GHCR; the authn-vs-authz lesson from Lab 6 comes straight back.

**Runners pull; nothing pushes to them.** A runner — hosted or self-hosted — opens an *outbound* HTTPS connection to GitHub and asks "got work for me?" (long-poll). GitHub never connects *in*. That one design fact is why a laptop behind home NAT, with zero open ports, can be a fully functional CI machine — and it's the entire reason Lab 5 works.

## Why this matters for jobs

- "**Walk me through your CI/CD pipeline**" is the DevOps interview opener, the way "tell me about yourself" is for HR. After this section your answer is a real pipeline you built, with test gates, multi-arch builds, cache strategy, and an SSH deploy — not a tutorial you read.
- "**Why do you build in CI and not on laptops?**" — you already ate the answer in Lab 6 (`exec format error`). Now you can also say: reproducible environment, no "works on my machine", multi-arch via one workflow, and an auditable trail from commit SHA to image digest.
- **CI speed is billable work.** "Our pipeline takes 25 minutes" is one of the most common freelance infra complaints; buildx cache + layer-order reasoning (Lab 4 + Section 1) routinely cuts that 5–10×.
- **Self-hosted runner security** is a genuinely senior interview topic (fork-PR code execution, ephemeral runners) — Lab 5 covers it from first principles.

## Versions used in this section (checked 2026-07)

Latest stable majors at time of writing — the lesson uses these exact pins:

| Tool | Pin | Current release |
|---|---|---|
| `actions/checkout` | `@v7` | v7.0.0 |
| `astral-sh/setup-uv` | `@v8` | v8.3.2 |
| `docker/login-action` | `@v4` | v4.4.0 |
| `docker/setup-qemu-action` | `@v4` | v4.2.0 |
| `docker/setup-buildx-action` | `@v4` | v4.2.0 |
| `docker/metadata-action` | `@v6` | v6.2.0 |
| `docker/build-push-action` | `@v7` | v7.3.0 |
| GitHub Actions runner (self-hosted) | — | 2.335.1 (the registration UI always shows current) |
| ruff / pytest (via uv) | `>=0.15` / `>=9` | 0.15.x / 9.1.x |

Major tags (`@v7`) are mutable — they follow patch releases. That's a convenience/security tradeoff you can now articulate (Lab 6's sticky-note lesson); Lab 1 spells out the SHA-pin alternative.

## Labs

| Lab | What you build | Proves |
|---|---|---|
| [1 — Workflow anatomy](labs/lab-01-workflow-anatomy.md) | a hello workflow you dissect | events, jobs, steps, runners, the Actions UI |
| [2 — Lint + test the capstone](labs/lab-02-lint-test.md) | `ci.yml` with a real test gate | uv in CI, ruff, pytest, path filters, matrix |
| [3 — Build + push to GHCR](labs/lab-03-build-push-ghcr.md) | CI pushes the image, not you | `GITHUB_TOKEN`, permissions, metadata tags |
| [4 — Cache + multi-arch](labs/lab-04-cache-multiarch.md) | fast builds, amd64+arm64 image | `type=gha` cache internals, QEMU, manifest lists |
| [5 — Self-hosted runner](labs/lab-05-self-hosted-runner.md) | your Mac joins the pipeline | pull model, NAT reality, runner security |
| [6 — Deploy to vps-lab](labs/lab-06-deploy-vps-lab.md) | push → live app on the "VPS" | SSH deploys, deploy keys, secrets, DinD |
| [7 — Branch protection (optional, short)](labs/lab-07-branch-protection.md) | main refuses broken code | rulesets, required checks |

Do them in order — each lab edits the same `ci.yml` the previous one left behind. Progress:

- [ ] Lab 1 — workflow anatomy
- [ ] Lab 2 — lint + test
- [ ] Lab 3 — build + push to GHCR
- [ ] Lab 4 — cache + multi-arch
- [ ] Lab 5 — self-hosted runner
- [ ] Lab 6 — deploy to vps-lab
- [ ] Lab 7 — branch protection (optional)

## Reading (curated, ~1.5h total)

- [Workflow syntax reference](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax) — skim now, return often; this is the page you'll live on
- [Docker docs: GitHub Actions CI](https://docs.docker.com/build/ci/github-actions/) + [multi-platform builds](https://docs.docker.com/build/ci/github-actions/multi-platform/) — the exact patterns Labs 3–4 use
- [uv: GitHub Actions integration](https://docs.astral.sh/uv/guides/integration/github/) — the Lab 2 pattern, from the source
- [Self-hosted runners](https://docs.github.com/en/actions/how-tos/hosting-your-own-runners/managing-self-hosted-runners/about-self-hosted-runners) — read the security section twice
- [Security hardening for GitHub Actions](https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions) — interview gold, especially the `pull_request_target` and script-injection parts

## Done when

Every task in [checkpoint.md](checkpoint.md) passes from memory, and [notes.md](notes.md) is filled in your own words. Then Section 3 (Linux & networking, inside vps-lab) gets written — it assumes the capstone container this section deploys is running inside vps-lab.
