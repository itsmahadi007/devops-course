# Lab 6 — Ship the image to a registry (GHCR)

**Goal:** push the capstone image to GitHub Container Registry, then pull and run it like a stranger would — anonymously, after `docker logout`. Registries are how images travel between machines; Section 2's CI will do this exact dance automatically on every git push.

## The mental map (read this first)

Where does an image *go* when it leaves your machine? A **registry** — a content-addressed warehouse of layers, plus a small phone book of names pointing into it. You already know this whole system from git; only the words change:

| git | docker | mutable? |
|---|---|---|
| commit sha | **digest** (`sha256:9f2c…`) | never — it IS the hash of the content |
| branch name | **tag** (`:0.1.0`, `:latest`) | yes — a sticky note you can re-stick |
| remote (`origin`) | **registry** (`ghcr.io`, Docker Hub) | — |
| `push` / `pull` | `push` / `pull` | — |

```
 YOUR MAC (daemon's image store)             REGISTRY (ghcr.io)
┌───────────────────────────┐    push    ┌────────────────────────────┐
│ layers (content-addressed)│ ─────────▶ │ layers (deduped by hash —  │
│                           │            │  "Layer already exists")   │
│ capstone:0.1.0 ────────┐  │            │                            │
│ ghcr.io/…/capstone:0.1.0 ─┼─▶ ONE      │ tags (the phone book):     │
│ ghcr.io/…/capstone:latest ┘   image    │  :0.1.0  ──▶ sha256:9f2c…  │
└───────────────────────────┘            │  :latest ──▶ sha256:9f2c…  │
                                         └────────────────────────────┘
```

Anatomy of a full image name — `ghcr.io/itsmahadi007/capstone:0.1.0` = **registry host / owner / name : tag**. Two silent defaults you've been relying on for 6 years without seeing them: no registry prefix → `docker.io` (Docker Hub — that's why `FROM debian:12-slim` just works), no tag → `:latest`.

This lab also pays off two debts from earlier labs:

- Lab 1's `Already exists` lines during pull — that was **registry-side layer dedup**, the same content-addressing you saw locally.
- Lab 3's ":latest bit me overnight" — because **tags are mutable pointers**. `:latest` is not a version; it's a sticky note someone else can move. The un-movable name is the **digest**, and today you'll use it.

## Steps

### 1. Log in to GHCR with the gh credentials you already have

```bash
gh auth token | docker login ghcr.io -u itsmahadi007 --password-stdin
```

GHCR accepts a GitHub token as the password. The pipe + `--password-stdin` keeps the token out of shell history and `ps` output — the same hygiene reflex as never committing keys.

#### If a later push says `denied` or `permission_denied`

Your gh token may lack the packages scope. Grant it and log in again:

```bash
gh auth refresh -s write:packages
gh auth token | docker login ghcr.io -u itsmahadi007 --password-stdin
```

### 2. Tag — stick registry-qualified names on the SAME image

```bash
cd capstone
docker tag capstone:0.1.0 ghcr.io/itsmahadi007/capstone:0.1.0
docker tag capstone:0.1.0 ghcr.io/itsmahadi007/capstone:latest
docker images | grep capstone
```

Expect **three names, one IMAGE ID**. `docker tag` copies nothing — it writes another sticky note pointing at content that already exists, instant and free. The registry host lives *inside the name*: that's how `docker push` knows where to send it.

### 3. Push — and watch content-addressing work over the network

```bash
docker push ghcr.io/itsmahadi007/capstone:0.1.0
docker push ghcr.io/itsmahadi007/capstone:latest
```

