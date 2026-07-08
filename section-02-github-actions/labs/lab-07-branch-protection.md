# Lab 7 — Branch protection (optional, short)

**Goal:** make `main` physically refuse code that hasn't passed CI. Right now your gate *runs* on every push — but nothing *stops* a red push from landing on `main`. This short lab wires the gate to the branch itself, so "broken code can't reach main" becomes a rule GitHub enforces, not a habit you hope holds.

## The mental map (read this first)

So far the pipeline is advisory: it tells you a push is broken, after the broken commit is already on `main`. A **ruleset** flips that — it makes the passing CI check a *precondition* for the code being allowed onto the branch at all.

```
 WITHOUT protection                          WITH a ruleset (required check: "test")
 ┌──────────────────────────┐               ┌────────────────────────────────────────┐
 │ push broken code to main │               │ push broken code → open PR               │
 │        │                 │               │        │                                  │
 │        ▼                 │               │        ▼                                  │
 │ main now broken ✗        │               │ CI runs on the PR → red                   │
 │ CI turns red AFTER       │               │        │                                  │
 │ the fact                 │               │        ▼                                  │
 └──────────────────────────┘               │ MERGE BUTTON DISABLED — main stays clean │
                                             └────────────────────────────────────────┘
```

The shift is *when* the gate acts: from "reports after landing" to "blocks before landing." Two rules do it:

- **Require a pull request** — direct pushes to `main` are refused; all change goes through a PR.
- **Require status checks to pass** — the PR's merge button is disabled until a named check (your `test` job) is green.

This is the professional default on every team repo, and "how do you stop broken code reaching main?" is a stock interview question whose answer is *this*, plus code review.

## Steps

### 1. Create a ruleset for `main`

Rulesets are the modern replacement for classic "branch protection rules." Open the repo settings:

```bash
gh browse --settings
```

Navigate **Settings → Rules → Rulesets → New ruleset → New branch ruleset**. Configure:

- **Name:** `protect-main`
- **Enforcement status:** **Active**
- **Target branches:** Add target → **Include default branch** (that's `main`).
- Tick **Require a pull request before merging** (you can set required approvals to 0 for a solo repo — the PR flow is the point, not the review count here).
- Tick **Require status checks to pass** → **Add checks** → search and add **`test`** (the job name from `ci.yml`). Optionally also tick **Require branches to be up to date before merging** (forces the PR to include latest `main` before its checks count — prevents "green against stale main" merges).
- Save the ruleset.

Why require the **`test`** check specifically and not `build`/`deploy`? The bouncer is the test gate — that's what proves the *code* is sound. `build` and `deploy` are what happen *after* main is trusted; gating merges on a deploy would be circular. Require the check that validates correctness, not the ones that ship.

### 2. Watch it block a bad merge

Prove the rule bites. Make a branch with a deliberately failing test:

```bash
cd /Users/mahadihassan/Documents/plan/projects/devops-course
git checkout -b break-on-purpose
# break an assertion in capstone/tests/test_api.py, e.g. change "ok" to "nope"
git commit -am "test: deliberately break a test to prove the gate"
git push -u origin break-on-purpose
gh pr create --fill
gh pr view --web
```

On the PR page: the `test` check runs and goes **red**, and the **Merge** button is disabled with "Required statuses must pass." You *cannot* merge broken code into `main` even if you want to — that's the ruleset doing its job. Now fix it:

```bash
# revert the assertion back to the correct value
git commit -am "test: restore the assertion"
git push
gh run watch
```

The check flips green, the merge button enables. Merge it (`gh pr merge --squash --delete-branch`), and confirm `main` was never broken at any point.

### 3. Confirm direct pushes to main are refused

```bash
git checkout main
echo "# direct push attempt" >> capstone/app/main.py
git commit -am "chore: try to push straight to main"
git push
```

Expect a rejection: `Changes must be made through a pull request`. Undo the local commit so your branch is clean:

```bash
git reset --hard origin/main
```

That refusal is the "require a pull request" rule. On `main`, the only way in is now a green PR.

#### If you can still push to main despite the ruleset

Two usual causes: the ruleset's **Enforcement status** is left on *Evaluate* (dry-run — logs would-be violations without blocking) instead of **Active**; or a **bypass list** includes your role (repo admins can be granted bypass). For a solo learning repo, admin bypass is convenient but defeats the demo — remove yourself from bypass while testing, and know that on real teams the bypass list is a reviewed, minimal thing (break-glass only).

#### If the required check never resolves (PR stuck "Expected")

The check name must match a job that actually *runs on the PR*. Your `ci.yml` triggers `test` on `pull_request` (Lab 2), so it will — but if you required a check name that never fires for PRs (e.g. a push-only job), the PR waits forever for a check that can't arrive. Require only checks that run on `pull_request` events.

## Verify

- Direct `git push` to `main` is refused with a pull-request-required message.
- A PR with a failing `test` check has its merge button disabled.

Then answer aloud:

**1. Your CI already ran on every push. What does branch protection add that CI alone didn't?**

<details><summary>Answer (read after attempting aloud)</summary>

Enforcement of *when*. CI alone is advisory — it turns red *after* a broken commit already landed on `main`. A ruleset makes the passing check a *precondition*: change must go through a PR, and the merge button stays disabled until the check is green, so broken code never reaches `main` in the first place. It moves the gate from "reports after the fact" to "blocks before the fact."

</details>

**2. Why require the `test` check for merges and not `deploy`?**

<details><summary>Answer (read after attempting aloud)</summary>

`test` validates that the *code* is correct — that's what should gate whether it's allowed onto `main`. `build` and `deploy` are consequences that run *after* `main` is trusted (deploy only fires on push-to-main). Gating a merge on deploy would be circular and would block merges on infrastructure issues unrelated to code correctness. Require the check that proves soundness; let shipping happen after the merge.

</details>

**3. On a solo repo you can grant yourself bypass. When is that reasonable, and what's the risk?**

<details><summary>Answer (read after attempting aloud)</summary>

Bypass is a "break-glass" convenience — reasonable for a solo repo or genuine emergencies (revert a bad deploy fast). The risk is that it quietly becomes the norm: if admins routinely bypass, the protection is theater. Real teams keep the bypass list minimal and audited, and treat each use as an event. For this course, having it *available* is fine; using it during the demo just hides whether the rule actually works.

</details>

## Clean up

Leave the ruleset **active** — a protected `main` is the correct end state and good portfolio hygiene. Ensure the `break-on-purpose` branch is merged-and-deleted (or just deleted) and `main` is green. That's Section 2 complete: a push-to-live pipeline standing behind a protected branch.
