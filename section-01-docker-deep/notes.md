# My notes — Section 01: Docker Deep

> Fill this as you go, in your own words (Bangla is fine). This file steers how Section 2 gets written — flag anything confusing and the next section will slow down there.

## Lab 1 digest (session summary — the personal sections below are still yours to fill)

**Done 2026-07-06.** The one-liners worth keeping:

- **Image = stack of read-only layers + config JSON.** Only `RUN`/`COPY`/`ADD` make layers; `ENV`/`CMD`/`EXPOSE` are `0B` notes in the config. Layers are content-addressed (sha256 of bytes) → same base = stored once, `Already exists` in pull output IS layer sharing.
- **A container is not a mini-VM — it's a process tree with isolation.** No systemd inside. Docker watches PID 1; PID 1 exits → container dies. `docker exec` injects a process into the existing namespaces (not SSH) — my shell showed up as PID 42 next to nginx.
- **Foreground rule:** daemonizing = fork child + parent exits → in a container the exiting parent is PID 1 → instant `Exited (0)`. Hence `daemon off;`. The runtime IS the init system.
- **10-second `docker stop` = PID 1 never heard the knock.** SIGTERM → wait 10s → SIGKILL → `Exited (137)` (128+9). PID 1 has no default signal handlers, and shell-form `CMD` puts a shell (which doesn't forward signals) at PID 1. Fixes: exec-form `CMD ["..."]`, handle SIGTERM, or `--init` (tini = signal-forwarding + zombie-reaping doorman).
- **Writes go to a thin writable layer on top (copy-on-write).** Image files get copied up on first modify; image never changes. `stop`/`start` = pause/resume (same container, layer survives). `rm`/`run` = destroy/recreate (new ID, fresh empty layer) — proved with `/tmp/i-will-die`. Real data → volumes.
- **Logs:** Docker captures PID 1's stdout/stderr — that's `docker logs`. nginx image symlinks its log files to `/dev/stdout`. Logs survive `stop` (post-mortems on dead containers), die with `rm`.
- **Exit codes as first diagnostic:** 0 = clean, 137 = SIGKILLed (stop timeout or OOM), 139 = segfault.
- **Anti-pattern:** `docker commit` = "I SSH'd in and fixed it manually." Always Dockerfile instead.

## Lab 2 digest (session summary)

**Done 2026-07-07.** The one-liners worth keeping:

- **`docker build` = send → execute → stack.** The trailing `.` is the build context — your folder, sent to the builder; it's all `COPY` can see. `.dockerignore` controls what's excluded (like `.gitignore` for builds). Without it: 18.88MB context, `__pycache__` snuck into the image; with it: ~100kB.
- **Cache rule = ladder.** A layer is reused only if the instruction + the files it uses are unchanged; break one rung and **every rung above reruns**. Judged by **content checksum, NOT timestamp** — `touch` = cache hit, one-character edit = bust. Proved: one comment line → `pip install` reran (4s here; minutes on a real project, on every CI commit). Fix = ordering: deps alone → install → then code (Lab 3).
- **`RUN` = do it now (build time, makes a layer). `CMD` = do it later** (0B note in config JSON; `docker run` reads it and launches it as PID 1).
- **CMD always in brackets (exec form).** Shell form = `/bin/sh -c "..."` is PID 1 → signals never reach the app → 10s stop. Exec form = app IS PID 1 — saw it live: `Started server process [1]`.
- **`--host 0.0.0.0` or nothing works.** Container = own network namespace; `127.0.0.1` bind = "only from inside this container" → `-p` traffic refused while the app runs fine. Proof in the logs: my curl arrived from `192.168.65.1` (Docker Desktop's gateway), not 127.0.0.1 — the request really is external.
- **Naive image sins, measured:** `python:3.14` base → **1.7GB disk / 427MB compressed** for a 3-file app. Sins: fat base, `COPY . .` before install (code+deps in one cache rung), no `.dockerignore`.
- **Misc collected on the way:** errno 48 = port already taken on host (containers solve this — each gets its own netns) · "started ≠ ready" — curl raced uvicorn twice (healthchecks fix this properly, Labs 3–4) · exit 143 = 128+15 = graceful SIGTERM · connection-refused requests never appear in app logs (refused at TCP, app never saw them) · even cached builds re-check the tag's registry metadata — tags are mutable pointers (Lab 6) · Docker Desktop's two sizes: disk usage = uncompressed, content size = compressed (what push/pull ships).

## Lab 3 digest (session summary)

**Done 2026-07-08.** The one-liners worth keeping:

- **Multi-stage = kitchen vs dining room.** Two `FROM`s, only the last ships; uv and build leftovers stay behind. Measured: 1.67GB → 220MB disk (**7.6×**), 421MB → 47.2MB compressed (**8.9×** — the number pulls actually ship).
- **`COPY --from` = lift files off a neighbor's shelf**, not "run an installer": Docker pulls uv's image like any image, copies two Rust binaries, nothing executes. Same mechanism as the stage handoff. And `--from` resolution has a fallback: no stage with that name → treat it as a **registry image** — my `AS build` vs `--from=builder` typo sent Docker shopping for `docker.io/library/builder:latest` → pull denied.
- **`:latest` bit me live:** uv's tag moved overnight → new digest → `COPY --from=uv` rung broke → the whole builder ladder re-ran, `uv sync` included. Nothing in *my* files changed. Pin versions when it matters.
- **`uv.lock` + `--frozen` = reproducible builds.** Lockfile is law; if `pyproject.toml` and lock drift apart, the build fails loudly instead of silently re-resolving.
- **Owner vs permissions:** every file = name tag (owner **user** + owner **group**) + rulebook (`rwx` × owner/group/others). **Root skips permission checks entirely** — that's how build-time COPY writes anywhere, and why the app shouldn't run as root. Without `--chown`, appuser could read/execute via the "others" column but never write → `PermissionError`s.
- **`--chown=appuser:appuser` = two fields (`user:group`), not a transfer.** Same word, two registries — Debian auto-creates a private group per user (UID 1000 ↔ GID 1000). `--chown` in COPY beats a later `RUN chown -R`: layers are append-only, so a separate chown duplicates every file into a second layer.
- **UID 1000:** the kernel thinks in numbers, not names (`/etc/passwd` just maps them). 0 = root, 1–999 = system, 1000 = first normal user. Pin it: volume file ownership is stored numerically, and K8s `runAsUser` speaks numbers.
- **Flow map: each stage is its own cache ladder; the only bridge is the handoff COPY.** Code edit → top rung of builder breaks, `uv sync` below it stays CACHED, only the bridge re-runs in stage-1. ~2s rebuild vs Lab 2's full reinstall — *order was the entire fix*.
- **BuildKit is a dependency graph, not a script:** stage-1's `useradd` ran while builder was still downloading uv; only the bridge COPY had to wait. Unnamed stages get auto-names (`stage-1`, numbered from 0).
- **Healthcheck:** `start-period` grace / `interval` / `timeout` / `retries` (3 consecutive fails → unhealthy). The probe runs **inside** the container — hence `python -c urllib` (slim has no curl) against `127.0.0.1:8000`, no contradiction with CMD's `0.0.0.0` (opposite sides of the netns wall). `docker inspect '{{json .State.Health}}'` keeps the probe log. Payoff: compose `service_healthy` gating (Lab 4), K8s probes (Section 4).
- **`ENV PATH` trick:** never `source activate` in a Dockerfile — activation IS PATH manipulation. A venv is only portable if the Python under it and the absolute path both match (hence `/app` → `/app`).
- **Ghost containers (hit twice):** a Created/stopped container still owns its NAME; `docker ps` hides it, `docker ps -a` shows it. Name conflict error + empty `docker ps` = ghost.
- **"port is already allocated" ≠ name conflict:** another container publishes that host port (bare `docker ps`, PORTS column — it was my own cashlessai gateway on 8000). Fix = remap the **host side only**: `-p 9000:8000`, left = my Mac, right = inside the box. Healthcheck unaffected (never leaves the building); no rebuild — the mapping is a runtime decision, the image hardcodes only its own side. **My machine: 8000-series is taken by the real dev stack → labs use 9000-series host ports from now on.**
- **Misc:** bare `5678/tcp` in PORTS = EXPOSEd-but-unpublished, burns no host port · `FINISHED` banner ≠ success — scan for ERROR lines; metadata failures kill the build at planning, before any instruction runs · `[200~` in zsh = bracketed-paste artifact, not Docker.

## Lab 4 digest (session summary)

**Done 2026-07-08.** The one-liners worth keeping:

- **Compose = declare the stack in one YAML; `up` makes reality match the file.** You describe the end state (services, network, volume, order); Docker does the doing. Same philosophy as K8s later — compose is the training wheels. Project name = folder name → `capstone_default`, `capstone_pgdata`, `capstone-api-1`.
- **Service name = DNS hostname.** Docker runs a tiny DNS server (`127.0.0.11` inside every container) mapping names → current IPs; proved from inside: `redis`/`db` → `172.30.0.2/.3`. IPs are disposable (change on recreate), names aren't — so config says `redis://redis:6379`, never an IP. And the app reads it from env (`REDIS_URL`) → same image everywhere, only env changes (12-factor).
- **`service_healthy` is a fixed compose keyword** (with `service_started`, `service_completed_successfully`). Engine stamps health, compose reads the stamp and holds the api at the door — watched it live: redis/db `Healthy 5.7s`, api `Started 5.8s`. Gate exists **only at startup**; if redis dies later the api is on its own (K8s fixes that, Section 4). No healthcheck from either source → `up` fails loudly: "has no healthcheck configured".
- **Healthcheck behind the scenes = scheduled `exec` + exit code + stamp.** Config is a 0B JSON note; the daemon's timer injects the probe into the container's namespaces (same mechanism as `docker exec`); exit 0 = healthy, 1 = unhealthy; `retries` *consecutive* fails flip the stamp. Docker itself does NOTHING on unhealthy — consumers act (compose gate; K8s kubelet restarts). Healthcheck can come from the image (api, Lab 3) or the compose file (redis/db) — same stamp.
- **Postgres 18 trap (hit live):** image moved data to a version subdir (`/var/lib/postgresql/18/docker`) so future `pg_upgrade` works across one mount; a volume at the legacy `.../data` → deliberate `exit 1` with a lecture in the logs. 18+ rule: **mount at `/var/lib/postgresql`**. Same "loud failure > silent drift" as `--frozen`. Diagnostic chain: `exited (1)` → `docker logs` → read the reason. Cascade: db Error → api stuck at `Created` — `depends_on` refusing a dead dependency.
- **Volume punchline, proved by the counters:** `down` output = 4 removals, no volume line; second `up` = `4/4` vs first run's `5/5` (no `Volume Created`). Postgres kept `survivors` (named volume re-mounted); Redis reset to `visits: 1` (writable layer died with the container). **Persistence is a per-service decision** — cache losing data on restart is correct, a database doing that is an incident.
- **Only the api gets `ports:`** (`9000:8000`); redis/db have no host door at all — reachable only by service DNS inside the network. Fewer doors = smaller attack surface; the real Redis on 6379 never noticed.
- **A log line's life: stdout → engine → JSON file** (`json-file` driver; `docker inspect '{{.LogPath}}'`; inside the Docker Desktop VM). `docker logs` is just a reader. Default = grows forever → full disk = host-wide outage; capped with `logging: max-size "10m" / max-file "3"` (quoted — the driver wants strings, not YAML ints).
- **Log config is container-creation-time** → `up -d` surgically `Recreated` only api, redis/db untouched — compose diffs file vs reality and reconciles only the drift (that reconcile loop IS Kubernetes' whole personality). Side effect: recreation destroyed the old log file.
- **`down` = `rm` for every container → logs are evidence on borrowed time.** The postgres-18 error lecture is unrecoverable now. That's why central log shipping exists (Loki/CloudWatch/ELK — Section 8).
- **Log slicing flags:** `-t` engine timestamps (one clock across services — trust for cross-service ordering), `--since 10m` / `--until` incident windows, `logs -f api db` subset follow, `--no-log-prefix` for clean grep/jq pipes.
- **Misc:** `CMD` vs `CMD-SHELL` in healthchecks — shell form is harmless here (no PID 1/signals involved) · `psql` version line read: `aarch64` = native ARM build, `linux-musl` = Alpine's libc (that's literally what `-alpine` means) · `docker compose ps` = `docker ps` scoped to the project.

## Lab 5 digest (session summary)

**Done 2026-07-08.** The one-liners worth keeping:

- **A VPS, stripped of marketing = Linux + sshd + a user + your key** — all four fit in a container. The login banner proved the two honest differences live: `6.12.76-linuxkit` = Docker Desktop's VM kernel (containers never bring their own — my "Debian VPS" is Debian userland on a borrowed kernel), `aarch64` = Apple Silicon.
- **Two directions of trust in every SSH connection.** First the *server* proves itself — host key shown on first connect, TOFU'd into `~/.ssh/known_hosts` (on a real box you'd verify the fingerprint against the provider's console before typing yes). Then *you* prove yourself — challenge/response against `authorized_keys`; the private key never travels.
- **The host key is born at image build** (apt installing openssh-server generates it) → `down`/`up` = same identity, silent connect; a *rebuild* that reruns the apt layer = new identity → `REMOTE HOST IDENTIFICATION HAS CHANGED`. Two readings: MITM on a real server, expected after your own rebuild. Fix: `ssh-keygen -R "[localhost]:9022"`.
- **Image size sanity check:** 242MB disk / 53MB compressed — slim Debian + openssh/sudo/curl/vim/iproute2 deps. Fine: this image is meant to feel like a server, not be minimal.
- **stop ≠ delete.** Files survive stop/start with NO volume because the container's writable layer (Lab 1's transparent sheet) persists as long as the *container* exists; only `rm`/`down` scrap it. `docker diff vps-lab` lists every A/C/D vs the image.
- **`docker up`/`docker down` don't exist** — up/down are compose-only verbs. And compose has BOTH pairs: `up`/`down` = create/destroy, `stop`/`start` = power off/on. Didn't realize they were separate things for 6 years.
- **`up` is declarative, `start` is imperative.** `up -d` = "make reality match the file" — creates, starts, recreates only what changed, or does nothing; always safe. `start` boots the *old* config even if the file changed. Same mindset as `kubectl apply` and `terraform apply` later — compose is the training wheels.
- **Env vars are stamped at container CREATION.** stop/start — and even `docker compose restart` — keep the old `.env` values; only `up -d` recreates on a config diff. Verify what a running container really has: `docker inspect vps-lab --format '{{.Config.Env}}'`.
- **PATH anatomy** (the one env var debian ships): six dirs = {`/usr/local`, `/usr`, `/`} × {`bin`, `sbin`}. `sbin` = admin/system tools (why commands "don't exist" for normal users), `/usr/local` = hand-installed software apt never touches — listed first so it wins. Order = priority, left to right; modern Debian symlinks `/bin` → `/usr/bin`. Lab 3's `ENV PATH` venv trick is this exact mechanism: prepend a folder so *your* python wins.

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
