# Lab 1 — Image anatomy

**Goal:** see layers, cache, and container lifecycle with your own eyes instead of taking them on faith.

## The mental map (read this first)

An image is **not one big blob** — it's a stack of read-only layers, like a layer cake:

```
        IMAGE (read-only, built bottom → top)
┌─────────────────────────────────────────────┐
│  RUN install nginx            ← real layer  │
│  COPY entrypoint scripts      ← real layer  │
│  RUN create nginx user        ← real layer  │
│  ADD alpine base OS           ← real layer  │
└─────────────────────────────────────────────┘
   + config JSON (ENV, CMD, EXPOSE... = 0B, no layer)
```

Two rules that explain everything in this lab:

1. **Only instructions that change files create a layer.** `RUN`, `COPY`, `ADD` → real layers with size. `ENV`, `CMD`, `EXPOSE`, `LABEL` → just notes in the config JSON → `0B`.
2. **Layers are content-addressed (`sha256:...`) and shared.** If two images use the same base, that layer is stored on disk **once**.

And when you *run* an image:

```
IMAGE (read-only)          CONTAINER = image + thin writable layer on top
┌──────────────┐           ┌────────────────────────────┐
│ layer 4      │           │  writable layer  ← your    │
│ layer 3      │   run →   │  changes go here, dies     │
│ layer 2      │           │  with the container        │
│ layer 1      │           ├────────────────────────────┤
└──────────────┘           │  image layers (read-only)  │
                           └────────────────────────────┘
```

## Steps

### 1. Pull and dissect an image

```bash
docker pull nginx:alpine
docker history nginx:alpine
```

`docker history` = one row per Dockerfile instruction. **Read bottom-up** (bottom = built first). What to spot:

- **Bottom row** — `ADD alpine-minirootfs-...-aarch64.tar.gz`: the entire Alpine OS (~9MB). `aarch64` because you're on Apple Silicon — Docker picked the ARM variant automatically.
- **`0B` rows** — `ENV`, `CMD`, `EXPOSE`, `ENTRYPOINT`, `STOPSIGNAL`: config-only, no files, no layer.
- **`<missing>` in the IMAGE column** — NOT an error. Intermediate layer IDs only exist on the machine that *built* the image; you pulled it, so you only have the final ID. Ignore it forever.

Now count the **real** layers. The history has ~19 rows but only 8 changed files (1 `ADD` + 2 `RUN` + 5 `COPY`). Prove the image has exactly 8 layers:

```bash
docker image inspect nginx:alpine --format '{{json .RootFS.Layers}}' | tr ',' '\n'
```

Count the `sha256:` digests → 8. Then see **layer sharing** in action:

```bash
docker pull redis:alpine
docker image inspect redis:alpine --format '{{json .RootFS.Layers}}' | tr ',' '\n'
```

If the *first* digest matches nginx's first digest, both images share one on-disk copy of the Alpine base. That's why your 10th alpine pull is fast.

**Why sharing works — it's git for filesystems.** A layer's ID is a sha256 hash of its *contents*, so same bytes → same hash → same layer, regardless of which image references it. An image is just a manifest (a list of layer digests + config JSON) — a pointer structure, not a copy:

```
nginx:alpine                    redis:alpine
┌──────────────────┐            ┌──────────────────┐
│ nginx layers     │            │ redis layers     │
├──────────────────┤            ├──────────────────┤
│ sha256:abc123... │  ← SAME →  │ sha256:abc123... │   (Alpine base — on disk ONCE)
└──────────────────┘            └──────────────────┘
```

`docker pull` is per-layer: download the manifest, then for each layer — already on disk? skip. That's the **`Already exists`** lines you see in pull output (vs `Pull complete` for layers it actually downloaded). Those lines ARE layer sharing happening.

Caveat: nginx and redis only share the base if both were built from the *same* Alpine release. Built weeks apart on different versions → different bytes → different hashes → nothing shared. Sharing is purely "same bytes, same hash."

Why this matters beyond fast pulls:

- **Disk** — 50 services all built `FROM python:3.12-slim` store one ~120MB base, not 50 copies.
- **Deploys** — pushing a new app version only ships the layers that *changed*. Order your Dockerfile well (deps before code) and a code-only change ships as a tiny layer. That's the whole game of layer ordering — Lab 2.

### 2. Run it, poke it

```bash
docker run -d --name anatomy -p 8080:80 nginx:alpine
curl -s localhost:8080 | head -4
docker exec -it anatomy sh
```

Inside the container:

```sh
ps aux                 # PID 1 is nginx — read the deep-dive below
cat /etc/os-release    # Alpine, not macOS — you're in the image's filesystem
exit
```

