# Lab 3 — Multi-stage, slim, non-root, healthy

**Goal:** fix every sin you measured in Lab 2 and end up with *the* production-grade Python image — multi-stage with uv, slim base, correct cache order, non-root user, healthcheck. This exact Dockerfile pattern is reusable for every Python service you'll ever ship.

## The mental map (read this first)

The big new idea is the **multi-stage build**: one Dockerfile, two `FROM` lines, two separate images built in sequence — and **only the last one ships**.

Think kitchen vs dining room. Cooking needs a messy kitchen: knives, flour everywhere, the oven (= uv, compilers, build caches). But you don't serve dinner in the kitchen — you carry the finished dish to a clean dining room. Multi-stage is exactly that:

```
 STAGE 1: "builder" (the kitchen)             STAGE 2 (the dining room)
┌──────────────────────────────────┐         ┌──────────────────────────────────┐
│ FROM python:3.14-slim AS builder │         │ FROM python:3.14-slim            │
│  + uv (copied in)                │         │  + non-root user                 │
│  + pyproject.toml, uv.lock       │  COPY   │  + /app (venv + code) ◀── only   │
│  + RUN uv sync  → builds .venv   │ ──from──▶     this crosses over            │
│  + code                          │ builder │  + HEALTHCHECK + CMD             │
└──────────────────────────────────┘         └──────────────────────────────────┘
   thrown away after the build                  ← THIS is the image you ship
```

uv, its cache, and every build-time tool stay behind in the kitchen. The shipped image contains just Python, your venv, and your code — smaller, and with far fewer packages an attacker could exploit.

The other three upgrades come straight from Lab 2's pain list:

| Lab 2 sin | Lab 3 fix |
|---|---|
| Fat base (`python:3.14`, full Debian) | `python:3.14-slim` — same Python, ~10× less OS |
| `COPY . .` before install → code change reinstalls deps | **Deps rung below, code rung above**: copy `pyproject.toml`+`uv.lock` alone → install → *then* copy code. A commit only breaks the cheap top rung. |
| Runs as root (every container so far did!) | `USER appuser` — the app runs as a nobody, not the admin |

Plus one thing Lab 2 only hinted at: **"started ≠ ready"** (remember curl losing the race against uvicorn?). `HEALTHCHECK` makes Docker itself ping the app on a schedule, so the container's status says *healthy*, not just *running*.

## Steps

### 1. Lock dependencies

```bash
cd capstone
uv lock
```

#### What a lockfile buys you

`pyproject.toml` says what you *want* ("fastapi >= 0.100"). `uv.lock` records what you actually *got* — every package, every transitive dependency, exact versions, checksums. Without it, two builds a week apart can silently install different versions ("works on my machine, broke in CI Friday"). With it, every build — your Mac today, CI next month — installs byte-identical dependencies. That's what "reproducible build" means, and it's why `uv.lock` gets committed to git.

### 2. Write the real `capstone/Dockerfile`

