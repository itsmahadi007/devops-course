# Checkpoint — Section 01: Docker Deep

Pass every task **from memory** — no peeking at the labs. If you have to peek, the section isn't done yet; redo that lab tomorrow and try again.

## Practical tasks

- [ ] **1.** From a blank folder, write a multi-stage Dockerfile for a tiny FastAPI app (deps → code order, slim base, non-root, healthcheck) and get it to `(healthy)` status. Target: under 10 minutes, no references.
- [ ] **2.** Given `capstone:naive` vs your final image, demonstrate with `time docker build` why one rebuilds deps on every code change and the other doesn't.
- [ ] **3.** Write a compose file from scratch: your API + Redis, healthcheck-gated `depends_on`, service-DNS wiring. Verify with `/visits`.
- [ ] **4.** Destroy and fully rebuild `vps-lab` from its Dockerfile, SSH in, and confirm root + password logins are refused.
- [ ] **5.** Tag and push an image to GHCR, then pull and run it after `docker logout`.

## Explain aloud (interview drill — answer in 60–90 seconds each)

- [ ] What is an image layer, physically? Why do two images `FROM` the same base not double disk usage?
- [ ] Walk through what invalidates the build cache and how you order a Dockerfile because of it.
- [ ] Why multi-stage instead of one slim stage with build tools removed at the end?
- [ ] What does a container healthcheck change compared to "the process is running"? Who consumes it?
- [ ] A teammate's image is 1.4 GB. Give your first four moves to shrink it.
- [ ] Why key-only SSH auth? What do the 700/600 permissions on `.ssh` protect against?

## Gate

- [ ] `notes.md` filled in my own words
- [ ] Everything committed (Dockerfiles, compose files, `.dockerignore`, `uv.lock` — no keys)

When all boxes are checked, say so — the next section (CI/CD with GitHub Actions) gets written against your notes.
