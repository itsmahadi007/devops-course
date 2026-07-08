# Lab 4 — Modules: extract a reusable `service`, refactor without destroying

**Goal:** notice that your three container resources are near-identical copies, extract the shared shape into one reusable **`service` module**, and refactor the whole stack to call it three times — *without destroying and recreating a single running container*. The trick that makes the last part possible, `moved` blocks, is exactly the tool freelance "our Terraform is a mess" gigs are hiring for. You'll finish able to explain module composition from first principles: what a module *is*, how values cross its boundary, and why refactoring stateful infra is scary until you know this.

## The mental map (read this first)

A **module** is just a folder of `.tf` files. You've already been using one — the folder you run `terraform` in is the **root module**. A **child module** is another folder you *call*, passing it inputs (its `variable`s) and reading back outputs (its `output`s). It's a function, and `module "redis" { source = "..." }` is the call site:

```
   ROOT MODULE  (infra/terraform/capstone-stack/)
   ┌───────────────────────────────────────────────────────────┐
   │  docker_network, docker_volume, docker_image.{redis,db,api} │  ← images stay here
   │                                                             │
   │  module "redis" { source=../modules/service   ... }  ───────┼──┐
   │  module "db"    { source=../modules/service   ... }  ───────┼──┤ same folder,
   │  module "api"   { source=../modules/service   ... }  ───────┼──┤ called 3×
   └─────────────────────────────────────────────────────────────┘  │
                                                                      ▼
                          CHILD MODULE  (infra/terraform/modules/service/)
                          ┌──────────────────────────────────────┐
                          │  variable "name"  "image"  "env" …    │ ← the parameters
                          │  resource "docker_container" "this"{…} │ ← the body (one container)
                          │  output "container_id" …               │ ← the return value
                          └──────────────────────────────────────┘
```

**Two boundaries do all the work.** *Down* the boundary: root passes `name`, `image`, `env`, `labels`… as the module's variables. *Up* the boundary: the module returns `container_id` as an output the root reads. Nothing else crosses — a module can't reach into the root's variables, and the root can't touch the module's resources except through its outputs. That encapsulation is the entire value: the module is a black box with a typed interface, reusable across roots, testable in isolation.

**The scary part, and why `moved` exists.** A resource's *address* includes its module path. Today redis lives at `docker_container.redis`. After the refactor it lives at `module.redis.docker_container.this` — a **different address**. Terraform tracks resources in state *by address*. So without help, it reads the plan as "the resource at `docker_container.redis` is gone (destroy it) and a new resource at `module.redis.docker_container.this` appeared (create it)" — a destroy-and-recreate of your running database. `moved { from = ... to = ... }` is a note in your config that says **"same resource, new address — just relabel it in state, don't touch reality."**

```
   WITHOUT moved:                          WITH moved block:
   docker_container.redis   → DESTROY      state entry relabeled in place
   module.redis...this      → CREATE       docker_container.redis ─▶ module.redis...this
   = downtime, data loss risk              = 0 to add, 0 to change, 0 to destroy
```

## Steps

### 1. Re-stand-up the Lab 3 stack

```bash
cd infra/terraform/capstone-stack
terraform apply -auto-approve
```

Note the three running container IDs — you'll prove they *survive* the refactor:

```bash
docker inspect -f '{{.Id}}' capstone-tf-redis    # remember the first 12 chars
```

### 2. Write the module — `infra/terraform/modules/service/`

The module lives *outside* the root folder (siblings under `infra/terraform/`), so many roots could reuse it. Create three files.

`infra/terraform/modules/service/variables.tf` — the typed interface:

```hcl
variable "name"         { type = string }
variable "image"        { type = string }               # an image reference (id), passed in from root
variable "network_name" { type = string }
variable "aliases"      { type = list(string) ; default = [] }
variable "env"          { type = list(string) ; default = [] }
variable "labels"       { type = map(string)  ; default = {} }

# optional bits — object-or-null so a caller can omit them
variable "published_port" {
  type    = object({ internal = number, external = number })
  default = null                                          # redis/db publish nothing → leave null
}
variable "volume" {
  type    = object({ name = string, path = string })
  default = null
}
variable "healthcheck" {
  type    = object({ test = list(string), interval = string, timeout = string, retries = number })
  default = null
}
```

