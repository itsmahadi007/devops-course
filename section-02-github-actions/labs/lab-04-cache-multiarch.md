# Lab 4 — Fast builds and a multi-arch image

**Goal:** pay off the debt that has been open since Section 1 Lab 6 — the image that runs on your Mac but dies on an x86 VPS with `exec format error`. You'll make CI build the capstone for **both** amd64 and arm64 in one workflow, publish them under **one tag** (a manifest list), and add a layer cache so rebuilds go from minutes to seconds. Three actions join the build job: QEMU, Buildx, and a cache config on the step you already have.

## The mental map (read this first)

Two independent problems, solved by the same three lines.

**Problem 1 — one CPU, many architectures.** A compiled program is machine code for *one* CPU family. Your Mac's build produced arm64; `ubuntu-latest` produces amd64. A real fleet has both (Apple Silicon laptops, x86 cloud VMs, arm Graviton servers). You want *one* image name that just works on all of them.

The fix has two halves:

```
        QEMU (emulator)                          Buildx (the fat-manifest builder)
┌──────────────────────────────┐        ┌───────────────────────────────────────────┐
│ ubuntu runner is amd64.       │        │ builds the image TWICE (once per platform), │
│ QEMU pretends to be an arm64  │        │ pushes both, then writes a MANIFEST LIST:   │
│ CPU so arm64 binaries run     │  ───▶  │                                             │
│ (slowly) on it → arm64 build  │        │   capstone:sha-abc  ──┬─▶ amd64 image       │
│ possible without an arm host  │        │   (one tag, a "fat     └─▶ arm64 image       │
└──────────────────────────────┘        │    manifest") — registry serves the right   │
                                         │    one based on WHO is pulling               │
                                         └───────────────────────────────────────────┘
```

A **manifest list** (aka "fat manifest") is a tiny index: one tag pointing at *several* real images, keyed by architecture. When your Mac runs `docker pull ghcr.io/…/capstone`, the registry reads the puller's arch from the request and hands back the arm64 image; the x86 VPS asking for the same tag gets amd64. One name, no `exec format error`, ever. This is exactly what `FROM python:3.14-slim` has been doing *for* you all along — you're now on the publishing side of it.

**Problem 2 — the empty hotel room rebuilds the world.** Every runner is fresh (Lab 1). Without a cache, every build re-runs `uv sync` from scratch — and now you're doing it *twice* (two arches), the arm64 half under slow emulation. The fix is `cache-type=gha`: Buildx stashes each built layer in **GitHub's cache service** (the same warehouse `setup-uv` used in Lab 2, different shelf) and pulls them back next run. Your Section 1 cache-ladder reasoning now pays off across machines: change only `app/` code and the `uv sync` layer restores from cache instead of rebuilding — on *both* arches.

## Steps

### 1. Add QEMU and Buildx before the build step

In `.github/workflows/ci.yml`, in the `build` job, add two setup steps **between** the login step and the metadata step (order matters — the builder must exist before it builds):

```yaml
      - name: Set up QEMU (emulation for arm64 on an amd64 runner)
        uses: docker/setup-qemu-action@v4

      - name: Set up Docker Buildx (the multi-platform builder)
        uses: docker/setup-buildx-action@v4
```

Why these are separate steps, and why now:

- **`setup-qemu-action`** registers QEMU with the kernel so the amd64 runner can *execute* arm64 binaries during the build. Without it, the moment the arm64 build hits its first `RUN` (which runs arm64 code), you'd get — fittingly — `exec format error`, the very thing you're here to kill, this time inside the builder.
- **`setup-buildx-action`** swaps the runner's default Docker builder for a **BuildKit "docker-container" builder**. The plain builder can't do multi-platform or `type=gha` cache; buildx can. In Lab 3 you got away without it because you built one native arch with no cache. This step is the price of admission for both upgrades.

### 2. Upgrade the build-push step

