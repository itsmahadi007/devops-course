# Lab 2 — The capstone stack as code

**Goal:** rebuild the *entire* Section 4 compose stack — api + redis + postgres, on their own network, with a persistent volume — in HCL, and stand it up with one `terraform apply`. By the end you'll have watched Terraform build a dependency graph across four resource types and you'll be able to answer the interview question that actually separates people: **"you already have compose — what does Terraform give you that compose doesn't, and what does it take away?"**

## The mental map (read this first)

Your `capstone/docker-compose.yml` is a stack in one file. This lab is that same stack, re-expressed as a *graph of resources* the Docker provider will materialize. The shapes line up almost one-to-one — the job is learning which HCL block plays which compose role:

```
  docker-compose.yml                    infra/terraform/capstone-stack/main.tf
  ─────────────────                     ────────────────────────────────────
  services:                             each service splits into TWO resources:
    api:  build: .            ───────▶   docker_image.api   (build the image)
                                         docker_container.api (run it)
    redis: image: redis…      ───────▶   docker_image.redis + docker_container.redis
    db:    image: postgres…   ───────▶   docker_image.db    + docker_container.db
  networks: (implicit default) ──────▶   docker_network.capstone  (you declare it explicitly)
  volumes:  pgdata:            ───────▶   docker_volume.pgdata
```

Two structural differences to hold in your head before you type anything:

1. **Compose fuses "the image" and "the running thing" into one service block. Terraform splits them** — a `docker_image` resource (pull or build) and a `docker_container` resource that references it. This is why Lab 1's `destroy` deleted the *image* too: to Terraform the image is a managed resource with its own lifecycle, not a side-effect of running a container. That bites hard here (redis/postgres images are shared with your still-running compose stack) — you'll defend against it with `keep_locally`.

2. **Compose has `depends_on: condition: service_healthy`. The Docker provider has nothing like it.** `depends_on` in Terraform sets *creation order* only — "make redis before api" — it does **not** wait for redis to answer `PONG`. That startup race you killed with health-gating in Section 4 Lab 4 comes *back* here, and naming that gap out loud is a senior-signal answer (Verify Q3). The healthcheck we still add is for `docker ps` visibility and for the human, not for a gate the provider will honor.

```
        THE GRAPH TERRAFORM DERIVES (from the references you write)

   docker_network.capstone ──┐
                             ├──▶ docker_container.redis ─┐
   docker_image.redis ───────┘                            │
                                                          ├─(depends_on, order only)─▶ docker_container.api
   docker_network.capstone ──┐                            │                                   ▲
                             ├──▶ docker_container.db ─────┘                                   │
   docker_image.db ──────────┘                                          docker_image.api ──────┘
   docker_volume.pgdata ─────────▶ (mounted into db)                    (built from ../../../capstone)
```

You never write that order. The references do — exactly like Lab 1's image→container edge, now with six edges instead of one.

## Steps

### 1. New folder, keep Lab 1 intact

From the repo root:

```bash
mkdir -p infra/terraform/capstone-stack
cd infra/terraform/capstone-stack
```

Lab 1's `hello-nginx/` stays where it is — each folder is its own Terraform **root** with its own state file. (A folder with `.tf` files that you run `terraform` inside is called a *root module*; Lab 4 turns the reusable bits into *child modules*.)

### 2. Write `infra/terraform/capstone-stack/main.tf`

This is longer than Lab 1's file, but every block is a shape you just saw in the map. Read the comments as you paste — they connect each line back to the compose file it replaces:

