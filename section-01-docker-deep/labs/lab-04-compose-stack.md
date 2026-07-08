# Lab 4 — Compose stack: capstone + Redis + Postgres

**Goal:** run a multi-service stack with one command — service DNS, healthcheck-gated startup, persistent volumes. This is the shape of every real backend you'll operate.

## The mental map (read this first)

Until now, one container = one `docker run` command. But a real backend is never one container — it's at least API + cache + database. Running that by hand means three terminals, three long commands, wiring the network yourself, and remembering the start order every time. Nobody does that.

**Compose = one YAML file that describes the whole stack, and one command that makes reality match the file.** You *declare* what you want (three services, one network, one volume, this start order) and Docker does the doing. You never script the steps — you describe the end state. Hold onto that idea: it's the exact same philosophy as Kubernetes later; compose is the training-wheels version.

Three new ideas carry this lab:

1. **Service DNS.** Compose puts every service on a private network that has a built-in phonebook: **the service name IS the hostname**. The API connects to `redis:6379` — the *word* `redis`, no IP address anywhere. Like an office intercom: you dial a name, the switchboard finds the room.
2. **Healthcheck-gated startup.** `depends_on` with `condition: service_healthy` means "don't start me until they *answer*, not merely exist." That's Lab 3's healthcheck ("started ≠ ready"), finally getting its payoff.
3. **Named volumes.** Data that must outlive containers goes into a Docker-managed parking spot outside the container's throwaway writable layer (Lab 1's `/tmp/i-will-die` lesson). Postgres gets one. Redis deliberately doesn't — step 4 makes you *feel* that difference.

The stack you're about to build:

```
 your Mac (the host)
      │  only ONE door is published
      ▼
 localhost:9000
      │
┌─────┼─────────── compose network "capstone_default" ──────────┐
│     ▼                (private hallway + phonebook)            │
│  ┌────────┐  redis://redis:6379  ┌────────┐                   │
│  │  api   │ ────────────────────▶│ redis  │ no ports: →       │
│  │ :8000  │                      │ :6379  │ host can't reach  │
│  └────────┘──────┐               └────────┘                   │
│                  │ db:5432                                    │
│                  ▼                                            │
│             ┌────────┐                                        │
│             │   db   │ no ports: → host can't reach           │
│             │ :5432  │                                        │
│             └───┬────┘                                        │
└─────────────────┼─────────────────────────────────────────────┘
                  ▼
           pgdata (named volume — survives `down`)
```

## Steps

### 1. Write `capstone/docker-compose.yml`

The comments explain each line — read them as you type/paste:

```yaml
services:            # each entry = one container Docker will run and babysit

  api:               # ── your capstone, built from the Lab 3 Dockerfile ──
    build: .         # "don't pull an image — build one from the Dockerfile in this folder"
    ports:
      - "9000:8000"  # host:container — ONLY the api gets a door to your Mac
    environment:     # env vars injected at start — config lives here, not baked into the image
      REDIS_URL: redis://redis:6379/0   # hostname "redis" = the service below (compose DNS)
    depends_on:      # start order: bring these up first, and…
      redis:
        condition: service_healthy      # …wait until redis ANSWERS, not merely exists
      db:
        condition: service_healthy

  redis:             # ── the cache; this name doubles as its DNS hostname ──
    image: redis:8-alpine       # pulled, not built — and no ports: → invisible to the host
    healthcheck:                # the redis image ships no healthcheck, so we add one here
      test: ["CMD", "redis-cli", "ping"]   # exec form; redis answers PONG when actually ready
      interval: 5s   # probe every 5 seconds
      timeout: 3s    # a probe that hangs longer than 3s counts as a fail
      retries: 5     # 5 consecutive fails → status flips to unhealthy

  db:                # ── the database; hostname "db" on the network ──
    image: postgres:18-alpine
    environment:
      POSTGRES_PASSWORD: localdev   # local lab only — never a real secret
    volumes:
      - pgdata:/var/lib/postgresql   # 18+ rule: mount HERE, not .../data — see the trap below
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]   # CMD-SHELL = run through a shell (see below)
      interval: 5s
      timeout: 3s
      retries: 5

volumes:
  pgdata:            # declare the named volume — Docker creates and owns it; it outlives containers
```

