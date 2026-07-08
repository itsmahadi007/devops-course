# Lab 2 — Containerize the capstone (the naive way)

**Goal:** put `capstone/` in a container the way most tutorials do — then *measure* why it's bad. You'll build this image wrong on purpose. Feeling the pain here is the setup for Lab 3, where you fix it.

## The mental map (read this first)

`docker build` does three things, in order:

```
1. SEND        your folder ("build context") is copied to the builder
2. EXECUTE     each Dockerfile line runs, top to bottom
3. STACK       each RUN/COPY line becomes one layer (Lab 1!)
```

And one rule explains everything you'll measure today — **the cache rule**:

> Before running a line, Docker asks: *"Did this line, or the files it uses, change since last build?"*
> No → reuse the old layer (instant, shows `CACHED`).
> Yes → run it for real — **and every line below it too**, cached or not.

Think of the Dockerfile as a ladder: break one rung, and every rung *above* it has to be rebuilt. So the order of lines is not style — it decides how slow every future build is.

## Steps

### 1. Sanity-check the app outside Docker first

Never debug two things at once. Prove the app itself works before wrapping it:

```bash
cd capstone
uv sync && uv run uvicorn app.main:app &
sleep 2 && curl -s localhost:8000/health
kill %1
```

Expect `{"status":"ok"}`. Now anything that breaks later is a Docker problem, not an app problem.

Two traps if this misbehaves (both are mini-lessons):

- **Empty curl output** → the server goes to the background but takes a moment to boot; curl without the `sleep` races it and loses ("started" ≠ "ready" — the exact problem healthchecks solve in Labs 3–4).
- **`[Errno 48] address already in use`** → a stray server from an earlier attempt still holds port 8000. Free it: `lsof -ti :8000 | xargs kill`. On a host, only one process can own a port — containers fix this by giving each its own network namespace.

### 2. Write the naive Dockerfile

Create `capstone/Dockerfile.naive` by hand (type it, don't paste — it's 5 lines):

