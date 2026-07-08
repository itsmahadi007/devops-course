# Checkpoint — Section 02: CI/CD with GitHub Actions

Pass every task **from memory** — no peeking at the labs. If you have to peek, the section isn't done yet; redo that lab tomorrow and try again.

## Practical tasks

- [ ] **1.** From a blank `.github/workflows/` folder, write a workflow that triggers on push *and* a manual button, checks out the repo, and prints the runner's OS/user/arch. Push it and read the "Set up job" step to identify the runner image. Target: under 10 minutes, no references.
- [ ] **2.** Add a `test` job that installs uv, runs `ruff check` and `pytest` on the capstone, scoped with a `paths:` filter so notes-only commits don't trigger it, fanned across `ubuntu-latest` + `macos-latest`. Prove the bouncer bounces: break an assertion, watch red, revert, watch green.
- [ ] **3.** Add a `build` job that `needs:` the test job, logs into GHCR with `GITHUB_TOKEN`, computes tags with `metadata-action`, and pushes. Grant *only* `packages: write`, on the job. Confirm a `:sha-<commit>` tag appears on the package.
- [ ] **4.** Turn the build multi-arch (amd64+arm64) with QEMU + buildx, add `type=gha` cache with `mode=max`, and prove with `docker buildx imagetools inspect` that one tag serves both architectures.
- [ ] **5.** Register a self-hosted runner on your Mac with labels, route a job to it via `runs-on:`, and prove from the step output that it ran on your machine (hostname/arch), not GitHub's cloud.
- [ ] **6.** Write a `deploy` job that SSHes into `vps-lab` from the self-hosted runner using a dedicated deploy key (stored as a repo secret), pulls the `:sha-` image, and runs it. Verify the full port chain with `curl localhost:9030/health`.
- [ ] **7.** Protect `main` with a ruleset requiring a PR and the `test` check; demonstrate that a failing check disables the merge button and a direct push is refused.

## Explain aloud (interview drill — answer in 60–90 seconds each)

- [ ] Walk me through your CI/CD pipeline, job by job — what triggers it, what runs where, and what stops a broken change from shipping.
- [ ] Event → workflow → job → step: define each, and say exactly what two jobs in one workflow share and don't share. Which line makes one job wait for another?
- [ ] Why does every job start with `checkout`? What does that tell you about a runner's lifecycle, and why does caching matter as pipelines grow?
- [ ] `uses: actions/checkout@v7` — what *is* that, physically? What can silently change under you, and what's the paranoid pin (and its downside)?
- [ ] `GITHUB_TOKEN` vs a personal access token: three differences (scope, lifetime, permissions). Where do you declare what the keycard can do, and why put it on the job, not the file?
- [ ] `metadata-action` produced `:sha-abc123` and `:latest` but no semver tag on a plain push. Explain each rule and which tag a deploy should pin to, and why.
- [ ] Why do you build images in CI and not on your laptop? (Name at least the architecture reason and the reproducibility reason.)
- [ ] How does an amd64 runner produce a working arm64 image? What is a manifest list, and how does one `docker pull` get the right arch with no arch in the command?
- [ ] `type=gha` cache with `mode=max` vs `mode=min` — why does *this* image (multi-stage) specifically need `max`? Where do the layers live between two runs on two disposable machines?
- [ ] Why can't a GitHub-hosted runner deploy to `vps-lab`, but a self-hosted runner on your Mac can? Explain the pull model and NAT in the answer.
- [ ] Self-hosted runner on a *public* repo — why dangerous, and what are your mitigations? (Fork PRs, `if:` guards, ephemeral runners, least privilege.)
- [ ] What is Docker-in-Docker, why does `vps-lab` need `privileged: true` for it, and why is privileged a "big hammer"? What would you do instead on a real system?
- [ ] Why a dedicated deploy key in a secret instead of your personal SSH key? What's the blast radius if it leaks?
- [ ] Trace the port chain `Mac:9030 → vps-lab:8080 → inner:8000` and say where each hop's mapping is defined.
- [ ] Branch protection vs CI-that-just-runs: what does the ruleset add, and which check should gate merges — `test` or `deploy`? Why?

## Gate

- [ ] `notes.md` filled in my own words
- [ ] Everything committed (`ci.yml`, `hello.yml`, `capstone/tests/`, ruff/pytest config in `pyproject.toml`, `uv.lock`, `vps-lab/Dockerfile` + `docker-compose.yml` — **no keys, no tokens, no secrets**)
- [ ] `VPS_DEPLOY_KEY` set as a repo secret; `keys/deploy_key*` present locally and gitignored (never committed)
- [ ] The pipeline is green end-to-end: a push to `main` runs test → build → deploy, and `curl localhost:9030/health` returns the app

When all boxes are checked, say so — Section 3 (Linux & networking, inside vps-lab) gets written against your notes. It assumes the capstone container this section deploys is running inside vps-lab.