Replace the Lab 3 `build-push-action` step with this expanded version (the `context`/`tags`/`labels` lines are unchanged — you're adding three keys):

```yaml
      - name: Build and push (amd64 + arm64, cached)
        uses: docker/build-push-action@v7
        with:
          context: capstone
          push: true
          platforms: linux/amd64,linux/arm64
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

The three new keys, decoded:

- **`platforms: linux/amd64,linux/arm64`** — build both. Buildx runs the Dockerfile twice (arm64 under QEMU), then writes the manifest list. One line turns a single-arch push into a fat-manifest push.
- **`cache-from: type=gha`** — before building a layer, check GitHub's cache service for it. Hit → restore, skip the work.
- **`cache-to: type=gha,mode=max`** — after building, push layers *into* the cache. `mode=max` caches *every* layer including intermediate builder-stage layers (not just the final image's), so your multi-stage builder's `uv sync` layer is cached too — `mode=min` (the default) would only cache the final runtime layers and you'd rebuild deps every time. For a multi-stage build, `mode=max` is what makes the cache actually bite.

### 3. Push and watch the first (cold) build

```bash
cd /Users/mahadihassan/Documents/plan/projects/devops-course
git add .github/workflows/ci.yml
git commit -m "ci: multi-arch build with buildx gha cache"
git push
gh run watch
```

**First run is slow and that's expected** — read it as evidence, not a problem:

- The arm64 build runs under QEMU emulation — CPU-bound steps like `uv sync` can take several times longer than native. A 20s native build becoming a 2–3 min emulated one is normal.
- The cache is cold: `cache-from` finds nothing, every layer builds, `cache-to` uploads them at the end (you'll see a `exporting cache` line).
- In the build log you'll see the work fan out per platform: lines tagged `[linux/amd64 ...]` and `[linux/arm64 ...]` interleaved.

### 4. Push a code-only change and watch the cache bite

Make a trivial change to *code only* (not deps), so the Section 1 cache ladder should save the expensive `uv sync` layer:

```bash
echo "# ci cache demo" >> capstone/app/main.py
git add capstone/app/main.py
git commit -m "chore: trivial change to exercise the build cache"
git push
gh run watch
```

Now read the build step: the `COPY pyproject.toml uv.lock` and `RUN uv sync` layers should report `CACHED` — restored from GitHub's cache service, on **both** arches — and only `COPY app ./app` and below rebuild. This is the Section 1 Lab 3 flow map (each stage a ladder, break the top rung, expensive rung below survives), now working *across disposable machines* because the layers live in the cache warehouse between runs. The arm64 half especially thanks you: the slow emulated `uv sync` didn't re-run.

(Undo the demo line so you don't ship a stray comment: `git checkout capstone/app/main.py` won't work after commit — instead `git revert` or just delete the line, commit, push. A clean `main.py` is what later labs assume.)

### 5. Prove it's genuinely multi-arch

```bash
docker buildx imagetools inspect ghcr.io/itsmahadi007/capstone:latest
```

Expect a **manifest list** with two entries — `linux/amd64` and `linux/arm64` — each with its own digest, under the one tag. This is the fat manifest from the mental map, printed. Compare to Section 1 Lab 6, where the same command (or a plain `docker manifest inspect`) would have shown a single arm64 entry.

Then confirm your Mac pulls the right one automatically:

```bash
docker pull ghcr.io/itsmahadi007/capstone:latest
docker image inspect ghcr.io/itsmahadi007/capstone:latest --format '{{.Architecture}}'
```

Expect `arm64` — the registry served your Mac its matching arch from the shared tag, with no arch in the pull command. **The debt is paid**: that same tag now hands an x86 VPS the amd64 image, and neither machine ever sees `exec format error`.

#### If the arm64 build times out or fails under QEMU

Emulation is slow and occasionally flaky for CPU-heavy native builds. First, confirm `setup-qemu-action` ran *before* buildx and before the build step (order in the YAML = order of execution). If a specific package fails to compile under emulation, the escape hatch is a **native arm64 runner** — but that's a Lab 5 idea (your own Mac *is* arm64), and for a pure-Python app like the capstone, QEMU handles it fine. If it's just slow, that's the emulation tax, not a bug.

#### If `cache-to` warns `Cache export is not supported` or layers never cache

You skipped `setup-buildx-action`, so the build ran on the default docker builder, which can't do `type=gha`. The buildx step is mandatory for caching *and* multi-platform — both features live in BuildKit's container driver, not the plain builder. Re-check that the buildx setup step is present and green.

#### If the cache seems to help nothing on the code-change run

Check `mode=max` is on `cache-to`. With the default `mode=min`, only final-image layers cache, so the multi-stage *builder* layers (including `uv sync`) rebuild every time and the whole point is lost. Also: the very first run after adding the cache is always cold — you need at least one prior run to have populated it.

## Verify

- `docker buildx imagetools inspect ghcr.io/itsmahadi007/capstone:latest` lists **both** `linux/amd64` and `linux/arm64`.
- A code-only push shows the `uv sync` layer `CACHED` in the build log on both arches.

Then answer aloud:

**1. The runner is amd64. How did it produce a working arm64 image, and what one line makes that possible?**

<details><summary>Answer (read after attempting aloud)</summary>

QEMU emulation. `docker/setup-qemu-action` registers QEMU with the runner's kernel so arm64 machine code can execute on the amd64 CPU (slowly). Buildx then runs the Dockerfile a second time targeting `linux/arm64`, with every `RUN` step's arm64 binaries interpreted by QEMU. Without QEMU, the first `RUN` in the arm64 build would itself fail with `exec format error` — the emulator is what turns "can't run this arch" into "can, just slower."

</details>

**2. What is a manifest list, and how does one `docker pull` get the right architecture with no arch in the command?**

<details><summary>Answer (read after attempting aloud)</summary>

A manifest list (fat manifest) is a small index under one tag that points at multiple real images, each keyed by OS/architecture. On `docker pull`, the client tells the registry its platform; the registry reads the list and returns the matching image's digest. So one name (`:latest`) resolves to the arm64 image on a Mac and the amd64 image on an x86 box — the selection happens server-side, invisibly. It's the same mechanism `FROM python:3.14-slim` has always used; now you publish it.

</details>

**3. Why `mode=max` and not the default `mode=min` for this specific image?**

<details><summary>Answer (read after attempting aloud)</summary>

The capstone is a multi-stage build: the expensive `uv sync` happens in the *builder* stage, whose layers don't appear in the final image. `mode=min` caches only final-image layers, so the builder stage — including `uv sync` — would rebuild every run, defeating the cache. `mode=max` caches all intermediate layers too, so the dependency-install layer restores across runs. For multi-stage builds, `mode=max` is the difference between a cache that helps and one that doesn't.

</details>

**4. First run took minutes, the next code-only run took seconds. Where do the reused layers physically live between two runs on two different disposable machines?**

<details><summary>Answer (read after attempting aloud)</summary>

In GitHub's cache service — the same external warehouse `setup-uv` used in Lab 2, a different scope. Runners are ephemeral (Lab 1), so nothing survives *on* the machine; `cache-to: type=gha` uploads layers there at build end and `cache-from: type=gha` restores them at the next build's start. Combined with Section 1's cache-ladder ordering (deps below code), a code-only change restores the `uv sync` layer instead of rebuilding it — on both arches.

</details>

## Clean up

Nothing to tear down. Make sure the `main.py` demo line from step 4 is reverted and pushed, and `git status` is clean. The multi-arch, cached build is now the permanent shape of the pipeline — Lab 6 deploys the image it produces. If you did the local `docker pull` in step 5, you can `docker rmi ghcr.io/itsmahadi007/capstone:latest` to reclaim the space; the registry copy is untouched.