`infra/terraform/modules/service/main.tf` — the body:

```hcl
terraform {
  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "~> 4.0"
    }
  }
}
# NOTE: no `provider "docker"` block here. A child module INHERITS the provider
# the root configured. required_providers only declares which provider this
# module's resources belong to (so the source address is unambiguous).

resource "docker_container" "this" {
  name  = var.name
  image = var.image
  env   = var.env

  networks_advanced {
    name    = var.network_name
    aliases = var.aliases
  }

  # each optional block is generated 0-or-1 times depending on whether its
  # variable is null. `var.x == null ? [] : [var.x]` = "loop zero times, or once."
  dynamic "ports" {
    for_each = var.published_port == null ? [] : [var.published_port]
    content {
      internal = ports.value.internal
      external = ports.value.external
    }
  }

  dynamic "volumes" {
    for_each = var.volume == null ? [] : [var.volume]
    content {
      volume_name    = volumes.value.name
      container_path = volumes.value.path
    }
  }

  dynamic "healthcheck" {
    for_each = var.healthcheck == null ? [] : [var.healthcheck]
    content {
      test     = healthcheck.value.test
      interval = healthcheck.value.interval
      timeout  = healthcheck.value.timeout
      retries  = healthcheck.value.retries
    }
  }

  dynamic "labels" {
    for_each = var.labels
    content {
      label = labels.key
      value = labels.value
    }
  }
}
```

`infra/terraform/modules/service/outputs.tf` — the return values:

```hcl
output "container_id" { value = docker_container.this.id }
output "name"         { value = docker_container.this.name }
```

#### Why the module takes an image *reference*, not an image *tag*

Notice the module never pulls or builds — it takes `var.image` (an image id) and runs a container. The images stay in the **root** (`docker_image.redis`, `docker_image.api` with its `build` block, all with `keep_locally`). That's a deliberate design call: this module's single responsibility is "run a container on the shared network." Image lifecycle — pull vs build, `keep_locally`, `triggers` — is a separate concern the root owns. A module that tried to do both would need a `pull-or-build?` flag and couldn't cleanly express the api's build step. **Good modules have one job and a narrow interface;** resist the urge to make `service` do everything.

#### The `object(...)`-or-`null` pattern, pre-explained

`published_port`'s type is `object({ internal=number, external=number })` with `default = null`. This is how you make a *structured, optional* input: a caller either passes the whole object (`{ internal=8000, external=9071 }`) or omits it and gets `null`. The `dynamic` block then emits the `ports {}` block zero times (when null) or once (when set). Redis and db pass `null` (no host port — the Section 4 "fewer doors" lesson), api passes the object. One module, three different shapes, no copy-paste.

### 3. Rewrite the root `main.tf` to call the module three times

Keep the `terraform {}`, `provider {}`, `docker_network`, `docker_volume`, and all three `docker_image` blocks **exactly as they are**. Replace only the three `docker_container` blocks with three module calls:

```hcl
module "redis" {
  source       = "../modules/service"
  name         = local.names.redis
  image        = docker_image.redis.image_id
  network_name = docker_network.capstone.name
  aliases      = ["redis"]
  labels       = local.common_labels
  healthcheck  = { test = ["CMD", "redis-cli", "ping"], interval = "5s", timeout = "3s", retries = 5 }
}

module "db" {
  source       = "../modules/service"
  name         = local.names.db
  image        = docker_image.db.image_id
  network_name = docker_network.capstone.name
  aliases      = ["db"]
  env          = ["POSTGRES_PASSWORD=${var.pg_password}"]
  volume       = { name = docker_volume.pgdata.name, path = "/var/lib/postgresql" }
  labels       = local.common_labels
  healthcheck  = { test = ["CMD-SHELL", "pg_isready -U postgres"], interval = "5s", timeout = "3s", retries = 5 }
}

module "api" {
  source         = "../modules/service"
  name           = local.names.api
  image          = docker_image.api.image_id
  network_name   = docker_network.capstone.name
  env            = ["REDIS_URL=redis://redis:6379/0"]
  published_port = { internal = 8000, external = var.api_port }
  labels         = local.common_labels
  depends_on     = [module.redis, module.db]   # order-only, same caveat as Lab 2
}
```