#### Reading that `ps aux` — the most important output in this lab

```
PID   USER     TIME  COMMAND
    1 root     0:00  nginx: master process nginx -g daemon off;
   30 nginx    0:00  nginx: worker process
   ...
   42 root     0:00  sh          ← your docker exec shell
```

Five things are hiding in those few lines:

- **PID 1 is nginx, and the container lives exactly as long as PID 1.** A container is not a mini-VM — it's just a process tree with isolation around it. No init system, no systemd. Docker watches PID 1; PID 1 exits → container exits. What you see in `ps aux` is *everything* that exists.
- **Master is `root`, workers are `nginx`** — classic privilege separation: the master needs root to bind port 80 (<1024) and read config/certs, then spawns unprivileged workers to handle actual traffic.
- **PIDs are tiny (1, 30, 31...)** — you're in an isolated **PID namespace**. On the host these processes have big PIDs; inside, the container thinks it's a machine that just booted.
- **Your `sh` shows up as PID 42** — `docker exec` didn't SSH in. It injected a new process *into the container's existing namespaces*, which is why your shell appears next to nginx in the same `ps`. Your shell does NOT keep the container alive — only PID 1 does.
- **`/etc/os-release` says Alpine, but the kernel is shared.** You're seeing the image's filesystem (that ~9MB `ADD` layer from step 1) through a **mount namespace**. Containers share the host kernel — only userland is Alpine. (On macOS the "host kernel" is the Linux VM Docker Desktop runs.)

#### Why `daemon off;` — the PID 1 contract

**What "daemonize" means.** On a traditional server, a service started from a shell would die when the terminal closed. So daemons did a trick at startup: **fork a child, then the parent exits.** The shell gets its prompt back; the child runs in the background forever, adopted and supervised by init/systemd. Good behavior for 30 years.

**That same good behavior kills a container.** Trace daemonized nginx as PID 1:

```
docker starts container → nginx (PID 1)
PID 1 forks the real daemon (PID 5), then exits   ← classic daemon behavior
Docker: "PID 1 exited with code 0 — container finished."
Container torn down, taking PID 5 with it.
```

The container dies *instantly*, "successfully". Classic real-world bug: `docker run -d` → `docker ps` empty → `docker ps -a` shows Exited (0). `daemon off;` tells nginx to skip the fork-and-exit trick and stay in the foreground *as* PID 1. **In containers, the runtime IS your init system — daemonizing is redundant and fatal. "Run in foreground" is the rule for every containerized process.**

