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
- [ ] "A container is not a mini-VM." What is it actually? What does `docker exec` really do (hint: not SSH)?
- [ ] Why must a containerized process run in the foreground? Then: why can `docker stop` take exactly 10 seconds on a badly-built image, and what does `--init` fix?
- [ ] `stop` vs `rm`: what survives each? Where do a container's writes physically go (copy-on-write), and why does real data need volumes?
- [ ] Walk through what invalidates the build cache (checksum or timestamp?) and how you order a Dockerfile because of it.
- [ ] What is the build context? Two costs of a missing `.dockerignore`?
- [ ] `RUN` vs `CMD`: when does each execute? Shell form vs exec form — who is PID 1 in each, and what breaks with shell form?
- [ ] Containerized app runs, port is published, every request refused — first suspect and why?
- [ ] Why multi-stage instead of one slim stage with build tools removed at the end?
- [ ] What does a container healthcheck change compared to "the process is running"? Who consumes it?
- [ ] A teammate's image is 1.4 GB. Give your first four moves to shrink it.
- [ ] Why key-only SSH auth? What do the 700/600 permissions on `.ssh` protect against?

### Added after Lab 3 (session went deeper here)

- [ ] Files in the image are copied as root — so how can `appuser` read and run the app at all? What's the first thing that *breaks* without `--chown`? And why does `--chown` belong in the COPY line instead of a `RUN chown -R` after it?
- [ ] `--chown=appuser:appuser` — what are the two fields, and why do both have the same name on Debian?
- [ ] What is UID 1000, and give two reasons to pin it explicitly instead of letting `useradd` pick (think volumes and Kubernetes).
- [ ] How does Docker resolve the name in `COPY --from=X`? What error do you get when you typo a stage name, and why is it a *pull* error?
- [ ] Your CMD must bind `0.0.0.0`, but the HEALTHCHECK probes `127.0.0.1` — explain why both are correct.
- [ ] `docker run` says the container name is in use, but `docker ps` shows nothing. What state is that container in, and which command reveals it?
- [ ] "Bind for 0.0.0.0:8000 failed: port is already allocated" — walk through the diagnosis, the fix, and which side of `-p` the image is allowed to care about.
- [ ] BuildKit ran a runtime-stage step *before* the builder stage finished. Why is that legal, and which step is the one that must wait?
- [ ] Your files are unchanged, yet a rebuild re-runs the whole builder stage including the dependency install. What moved, and what's the defense?

### Added after Lab 4 (session went deeper here)

- [ ] `depends_on` with vs without `condition: service_healthy` — which Lab 2 race comes back without it, and why does the gate protect only *startup*, not runtime?
- [ ] Behind the scenes of a healthcheck: who runs the probe, *where* does it run, what single value decides the verdict, and what does Docker itself do when a container flips to unhealthy?
- [ ] `up` fails with "container has no healthcheck configured" — what are the *two* places a healthcheck can come from, and why did the api pass this check with nothing in the compose file?
- [ ] `postgres:18` refuses to start with your volume mounted at `/var/lib/postgresql/data`. What changed in 18, where does the mount go now, and why did the image choose a loud `exit 1` over silently initializing elsewhere?
- [ ] `down` vs `down -v`: what exactly does each remove? How did the `up` task counters (5/5 first run vs 4/4 second) *prove* the volume survived before you even ran psql?
- [ ] Why does `REDIS_URL` contain the word `redis` instead of an IP? Who answers that name, from where, and when can the answer change?
- [ ] Where does a container's log line physically live? Name the two default-config risks (and the fix for each).
- [ ] You added a `logging:` block and ran `up -d` — why did compose *recreate* the api container instead of editing it live, and why did redis/db stay untouched? What bigger idea (Section 4 spoiler) is that reconcile behavior?

## Gate

- [ ] `notes.md` filled in my own words
- [ ] Everything committed (Dockerfiles, compose files, `.dockerignore`, `uv.lock` — no keys)

When all boxes are checked, say so — the next section (CI/CD with GitHub Actions) gets written against your notes.