```dockerfile
# ---- build stage: has uv, resolves and installs deps into .venv ----
FROM python:3.14-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app

# Deps first — this layer survives code changes
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Code last — only this layer rebuilds on a commit
COPY app ./app

# ---- runtime stage: no uv, no build tools, just the venv and the code ----
FROM python:3.14-slim
RUN useradd --create-home --uid 1000 appuser
WORKDIR /app
COPY --from=builder --chown=appuser:appuser /app /app
ENV PATH="/app/.venv/bin:$PATH"
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Read it line by line — every line has a *reason* you could defend in review. Here they are:

#### Build stage, line by line

- **`FROM python:3.14-slim AS builder`** — `slim` = same Python, but Debian stripped of compilers, git, man pages (~1 GB → ~120 MB). `AS builder` just names this stage so later lines can refer to it.
- **`COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/`** — `COPY --from` can pull files out of *another image*, not just your build context. This grabs the uv binary from uv's official image — no `pip install uv`, no curl-a-script. Unpacked fully in the subsection below.
- **`COPY pyproject.toml uv.lock ./` then `RUN uv sync`** — the ladder fix, finally applied. These two rungs only break when *dependencies* change (rare). Code changes live on a higher rung, so the expensive install stays `CACHED` on every ordinary commit. This is the direct answer to Lab 2 step 4.
- **`--frozen`** — "install exactly what `uv.lock` says; if `pyproject.toml` and the lockfile disagree, **fail the build**." Without it, uv would quietly re-resolve — and there goes your reproducibility. Loud failure > silent drift.
- **`--no-dev`** — pytest and friends have no business in a production image.
- **`COPY app ./app`** — code last, top of the ladder. Note it copies *only* `app/`, not `.` — even with a `.dockerignore`, being explicit means a stray file in the folder can never ride along.

#### `COPY --from` = lifting files off a neighbor's shelf

The uv line is *not* "download an installer and run it" — it copies two finished files out of *another Docker image*:

- `ghcr.io/astral-sh/uv:latest` — uv's official image on GitHub Container Registry. A normal image, pulled exactly like `docker pull` in Lab 1 (layers, `Already exists` caching, all of it).
- `/uv /uvx` — inside that image sit two pre-compiled binaries. uv is written in Rust, so it's a single self-contained file — no Python needed to run it, nothing to install.
- `/bin/` — where they land in *your* builder stage, so `uv` is on PATH.

The mental model is **"lift two files from a neighbor's shelf"**, not "run an installer." Compare the alternatives:

```dockerfile
RUN pip install uv                      # runs pip, adds uv + pip cache into a layer
RUN curl -sSf https://... | sh          # downloads and EXECUTES a script from the web
COPY --from=ghcr.io/astral-sh/uv ...    # copies 2 files. Nothing executes.
```

The `COPY --from` version wins because nothing runs during the copy (no script to trust, no pip resolution), and the layer contains exactly two files.

Does it touch the web? First build: yes — Docker pulls that image's layers, then caches it like any pulled image. Later builds copy from the local cache. And it's the *same mechanism* as `COPY --from=builder` in stage 2: `--from` can name a stage you defined or any registry image — either way, "copy from that other filesystem instead of my build context."

One real caveat: `:latest` is a mutable tag (Lab 2 — tags are moving pointers), so builds a month apart could get different uv versions. Stricter setups pin a version, e.g. `ghcr.io/astral-sh/uv:0.9` — worth remembering for interviews.

#### Runtime stage, line by line

- **Second `FROM python:3.14-slim`** — fresh, empty dining room. Nothing from the builder exists here until you copy it in. uv is gone; there isn't even a package installer a malicious payload could use.
- **`RUN useradd --create-home --uid 1000 appuser`** — creates a regular user. Why bother? Every container you've run so far ran as **root**. Container root is not full host root, but it's one kernel bug away from it — container escape as root = game over on the host. As `appuser`, an attacker who gets code execution inside your app lands in an account that can't install packages, can't write outside `/app`, can't do much of anything. Interviewers love this question. (What the `1000` is → subsection below.)
- **`COPY --from=builder --chown=appuser:appuser /app /app`** — the handoff: the whole `/app` (venv + code) crosses from kitchen to dining room in one layer. `--chown` sets the owner during the copy — by default COPY writes files as root, and then `appuser` wouldn't own its own app (the ownership story is unpacked in the subsection below). The venv works unmodified because both stages share the same base image and the same `/app` path — a venv is only portable if the Python underneath and the absolute path both match.
- **`ENV PATH="/app/.venv/bin:$PATH"`** — the "activation" trick. You never `source .venv/bin/activate` in a Dockerfile — activation *is* just putting the venv's `bin/` first on PATH, so this line does the same thing permanently. Now `uvicorn` and `python` mean the venv's copies.
- **`USER appuser`** — everything after this line (including CMD at runtime) runs as appuser, not root. Placed *after* the COPY/useradd lines, which still need root.
- **`EXPOSE 8000`** — pure documentation, a 0B config note (like CMD in Lab 2). It does **not** publish the port — `-p 8000:8000` at run time does. It tells humans and tools which port the app expects.
- **`HEALTHCHECK ...`** — explained in step 5, where you'll watch it live.
- **`CMD [...]`** — exec form (brackets → uvicorn IS PID 1, hears SIGTERM), `--host 0.0.0.0` (accept traffic from outside the netns). Both are Lab 2 scar tissue.

#### UID 1000 — the number behind the name

`1000` is the **user ID (UID)** — the number Linux actually uses to identify a user. The name is just a label for humans. The kernel never thinks in names: every file's "name tag" (next subsection) is really stored as a *number*; the name→number mapping lives in `/etc/passwd`, and tools like `ls -l` translate back for display. When appuser tries to write a file, the kernel checks "does UID 1000 own this?" — the string "appuser" is never consulted.

Why 1000 specifically? Convention, baked into Debian/Ubuntu:

```
UID 0          root — the "skip all permission checks" account
UID 1–999     system accounts (daemons: www-data, postgres, ...)
UID 1000+     regular human/app users — 1000 is "the first normal user"
```

(Your account on any Linux box is almost certainly 1000. On your Mac it's 501 — macOS starts its range there, same idea.)

Why pin it explicitly instead of letting `useradd` pick? Because **ownership is stored by number, not name** — the number is what must match across boundaries:

- **Volumes (Lab 4):** files a container writes into a mounted volume are owned by UID 1000 *as a number*. Another container reading that volume sees the number; permissions only line up if its user has the same UID. Pinning makes this predictable.
- **Kubernetes (Section 4):** security policies say `runAsUser: 1000` — numbers, never names. Images with a fixed, non-zero UID slot straight into that.
- **Reproducibility:** without `--uid`, `useradd` picks "next free number" — usually 1000 anyway, but "usually" isn't a contract. Pinning makes it one.

So the line reads: "create a regular (non-system) user, name it appuser for humans, and pin its real identity to the conventional first-user number 1000."

#### Owner vs permissions — why `--chown`, and why root doesn't need it

One piece of Linux you've never had to care about as a backend dev: **every file carries two separate things — an owner and permission bits.**

```
-rwxr-xr-x  root  root  /app/.venv/bin/uvicorn
 │││ │  │
 │││ │  └── "others" can: read, execute (no write)
 │││ └───── group can:  read, execute
 └┴┴─────── owner can:  read, write, execute
