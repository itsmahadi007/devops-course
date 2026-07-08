# Lab 6 — Deploy to vps-lab over SSH

**Goal:** close the loop. A push to `main` now runs tests → builds a multi-arch image → pushes to GHCR → and a **deploy job on your self-hosted runner** SSHes into `vps-lab`, pulls the image, and runs it. You'll teach `vps-lab` to run Docker *inside itself* (Docker-in-Docker), use a **dedicated deploy key** (never your personal one), and store its private half as a repo secret. End state: `curl localhost:9030/health` returns your app, deployed with no human in the loop.

## The mental map (read this first)

The runner is on your Mac (Lab 5). `vps-lab` is a container on the same Mac, listening on `localhost:9022`. So the runner can just SSH in. Once inside, it needs Docker to `pull` and `run` the image — but `vps-lab` is *itself* a container. Running Docker inside a container is **Docker-in-Docker (DinD)**, and it needs `privileged: true`.

```
 git push to main
      │  test ✓ → build ✓ (multi-arch image on GHCR)
      ▼
 ┌───────── deploy job (runs-on: self-hosted) ──────────┐
 │  on YOUR MAC (Lab 5's runner)                        │
 │                                                       │
 │  ssh -i deploy_key -p 9022 mahadi@localhost  ────────┼──┐
 └───────────────────────────────────────────────────────┘  │
                                                              ▼
   ┌──────────────── vps-lab (privileged container) ──────────────┐
   │  sshd (PID 1)  +  dockerd running INSIDE (DinD)               │
   │                                                               │
   │   docker pull ghcr.io/itsmahadi007/capstone:sha-abc123        │
   │   docker run -d --name capstone -p 8080:8000  ...             │
   │                                        │                       │
   │        ┌───────────────────────────────▼──────────────┐        │
   │        │ inner capstone container : listens on :8000   │        │
   │        └───────────────────────────────────────────────┘        │
   └───────────────────────────────────────────────────────────────┘

 THE PORT CHAIN (memorize this — it's the verify):
   Mac : 9030   ──▶   vps-lab : 8080   ──▶   inner capstone : 8000
   (compose            (inner docker            (the app's own
    publishes           publishes                EXPOSE, unchanged)
    9030:8080)          8080:8000)
```

Three ideas to hold:

**1. The runner's location IS the deploy's superpower.** Lab 5's whole point: only a machine *on your Mac* can reach `vps-lab:9022`. The deploy job runs there, so `ssh … localhost` just works. A hosted runner could not do this line.