```hcl
terraform {
  required_version = ">= 1.15.0"
  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "~> 4.0"
    }
  }
}

provider "docker" {
  host = "unix:///var/run/docker.sock"
}

# ── NETWORK ──────────────────────────────────────────────────────────
# compose created a "capstone_default" network for you silently.
# In TF you declare it. This is the private LAN the three containers share,
# and the thing that makes service-name DNS work (Section 4 Lab 4 lesson).
resource "docker_network" "capstone" {
  name = "capstone-tf"
}

# ── VOLUME ───────────────────────────────────────────────────────────
# the exact analog of compose's top-level `volumes: pgdata:`.
# Docker creates and owns it; it outlives the container (the whole point).
resource "docker_volume" "pgdata" {
  name = "capstone-tf-pgdata"
}

# ── IMAGES ───────────────────────────────────────────────────────────
# redis + postgres are PULLED. keep_locally = true is the scar from Lab 1:
# `terraform destroy` deletes managed images by default, and these tags are
# SHARED with your running compose stack. keep_locally tells the provider
# "manage the pull, but do NOT delete the image on destroy." Non-negotiable here.
resource "docker_image" "redis" {
  name         = "redis:8-alpine"
  keep_locally = true
}

resource "docker_image" "db" {
  name         = "postgres:18-alpine"
  keep_locally = true
}

# the api is BUILT, not pulled — this is compose's `build: .`.
# context points at the capstone/ folder (three levels up from here).
# abspath() + path.module makes it robust no matter where you run terraform from.
resource "docker_image" "api" {
  name = "capstone:tf"
  build {
    context = abspath("${path.module}/../../../capstone")
    tag     = ["capstone:tf"]
  }
  # rebuild the image when the Dockerfile or app code changes — otherwise TF
  # sees the same name = "capstone:tf" and assumes nothing changed (see step 6).
  triggers = {
    dockerfile = filesha256("${path.module}/../../../capstone/Dockerfile")
  }
}

# ── CONTAINERS ───────────────────────────────────────────────────────
resource "docker_container" "redis" {
  name  = "capstone-tf-redis"
  image = docker_image.redis.image_id

  # join the private network AND answer to the DNS name "redis" on it.
  # aliases are how api's REDIS_URL=redis://redis:6379 resolves — same
  # embedded-DNS trick as compose, just spelled out.
  networks_advanced {
    name    = docker_network.capstone.name
    aliases = ["redis"]
  }

  # healthcheck for `docker ps` visibility + humans. NOTE: the provider does
  # NOT gate api on this being healthy (see the mental map). This is the
  # compose block, translated — it just buys less here.
  healthcheck {
    test     = ["CMD", "redis-cli", "ping"]
    interval = "5s"
    timeout  = "3s"
    retries  = 5
  }
}

resource "docker_container" "db" {
  name  = "capstone-tf-db"
  image = docker_image.db.image_id

  env = ["POSTGRES_PASSWORD=localdev"]   # local lab only — never a real secret

  # the Postgres-18 rule you learned the hard way in Section 4 Lab 4:
  # mount at /var/lib/postgresql, NOT /.../data (18 keeps data in a version subdir).
  volumes {
    volume_name    = docker_volume.pgdata.name
    container_path = "/var/lib/postgresql"
  }

  networks_advanced {
    name    = docker_network.capstone.name
    aliases = ["db"]
  }

  healthcheck {
    test     = ["CMD-SHELL", "pg_isready -U postgres"]
    interval = "5s"
    timeout  = "3s"
    retries  = 5
  }
}

resource "docker_container" "api" {
  name  = "capstone-tf-api"
  image = docker_image.api.image_id

  env = ["REDIS_URL=redis://redis:6379/0"]   # hostname "redis" = the alias above

  ports {
    internal = 8000
    external = 9071          # Section 6 block. NOTE: not 9000 — your compose
  }                          # stack may still own 9000; these run side by side.

  networks_advanced {
    name = docker_network.capstone.name
  }

  # ORDER ONLY. Not a health gate. redis/db get CREATED first; whether they're
  # READY when api starts is a race the provider won't win for you (Verify Q3).
  depends_on = [docker_container.redis, docker_container.db]
}
```

#### Why `env` is a list of `"KEY=value"` strings, not a map

Compose lets you write `environment:` as a YAML map. The Docker provider mirrors Docker's *own* API, where env is an array of `KEY=value` strings (the same shape `docker inspect` shows you). Small friction, worth internalizing: **the provider is a thin translator over the daemon API, not over the compose UX.** Anywhere the compose ergonomics feel missing, that's why — you're one layer closer to the metal.

#### Why the api splits into build + reference, and what `triggers` buys you

`docker_image.api` with a `build {}` block is `docker build` run by Terraform. But here's the trap: the image's *name* is always `capstone:tf`, so on the next `plan` Terraform looks at "name = capstone:tf, still capstone:tf" and concludes **nothing changed** — even if you edited the app. It has no way to know the bytes behind the tag moved (the mutable-tag problem from Section 1, now on your side of the fence). `triggers` fixes it: a map of values that, when any changes, forces the image to rebuild. Hashing the Dockerfile means "rebuild when the recipe changes." (A fuller version would hash the whole app dir; Dockerfile-only keeps this lab fast and the lesson clear.)

### 3. `terraform init`