```

Think of it as a name tag plus a rulebook: the name tag says *who owns it* (`root root`), the rulebook says *what the owner / the group / everyone else may do* (`rwx r-x r-x`).

Two questions this immediately raises:

**"How does root get permission?"** — It doesn't need any. Root is the exception to the whole system: the kernel skips permission checks for root entirely. So during the build, every RUN/COPY (running as root) can write files anywhere and stamp any owner on them. That's also exactly why we *don't* want the app running as root — the rulebook doesn't apply to it.

**"If files are owned by root, how does appuser access them?"** — Via the *"others"* column. Look at the rulebook above: `r-x` for everyone else. So even without `--chown`, appuser could read the code and execute uvicorn — the app would mostly run! What appuser could **not** do is write: no creating `__pycache__`, no writing anything under `/app`. You'd get random `PermissionError`s at runtime for anything that writes.

`--chown=appuser:appuser` swaps the name tag during the copy, so appuser is the *owner* and gets the owner column (`rwx`) — full control of its own app, and only its app. Everything else in the container (system files, `/bin`, `/etc`) stays root-owned, which is the security win: appuser owns `/app` and nothing more.

**Why in the COPY line and not a `RUN chown -R ...` after?** Layers are append-only (Lab 1). A separate `chown` "modifies" every file, so copy-on-write duplicates all of them into a new layer — the image would carry the venv **twice**. `--chown` stamps the tag while the files are being written the first time: one layer, no duplication.

Timeline of who's who, to lock it in:

```
BUILD TIME   every RUN/COPY runs as root  → can write anywhere, stamp any owner
USER appuser line                          → note in config: "from here on, be appuser"
RUN TIME     PID 1 (uvicorn) runs as appuser → rulebook now applies; owns /app only
```

#### Reading the handoff line: `appuser:appuser` and `/app /app`

Two more pieces of that COPY line worth decoding:

**`--chown=appuser:appuser` = `user:group`.** Not a transfer from one thing to another — the colon separates **two different fields** being set at once:

```
--chown = appuser : appuser
          ───────   ───────
          field 1   field 2
          WHICH USER  WHICH GROUP
          owns it     owns it