First push uploads layer by layer — and what travels is the **compressed content** (Lab 3's 47.2MB "content size", not the 220MB disk number; this is why that column is the one that matters for ship speed).

Second push finishes in about a second, every line saying `Layer already exists` — the warehouse already holds those hashes; only the `:latest` sticky note got written into the phone book.

The last line of the push output looks like:

```
0.1.0: digest: sha256:e3b0c44298fc1c... size: 1234
```

**Copy that digest** — step 5 uses it.

### 4. Make the package public

GitHub → your profile → **Packages** → `capstone` → Package settings → Change visibility → **Public**. (New GHCR packages default to private.) Public means anyone on earth can run your service with one command — that URL is portfolio evidence.

### 5. Pull by digest — the name that cannot lie

```bash
docker pull ghcr.io/itsmahadi007/capstone@sha256:<digest from step 3>
```

Note `@` instead of `:`. A digest reference can never be re-pointed — it's the hash *of* the content, commit-sha-style. This is the defense against Lab 3's moving-tag bite, and you've already seen the production form of it without noticing: your own build output said `FROM docker.io/library/debian:12-slim@sha256:60eac7…` — BuildKit resolves the mutable tag to an immutable digest before trusting it.

### 6. Round-trip like a stranger

```bash
docker rmi ghcr.io/itsmahadi007/capstone:0.1.0 ghcr.io/itsmahadi007/capstone:latest capstone:0.1.0
docker logout ghcr.io
docker pull ghcr.io/itsmahadi007/capstone:0.1.0
docker run -d --name from-registry -p 9006:8000 ghcr.io/itsmahadi007/capstone:0.1.0
curl -s localhost:9006/health
```

#### Why that big `rmi` mostly doesn't delete anything

Removing one name from a multi-named image just peels a sticky note — the output says `Untagged:`. Layers actually die only when the *last* name goes (`Deleted:` lines). Tags are pointers on the way out, too.

#### Why host port 9006, not 9000

Your Lab 4 compose stack may still be running and publishing 9000, and the 8000-series belongs to the real dev stack. You diagnosed `port is already allocated` in Lab 3; cheaper to not collide at all. Only the host side moves — container side stays 8000, because that's the image's own business.

#### The catch a laptop build hides (CI will fix it)

This image is **arm64-only** — built on Apple Silicon. A rented x86 VPS would pull it fine and then die at startup with `exec format error` (right architecture words, wrong CPU language). GitHub's CI runners are amd64 — one of the quiet reasons the rule everywhere is "build in CI, not on laptops." Section 2 makes this concrete.

## Verify

- `curl -s localhost:9006/health` returns the health JSON — from an image pulled **anonymously, after logout**.
- `docker images | grep capstone` shows the image back under its `ghcr.io/...` name.

Then answer aloud:

**1. What does a tag point to, physically? Why was the second push near-instant?**

<details><summary>Answer (read after attempting aloud)</summary>

A tag is a mutable pointer — a name in the registry's phone book mapping to a digest (the sha256 of the image content). It contains no data itself. The second push was instant because every layer's hash already existed in the registry (`Layer already exists`); the only write was pointing the `:latest` name at the same digest.

</details>

**2. `:latest` vs a digest — which one can lie to you, and what's the pin syntax?**

<details><summary>Answer (read after attempting aloud)</summary>

`:latest` (any tag, really) can lie: it's re-stickable, so the same name can mean different bytes tomorrow — that's exactly how uv's moved tag broke the Lab 3 build cache overnight. A digest cannot lie — it's computed from the content. Pin syntax swaps `:` for `@`: `image@sha256:…`, usable in `pull`, `run`, and `FROM`.

</details>

**3. You `docker rmi` an image that carries three names. What actually happens?**

<details><summary>Answer (read after attempting aloud)</summary>

Each `rmi` of a name just untags — peels one sticky note off, `Untagged:` in the output. The layers are only deleted when the last remaining name is removed (`Deleted:` lines) — and even then, any layer still used by another image survives, because layers are shared by content hash.

</details>

## Clean up

```bash
docker rm -f from-registry
docker tag ghcr.io/itsmahadi007/capstone:0.1.0 capstone:0.1.0   # restore the short local name later labs expect
```

Stay logged out of ghcr.io — Section 2's CI authenticates with its own short-lived `GITHUB_TOKEN`, never your personal one.