```bash
terraform init
```

Same output shape as Lab 1 — it downloads `kreuzwerker/docker` again into *this* folder's `.terraform/` (providers are per-root, not global) and writes a fresh `.terraform.lock.hcl`. Commit the lock file.

### 4. `terraform plan` — read a six-resource proposal

```bash
terraform plan
```

The summary line is the headline you check first:

```
Plan: 6 to add, 0 to change, 0 to destroy.
```

Six: one network, one volume, three images… wait, that's five plus three containers = **six**? Count them — network(1) + volume(1) + images redis/db/api(3) + containers redis/db/api(3) = **8**. If your summary says `8 to add`, good — that's the honest count. (If you see `6`, you likely reused an already-pulled image; `keep_locally` images that already exist locally still register as resources to *add* to state, so 8 is the clean-machine number.) The point of the drill: **the number must equal what you can count in your head.** A plan that adds more than you can explain is the plan you stop and investigate.

You'll also see, inside `docker_container.api`:

```
  + image = (known after apply)      ← the built image's digest, unknowable pre-build (Lab 1 lesson)
```

and inside the build image, a big block of build settings mostly defaulted — normal noise, same as Lab 1's container attribute dump.

### 5. `terraform apply`

```bash
terraform apply
```

Type `yes`. Watch the ordering — this is the graph executing across eight nodes:

```
docker_network.capstone: Creating...
docker_volume.pgdata: Creating...
docker_image.redis: Creating...
docker_image.db: Creating...
docker_image.api: Creating...
docker_image.redis: Creation complete after 1s [id=sha256:...]
docker_image.db: Creation complete after 1s [id=sha256:...]
docker_network.capstone: Creation complete after 0s [id=...]
docker_volume.pgdata: Creation complete after 0s [id=...]
docker_image.api: Still creating... [30s elapsed]        ← this is `docker build`; uv sync etc.
docker_image.api: Creation complete after 48s [id=sha256:...]
docker_container.redis: Creating...                       ← containers wait on image+network
docker_container.db: Creating...
docker_container.redis: Creation complete after 1s [id=...]
docker_container.db: Creation complete after 1s [id=...]
docker_container.api: Creating...                         ← LAST: it depends_on the other two
docker_container.api: Creation complete after 1s [id=...]

Apply complete! Resources: 8 added, 0 changed, 0 destroyed.
```

Everything with no dependency on anything else (network, volume, the three image pulls/builds) kicked off **in parallel** — Terraform's default is up to 10 concurrent operations. The containers waited only as long as their references demanded. Nobody wrote a sequence; the graph derived it.

#### If the api build fails

The most likely failure is a Docker build context problem. Two checks, in order:

- **`lstat .../capstone: no such file or directory`** — the `abspath("${path.module}/../../../capstone")` didn't resolve to your capstone folder. From `infra/terraform/capstone-stack`, three `../` lands at the repo root; run `ls ../../../capstone/Dockerfile` to confirm the path before blaming Terraform.
- **build succeeds but is slow every time** — expected on the first apply (full `uv sync`); the cache ladder from Section 1 still applies, so a second build with no code change is seconds.

### 6. Verify it's a real, running stack

```bash
docker ps --filter name=capstone-tf        # three containers, api shows 0.0.0.0:9071->8000
curl -s localhost:9071/health               # {"status":"ok"}
curl -s localhost:9071/visits               # {"visits": N}  ← proves api → redis DNS works
curl -s localhost:9071/visits               # {"visits": N+1}
```

The `/visits` counter incrementing is the whole stack proving itself: api resolved the DNS name `redis` (via the network alias) → talked to the redis container → incremented a key. The private network, the alias, and the env var all had to be right.

### 7. Read the state — now with dependencies in it

```bash
terraform state list
```

```
docker_container.api
docker_container.db
docker_container.redis
docker_image.api
docker_image.db
docker_image.redis
docker_network.capstone
docker_volume.pgdata
```

Eight addresses — the same inventory you counted in the plan. Now peek at how state records an edge:

```bash
terraform state show docker_container.api | grep -A2 network_data
```

State stores the container's *resolved* network attachment (the network's real ID, the assigned container IP) — the runtime facts that only existed after apply. This is the "known after apply" promises from the plan, now filled in. State isn't just a name→ID list; it's the full post-apply attribute snapshot of every resource, which is exactly what the next `plan` diffs against.

## Verify