```

Every file is owned by a **user** (an account — "whose file is this?") AND a **group** (a team of users — "which team also gets special access?"). A group lets you grant access to many users at once ("the `postgres` group may read this").

The confusion: both fields here have the same name. They're two *different things* that happen to be *called the same* — a **user** named appuser (UID 1000), and a **group** named appuser (GID 1000). Same word, two separate registries — like a person named "Jordan" who also runs a company named "Jordan." Why does the group even exist? `useradd` created it automatically — Debian gives every new user a private group with the same name. This `name:name` pattern is everywhere: `www-data:www-data`, `postgres:postgres`.

It's clearer with different names — this is completely valid:

```dockerfile
--chown=appuser:staff     # owner user = appuser, owner group = staff
```

Each name feeds exactly one column of the rulebook:

```
-rwx r-x r-x    appuser  appuser
 │    │   │        │        │
 │    │   │     user field  group field
 │    │   └─ everyone else gets this
 │    └───── members of group "appuser" get this
 └────────── user "appuser" gets this
```

In our image the group column is basically unused — appuser is the only member of its group, so it's just filling a required field with the obvious value. The real work is done by the first field: user appuser owns `/app`.

**`/app /app` = source → destination**, nothing to do with chown. Same shape as every COPY: `COPY <from-here> <to-here>`. First `/app` = the folder inside the **builder stage** (where uv built the venv), second `/app` = where it lands in **this stage**. They match on purpose — the venv only works at the same absolute path (its scripts have `/app/.venv/bin/python` hard-wired inside them).

The whole line, read aloud: *"From the builder stage, copy its `/app` folder to my `/app`, and stamp every file's name tag as user appuser, group appuser while writing."*

### 3. Build and compare

```bash
docker build -t capstone:0.1.0 .
docker images | grep capstone
```

No `-f` flag this time — `Dockerfile` is the default name. Watch the build output: you'll see the two stages run in sequence (the step numbers restart at the second `FROM`).

Put `capstone:0.1.0` next to `capstone:naive` — expect roughly **5–6× smaller**. Same app, same functionality; the difference is purely what you *didn't* ship.

Optional deeper look: `brew install dive && dive capstone:0.1.0` — an x-ray that shows each layer's files, so you can see with your own eyes that uv is nowhere in the final image.

### 4. Prove the cache order is fixed

This is Lab 2 step 4's experiment, re-run against the fixed ladder. Remember the checksum subtlety: `touch` alone may not bust anything — make a real edit if you want to see a genuine rebuild:

```bash
echo "# pretend code change" >> app/main.py
time docker build -t capstone:0.1.0 .
```

Read the output carefully: `COPY pyproject.toml uv.lock` → `CACHED`. `RUN uv sync` → `CACHED`. Only `COPY app ./app` and below re-ran. **The code change broke a top rung, and the expensive install lives below it now.** In Lab 2 this same one-character edit re-installed everything; that's the entire before/after of this section, in one build log.

(Undo the pretend change: delete the comment line, or `git checkout app/main.py` — then rebuild once so the image doesn't ship your test comment.)

#### Flow map — what reruns, what stays cached

The whole Dockerfile as two ladders joined by the handoff — marks show a build where only `app/main.py` was edited:

```
BUILDER LADDER                                   RUNTIME LADDER (stage-1)

FROM python:3.14-slim AS builder   ✅ cached      FROM python:3.14-slim              ✅ cached
COPY --from=uv /uv /uvx /bin/      ✅ CACHED      RUN useradd ... appuser            ✅ CACHED
WORKDIR /app                       ✅ CACHED      WORKDIR /app                       ✅ CACHED
COPY pyproject.toml uv.lock ./     ✅ CACHED      COPY --from=builder /app /app      🔴 RERUN ◀─┐
RUN uv sync --frozen --no-dev      ✅ CACHED      ENV PATH=...                       ─ 0B note  │
COPY app ./app                     🔴 RERUN ──── its output (/app) changed ──────────────────────┘
        ▲                                        USER appuser                       ─ 0B note
        │                                        EXPOSE 8000                        ─ 0B note
   you edited app/main.py                        HEALTHCHECK ...                    ─ 0B note
   → this rung breaks                            CMD [...]                          ─ 0B note
   → nothing sits above it
     in THIS ladder
