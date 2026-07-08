# Lab 3 — CI builds and pushes the image (GHCR)

**Goal:** stop building images on your laptop. Add a `build` job that runs *after* the test gate, builds the capstone image on a runner, and pushes it to GHCR — authenticating with the job's own short-lived `GITHUB_TOKEN`, never your personal token. Along the way: the `permissions:` block (the keycard's scopes, made concrete), and `docker/metadata-action` generating tags automatically from the git event.

## The mental map (read this first)

In Lab 6 of Section 1 you did this dance by hand: `docker login` with your personal token, `docker tag`, `docker push`. This lab hands the whole dance to a robot that gets a *fresh, scoped, self-destructing* credential for the job — and only builds if the Lab 2 gate went green.

```
 git push (touches capstone/**)
      │
      ▼
 ┌── test job (Lab 2) ──┐        green?
 │ ubuntu + macos       │ ───────────────┐
 │ ruff + pytest        │  no → STOP      │ yes
 └──────────────────────┘                 ▼
                                ┌──────── build job (NEW) ─────────┐
                                │ runs-on: ubuntu-latest           │
                                │ permissions: packages: write ◀── the keycard gets ONE new scope
                                │                                  │
                                │  login-action  ──▶ GITHUB_TOKEN as password to ghcr.io
                                │  metadata-action ─▶ computes tags: :sha-abc123, :latest, :0.1.0
                                │  build-push-action ─▶ docker build + push in one step
                                └──────────────────────────────────┘
                                                 │
                                                 ▼
                                      ghcr.io/itsmahadi007/capstone
                                        now updated by CI, not by you
```

Three ideas do the heavy lifting:

**1. `needs:` turns parallel jobs into a chain.** By default jobs race (Lab 1: two rooms at once). `needs: test` tells the `build` job to wait for `test` and start *only if it succeeded*. This is how a failed test stops a shipment — the arrow you drew on paper in Lab 1 becomes real, and the run's summary page redraws the two jobs as a graph instead of two boxes.

**2. `GITHUB_TOKEN` is the keycard, `permissions:` is what it opens.** Every job is handed a token minted for that one run (Lab 1's hotel-keycard). By default on a hardened workflow it can only *read* the repo. Pushing a package needs one more door: `packages: write`. You grant exactly that, at the job level, and nothing more — the least-privilege habit Section 1's registry lab set up (authn vs authz: login proves *who*, the scope decides *what*). Compare to Lab 6's personal token: a master key to everything you own, forever. The keycard opens one package, then dies with the job.

**3. `metadata-action` computes tags so humans don't.** Hand-typing `:0.1.0` and `:latest` is how tags drift and lie (Lab 6's overnight `:latest` bite). Instead, a step reads the git event and *derives* tags: a `:sha-<short>` tag that is unique to this exact commit (never lies, like a digest-lite), `:latest` only on the default branch, and a `:1.2.3` semver tag when you push a git tag. Deterministic tags, zero typing.

One honest catch to notice at the end: this build runs on `ubuntu-latest`, which is **amd64**. So the pushed image flips from Section 1's arm64-only to *amd64-only* — the `exec format error` debt didn't get paid, it just changed which machine it bites. **Lab 4 is where it actually gets paid** (both arches, one tag).

## Steps

### 1. Understand what you're about to widen

Open `.github/workflows/ci.yml` (Lab 2 left it here). At the top it has:

```yaml
permissions:
  contents: read
```

That is the whole keycard right now: read the repo, nothing else. You are about to add a second job that needs to *write a package*. You will **not** loosen the top-level line — instead you grant the extra scope *only on the build job*, so the test job (which runs untrusted-ish code — linters, test code) keeps the minimal keycard. Scopes belong as close to the job that needs them as possible.

### 2. Add the build job