- `curl -s localhost:9071/visits` twice returns an incrementing counter.
- `terraform state list` shows all eight resources.
- `terraform plan` now says `No changes.` — the stack matches the config.

**Answer aloud** (then check):

1. You already have a working `docker-compose.yml` for this exact stack. Give two things Terraform adds and two things it takes away.

<details><summary>Answer (read after attempting aloud)</summary>

**Adds:** (1) One workflow for *everything with an API*, not just Docker — the same `plan`/`apply` manages AWS, K8s, Cloudflare (Section 7 onward); compose only speaks Docker. (2) An explicit **state file** and therefore real diffing/drift-detection against a recorded prior — compose re-derives "mine" from labels every time and has no memory of intended state to detect drift against. (3) Rich dependency graph across resource *types* (network, volume, image, container as first-class nodes), plus modules/variables for reuse at scale.

**Takes away:** (1) The `service_healthy` startup gate — the Docker provider's `depends_on` is order-only, so the readiness race returns. (2) Ergonomics — env is `KEY=value` strings not a map, images and containers are separate resources, more ceremony for the same small stack. **Honest verdict for an interview:** for a single-host dev stack, compose is the better tool; Terraform earns its keep the moment infra spans more than the Docker daemon or more than one person needs a shared record of it.

</details>

2. `terraform destroy` in Lab 1 deleted the nginx *image* from your machine. Why would that be dangerous here, and what one argument prevents it?

<details><summary>Answer (read after attempting aloud)</summary>

`docker_image` is a *managed* resource; its default lifecycle deletes the image on destroy. Here `redis:8-alpine` and `postgres:18-alpine` are the **same tags your running compose stack uses** — destroying this Terraform root would yank images out from under a different, unrelated stack (best case a slow re-pull, worst case a broken running service). `keep_locally = true` tells the provider to manage the *pull* into state but never *delete* the image on destroy. The api image (`capstone:tf`) isn't shared, so it's fine to let that one go.

</details>

3. In compose you had `depends_on: redis: condition: service_healthy`. You wrote `depends_on = [docker_container.redis, ...]` here. Are they the same? What race is back?

<details><summary>Answer (read after attempting aloud)</summary>

**Not the same.** Compose's `condition: service_healthy` waits for redis's healthcheck to pass before *starting* api. Terraform's `depends_on` only orders *creation* — redis container gets created before api, but "created" ≠ "ready to answer `PONG`." So the Section 4 Lab 4 startup race is back: api can start against a redis that's still warming up. It works here only because the capstone app connects to redis lazily / on first request, not at boot. The provider has **no health-gate primitive** — the honest fix in real TF-managed infra is app-level retries (12-factor: assume dependencies flap), or an orchestrator that owns readiness (Kubernetes probes, Section 4). Naming this gap is the senior answer; pretending `depends_on` closed it is the junior one.

</details>

4. You added `triggers = { dockerfile = filesha256(...) }` to the api image. What breaks if you delete that line?

<details><summary>Answer (read after attempting aloud)</summary>

The image resource is identified by `name = "capstone:tf"`. Without `triggers`, that name never changes, so `terraform plan` always sees "capstone:tf → capstone:tf, no diff" and **never rebuilds** — even after you edit the app code. You'd `apply`, see `No changes`, and ship stale bytes. It's the mutable-tag problem from Section 1 (Lab 6's `:latest` bite) reappearing on the authoring side: the tag is a re-stickable pointer, and Terraform diffs the *pointer*, not the *content* behind it. `triggers` gives Terraform a content-derived value to diff, so a Dockerfile change forces a rebuild.

</details>

## Clean up

```bash
terraform destroy
```

Read the plan first: `Plan: 0 to add, 0 to change, 8 to destroy` — but watch the image lines:

```
docker_image.redis: Destroying... [id=...]
docker_image.redis: Destruction complete after 0s     ← removed from STATE, image kept on disk (keep_locally)
```

`keep_locally` means "forget it from state, leave it on the machine." Confirm your compose images survived:

```bash
docker images | grep -E 'redis|postgres'    # still there — compose stack unharmed
docker images | grep capstone               # capstone:tf is GONE (not kept), capstone:latest survives
```

The volume `capstone-tf-pgdata` is destroyed (it was TF-managed and not kept) — this stack's Postgres data is gone, which is correct for a lab. Keep the folder: `main.tf` + `.terraform.lock.hcl` get committed; `terraform.tfstate` stays gitignored.