#### Read it like a story

- **`services:`** — the cast list. Each service is a *recipe* for a container; `up` turns recipes into running containers.
- **`build: .` vs `image:`** — the api is *yours* (built from the Lab 3 Dockerfile right there), Redis/Postgres are *rented* (pulled from the registry). A stack almost always mixes both.
- **`REDIS_URL` uses the hostname `redis`** — the service name is a DNS name on the compose network. The app reads its config from the environment, so the *same image* works on your Mac, in CI, and in prod — only the env changes. (That's "12-factor config", an interview phrase worth owning.)
- **`depends_on … service_healthy`** — without the `condition`, `depends_on` only orders the *starts* ("launch redis first"), which re-creates Lab 2's curl-vs-uvicorn race at stack level. With it, the api container isn't even created until both probes pass. One catch worth knowing: this gate exists **only at startup** — if Redis dies later, the api keeps running and must handle it (K8s handles that part better; Section 4).
- **`"9000:8000"`** — Lab 3's port lesson applied: left = your Mac (the 8000-series belongs to your real cashlessai stack, its gateway sits on exactly 8000 — labs use the 9000-series), right = inside the container, where the app still binds 8000. The image never needs to know about the remap.
- **Redis and Postgres get no `ports:` at all** — the api reaches them by service DNS *inside* the network, so they never touch a host port (your real Redis on 6379 stays undisturbed). Same "EXPOSEd-but-unpublished" pattern you spotted in `docker ps` — but here they're not even exposed to the host, only to neighbors on the compose network. Fewer doors = smaller attack surface.
- **`CMD` vs `CMD-SHELL` in healthchecks** — `["CMD", ...]` = exec form, runs the binary directly (Lab 2's bracket rule). `CMD-SHELL` = wrap it in `sh -c`. For *healthchecks* shell form is harmless — no PID 1, no signals involved; it's just convenient when you need shell features. `pg_isready` is Postgres's official "are you accepting connections?" tool.
- **Why healthchecks here but not on api?** The api already has one **baked into its image** (Lab 3's `HEALTHCHECK` line). Redis/Postgres images ship none, so compose supplies them. Both sources feed the same status you'll see in `docker compose ps`.
- **`volumes:` (bottom-level)** — declares `pgdata` as a *named volume*: a chunk of disk Docker manages, completely separate from any container's writable layer. The container mounts it at `/var/lib/postgresql` and Postgres keeps everything in a subfolder inside it. Container destroyed → volume untouched. This is the fix for Lab 1's "writes die with the container".

#### Trap (hit live): postgres 18 moved its data directory

Every tutorial on the internet mounts the volume at `/var/lib/postgresql/data` — and with `postgres:18` that now **kills the container at startup, exit 1**, with a long lecture in the logs. What changed: for years the image kept data directly in `.../data`; version 18 reorganized to a *version-numbered* subfolder (`/var/lib/postgresql/18/docker`) so a future major upgrade can hold both versions' data side by side under one mount and run `pg_upgrade` across them. The official 18+ rule: **mount one level up, at `/var/lib/postgresql`**, and let Postgres manage subfolders.

The entrypoint sees a mount at the legacy path, assumes "old data / old-style config," and *refuses to guess* — deliberate `exit 1` with an explanation instead of silently initializing somewhere else. Same "loud failure > silent drift" principle as `--frozen` in Lab 3. Diagnostic chain worth keeping: `exited (1)` in compose output → `docker logs capstone-db-1` → read the actual reason. And notice the cascade: db failed → api stayed at `Created`, never started — `depends_on` refusing to launch on a dead dependency.

### 2. Bring it up and test the wiring

```bash
cd capstone
docker compose up -d --build
```

What you'll see, in order — this *is* the mental map executing:

```
 docker compose up -d --build
   │
   ├─ 1. build the api image (your Lab 3 Dockerfile — mostly CACHED)
   ├─ 2. Network capstone_default   Created   ← the private hallway
   ├─ 3. Volume  capstone_pgdata    Created   ← the parking spot
   ├─ 4. redis + db start together ── probes run every 5s ──▶ Healthy
   └─ 5. api starts ONLY after both report healthy
```

Names are prefixed with the **project name** = the folder name (`capstone`) — that's why it's `capstone_default` and `capstone_pgdata`, and containers come out as `capstone-api-1` etc. Watch the ordering live: redis and db lines say `Started` then `Healthy`; the api line says `Waiting` until both flip, then starts. That pause IS `service_healthy` working.

```bash
docker compose ps                    # all three services — STATUS should say Up ... (healthy)
curl -s localhost:9000/visits        # {"visits": 1}
curl -s localhost:9000/visits        # {"visits": 2} — the api really is talking to Redis by name
```

`docker compose ps` = `docker ps` scoped to this project. All three should show `(healthy)` — redis/db from the compose healthchecks, api from the one baked into its image in Lab 3.

### 3. Prove service DNS from inside

```bash
docker compose exec api python -c "import socket; print(socket.gethostbyname('redis'), socket.gethostbyname('db'))"
```

This asks, from *inside* the api container: "phonebook, who is `redis`? who is `db`?" — expect two private IPs like `172.18.0.2 172.18.0.3`. Docker runs a tiny DNS server inside each network (at `127.0.0.11` in every container) that maps service names → current container IPs. That indirection is the whole point: containers get fresh IPs on every recreate, but the *name* always resolves to the right one. Nobody hardcodes container IPs, ever.

```bash
docker compose exec db psql -U postgres -c 'SELECT version();'
```

Same `exec` trick as Lab 1 (inject a process into the running container — not SSH), just compose-flavored: service name instead of container name. This one drops you into Postgres's own client to prove the db is alive and queryable.

### 4. Prove volume persistence

Now the stateful-vs-stateless punchline. Create data in both stores, destroy everything, bring it back:

```bash
docker compose exec db psql -U postgres -c 'CREATE TABLE survivors(id int);'   # data in Postgres → lands in the pgdata VOLUME
docker compose down                  # containers + network DESTROYED — but no -v, so volumes stay
docker compose up -d                 # fresh containers, new IDs, empty writable layers
docker compose exec db psql -U postgres -c '\dt'   # survivors is STILL THERE
curl -s localhost:9000/visits        # {"visits": 1} — counter reset!
```

What just happened, per store:

- **Postgres kept the table** — its data lives in the `pgdata` volume, which `down` doesn't touch. The new container simply re-mounted the same parking spot and found everything where the old one left it.
- **Redis lost the counter** — it had no volume, so its data lived in the container's writable layer, which died with the container (Lab 1's `rm`/`run` = destroy/recreate, at stack scale).

Sit with that difference for a second — it's the whole **stateful vs stateless** conversation. For a cache, losing data on restart is *fine, even correct* (it refills). For a database it would be a career-ending incident. That's why `pgdata` exists and Redis gets nothing: persistence is a *decision you make per service*, not a default.

### 5. Read the logs like an operator

```bash
docker compose logs -f --tail 20 api
```

`--tail 20` = last 20 lines, `-f` = follow live (Ctrl-C stops following, doesn't touch the container). Drop the service name (`docker compose logs -f`) and you get **all services interleaved with color-coded prefixes** — that's the view you'll use when something breaks and you don't yet know *which* service did it. Same engine-captured stdout/stderr from Lab 1, aggregated across the stack.

#### Slicing logs by time, service, and pattern

The tail is just the beginning. The questions you actually ask during an incident, and the flag for each:

```bash
docker compose logs -t api                # -t = engine-stamped timestamp on every line
docker compose logs --since 10m           # only the last 10 minutes, all services
docker compose logs --since 2026-07-08T14:00:00 --until 2026-07-08T14:05:00 db
docker compose logs -f api db             # follow a SUBSET (skip the noisy one)
docker compose logs --no-log-prefix api | grep -i error   # clean lines for grep/jq
```

- **`-t`** — the *engine's* arrival timestamp, not the app's. When correlating across services ("did the api error before or after the db hiccup?"), trust these: one clock for everything, present even if an app logs without timestamps.
- **`--since` / `--until`** — incident-window slicing. "Show me 14:00–14:05" is the single most common question in a postmortem.
- **naming several services** — follow just the suspects, mute the rest.
- **`--no-log-prefix`** — strips the `capstone-api-1  |` prefix so pipes into `grep`/`jq` see raw lines.

#### Where a log line actually lives

Every line PID 1 prints gets appended by the engine to a JSON file on disk — that's the default `json-file` **logging driver**:

```bash
docker inspect --format '{{.LogPath}}' capstone-api-1
```

You'll get a path like `/var/lib/docker/containers/<id>/<id>-json.log` (on Docker Desktop it's inside the Linux VM, not your Mac's filesystem). Each log line is stored as a tiny JSON object — `{"log":"...","stream":"stdout","time":"..."}`. `docker logs` and `docker compose logs` are just readers of this file. No magic anywhere in the pipeline: stdout → engine → JSON file → your terminal.

The ops concern hiding here: **by default that file grows forever.** A chatty service plus months of uptime = full disk = *every* container on the host starts failing. Classic self-inflicted outage. Production caps it — and so do we. Add this to the **api service** in `docker-compose.yml` (same indent level as `build:` / `ports:`):

```yaml
    logging:         # cap the on-disk log file so it can never fill the disk
      driver: json-file
      options:
        max-size: "10m"   # rotate the file at 10MB
        max-file: "3"     # keep max 3 rotated files → hard 30MB cap for this container
```

Two details: it's **per-service, not global** (production would cap all three — or use a shared `x-logging: &logging` anchor to avoid repetition), and **the quotes matter** — unquoted `3` would be a YAML integer, and the driver wants strings.

Now apply and verify:

```bash
docker compose up -d      # only api says "Recreated" — redis/db stay Running
docker inspect --format '{{json .HostConfig.LogConfig}}' capstone-api-1
# → {"Type":"json-file","Config":{"max-file":"3","max-size":"10m"}}
```

Two lessons inside that tiny `up -d`:

- Log config is **container-creation-time** config (like port mappings — it lives in the container's settings, not the image). So compose can't edit the running api; it recreates it. And it touches *only* api: compose diffs the file against reality and reconciles just what drifted. That reconcile loop is the core idea you'll meet again as Kubernetes' whole personality.
- Recreating the container **destroyed its old JSON log file** — run `docker compose logs api` right after and it's nearly empty. Which is the perfect segue:

#### Logs die with `down` — the operator's dilemma

Lab 1 taught: logs survive `stop`, die with `rm`. Now connect it: **`docker compose down` IS an `rm` of every container** — so your step-4 down/up cycle silently destroyed the first boot's logs. The postgres-18 error lecture from the failed first run? Gone. If that failure had happened at 3am in production and someone ran `down` before reading the logs, the evidence would be deleted.

That's the fundamental limit of container-local logs, and the reason real systems *ship* logs out to a central store as they happen (Grafana Loki, CloudWatch, ELK — via logging drivers or agent sidecars). Section 8 (observability) builds exactly that. Until then, the instinct to keep: **if a container might get removed, its logs are already on borrowed time.**

## Verify

- One command (`docker compose up -d --build`) brings up all three services healthy — and you saw api *wait* for the other two.
- `/visits` increments; the Postgres table survives `down`+`up`; you can explain why Redis's counter didn't.
- You can explain, out loud: why `REDIS_URL` contains the word `redis` and no IP; why only api has `ports:`; why the api starts last.

## Clean up

```bash
docker compose down -v   # -v ALSO removes named volumes — the survivors table dies now. Full reset.
```

Plain `down` = containers + network gone, volumes kept (safe daily habit). `down -v` = everything including data (deliberate act). That split is exactly why step 4 worked.

Commit `docker-compose.yml`. Update the capstone evolution log.
