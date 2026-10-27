# My notes — Section 02: CI/CD with GitHub Actions

> Fill this as you go, in your own words (Bangla is fine). This file steers how Section 3 gets written — flag anything confusing and the next section will slow down there. (Per-lab digests get appended here during the live sessions; the sections below are yours to fill.)

## What clicked

-

## What confused me / want to revisit

-

## Commands I keep forgetting

-

## Gotchas I hit (and fixes)

-

## Questions for later sections

-

---

## Lab digests (session summaries — auto-added, not my own-words sections)

### Lab 1 — Workflow anatomy (2026-07-09)

- **The pipeline IS a file in git.** `.github/workflows/*.yml` at the repo root; GitHub reads it at the pushed commit, checks each file's `on:` against the event, runs the matches. No server, no UI form to configure ("pipeline as code").
- **One job = one fresh VM, destroyed after.** Two jobs in a file = two machines that share *nothing* (no filesystem, no env, no checked-out code). They run **in parallel by default** — proved it: `a-second-machine` (2–3s, no checkout) consistently beat `look-around` (3–5s, pays for checkout). Ordering is opt-in via `needs:` (Lab 3).
- **The runner starts as an empty hotel room.** `ls -la` before checkout = empty; `actions/checkout@v7` carries the repo in; `ls -la` after = files. Every job that needs code re-pays this → why caching matters (Lab 2).
- **Auto-steps you never wrote:** "Set up job" (room check-in: runner image/OS), "Complete job" (teardown), and "Post Fetch the repo" (checkout's own cleanup half — a `uses:` action can register a post-step).
- **Same file, different doorbell.** `${{ github.event_name }}` reads which trigger fired — `push` vs `workflow_dispatch`. Expressions `${{ }}` are evaluated by GitHub *before* the shell sees the line (templating, not bash). Manual button needs `workflow_dispatch:` in `on:` and only works once the file is on the default branch.
- **`uses: actions/checkout@v7` = owner/repo@ref** — an action is literally a GitHub repo fetched at a ref. `@v7` is a *movable git tag* (maintainer re-sticks it on each patch → code can change with no edit on your side; same trust model as Docker `:latest`). Immutable pin = full commit SHA (= Docker pull-by-digest). SHA freezes security fixes out too → pair with Dependabot bump PRs. Supply-chain threat is real: **tj-actions/changed-files 2025** compromise.
- **`gh` CLI split:** `gh run watch` = scoreboard only (step names + ✓/✗, **no output**); `gh run view <id> --log` or `--web` = the actual step output (where the `event : workflow_dispatch` answer lives); `gh run list --limit 1` = the run's **overall** status (one ✓ only if *every* job passed). `gh` pipes into the `less` pager — the `~` lines are empty-row padding, press `q` to exit.

**Detour — Dependabot failure (real fix, not a lab):** The repo's "Dependabot Updates" runs were red. Cause: the capstone app was **named `capstone`** in `pyproject.toml`, which collides with a real PyPI package also called `capstone`. GitHub's Dependency Graph registered the project's own name as a dependency; Dependabot tried `uv lock --upgrade-package capstone==4.0.0` and uv refused — *"your project requires your project"* (self-dependency). Fixed by renaming to `capstone-devops` (safe: `package = false`, name is cosmetic) + regenerating `uv.lock`. Separately, the `2 vulnerabilities (1 high, 1 moderate)` warning on every push is **unrelated** — real advisories on fastapi/uvicorn/redis, deferred to a future Dependabot-config lab in this section.

### Lab 2 — Lint + test gate (2026-07-09)

- **The capstone now has a real CI gate:** `ci.yml` runs `ruff check` (lint) + `pytest` (test) on every push touching `capstone/**` or `ci.yml`, on **two OSes at once**. Job step order = a pipeline: checkout → Install uv → `uv sync --frozen` → Lint → Test → auto Post-cleanup → teardown.
- **`uv run pytest` locally:** three dots = three passing tests (`.`=pass, `F`=fail, `E`=error). The `StarletteDeprecationWarning` about httpx is **inside FastAPI's own `site-packages/`, not my code** — a warning is not a failure, pytest still exits 0. Habit banked: read the *file path* in any warning/traceback first — `site-packages/` = someone else's library, a repo path = my problem.
- **`--frozen` is the point of the lockfile:** installs the exact `uv.lock` versions and **fails if `pyproject.toml` and `uv.lock` disagree** → Mac and both CI machines get byte-identical dep trees, no silent drift. (This is why the earlier rename *had* to `uv lock` again.)
- **`strategy.matrix` = one job, N machines.** `os: [ubuntu-latest, macos-latest]` (list) + `runs-on: ${{ matrix.os }}` (spends it) → GitHub expands the job once per list item. UI labels them `test (ubuntu-latest)` / `test (macos-latest)`. Multiple axes multiply (2 OS × 2 Python = 4 legs).
- **Both runners are GitHub-hosted cloud VMs** — even `macos-latest` (GitHub rents real Apple-silicon Macs). Nothing runs on my laptop until I register a **self-hosted** runner (later lab). Tell: the cloud Mac had to `Install uv` from scratch.
- **Per-OS setup differences:** `if: runner.os == 'Linux'/'macOS'` on a step (skips, doesn't fail), or `matrix.include` for per-leg *values*, or two separate jobs when recipes fully diverge. Capstone needs none — uv papers over OS differences.

**Bug fixed in the lab itself:** `ci.yml` (and lab-02) pinned `astral-sh/setup-uv@v8`, which **failed to resolve** — astral-sh publishes no floating `v8` major tag, only exact tags (`v8.3.2`) + a floating `v7`. Not every publisher moves a major-version sticky note (contrast `actions/checkout@v7`, which does). Failed at "Set up job" *before* any code ran. **Matrix fail-fast footgun seen live:** the annotation *"strategy configuration was canceled because macos-latest failed"* — macOS didn't independently break, it got **canceled** because the default `fail-fast: true` kills sibling legs the instant one fails. Fixed by pinning `@v8.3.2` in both `ci.yml` and the lab file. **Still TODO for checkpoint #2:** prove the gate *bounces* bad code (break an assertion → red → revert → green) — so far only seen it pass.