**Two more PID 1 gotchas** (planting seeds — you'll hit both later):

1. **Signals.** `docker stop` sends SIGTERM to PID 1, waits 10s, then SIGKILL. But Linux treats PID 1 specially: default signal handlers don't apply — if PID 1 hasn't explicitly installed a SIGTERM handler, the signal is *ignored*. nginx handles it; a naive `CMD ./run.sh` (shell doesn't forward signals) doesn't — so every `docker stop` hangs 10s then hard-kills. That's 10s added to every K8s pod rollout later.
2. **Zombie reaping.** Orphaned processes get re-parented to PID 1, which is expected to `wait()` on them (an init-system job). Apps that spawn subprocesses can accumulate zombies. Fix for both: `docker run --init` injects `tini`, a tiny init as PID 1 that forwards signals and reaps zombies, with your app as its child.

**The mental mapping** — the orchestrator outside the container took over everything init used to do inside the machine:

| VM / bare metal world | Container world |
|---|---|
| systemd starts and supervises services | Docker/K8s starts and supervises containers |
| service daemonizes into the background | process runs in foreground as PID 1 |
| systemd restarts it on crash | restart policy / K8s restarts the *container* |
| logs to files in `/var/log` | logs to stdout/stderr → `docker logs` |

"One process per container, foreground, log to stdout" isn't style advice — it's the contract that makes supervision, restarts, and log collection work.

One more thing from the `docker run` line: **`-p 8080:80`.** nginx listens on 80 inside its own **network namespace** — unreachable from outside until you publish a port. `-p 8080:80` wires host:8080 → container:80; that's the path your `curl localhost:8080` traversed.

### 3. Prove the writable layer is ephemeral

The flow you're about to execute:

```
write file → verify it exists → rm container → new container → file GONE
   (goes into writable layer)      (writable layer destroyed)   (fresh writable layer)
```

```bash
docker exec anatomy sh -c 'echo scratch > /tmp/i-will-die'
docker exec anatomy cat /tmp/i-will-die        # it's there
docker rm -f anatomy
docker run -d --name anatomy -p 8080:80 nginx:alpine
docker exec anatomy cat /tmp/i-will-die        # gone — new container, fresh writable layer
```

Same image, new container = new empty writable layer. This is why real data needs volumes (Lab 3).

#### What you just proved

**Where `scratch` actually went.** The image's 8 layers are read-only, always. Your write landed in the **thin writable layer** that `docker run` created on top — the image was never touched. The mechanism is **copy-on-write** (overlayfs): reads fall through to the image layers below; writes go to the top layer. And if you *modify* an existing image file — say nginx's config — it gets copied up to the writable layer first, and the copy shadows the original. The image file underneath stays pristine.

**What `rm -f` destroyed.** Compare the two container IDs you got from `docker run` — completely different. Two different containers sharing the same read-only image and the same name. `docker rm` deleted the first container's writable layer — `scratch` and all — and the new container got a brand-new empty one. The image is untouched either way; run 50 containers from it and each gets its own writable layer.

**Why this is a feature, not a bug.** This is what makes containers disposable: a misbehaving container isn't debugged and nursed back to health — it's killed and replaced, and the replacement is *guaranteed* to start from the exact image state. Kubernetes does this to your pods constantly (rescheduling, rolling updates, node drains). The corollary is the rule this step teaches: **anything worth keeping must not live in the writable layer** — databases, uploads, logs you care about go to volumes (Lab 3) or external services. An app that writes important state to its own filesystem silently loses data on every redeploy.

**Anti-pattern to recognize:** `docker commit` snapshots a container's writable layer into a new image layer. It "works" but produces unreproducible images nobody can rebuild. The fix is always "put it in the Dockerfile instead."

### 4. Logs and lifecycle

The container lifecycle:

```
docker run ──→ RUNNING ──(docker stop)──→ EXITED ──(docker rm)──→ GONE
                  ↑                          │
                  └──────(docker start)──────┘
                                             │
        writable layer SURVIVES stop/start ──┘── writable layer DESTROYED by rm
```

```bash
docker logs anatomy --tail 5
docker stop anatomy && docker ps -a --filter name=anatomy   # Exited, not deleted
docker start anatomy && docker ps --filter name=anatomy
```

`stop` vs `rm`: a stopped container keeps its writable layer; `rm` destroys it. (Note: on macOS the Docker engine runs inside a lightweight VM — `/var/lib/docker` lives there, not on your Mac's filesystem.)

## Verify

You can answer, out loud, without looking:

- Why do `ENV`/`CMD` lines show `0B` in `docker history`?

  <details><summary>Answer (read after attempting aloud)</summary>

  Only instructions that **change files** create a layer — `RUN`, `COPY`, `ADD`. `ENV`, `CMD`, `EXPOSE`, `ENTRYPOINT`, `LABEL` don't touch the filesystem; they're just notes written into the image's **config JSON** ("when you run me, use this command, set these env vars"). No files changed → no layer → `0B`. An image = stack of file layers + one config JSON.

  </details>

- Why must a containerized process run in the foreground? Walk through what happens if nginx daemonizes as PID 1.

  <details><summary>Answer (read after attempting aloud)</summary>

  Docker's rule is simple: **it watches PID 1, and the container lives exactly as long as PID 1.** There's no systemd inside to keep background things alive.

  Daemonizing = the old-school trick: fork a child into the background, then the parent exits (so your terminal gets its prompt back). Trace it as PID 1:

  ```
  docker starts container → nginx (PID 1)
  PID 1 forks the real worker (PID 5), then exits   ← classic daemon behavior
  Docker: "PID 1 exited with code 0 — container finished."
  Container torn down, taking PID 5 with it.
  ```

  The container dies instantly, "successfully" — `docker ps` empty, `docker ps -a` shows `Exited (0)`. That's why the image runs `nginx -g "daemon off;"`: stay in the foreground *as* PID 1. In containers, the runtime IS your init system — daemonizing is redundant and fatal.

  </details>
- Why can `docker stop` take exactly 10 seconds on a badly-built image? What does `--init` fix?

  <details><summary>Answer (read after attempting aloud)</summary>

  `docker stop` is Docker being polite, then losing patience: knock on the door — *"please shut down"* (SIGTERM) — wait 10 seconds, then break the door down (SIGKILL). **Exactly 10 seconds always means the process never heard the knock.** Two common reasons:

  1. **PID 1 is deaf by default.** Normally a process dies on SIGTERM even with no preparation — Linux has a default reaction. PID 1 is special: it has **no default reactions**. Unless the program explicitly wrote handler code, the signal just disappears. nginx wrote it → instant stop. A quick script didn't → 10s wait, then killed → `Exited (137)` (128 + signal 9).
  2. **The knock goes to the wrong guy.** Shell-form `CMD python app.py` makes PID 1 a *shell* with your app as its child. Docker knocks on the shell; shells don't pass the message along. Your app never gets the memo, however well it handles SIGTERM.

  ```
  PID 1: sh -c "python app.py"   ← Docker knocks HERE
  PID 7:   python app.py          ← never hears anything
  ```

  **`--init` fix:** puts a tiny doorman (**tini**) at PID 1 with your app behind him. Two jobs: (1) **passes messages along** — SIGTERM actually reaches your app, stop becomes instant; (2) **cleans up dead children** — acknowledges dead subprocesses so zombie process entries don't pile up (an init-system chore).

  One-liner: **10-second stop = PID 1 never heard the shutdown signal. `--init` puts a tiny messenger at PID 1 that delivers signals and reaps zombies.** Cheapest fix without it: exec form `CMD ["python", "app.py"]` (your app IS PID 1) + handle SIGTERM yourself — tini only guarantees delivery; graceful shutdown is still your app's job.

  </details>
- What exactly is destroyed by `docker rm` that survives `docker stop`?

  <details><summary>Answer (read after attempting aloud)</summary>

  The container's **writable layer** (plus its config, logs, and identity). `stop` just kills the process — the container still exists in `docker ps -a`, same ID, writable layer intact, and `start` resumes it with all files and even its logs still there. `rm` deletes the container itself: writable layer, logs, everything. Memory hook: **stop/start = pause/resume; rm/run = destroy/recreate.** The image is untouched by both.

  </details>

- A container edits a config file that came from the image. What happens on disk (copy-on-write), and does the image change?

  <details><summary>Answer (read after attempting aloud)</summary>

  The image **never** changes — its layers are read-only, always. On the first write, overlayfs **copies the file up** into the container's thin writable layer, and the edit happens on that copy. From inside the container the copy *shadows* the original, so it looks edited; underneath, the image file is pristine. Reads of untouched files fall straight through to the image layers. That's copy-on-write: reads go down, writes go up. Delete the container → the copy dies → next container from the image sees the original again.

  </details>

- Why is `docker commit` an anti-pattern? What's the right alternative?

  <details><summary>Answer (read after attempting aloud)</summary>

  `docker commit` snapshots a container's writable layer into a new image layer — including whatever you exec'd in and did by hand. It "works," but the result is **unreproducible**: no record of how the image was made, nobody (including future-you) can rebuild it, no code review, no CI. It's the container version of "I SSH'd in and fixed it manually." Right alternative: put the change in the **Dockerfile** and rebuild — the image is then reproducible from source, diffable, and reviewable.

  </details>

- Two images share a base — is it stored twice? How do you check?

  <details><summary>Answer (read after attempting aloud)</summary>

  Stored **once**. A layer's ID is a sha256 hash of its *contents* — same bytes → same hash → same on-disk layer, no matter how many images reference it. An image is just a manifest (list of layer digests) pointing at layers, like git objects. Check it:

  ```bash
  docker image inspect nginx:alpine --format '{{json .RootFS.Layers}}' | tr ',' '\n'
  docker image inspect redis:alpine --format '{{json .RootFS.Layers}}' | tr ',' '\n'
  ```

  Same first digest = shared base. You also see it live during `docker pull`: `Already exists` lines ARE layer sharing. Caveat: only if both were built from the *same* base release — different Alpine versions → different bytes → different hashes → nothing shared.

  </details>

- Draw the image-vs-container diagram from memory: where do a running container's writes go?

  <details><summary>Answer (read after attempting aloud)</summary>

  ```
  IMAGE (read-only)          CONTAINER = image + thin writable layer on top
  ┌──────────────┐           ┌────────────────────────────┐
  │ layer 4      │           │  writable layer  ← ALL     │
  │ layer 3      │   run →   │  writes land here; dies    │
  │ layer 2      │           │  with the container (rm)   │
  │ layer 1      │           ├────────────────────────────┤
  └──────────────┘           │  image layers (read-only)  │
                             └────────────────────────────┘
  ```

  Every write goes to the writable layer — new files created there, image files copied up on first modify. It survives `stop`, dies with `rm`, and every new container gets a fresh empty one. Anything worth keeping goes in a **volume**, never the writable layer.

  </details>

## Clean up

```bash
docker rm -f anatomy
docker rmi redis:alpine   # only if you pulled it for the layer-sharing check
```
