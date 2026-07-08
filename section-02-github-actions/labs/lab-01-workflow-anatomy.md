# Lab 1 — Workflow anatomy: events, jobs, steps, runners

**Goal:** write a deliberately-simple workflow, push it, and dissect what actually happened — which machine ran it, what was on that machine, and how two jobs relate. No capstone changes yet; this lab is about reading the machinery before trusting it with your app.

## The mental map (read this first)

A workflow run, end to end:

```
 YOUR MAC                          GITHUB (the dispatcher)              A RUNNER (fresh VM)
┌───────────────┐   git push    ┌──────────────────────────┐   pulls   ┌─────────────────────┐
│ .github/      │ ────────────▶ │ event: "push happened"   │   job     │ empty hotel room:   │
│  workflows/   │               │ reads every workflow's   │ ◀──────── │ Ubuntu, 4 CPUs,     │
│   hello.yml   │               │ `on:` — does it match?   │           │ tools preinstalled, │
└───────────────┘               │ yes → queue its jobs     │ ────────▶ │ but NO repo, NO     │
                                └──────────────────────────┘  streams  │ code, NO state      │
                                                              logs     └─────────────────────┘
                                                                         demolished after job
```

Three things to internalize before touching YAML:

**1. The workflow file is cargo, not config you upload somewhere.** It lives in your repo at `.github/workflows/`, versioned like any code. When a push arrives, GitHub reads the workflows *at the commit that was pushed* and checks each file's `on:` block against the event. Matching workflows run. There is no server to configure, no UI form — the pipeline IS a file in git. (This idea has a name you'll drop in interviews: *pipeline as code*.)

**2. One job = one fresh machine.** GitHub boots a VM (for `ubuntu-latest`: currently Ubuntu 24.04, 4 CPUs, 16 GB RAM — free without limits on public repos), runs your steps in order, and destroys it. Two jobs in the same file = two separate machines that have never heard of each other. The room is *empty*: your repo is not there until a step fetches it.

**3. Steps come in two flavors.** `run:` = a shell command, executed right there. `uses:` = someone's packaged step pulled from a registry of steps — the marketplace. Same reuse move as `FROM python:3.14-slim` instead of building an OS: don't hand-roll a git-clone-with-auth script; pull `actions/checkout@v7`.

## Steps

### 1. Confirm the repo is on GitHub and gh is wired up

```bash
cd /Users/mahadihassan/Documents/plan/projects/devops-course
git remote -v          # expect: origin  https://github.com/itsmahadi007/devops-course.git
gh auth status         # expect: ✓ Logged in to github.com account itsmahadi007
```

If `git remote -v` prints nothing, create the repo first: `gh repo create devops-course --public --source=. --push`. Everything in this section rides on pushes to this repo.

### 2. Write the hello workflow