Append this job to `.github/workflows/ci.yml`, under the existing `test:` job (same indentation level — it's a sibling under `jobs:`):

```yaml
  build:
    needs: test                     # gate: only run if the test job went green
    runs-on: ubuntu-latest
    permissions:
      contents: read                # to checkout
      packages: write               # to push to GHCR — the ONE new door
    steps:
      - uses: actions/checkout@v7

      - name: Log in to GHCR
        uses: docker/login-action@v4
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Compute image tags and labels
        id: meta
        uses: docker/metadata-action@v6
        with:
          images: ghcr.io/itsmahadi007/capstone
          tags: |
            type=sha
            type=semver,pattern={{version}}
            type=raw,value=latest,enable={{is_default_branch}}

      - name: Build and push
        uses: docker/build-push-action@v7
        with:
          context: capstone
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
```

Pre-read, top to bottom — every line is defensible in a review:

- **`needs: test`** — the chain. If *any* matrix leg of `test` fails, `build` never starts (status: *skipped*). This one word is why "tests must pass to ship" is true and not a hope.
- **`permissions:` on the job** — overrides the top-level `contents: read` *for this job only*. `packages: write` is the GHCR push door. `contents: read` is repeated because a job-level `permissions:` block replaces the inherited one wholesale — omit `contents: read` and checkout loses its read access. (Footgun worth remembering: job-level permissions don't *add* to the top level, they *replace* it.)
- **`docker/login-action@v4`** — the `gh auth token | docker login` pipe from Lab 6, packaged. `username: github.actor` (you), `password: secrets.GITHUB_TOKEN` — the keycard, referenced by name. `secrets.GITHUB_TOKEN` is auto-provided; you never create it. It only has the scopes the `permissions:` block granted — which is exactly why the block had to come first.
- **`metadata-action` with `id: meta`** — the `id` lets the next step read this step's outputs (`steps.meta.outputs.tags`). It doesn't build anything; it just computes strings from the git event.
- **the three `tags:` rules** — decoded in step 4. Read them as three independent tag-generators, each firing when its condition matches.
- **`build-push-action` with `context: capstone`** — build using `capstone/Dockerfile` and `capstone/` as the build context (the app is a subfolder). `push: true` = build then push in one step. `tags:` and `labels:` are wired straight from the meta step — no hand-typed tag anywhere.

### 3. Check the package will accept the keycard

The `capstone` package on GHCR already exists — *you* created it by hand in Section 1 Lab 6, from your personal token. A package created that way doesn't automatically trust your repo's `GITHUB_TOKEN`. Two ways this resolves:

- **If the owner of the package matches the repo owner (`itsmahadi007`)** and the package is public, the first CI push usually just works and links the package to the repo.
- **If it doesn't** (you'll see it in step 5 as `denied`), you link them by hand once: GitHub → your **Packages** → `capstone` → **Package settings** → **Manage Actions access** → add the `devops-course` repository with the **Write** role. This is the exact authz lesson from Lab 6, one level up: authentication succeeded (the keycard is real), authorization failed (this package hadn't been told to trust that repo).

### 4. Push and read the tags that appear

```bash
cd /Users/mahadihassan/Documents/plan/projects/devops-course
git add .github/workflows/ci.yml
git commit -m "ci: build and push capstone image to ghcr"
git push
gh run watch
```

Expect the summary to now show **test → build** as a graph (the arrow is `needs:`). The build job's log ends with a push, and on GHCR the package gains new tags. Read what `metadata-action` produced:

```bash
gh api /user/packages/container/capstone/versions --jq '.[0].metadata.container.tags'
```

Expect something like `["sha-a1b2c3d","latest"]`. Decoding the three rules against *this* push (a push to `main`, no git tag):

| Rule | Fires when | This push → |
|---|---|---|
| `type=sha` | every push | `:sha-a1b2c3d` — the 7-char commit SHA, unique to this exact code |
| `type=semver,pattern={{version}}` | you push a **git tag** like `v0.1.0` | *dormant* — no git tag here, so no semver tag |
| `type=raw,value=latest,enable={{is_default_branch}}` | push is on the default branch (`main`) | `:latest` — moved to this build |

The **`:sha-` tag is the one that matters** for deploys: it names one immutable commit's worth of code, so "which image is running in prod?" has an exact answer that maps back to a line of git history. `:latest` is convenience for humans and lies the moment the next push lands (Lab 6). Lab 6 of *this* section deploys by a real tag for exactly that reason.

### 5. (Optional, 2 min) See the semver rule wake up

The `type=semver` rule is dormant because it keys off git tags. Prove it works:

```bash
git tag v0.1.0
git push origin v0.1.0
gh run watch
gh api /user/packages/container/capstone/versions --jq '.[0].metadata.container.tags'
```

Now the tag list includes `0.1.0` — `metadata-action` stripped the `v` and produced a clean semver tag. This is how a release becomes an image tag with no manual `docker tag`: `git tag` *is* the release action. (Delete the tag if you'd rather keep the history clean: `git push --delete origin v0.1.0 && git tag -d v0.1.0`.)

#### If the build fails with `denied: permission_denied` or `installation not allowed`

Authentication worked (the login step went green) but the *push* was refused — pure authz, Lab 6's exact split. Two usual causes: the `permissions: packages: write` block is missing/misindented on the build job (the keycard never got the scope), or the pre-existing package hasn't granted this repo write access (step 3's "Manage Actions access" fix). Read the failing step's log: `permission_denied` = scope/linkage, not a bad token.

#### If the build fails with `dockerfile: no such file` or context errors

`context: capstone` tells the action where the Dockerfile and build context live. Without it, the action looks at the repo root — where there is no Dockerfile. If you moved things, `file: capstone/Dockerfile` sets the Dockerfile path explicitly while `context:` stays the build root.

#### If nothing runs after editing only the workflow

Lab 2's path-filter footgun. `ci.yml` is in its own `paths:` filter, so editing it *does* trigger — but if you edited something outside `capstone/**` and outside `ci.yml`, the doorbell stays silent. `git show --stat HEAD` shows what you actually touched.

## Verify

- `gh run list --workflow=ci --limit 1` shows ✓, and the run graph shows `build` running *after* `test`.
- The package has a fresh `:sha-<commit>` tag matching your latest commit:

```bash
git rev-parse --short HEAD
gh api /user/packages/container/capstone/versions --jq '.[0].metadata.container.tags'
```

The `sha-` tag's suffix should equal the short SHA. That's your commit, built and shipped by a robot.

Then answer aloud:

**1. `GITHUB_TOKEN` vs the personal token you used in Lab 6 — three differences that matter for security?**

<details><summary>Answer (read after attempting aloud)</summary>

(a) **Scope of resources**: the personal token is a master key to everything you own on GitHub; `GITHUB_TOKEN` works only on the one repo the workflow runs in. (b) **Lifetime**: personal token lives until you revoke it; the keycard is minted at job start and revoked automatically at job end (minutes). (c) **Permissions**: the keycard's abilities are pinned by the `permissions:` block to the minimum the job needs (`packages: write` here) — the personal token carries whatever scopes you ever granted it. Least privilege + short life + blast-radius of one repo.

</details>

**2. Why put `packages: write` on the build job and not at the top of the file?**

<details><summary>Answer (read after attempting aloud)</summary>

Least privilege per job. The `test` job runs linters and test code and has no business writing packages — it keeps `contents: read`. Only `build` needs to push, so only `build` gets the scope. If the build job's dependencies were ever compromised, the blast radius is one package write, not the whole repo. (And a job-level `permissions:` block *replaces* the inherited one, so you list every scope that job needs, including `contents: read` for checkout.)

</details>

**3. Three tag rules; a plain push to `main` produced only two tags. Which rule stayed dormant and why — and which of the produced tags should a deploy pin to?**

<details><summary>Answer (read after attempting aloud)</summary>

`type=semver` stayed dormant — it keys off a *git tag* (`v1.2.3`), and a plain branch push has none, so it emits nothing. The push produced `:sha-<commit>` (every push) and `:latest` (default-branch only). A deploy should pin to the **`:sha-` tag** (or a digest): it names one immutable commit, so the running image maps back to an exact line of history. `:latest` is a moving pointer that lies the instant the next push lands.

</details>

**4. Why does `build` only run when `test` is green, and what status does `build` show if a test fails?**

<details><summary>Answer (read after attempting aloud)</summary>

`needs: test` makes `build` depend on `test` succeeding. If any matrix leg of `test` fails, GitHub never starts `build` — it shows as **skipped** (not failed, not cancelled). That dependency is the entire mechanism behind "a failed test stops the shipment": there is no image push to undo because the build never began.

</details>

## Clean up

Nothing to tear down — the build job stays in the pipeline forever; Lab 4 upgrades it in place. If you pushed the `v0.1.0` tag and want a clean slate for later semver demos, delete it (`git push --delete origin v0.1.0 && git tag -d v0.1.0`). Leave the GHCR package public.