**2. Docker-in-Docker is a real, honest hack.** `vps-lab` pretends to be a server; a server can run Docker; so `vps-lab` must run its own `dockerd`. That requires `privileged: true` — which hands the container near-total access to the host kernel. In production DinD is used carefully (CI build farms) and often avoided (people mount the host's Docker socket instead, or use rootless/Kaniko). Here it's the cleanest way to make the fake VPS behave like a real box you `docker run` on. You'll say "privileged is a big hammer" in interviews and mean it.

**3. A deploy key is a single-door key.** You will **not** put your personal SSH key in a repo secret. You'll mint a *new* keypair whose only job is "log into vps-lab as the deploy user." Its private half becomes a GitHub secret; if it ever leaks, the blast radius is one fake VPS, not your whole SSH identity. This is the least-privilege reflex from Lab 3's `GITHUB_TOKEN`, applied to SSH — and Lab 5's security lesson made concrete.

## Steps

### 1. Mint a dedicated deploy key

```bash
cd /Users/mahadihassan/Documents/plan/projects/devops-course/vps-lab
ssh-keygen -t ed25519 -f keys/deploy_key -N "" -C "capstone-ci-deploy"
ls keys/
```

This writes `keys/deploy_key` (private) and `keys/deploy_key.pub` (public). `-N ""` = no passphrase (CI can't type one). `keys/` is already in `.gitignore` (Section 1) — confirm with `git status` that neither file shows up as untracked. **Never commit either half.** This keypair exists only to open `vps-lab`; it is not your `~/.ssh/id_*` identity and must not be.

### 2. Teach vps-lab to run Docker, and trust the deploy key

Two files change. First, the **full** `vps-lab/Dockerfile` — three additions to Section 1's version (marked in comments):

```dockerfile
FROM debian:12-slim
# a bare Debian — the closest thing to what a hosting provider hands you

RUN apt-get update && apt-get install -y --no-install-recommends \
        openssh-server sudo curl vim iproute2 docker.io \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir /run/sshd
# ADDED docker.io — the reproducible form of "apt install docker.io" you'd run by
# hand on a fresh server. Provisioning-as-code: the Dockerfile IS the runbook, so
# a rebuilt vps-lab always has Docker (S1 Lab 1's "always Dockerfile, never manual").

RUN useradd --create-home --shell /bin/bash mahadi \
    && echo 'mahadi ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/mahadi \
    && usermod -aG docker mahadi
# ADDED usermod -aG docker — puts mahadi in the "docker" group so he can talk to
# the docker socket without sudo. The group owns /var/run/docker.sock (perms 660).

RUN sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config \
    && sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config

COPY keys/vps_key.pub keys/deploy_key.pub /home/mahadi/.ssh/
RUN cat /home/mahadi/.ssh/vps_key.pub /home/mahadi/.ssh/deploy_key.pub \
        > /home/mahadi/.ssh/authorized_keys \
    && rm /home/mahadi/.ssh/vps_key.pub /home/mahadi/.ssh/deploy_key.pub \
    && chown -R mahadi:mahadi /home/mahadi/.ssh \
    && chmod 700 /home/mahadi/.ssh && chmod 600 /home/mahadi/.ssh/authorized_keys
# ADDED the deploy key: authorized_keys now holds BOTH locks — your interactive
# vps_key (S1) AND the CI deploy_key. One file, two authorized keys; sshd accepts
# either. StrictModes still demands 700/600 (S1 Lab 5) — hence the chmods.

EXPOSE 22
# poor-man's init: start dockerd in the background, then hand PID 1 to sshd.
# A real server's systemd would supervise both as services; our container has no
# init (S1 Lab 1). `exec` makes sshd REPLACE the shell, so sshd is PID 1 and still
# hears SIGTERM — shell-form CMD without exec would leave /bin/sh as PID 1 (the
# 10-second-stop bug from S1 Lab 1). Here exec is the fix, deliberately.
CMD dockerd > /var/log/dockerd.log 2>&1 & exec /usr/sbin/sshd -D
```

Second, the **full** `vps-lab/docker-compose.yml` — two additions:

```yaml
services:
  vps:
    build: .
    container_name: vps-lab
    hostname: vps-lab
    privileged: true          # ADDED — Docker-in-Docker needs near-host kernel access.
                              # Big hammer: privileged ≈ root on the host. Fine for a
                              # local throwaway lab; a red flag on anything real.
    ports:
      - "9022:22"             # SSH (unchanged from S1)
      - "9030:8080"           # ADDED — Mac:9030 → vps-lab:8080 → inner capstone:8000
    restart: unless-stopped
```

### 3. Rebuild vps-lab and clear the stale host key

Because you changed the image (new authorized key, docker.io), you must rebuild — and a rebuild reruns the apt layer that *generates the SSH host key*, so vps-lab gets a **new identity** (S1 Lab 5's exact lesson). Your Mac's `known_hosts` still remembers the old one, so an interactive SSH would scream `REMOTE HOST IDENTIFICATION HAS CHANGED`.

```bash
cd /Users/mahadihassan/Documents/plan/projects/devops-course/vps-lab
docker compose down
docker compose up -d --build
ssh-keygen -R "[localhost]:9022"        # forget the old identity; next connect re-TOFUs
```

Now confirm Docker is alive *inside* vps-lab (give dockerd ~5–10s to start after `up`):

```bash
sleep 8
docker exec vps-lab docker info --format '{{.ServerVersion}}'
```

Expect a Docker version string — that's `dockerd`, running inside a container, answering. If it errors, see the failure notes below.

### 4. Store the private key as a repo secret

The deploy job needs the *private* deploy key to log in. It goes into GitHub Actions secrets — encrypted, write-only from the UI's view, referenced by name in YAML (never printed):

```bash
cd /Users/mahadihassan/Documents/plan/projects/devops-course
gh secret set VPS_DEPLOY_KEY < vps-lab/keys/deploy_key
gh secret list
```

`gh secret list` shows `VPS_DEPLOY_KEY` with an updated timestamp — but **not** its value; secrets are one-way. In workflow logs, GitHub also auto-masks the value if it ever appears, replacing it with `***`. This is why the lab uses a dedicated key even here: a secret is safe, but "never put your master key where a workflow can read it" is the discipline, not the exception.

### 5. Add the deploy job

Append to `.github/workflows/ci.yml` (sibling of `test`/`build` under `jobs:`):

```yaml
  deploy:
    needs: build
    runs-on: [self-hosted, macos, capstone-deploy]
    if: >-
      github.event_name == 'push' &&
      github.ref == 'refs/heads/main' &&
      github.repository == 'itsmahadi007/devops-course'
    steps:
      - name: Install the deploy key on the runner
        run: |
          mkdir -p ~/.ssh && chmod 700 ~/.ssh
          echo "${{ secrets.VPS_DEPLOY_KEY }}" > ~/.ssh/vps_deploy_key
          chmod 600 ~/.ssh/vps_deploy_key
          # vps-lab's host key may have changed since the last deploy (rebuild) —
          # forget the old one so accept-new can re-learn it, no interactive prompt
          ssh-keygen -R "[localhost]:9022" 2>/dev/null || true

      - name: Deploy the freshly-built image into vps-lab
        run: |
          SHORT_SHA=$(echo "${{ github.sha }}" | cut -c1-7)
          IMAGE="ghcr.io/itsmahadi007/capstone:sha-${SHORT_SHA}"
          echo "Deploying $IMAGE"
          ssh -i ~/.ssh/vps_deploy_key -p 9022 \
              -o StrictHostKeyChecking=accept-new \
              mahadi@localhost "bash -s" <<EOF
          set -euo pipefail
          docker pull "$IMAGE"
          docker rm -f capstone 2>/dev/null || true
          docker run -d --name capstone --restart unless-stopped -p 8080:8000 "$IMAGE"
          docker ps --filter name=capstone
          EOF
```

Pre-read — the parts that matter:

- **`needs: build`** — deploy only after a green multi-arch push. The full chain `test → build → deploy` is now three linked jobs.
- **`runs-on: [self-hosted, macos, capstone-deploy]`** — routes to *your Mac* (Lab 5's labels). Only that runner can reach `vps-lab`.
- **the `if:` guard** — the Lab 5 safety rail, live. Deploy runs only on a **push to main** in **your** repo — never on a pull request, never from a fork (a fork's `github.repository` isn't yours). A stranger's PR can build and test in isolation but can never trigger a deploy onto your machine. This one block is what makes a self-hosted deploy on a public repo defensible.
- **`SHORT_SHA` → `:sha-<7>`** — deploys the **immutable per-commit tag** from Lab 3, not `:latest`. `metadata-action`'s `type=sha` uses a 7-char short SHA by default, so `cut -c1-7` reconstructs the exact tag CI just pushed. Now "what's running on the VPS?" answers with an exact commit — the deploy-by-sha discipline, enforced.
- **the SSH heredoc** — `mahadi@localhost` on port 9022, keyed by the deploy key. `accept-new` silently learns vps-lab's (freshly reset) host key on first contact instead of prompting — safe here because you control both ends; on a real box you'd pin the known host key. The remote script: `pull` the new image, force-remove any old `capstone` container, `run` the new one with `-p 8080:8000` and a restart policy. `set -euo pipefail` makes the remote side fail loudly if any step breaks (so the job goes red instead of green-but-broken).

Push it:

```bash
cd /Users/mahadihassan/Documents/plan/projects/devops-course
# make sure Lab 5's runner is listening: ~/actions-runner/run.sh (or svc.sh start)
git add .github/workflows/ci.yml vps-lab/Dockerfile vps-lab/docker-compose.yml
git commit -m "ci: deploy capstone into vps-lab over ssh"
git push
gh run watch
```

Expect the run graph `test → build → deploy`, all green, with `deploy` running on your Mac (watch the `run.sh` terminal light up). The deploy step's log ends with a `docker ps` line showing the `capstone` container running *inside* vps-lab.

### 6. Verify the whole chain from your Mac

```bash
curl -s localhost:9030/health
```

Expect `{"status":"ok"}` — and trace what that one request just did: your Mac's port 9030 → vps-lab's published 8080 → the inner capstone container's 8000, all set up automatically by a git push. That is a complete CI/CD pipeline you built.

Confirm the deployed image is the right architecture (a callback worth savoring):

```bash
docker exec vps-lab docker image inspect ghcr.io/itsmahadi007/capstone:sha-$(git rev-parse --short=7 HEAD) --format '{{.Architecture}}'
```

Expect `arm64` — vps-lab runs on Docker Desktop's arm64 VM, so it pulled the arm64 slice of Lab 4's manifest list. Honest note: because vps-lab is arm64 like your Mac, a still-arm64-only image (pre-Lab-4) would *also* have worked here — you can't watch `exec format error` happen on this box precisely because there's no x86 in your `$0` lab. Lab 4's payoff is real but invisible until a real x86 droplet pulls the *same tag* and gets amd64 instead. Trust the manifest-list proof from Lab 4; this box just can't show the failure it prevents.

#### If the deploy step fails with `Permission denied (publickey)`

The deploy key isn't trusted, or the secret is malformed. Check: did the rebuild in step 3 actually happen (so `deploy_key.pub` is in vps-lab's `authorized_keys`)? Did `gh secret set` read the *private* key file (`< vps-lab/keys/deploy_key`, not `.pub`)? A common mangle: the secret lost its trailing newline — `echo "${{ secrets.VPS_DEPLOY_KEY }}"` adds one back, which is why the step writes it that way. Test the key by hand: `ssh -i vps-lab/keys/deploy_key -p 9022 mahadi@localhost whoami` should print `mahadi`.

#### If the deploy fails on `docker: command not found` or `Cannot connect to the Docker daemon`

`dockerd` inside vps-lab isn't running or mahadi isn't in the docker group. Check the daemon log: `docker exec vps-lab cat /var/log/dockerd.log`. If dockerd crashed on storage driver, add `/etc/docker/daemon.json` with `{"storage-driver":"vfs"}` (slower but works everywhere in DinD) via a Dockerfile `RUN`, and rebuild. If it's a group issue, confirm `docker exec vps-lab id mahadi` lists `docker`. Remember dockerd only starts via the CMD, so a `docker compose restart` (which doesn't recreate) that somehow skipped it — just `up -d` again.

#### If the job sits Queued forever

Lab 5's label footgun: the self-hosted runner isn't online. Start `~/actions-runner/run.sh`. `gh api /repos/itsmahadi007/devops-course/actions/runners --jq '.runners[].status'` should say `online`.

#### If `curl localhost:9030` connection-refused but the job was green

The port chain has a broken link. Check each hop: `docker exec vps-lab docker ps` (inner container running and mapped `0.0.0.0:8080->8000`?), then `docker port vps-lab` (does vps-lab publish `9030->8080`?). A green deploy with a refused curl usually means the inner `docker run` used the wrong `-p`, or vps-lab's compose is missing the `9030:8080` line from step 2.

## Verify

- `curl -s localhost:9030/health` returns `{"status":"ok"}` — the app, deployed by a push.
- `docker exec vps-lab docker ps` shows the `capstone` container running inside vps-lab.
- Make a visible code change (edit `/ask`'s canned answer), commit, push to main, and watch the pipeline redeploy it — then `curl localhost:9030/ask?q=hi` shows the new answer. The loop is closed: **commit → live**, hands-off.

Then answer aloud:

**1. Why must the deploy job run on the self-hosted runner and not `ubuntu-latest`?**

<details><summary>Answer (read after attempting aloud)</summary>

The deploy SSHes into `vps-lab` at `localhost:9022` — a container on your Mac, behind home NAT with no public inbound route (Lab 5). A GitHub-hosted runner in a datacenter has no path to it. The self-hosted runner is a process *on the Mac*, so `localhost:9022` is local and reachable, and it got there by pulling work outbound — GitHub never had to connect in. The deploy's reachability is exactly why Lab 5 existed.

</details>

**2. What is `privileged: true` doing for vps-lab, and why is it a "big hammer"?**

<details><summary>Answer (read after attempting aloud)</summary>

It's required for Docker-in-Docker: vps-lab runs its own `dockerd`, which needs kernel capabilities (cgroups, mounts, networking) that an unprivileged container is denied. `privileged` drops nearly all of Docker's isolation — the container gets near-root access to the host kernel, so a compromise inside it is close to a host compromise. Fine for a local throwaway lab; on anything real you'd avoid DinD (mount the host Docker socket, or use rootless/Kaniko) or tightly scope it. Naming that tradeoff is the senior answer.

</details>

**3. Why a dedicated deploy key in a repo secret instead of your personal SSH key?**

<details><summary>Answer (read after attempting aloud)</summary>

Blast radius. The deploy key's only power is "log into vps-lab as mahadi." If the secret ever leaks (a bad workflow, a compromised action), an attacker gets one fake VPS — not your entire SSH identity across every server and git host you use. Same least-privilege logic as scoping `GITHUB_TOKEN` (Lab 3): give the automation the narrowest credential that does the job, and keep master keys out of anything a workflow can read.

</details>

**4. Trace the port chain for `curl localhost:9030/health`. Where does each hop's mapping get defined?**

<details><summary>Answer (read after attempting aloud)</summary>

Mac:9030 → vps-lab:8080 → inner capstone:8000. Hop 1 (`9030:8080`) is vps-lab's compose `ports:` — published on your Mac. Hop 2 (`8080:8000`) is the inner `docker run -p 8080:8000` that the deploy job executed *inside* vps-lab, published in vps-lab's own network namespace. Hop 3 (8000) is the app's own `EXPOSE`/uvicorn bind, unchanged since Section 1. Three independent `-p` mappings, each owning one hop — a refused curl means one hop's mapping is missing.

</details>

**5. The deploy job has an `if:` guard on event, branch, and repository. What attack does it stop?**

<details><summary>Answer (read after attempting aloud)</summary>

Fork-PR code execution on your machine (Lab 5's core risk). Because the repo is public and the runner is self-hosted, a stranger could fork it and open a PR editing the workflow to run malicious code. The guard restricts deploy to `push` events, on `main`, in *your* repository — a fork's PR is a `pull_request` event whose `github.repository` isn't yours, so the deploy job never starts for it. The fork can still run isolated tests, but it can never reach the SSH-into-your-Mac step.

</details>

## Clean up

Leave the pipeline armed — this *is* the deliverable. But tidy the moving parts:

```bash
# stop the running app in vps-lab if you want a clean slate (next push redeploys it)
docker exec vps-lab docker rm -f capstone

# the self-hosted runner: stop run.sh when idle, or leave svc.sh running if you'll iterate
```

Keep `VPS_DEPLOY_KEY` in secrets and `keys/deploy_key*` on disk (gitignored) — Section 3 SSHes into this same vps-lab. Confirm `git status` shows only the intended files (workflow + vps-lab Dockerfile/compose) and **no keys**. Update `capstone/README.md` evolution log: "Section 2: CI builds+pushes multi-arch image and deploys it into vps-lab over SSH."