Notice how the call sites read like a table now — the shared shape is invisible (it's in the module), and only the *differences* between the three services are on screen. That readability is the reuse payoff.

### 4. Update `outputs.tf` — addresses changed

The root's outputs referenced `docker_container.api.id`; those resources now live inside modules. Rewrite `container_ids`:

```hcl
output "container_ids" {
  description = "The real Docker IDs of every container in the stack"
  value = {
    api   = module.api.container_id
    redis = module.redis.container_id
    db    = module.db.container_id
  }
}
```

`api_url` and `pg_password` outputs are unchanged (they reference variables, not the moved resources).

### 5. `terraform init` again — modules must be registered

```bash
terraform init
```

You'll see a new line you didn't get before:

```
Initializing modules...
- api in ../modules/service
- db in ../modules/service
- redis in ../modules/service
```

`init` isn't only for providers — it also records where each module's source is (here, a local path; for registry/git modules it would *download* them into `.terraform/modules/`). **If you skip this, the next command fails with `Module not installed`** — that's the #1 "why won't it plan?" after adding a module.

### 6. `terraform plan` — and see the destroy trap *before* you fix it

Run plan **without** the `moved` blocks first, to see the danger with your own eyes:

```bash
terraform plan
```

```
Plan: 3 to add, 0 to change, 3 to destroy.

  # docker_container.api will be destroyed
  # (because docker_container.api is not in configuration)
  - resource "docker_container" "api" { ... }

  # module.api.docker_container.this will be created
  + resource "docker_container" "this" { ... }
  ...
```

**This is the trap.** Terraform sees the old addresses vanish from config and new addresses appear, and — knowing nothing about your intent — plans to *destroy the running containers and build fresh ones*. On the db that's an empty database (the volume would survive, but the container restart is real downtime). `3 to add, 3 to destroy` on a refactor where you changed *nothing about reality* is the alarm bell. **Do not apply this.**

### 7. Add `moved` blocks — tell Terraform it's the same resource

Create `infra/terraform/capstone-stack/moved.tf`:

```hcl
moved {
  from = docker_container.redis
  to   = module.redis.docker_container.this
}
moved {
  from = docker_container.db
  to   = module.db.docker_container.this
}
moved {
  from = docker_container.api
  to   = module.api.docker_container.this
}
```

```bash
terraform plan
```

```
Terraform will perform the following actions:

  # docker_container.api has moved to module.api.docker_container.this
    resource "docker_container" "this" { ... }        ← no +/-/~ prefix: pure relabel
  # docker_container.db has moved to module.db.docker_container.this
  # docker_container.redis has moved to module.redis.docker_container.this

Plan: 0 to add, 0 to change, 0 to destroy.
```

`0, 0, 0` — the whole point. The `has moved to` lines carry *no* action symbol because nothing in reality changes: Terraform just rewrites the address label in state. Apply it:

```bash
terraform apply -auto-approve
```

Now the proof the container never died:

```bash
docker inspect -f '{{.Id}}' capstone-tf-redis    # SAME 12 chars you noted in step 1
curl -s localhost:9071/visits                     # still works, counter uninterrupted
```

**Same container ID = same running container.** You changed the entire code structure — three resources became one reusable module called three times — and touched zero running infrastructure. That's the skill: refactoring live systems safely.

#### When can you delete the `moved` blocks?

Once every state file that matters has been applied through them (here, just your local one), the `moved` blocks have done their job — they're a one-time migration instruction. In a team, you leave them for a release or two so everyone's state migrates, then remove them. They're harmless to keep; deleting a `moved` whose migration already happened changes nothing. (`terraform state mv` is the imperative, one-off alternative — but `moved` blocks are code-reviewed, apply everywhere automatically, and are the modern default.)

### 8. Feel the reuse — change the module once, all three benefit

Add a line to the module's container (`modules/service/main.tf`), e.g. inside `docker_container.this`:

```hcl
  restart = "unless-stopped"
```

```bash
terraform plan
```

```
Plan: 0 to add, 3 to change, 0 to destroy.
  ~ module.api.docker_container.this   ~ restart = "no" -> "unless-stopped"
  ~ module.db.docker_container.this    ~ restart = "no" -> "unless-stopped"
  ~ module.redis.docker_container.this ~ restart = "no" -> "unless-stopped"
```

One edit, three `~` changes — every caller of the module inherited it. That's the multiplier a module gives you (and the blast radius to respect: a careless module change hits every consumer at once). Apply it.

## Verify

- `terraform plan` after the `moved` blocks showed `0 to add, 0 to change, 0 to destroy` and `has moved to` lines.
- `docker inspect -f '{{.Id}}' capstone-tf-redis` returns the *same* ID as before the refactor.
- Editing the module once produced a `~` change on all three module instances.

**Answer aloud** (then check):

1. What crosses the boundary between a root and a child module, in each direction — and what deliberately can't?

<details><summary>Answer (read after attempting aloud)</summary>

**Down (root → child):** the child's `variable`s, set at the `module "x" { ... }` call site. **Up (child → root):** the child's `output`s, read as `module.x.<output_name>`. That's *all* that crosses. A child module cannot read the root's variables or locals, cannot reach a sibling module's resources, and the root cannot reference a child's resources directly (only through its outputs). This encapsulation is the point: the module is a black box with a typed interface, so you can reuse it across roots and reason about it in isolation. Provider *configuration* is the one thing that flows down implicitly (the child inherits the root's configured provider) unless you explicitly pass providers.

</details>

2. You moved three resources into modules and `plan` said `3 to add, 3 to destroy` before you fixed it. Why, and what exactly does a `moved` block change?

<details><summary>Answer (read after attempting aloud)</summary>

Terraform identifies every resource in state by its **address**, and a resource's address includes its module path. Moving `docker_container.redis` into a module changed its address to `module.redis.docker_container.this`. Terraform diffs config against state by address, so it saw the old address disappear (→ destroy) and a new address appear (→ create) — with no idea they're the same thing. A `moved` block changes **only state**: it relabels the state entry from the old address to the new one, so the diff sees continuity instead of a delete+create. Nothing in reality is touched — the plan drops to `0/0/0`. It's the safe, code-reviewed alternative to the imperative `terraform state mv`.

</details>

3. Redis and api both call the same module, but redis publishes no host port and api publishes 9071. How does one module express both?

<details><summary>Answer (read after attempting aloud)</summary>

Via the `published_port` variable typed as `object({...})` with `default = null`, plus a `dynamic "ports"` block whose `for_each` is `var.published_port == null ? [] : [var.published_port]`. When a caller omits it (redis), the variable is `null`, the list is empty, and the `ports {}` block is generated **zero** times — no host port. When api passes the object, the list has one element and the block is generated **once**. Same mechanism handles the optional `volume` (only db passes one) and `healthcheck`. That's the module design lesson: model optional structure as object-or-null + a dynamic block, and one module covers every real shape without a copy per service.

</details>

4. What does `terraform init` do for a module that it doesn't do for a plain resource, and what error tells you that you forgot?

<details><summary>Answer (read after attempting aloud)</summary>

`init` **installs/registers modules**: for a local path it records the source mapping; for a registry or git module it downloads the module source into `.terraform/modules/`. This is separate from provider installation. Adding or changing a `module` block requires re-running `init` before `plan`/`apply` will work — the tell-tale error is `Module not installed` / `Module source has changed, run terraform init`. Same idea as re-running `init` when you add a new provider: `init` is the "resolve and fetch my dependencies" step, and modules are dependencies too.

</details>

## Clean up

```bash
terraform destroy -auto-approve
```

`keep_locally` images survive; the api image and pgdata volume go. Commit the whole tree: root `.tf` files (including `moved.tf`), the new `modules/service/*.tf`, and both `.terraform.lock.hcl` files. Never commit `*.tfvars` or `*.tfstate`.

```bash
git status --short    # .tf files under capstone-stack/ and modules/service/ only
```