```dockerfile
FROM python:3.14
WORKDIR /app
COPY . .
RUN pip install .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Read it with Lab 1 eyes: `FROM`/`COPY`/`RUN` make real layers; `WORKDIR`/`CMD` are 0B config notes.

#### The CMD line, behind the scenes

**When does CMD run? Not now.** `RUN` executes *during the build* (that's why it makes a layer — it changes files). `CMD` executes *nothing* during the build. It's just a note written into the image's config JSON: *"when someone runs this image, start this command."* That's why it's 0B — building the image doesn't start your server; `docker run` does, later, by reading that note and launching the command **as PID 1**.

**Why the brackets matter.** There are two ways to write CMD, and they produce different PID 1s:

```dockerfile
CMD uvicorn app.main:app ...              # shell form  → Docker wraps it: /bin/sh -c "uvicorn ..."
CMD ["uvicorn", "app.main:app", ...]      # exec form   → Docker runs uvicorn directly, no shell
```

Run `ps aux` inside each and the difference is visible:

```
shell form:                          exec form:
PID 1: /bin/sh -c "uvicorn ..."      PID 1: uvicorn ...   ← your app IS PID 1
PID 7:   uvicorn ...
```

You know from Lab 1 why the left one is a trap: `docker stop` knocks on PID 1, the shell doesn't pass the message to its child, uvicorn never hears SIGTERM → 10-second hang → SIGKILL → `Exited (137)`. With exec form, uvicorn is PID 1 itself, hears the knock, and shuts down gracefully — you literally watched it do this in step 1 (`exit 143` = clean SIGTERM shutdown). **Rule: always brackets.**

**Why `--host 0.0.0.0`.** Step 1 showed uvicorn's default bind: `127.0.0.1`, meaning "accept connections from this machine only." But the container is "a machine" of its own (its own network namespace) — traffic arriving through `-p 8000:8000` comes from *outside* it, so a `127.0.0.1` bind refuses it. Result: app runs fine, port is published, every request fails. `0.0.0.0` = "accept from any interface," which lets the `-p` traffic in.

### 3. Build it and weigh it

```bash
docker build -f Dockerfile.naive -t capstone:naive .
docker images capstone:naive
```

That final `.` is the build context — "send *this folder* to the builder."

Look at the size. **~1 GB+ to run a 3-file FastAPI app.** This image commits three sins:

| Sin | What it costs |
|---|---|
| **Fat base** — `python:3.14` is a full Debian with compilers, git, headers | ~1 GB of stuff your app never uses; bigger pulls, bigger attack surface |
| **`COPY . .` before installing** — code and deps glued into one cache step | every code change re-installs all dependencies (you'll prove this next) |
| **No `.dockerignore`** — `.venv/`, `.git/`, caches all got sent to the builder | slow context upload, and junk can leak into the image |

### 4. Prove the cache sin

First, a subtlety worth knowing: Docker's cache compares **file contents (checksums), not timestamps**. So `touch app/main.py` changes nothing Docker cares about — try it and the build may come back fully `CACHED`. To break the cache honestly, make a *real* one-character change:

```bash
echo "# pretend code change" >> app/main.py
time docker build -f Dockerfile.naive -t capstone:naive .
```

One comment line added — yet watch `pip install` run again from scratch.

Why, in ladder terms: `COPY . .` copies **everything**, so any content change in any file breaks that rung → every rung above it reruns, including the expensive install. Your dependencies didn't change; your code did — but the naive Dockerfile can't tell the difference, because one `COPY` line mixed them together.

(Undo the pretend change after: delete the comment line from the bottom of `app/main.py`, or `git checkout app/main.py`.)

Now imagine this in CI on every commit: minutes of reinstalling identical dependencies, hundreds of times a week. **The fix (Lab 3) is simply order: copy the dependency files alone, install, *then* copy the code.** Then a code change only breaks the cheap top rungs.

### 5. Stop shipping junk — `.dockerignore`

`COPY . .` sent your whole folder — including `.venv/` (hundreds of MB of Mac-built packages, useless inside Linux) and `.git/`. Create `capstone/.dockerignore`:

```
.venv/
__pycache__/
*.pyc
.git/
Dockerfile*
```

Same idea as `.gitignore`, but for the build context: what never gets sent to the builder. Rebuild and compare the `transferring context` size in the build output — before vs after.

### 6. Run and test

```bash
docker run -d --name capstone-naive -p 8000:8000 capstone:naive
curl -s "localhost:8000/ask?q=hello"
```

Ugly image, but it works — that's exactly the trap: naive Dockerfiles *work*, so nobody fixes them until builds are slow and pulls are huge.

## Verify

You can answer, out loud, without looking:

- What is the "build context," and what does `.dockerignore` actually control?

  <details><summary>Answer (read after attempting aloud)</summary>

  The build context is the folder you point `docker build` at (the trailing `.`) — it gets **sent to the builder** before any instruction runs, and it's the only thing `COPY` can copy from. `.dockerignore` controls what's excluded from that send: less to upload, and no junk (`.venv/`, `.git/`) available for a careless `COPY . .` to drag into the image.

  </details>

- State the cache rule. Does `touch app/main.py` break the cache? Does editing one comment in it?

  <details><summary>Answer (read after attempting aloud)</summary>

  Docker reuses a layer only if the instruction and the files it uses are unchanged — and once one layer rebuilds, **everything after it rebuilds too** (the ladder). "Unchanged" is judged by **content checksum, not timestamp** — so `touch` (same bytes) is a cache hit, but a one-character edit busts it. `COPY . .` includes `app/main.py`, so the edit broke that rung; `RUN pip install .` sits above it and re-ran even though no dependency changed. Fix = ordering: copy dependency files alone → install → then copy code.

  </details>

- The naive image is ~1 GB. Name its three sins and what each costs.

  <details><summary>Answer (read after attempting aloud)</summary>

  1. **Fat base** (`python:3.14` = full Debian + compilers): ~1 GB you never use, slower pulls, more CVEs to patch. 2. **`COPY . .` before install**: code and deps share one cache rung → every code change reinstalls everything. 3. **No `.dockerignore`**: whole folder (`.venv/`, `.git/`) shipped to the builder — slow and leaky.

  </details>

- Why `--host 0.0.0.0` in CMD? What breaks with `127.0.0.1`?

  <details><summary>Answer (read after attempting aloud)</summary>

  The container has its own network namespace. `127.0.0.1` means "accept connections from inside this container only" — traffic arriving through `-p 8000:8000` comes from *outside* the container, gets refused, and your curl fails even though the app is running. `0.0.0.0` = listen on all the container's interfaces. (Classic symptom: image runs, port is published, `curl` says connection reset.)

  </details>

## Clean up

```bash
docker rm -f capstone-naive
```

**Keep the `capstone:naive` image** — Lab 3 needs it as the "before" in the before/after comparison. Commit `Dockerfile.naive` and `.dockerignore`.