Create `.github/workflows/hello.yml` **at the repo root** (not inside this section's folder — GitHub only reads workflows from this one magic path):

```yaml
name: hello                    # display name in the Actions tab

on:                            # the doorbells this workflow answers
  push:                        # any push, any branch (we'll narrow this later)
  workflow_dispatch:           # ...plus a manual "Run workflow" button

jobs:

  look-around:                 # job id — your name for it
    runs-on: ubuntu-latest     # which kind of hotel room to book
    steps:
      - name: What machine is this?
        run: |
          echo "kernel : $(uname -a)"
          echo "user   : $(whoami)"
          echo "cpus   : $(nproc)"
          echo "workdir: $(pwd)"
      - name: What is in the room BEFORE checkout?
        run: ls -la
      - name: Fetch the repo
        uses: actions/checkout@v7
      - name: And after
        run: ls -la
      - name: Who triggered me, and with what commit?
        run: |
          echo "event : ${{ github.event_name }}"
          echo "actor : ${{ github.actor }}"
          echo "sha   : ${{ github.sha }}"

  a-second-machine:
    runs-on: ubuntu-latest
    steps:
      - name: Prove I share nothing with the other job
        run: ls -la    # the repo look-around checked out is NOT here
```

Pre-read of what each part will do:

- **`on:` with a bare `push:`** — every push to any branch triggers it. Deliberately noisy for today; the clean-up step tames it.
- **`workflow_dispatch:`** — adds a manual trigger. Without this line there is no "run it again by hand" button.
- **`${{ ... }}`** — *expressions*, evaluated by GitHub before the shell ever sees the line. `github.*` is a context object describing the event: who pushed, what SHA, which branch. This is templating, not shell — same mental slot as compose's variable substitution, different engine.
- **The two `ls -la` steps** are the point of the lab: you'll see the workspace empty, then populated. Checkout is not decoration.

### 3. Push and watch it run

```bash
git add .github/workflows/hello.yml
git commit -m "ci: hello workflow"
git push
gh run watch
```

`gh run watch` attaches to the newest run and live-streams job status. Expect both jobs to flip to ✓ within ~20–30 seconds — and note they start at the *same time*: nothing says `look-around` must precede `a-second-machine`, so GitHub books two rooms at once.

#### If `gh run watch` says "no runs found"

The run may not be registered yet (give it 2–3 seconds and re-run), or the workflow file never parsed. Check the Actions tab: a red "Invalid workflow file" annotation with a line number means YAML trouble — indentation is meaning in YAML, and the classic mistake is `steps:` items not starting with `-`. Fix, commit, push again; every push is a fresh chance.

#### If nothing appears in the Actions tab at all

GitHub found no workflow to match. Three usual suspects: the folder is misspelled (`.github/workflow/` without the `s` — silent failure, no error anywhere), the file didn't get committed (`git status`), or you pushed a branch while looking at another branch's Actions view.

### 4. Read the run in the UI — the debugging surface you'll live in

Open it in the browser:

```bash
gh run view --web
```

Click into `look-around` and read top to bottom:

- **"Set up job"** — a step you never wrote. It's the room-preparation record: runner image and version, the OS, links to preinstalled software. When CI behaves differently than your Mac, this is where you check what the machine actually was.
- **Your named steps** — each collapsible, each with its exact output and duration. The two `ls -la` steps are the payoff: the first shows an **empty directory** (the workspace exists, nothing in it), the second shows your repo. The room really is empty until you carry your stuff in — and that's also your first hint why jobs need *caching* (Lab 2): every job re-downloads the world into a blank machine.
- **"Complete job"** — teardown. After this line, that VM no longer exists.

Also worth 60 seconds: the run's summary page shows both jobs as parallel boxes. In Lab 3 you'll see this become a *graph* when `needs:` draws arrows between them.

### 5. Trigger it by hand — no commit required

```bash
gh workflow run hello
gh run watch
```

This is the `workflow_dispatch` doorbell. Note what `github.event_name` prints this time (`workflow_dispatch`, not `push`) — same workflow, different doorbell, and the workflow can tell. One quirk worth knowing: manual dispatch only works once the workflow file exists **on the default branch** — a workflow_dispatch-only file on a feature branch has no button yet.

#### The `uses:` line, unpacked once properly

`actions/checkout@v7` is three ideas in one token:

```
actions / checkout @ v7
────────────────────────
owner  /  repo     @ ref  ──▶ it's literally a GitHub repo, fetched at that ref
```

An action is a repo containing packaged step-code plus a manifest (`action.yml`) declaring its inputs. GitHub fetches it at the ref you name and runs it. And `@v7` is a **git tag — a sticky note** (Lab 6's exact lesson): the maintainer re-sticks `v7` onto every `v7.x.y` patch release. Convenient — you get fixes free — but it means the code behind `@v7` can change without your file changing. The paranoid pin is a full commit SHA (`actions/checkout@08c6903cd8c0fde910a37f88322edcfb5dd907a8`), the marketplace's equivalent of pulling by digest: the ref that cannot lie. Course policy: major-version pins are fine here; know the SHA answer for interviews — supply-chain attacks on actions are a real, named threat (the 2025 `tj-actions/changed-files` compromise is the case study interviewers know).

## Verify

- Both jobs green in `gh run list --limit 1` (it shows the run's overall ✓).
- First `ls -la` step shows an empty workspace, second shows the repo, and `a-second-machine`'s listing is empty again.

Then answer aloud:

**1. Two jobs, one workflow file — how many machines, and what do they share?**

<details><summary>Answer (read after attempting aloud)</summary>

Two machines — one fresh VM per job, booked in parallel by default. They share *nothing*: no filesystem, no env vars, no checked-out repo. Coordination is opt-in only: `needs:` for ordering, job `outputs:` for passing small values, artifacts/caches for files. Steps *within* a job share a machine and run in sequence.

</details>

**2. Why was the workspace empty before checkout? What does that imply every job must do?**

<details><summary>Answer (read after attempting aloud)</summary>

The runner is a disposable hotel room — GitHub boots a clean VM with tools preinstalled but no knowledge of your repo. `actions/checkout` is the step that git-fetches the triggering commit into the workspace (using the job's keycard token for auth). Every job that needs code must check out — and every job re-pays that setup cost, which is why caching matters as pipelines grow.

</details>

**3. What kind of thing is `actions/checkout@v7`, physically? What can silently change under you, and what's the paranoid fix?**

<details><summary>Answer (read after attempting aloud)</summary>

A GitHub repo (`owner/name`) fetched at a git ref. `@v7` is a mutable tag — a sticky note the maintainer moves across patch releases, so the executed code can change with no edit on your side. Same trust model as `:latest` on images. The immutable pin is a commit SHA — the marketplace's pull-by-digest. Tradeoff: SHA pins freeze security fixes out too, so teams pair them with automated bump PRs (Dependabot/Renovate).

</details>

**4. Same workflow ran from a push and from the button. How could a step behave differently in each case?**

<details><summary>Answer (read after attempting aloud)</summary>

The event is exposed as data: `github.event_name` says which doorbell rang (`push` vs `workflow_dispatch`), and the whole `github` context carries the payload (SHA, actor, ref). Steps and jobs can branch on it with `if:` expressions — one file, different behavior per trigger. Lab 3 uses exactly this to run tests on PRs but only build images on pushes.

</details>

## Clean up

A bare `on: push` will fire on every commit for the rest of the course — noise. Tame it to button-only and keep it as a scratchpad workflow:

```yaml
on:
  workflow_dispatch:
```

```bash
git add .github/workflows/hello.yml
git commit -m "ci: hello workflow manual-only"
git push
```

(That push is the last one hello reacts to — after it lands, only the button triggers it.)