```

How to read it:

- **Each stage is its own ladder.** The break-everything-above rule applies per stage. In the builder, the edit broke the *top* rung — nothing above it existed to rerun. `uv sync` sits *below* the break → safe.
- **The only bridge between ladders is `COPY --from=builder`.** Its input is the builder's finished `/app`. Builder's `/app` came out different (new main.py) → this rung breaks in the runtime ladder. Everything *below* it there (`useradd`, `WORKDIR`) stays cached.
- **The 0B notes never "rerun"** — `ENV`/`USER`/`EXPOSE`/`HEALTHCHECK`/`CMD` execute nothing (Labs 1–2: config-JSON entries). They're just written into the new image's config, instantly, every build.

Same map, other scenarios — where the break lands decides the bill:

| You change… | First broken rung | What reruns |
|---|---|---|
| `app/` code only | `COPY app ./app` | that copy + the handoff — **~2s** |
| `pyproject.toml` / `uv.lock` | `COPY pyproject.toml uv.lock` | **`uv sync` too** (it's above the break) + everything after |
| uv publishes new `:latest` | `COPY --from=uv` (rung 2) | entire builder ladder, incl. `uv sync` — the cost of an unpinned tag |
| the `useradd` line itself | runtime rung 2 | runtime ladder only — builder untouched |

The design goal in one sentence: **put the expensive rung (`uv sync`) below the rung that changes daily (`COPY app`)** — exactly what the naive `COPY . .` failed to do.

### 5. Run and watch the healthcheck work

```bash
docker run -d --name capstone -p 8000:8000 capstone:0.1.0
docker ps --filter name=capstone        # STATUS: (health: starting) → (healthy)
docker inspect --format '{{.State.Health.Status}}' capstone
docker exec capstone whoami             # appuser — not root
```

Run `docker ps` a few times over the first ~20 seconds and watch STATUS change from `(health: starting)` to `(healthy)`.

#### If host port 8000 is taken (`Bind for 0.0.0.0:8000 failed: port is already allocated`)

Another container (or host process) already publishes 8000 — run a bare `docker ps` and scan the PORTS column, or `lsof -ti :8000` for host processes. The two halves of `-p` are independent (`-p <host>:<container>`), so remap only the host side and keep the container side at 8000 — that's what CMD binds and EXPOSE documents:

```bash
docker rm capstone                      # the failed attempt leaves a half-created ghost holding the name
docker run -d --name capstone -p 8001:8000 capstone:0.1.0
curl -s localhost:8001/health           # host side changed…
```

…but the **healthcheck still hits `127.0.0.1:8000` and works** — it runs *inside* the container, where the app really is on 8000. One app, three addresses: `8000` inside the netns, `8001` on the host, and the healthcheck never leaves the building. No rebuild needed — the mapping is a runtime decision, which is exactly why the image hardcodes only its *own* side. (Two related `docker ps` reading skills: a container that failed to start sits in **Created** state, invisible to plain `docker ps` — use `-a`; and a port with no `0.0.0.0:` prefix in the PORTS column is merely `EXPOSE`d, not published — it burns no host port.)

#### How HEALTHCHECK actually works

Lab 2 showed you "started ≠ ready" — your curl raced uvicorn and lost. Until now, Docker's idea of container health was just "is PID 1 alive?" — which says nothing about whether the app can *answer requests*. HEALTHCHECK gives Docker a real test to run, on a schedule, decoded flag by flag:

```
--start-period=5s   grace period: failures in the first 5s don't count (app is booting)
--interval=15s      run the check every 15 seconds, forever
--timeout=3s        if one check hangs >3s, that check counts as failed
--retries=3         3 consecutive failures → status flips to "unhealthy"
```

The check command itself runs **inside** the container — which explains two choices that look odd at first:

- **Why `python -c urllib` and not `curl`?** slim images don't have curl, and installing it just for a healthcheck would fatten the image. Python is already there — use it.
- **Why `127.0.0.1` when CMD needed `0.0.0.0`?!** Opposite directions. CMD binds `0.0.0.0` so traffic from *outside* the container's network namespace can get in. The healthcheck runs *inside* that namespace — from in there, `127.0.0.1` is exactly where the app lives. Same app, two addresses, depending on which side of the wall you're standing on.

Right now "unhealthy" only changes a label you can see and inspect. The payoff comes later: Compose (Lab 4) can hold dependent services until this says healthy, and Kubernetes (Section 4) runs the same idea as liveness/readiness probes — this 4-flag line is the training wheels for that.

Also try:

```bash
docker inspect --format '{{json .State.Health}}' capstone | python3 -m json.tool
```

— Docker keeps a log of the last few check results, timestamps and output included. That's your first stop when a container ever shows `(unhealthy)`.

## Verify

- Image at least ~5× smaller than naive; `whoami` inside = `appuser`; health status reaches `healthy`.
- You can answer, out loud, without looking:

- Why deps-then-code ordering?

  <details><summary>Answer (read after attempting aloud)</summary>

  The ladder (Lab 2): breaking a rung rebuilds every rung above it. Dependencies change rarely; code changes every commit. Put the expensive `uv sync` rung *below* the code rung, keyed only to `pyproject.toml`+`uv.lock`, and an ordinary commit breaks only the cheap `COPY app` rung — the install stays `CACHED`. Wrong order (naive `COPY . .`) glues them together, so every commit pays the full install.

  </details>

- Why two stages instead of just one slim stage?

  <details><summary>Answer (read after attempting aloud)</summary>

  One slim stage would still ship the kitchen: uv itself, its download cache, and any build leftovers all become layers in the final image. Layers are append-only (Lab 1) — even `RUN rm -rf ...` afterwards doesn't shrink earlier layers. With two stages you copy across *only* the finished `/app` and throw the rest away: smaller image, and fewer tools inside for an attacker to abuse (no installer, no uv, nothing to download payloads with).

  </details>

- What does `--frozen` protect against?

  <details><summary>Answer (read after attempting aloud)</summary>

  Silent re-resolution. `--frozen` means "install exactly what `uv.lock` pins — and if `pyproject.toml` and the lockfile have drifted apart, fail the build loudly." Without it, a build could quietly resolve fresh versions, and your Mac's image and CI's image would no longer be the same. Reproducibility = the lockfile is law; `--frozen` enforces the law.

  </details>

- Why does non-root matter if it's "just a container"?

  <details><summary>Answer (read after attempting aloud)</summary>

  Container isolation is kernel-enforced, and kernels have bugs. Root inside the container + one container-escape vulnerability = root on the host. Running as `appuser` means an attacker who compromises the app lands in an account that can't install tools, can't write outside `/app`, and has nothing to escalate with — defense in depth. Also: many managed platforms (and K8s policies) simply refuse root containers.

  </details>

- Your CMD binds `0.0.0.0` but the healthcheck hits `127.0.0.1`. Contradiction?

  <details><summary>Answer (read after attempting aloud)</summary>

  No — two sides of the same wall. `0.0.0.0` in CMD is about letting traffic from *outside* the network namespace in (the `-p` traffic). The healthcheck command executes *inside* the container, where `127.0.0.1` is local and always reachable. Binding `0.0.0.0` includes loopback, so both work.

  </details>

- What do `EXPOSE` and `HEALTHCHECK` have in common with `CMD`, layer-wise?

  <details><summary>Answer (read after attempting aloud)</summary>

  All three are 0B config-JSON notes (Lab 1), not layers. They change no files at build time — they're instructions for *later*: `CMD` = what `docker run` should launch, `EXPOSE` = which port to document, `HEALTHCHECK` = what the daemon should keep running against the live container.

  </details>

## Clean up

```bash
docker rm -f capstone
docker rmi capstone:naive   # done comparing — the naive image has served its purpose
```

Commit `Dockerfile` and `uv.lock`. Update `capstone/README.md` evolution log: "Section 1: production image — multi-stage uv, non-root, healthcheck."
