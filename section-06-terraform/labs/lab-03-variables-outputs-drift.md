# Lab 3 — Variables, outputs, locals, and drift

**Goal:** turn Lab 2's hard-coded stack into a *parameterized* one — inputs (`variable`), computed intermediates (`locals`), and published results (`output`) — fed by a `terraform.tfvars` file. Then, the payoff every interview probes: **cause drift on purpose** by hand-deleting a container behind Terraform's back, and read the plan that catches it. You'll leave this lab fluent in all four plan symbols (`+ - ~ -/+`) from having *made each one appear*.

## The mental map (read this first)

A Terraform root is a little function. Variables are its parameters, locals are its local variables, outputs are its return values, and the resources are the body:

```
      terraform.tfvars                     variables.tf
      "the arguments I'm                   "the parameters this
       calling with today"                  root accepts + defaults"
              │                                    │
              └──────────────┬─────────────────────┘
                             ▼
                    var.image_tag, var.api_port, var.pg_password …
                             │
                             ▼
                        locals.tf  ── computed once, reused ──▶  local.labels, local.names
                             │
                             ▼
                    resources (main.tf)  ← the body: builds reality
                             │
                             ▼
                        outputs.tf  ──▶ "return values": the api URL, the container IDs
```

**Why split one `main.tf` into several files?** Terraform loads *every* `.tf` file in the folder and concatenates them — filenames are for humans, not the parser. `variables.tf` / `locals.tf` / `outputs.tf` / `main.tf` is pure convention, but it's the convention every real codebase uses, and reviewers expect it. Order across files doesn't matter (it's a graph, not a script — Lab 1's lesson), so you can define an output before the resource it references.

**And the drift idea, stated precisely.** State is Terraform's belief about reality. `plan` starts with a **refresh**: it asks the real Docker daemon "is everything state remembers still true?" *Drift* is any gap it finds — a resource someone changed or deleted outside Terraform. Terraform's reaction is not to panic but to *plan the correction*: if you hand-deleted a container, refresh notices it's gone, and plan proposes `+ create` to make reality match config again. **Drift detection is just `plan`'s refresh step doing its job** — there is no separate "drift command," which is itself a good thing to be able to say.

```
   CONFIG says: 3 containers        STATE remembered: 3 containers
                          you: `docker rm -f capstone-tf-redis`  ← change behind TF's back
                                         │
                                         ▼
                          terraform plan → refresh sees redis GONE from reality
                                         → updates state's picture (redis: gone)
                                         → diffs config(3) vs reality(2)
                                         → proposes  + create redis   ← drift, caught and corrected
```

## Steps

### 1. Work in the Lab 2 folder, but re-stand-up the stack

```bash
cd infra/terraform/capstone-stack
terraform apply -auto-approve      # rebuild what Lab 2's cleanup destroyed
```

`-auto-approve` skips the `yes` prompt — fine here because you already trust this plan; **never** reflexive in real work. You now have the eight-resource stack running again on port 9071.

### 2. Extract inputs into `variables.tf`

Create `infra/terraform/capstone-stack/variables.tf`:

```hcl
variable "project" {
  description = "Name prefix for all resources — one knob to namespace the whole stack"
  type        = string
  default     = "capstone-tf"
}

variable "api_port" {
  description = "Host port for the api (must stay in the Section 6 block)"
  type        = number
  default     = 9071

  validation {
    condition     = var.api_port >= 9070 && var.api_port <= 9079
    error_message = "api_port must be in the Section 6 host-port block 9070–9079."
  }
}

variable "redis_image" {
  description = "Redis image tag to pull"
  type        = string
  default     = "redis:8-alpine"
}

variable "pg_image" {
  description = "Postgres image tag to pull"
  type        = string
  default     = "postgres:18-alpine"
}

variable "pg_password" {
  description = "Postgres superuser password — LOCAL LAB ONLY"
  type        = string
  default     = "localdev"
  sensitive   = true            # keeps it out of plan/apply console output (NOT out of state — see below)
}
```

#### `type`, `validation`, and `sensitive`, pre-explained

- **`type`** is a real contract, not a hint. Pass a string where a `number` is expected and Terraform rejects it before touching anything — the same "fail loud at the boundary" instinct as a typed function signature.
- **`validation`** runs your own rule at plan time. Here it enforces the host-port rule *this course* lives by, turning a convention into a guardrail — try `-var api_port=8080` later and watch it refuse.
- **`sensitive = true`** stops Terraform from *printing* the value in `plan`/`apply` output (you'll see `(sensitive value)`). Critical caveat, and a favorite gotcha question: **it does NOT encrypt the value in state.** The password still sits in `terraform.tfstate` as plaintext. That's the entire reason state is gitignored and, in real life, stored in an encrypted, access-controlled backend (Lab 6). `sensitive` protects your terminal and CI logs, not your state file.

### 3. Add computed values in `locals.tf`

Create `infra/terraform/capstone-stack/locals.tf`:

```hcl
locals {
  # derive every resource name from the one `project` variable — change it once,
  # rename everything consistently. This is the DRY payoff of parameterizing.
  names = {
    network = "${var.project}"
    volume  = "${var.project}-pgdata"
    api     = "${var.project}-api"
    redis   = "${var.project}-redis"
    db      = "${var.project}-db"
  }

  # labels stamped on every container — the kind of metadata real infra uses
  # for cost allocation and "who owns this?" queries.
  common_labels = {
    "managed-by" = "terraform"
    "project"    = var.project
    "section"    = "06"
  }
}
```

**variable vs local — the distinction that trips people:** a `variable` is an *input* you (or a tfvars file, or CI) set from outside. A `local` is *computed inside* the config from variables and other locals — you cannot pass a value to a local from the command line. Rule of thumb: if a human or another system should be able to change it per-run, it's a variable; if it's derived and just saves repetition, it's a local. `local.names.redis` here is derived from `var.project`; nobody sets `local.names` directly.

### 4. Rewire `main.tf` to use the variables and locals

Edit `main.tf` — replace the hard-coded strings with references. The diff, block by block:

```hcl
resource "docker_network" "capstone" {
  name = local.names.network          # was "capstone-tf"
}

resource "docker_volume" "pgdata" {
  name = local.names.volume           # was "capstone-tf-pgdata"
}

resource "docker_image" "redis" {
  name         = var.redis_image       # was "redis:8-alpine"
  keep_locally = true
}

resource "docker_image" "db" {
  name         = var.pg_image          # was "postgres:18-alpine"
  keep_locally = true
}
```

For the containers, add labels and swap the hard-coded values. Redis:

```hcl
resource "docker_container" "redis" {
  name  = local.names.redis
  image = docker_image.redis.image_id

  dynamic "labels" {                   # attach every common_label as a labels{} block
    for_each = local.common_labels
    content {
      label = labels.key
      value = labels.value
    }
  }

  networks_advanced {
    name    = docker_network.capstone.name
    aliases = ["redis"]                # the DNS name stays fixed — it's an app contract
  }

  healthcheck {
    test     = ["CMD", "redis-cli", "ping"]
    interval = "5s"
    timeout  = "3s"
    retries  = 5
  }
}
```

Do the same `name`/`labels` swap for `docker_container.db` (add `env = ["POSTGRES_PASSWORD=${var.pg_password}"]`) and `docker_container.api` (use `local.names.api`, and `external = var.api_port` in the `ports` block). Keep the `aliases = ["db"]`, the volume mount at `/var/lib/postgresql`, and the `depends_on`.

#### The `dynamic` block, pre-explained

A `dynamic "labels"` block is a `for_each` loop that *generates* nested blocks. `local.common_labels` is a map of three entries, so this emits three `labels { label=… value=… }` blocks — one per entry — without you writing them out. `labels.key`/`labels.value` are the current iteration's map key and value. It's the HCL answer to "I have N of these nested blocks and don't want to copy-paste." You'll meet the same `for_each` on *resources themselves* in Lab 4. (Note the naming collision that reads oddly at first: the block type is `labels`, and the iterator is also named `labels` — the iterator name defaults to the block type. Both are correct; the inner `labels.key` is the loop variable, the outer is what kind of block to produce.)

### 5. Publish results in `outputs.tf`

Create `infra/terraform/capstone-stack/outputs.tf`:

```hcl
output "api_url" {
  description = "Where to curl the running api"
  value       = "http://localhost:${var.api_port}"
}

output "container_ids" {
  description = "The real Docker IDs of every container in the stack"
  value = {
    api   = docker_container.api.id
    redis = docker_container.redis.id
    db    = docker_container.db.id
  }
}

output "pg_password" {
  description = "The DB password (marked sensitive so it won't print)"
  value       = var.pg_password
  sensitive   = true             # required: referencing a sensitive value in an output
}                                 # that isn't marked sensitive is an ERROR, not a warning
```

Outputs are a root module's *return values*. Two real uses: (1) a human runs `terraform output api_url` instead of hunting through `docker ps`; (2) one module's outputs feed another module's variables (Lab 4) — and remote state lets a *different* root read them (the "networking team publishes the VPC ID, the app team consumes it" pattern, Lab 6). If you reference a `sensitive` value in an output, Terraform forces you to mark the output sensitive too — it refuses to let a secret leak through the back door.

### 6. Create `terraform.tfvars` — the arguments for this run

Create `infra/terraform/capstone-stack/terraform.tfvars`:

```hcl
project     = "capstone-tf"
api_port    = 9071
pg_password = "localdev"
```

Terraform auto-loads `terraform.tfvars` (and `*.auto.tfvars`) — no flag needed. Precedence, highest wins: `-var` on the CLI > `-var-file` > `terraform.tfvars`/`*.auto.tfvars` > variable `default`. **This file is gitignored** (Lab 1's `.gitignore` added `*.tfvars`) because it holds `pg_password` — the same "state is public-repo poison" reasoning. Teams that keep non-secret tfvars in git split secrets into a separate `*.auto.tfvars` that stays ignored; blanket-ignore is the safe call for a public repo.

### 7. Apply the refactor — it should be a *no-op*

```bash
terraform plan
```

If you rewired names to the same values, the headline is the one you want after a pure refactor:

```
No changes. Your infrastructure matches the configuration.
```

**This is the goal of a good refactor: you changed how the config is *written* without changing what it *builds*.** The names resolve to the same strings, so state sees no diff. The one exception: you *added* labels to the containers, so you'll likely see:

```
  ~ resource "docker_container" "redis" {
      + labels { label = "managed-by"  value = "terraform" }   ← new nested blocks
      ...
    }
Plan: 0 to add, 3 to change, 0 to destroy.
```

`~` on three containers, adding label blocks. Whether labels force an in-place update or a replace depends on the provider — read for `# forces replacement`. Apply it:

```bash
terraform apply -auto-approve
terraform output api_url            # http://localhost:9071
terraform output container_ids      # the map of real IDs
terraform output pg_password        # <sensitive> — run `terraform output -raw pg_password` to actually see it
```

### 8. Cause drift on purpose — the main event

Reality is about to change behind Terraform's back. Delete a container by hand:

```bash
docker rm -f capstone-tf-redis
docker ps --filter name=capstone-tf     # only api + db now — redis is gone
```

Now the app is broken (`curl -s localhost:9071/visits` will error — no redis to answer). Ask Terraform what it thinks:

```bash
terraform plan
```

```
docker_container.redis: Refreshing state... [id=<old id>]
  # docker_container.redis has been deleted, so it must be created
  # (refresh found the resource state recorded no longer exists in reality)

  # docker_container.redis will be created
  + resource "docker_container" "redis" {
      + name = "capstone-tf-redis"
      ...
    }

Plan: 1 to add, 0 to change, 0 to destroy.
```

Read what just happened, because this is the interview answer made concrete: **the refresh step queried Docker, discovered the container state remembered was gone, updated state to reflect that, then diffed config (wants redis) against the new reality (no redis) and proposed `+ create`.** No special command. Drift is just `plan` telling the truth. Heal it:

```bash
terraform apply -auto-approve
curl -s localhost:9071/visits           # works again — the counter is back
```

Terraform re-created *only* redis (the other two were untouched — it corrects the gap, not the whole world). This self-healing-on-next-apply is the same reconcile instinct compose's `up` had (Section 4), and the exact thing Kubernetes does *continuously* (Section 4) and Argo CD does *automatically on drift* (Section 9). Same idea, escalating automation.

### 9. Force the last symbol you haven't made appear: `-/+`

You've now produced `+`, `-`, and `~`. The fourth — `-/+` destroy-and-recreate — happens when you change an attribute the provider *can't* edit in place. Change the redis container's *name* (a real identity, not a live-tunable knob). Temporarily edit `locals.tf`:

```hcl
    redis = "${var.project}-redis-v2"      # was "${var.project}-redis"
```

```bash
terraform plan
```

```
  -/+ resource "docker_container" "redis" {
      ~ name = "capstone-tf-redis" -> "capstone-tf-redis-v2"  # forces replacement
      ...
    }
Plan: 1 to add, 1 to change, 0 to destroy.
```

There it is: `-/+` with the `# forces replacement` annotation naming the culprit attribute. A container can't be renamed live, so the only way to reach the desired state is *destroy the old one and create a new one* — a moment of downtime the plan is warning you about. **Reading `-/+` before approving is the single most important plan-literacy skill:** it's the difference between "this changes a label" and "this deletes my database and makes a new empty one." Revert the edit (put `-redis` back) so the stack stays consistent, and `terraform apply -auto-approve` to settle.

## Verify

- `terraform output api_url` prints `http://localhost:9071`; `terraform output -raw pg_password` prints the password only with `-raw`.
- After `docker rm -f capstone-tf-redis`, `terraform plan` proposes exactly `1 to add` and re-creating it heals `/visits`.
- You made all four symbols appear and can say what each means.

**Answer aloud** (then check):

1. You marked `pg_password` as `sensitive`. A teammate says "great, the password is protected now." What's the precise correction?

<details><summary>Answer (read after attempting aloud)</summary>

`sensitive = true` only suppresses the value from **console output** (plan/apply/output print `(sensitive value)`). It does **nothing** to state: `pg_password` sits in `terraform.tfstate` as plaintext, readable by anyone with the file. So the protection is against shoulder-surfing and CI-log leaks, not against state exposure. The real defenses are: gitignore state (done), store it in an encrypted/access-controlled remote backend (Lab 6), and for actual secrets pull them from a secrets manager at apply time rather than putting them in tfvars at all. Interviewers love this one because it separates people who read the tooltip from people who read the state file.

</details>

2. There's no `terraform drift` command. So how does Terraform detect drift, and what does it do about it?

<details><summary>Answer (read after attempting aloud)</summary>

Drift detection is the **refresh** step at the start of every `plan` (and `apply`). Refresh queries each provider's real API for the current state of every managed resource and updates state's picture. Then the normal diff runs: config vs (refreshed) reality. Any gap — a hand-deleted container, a console-edited setting — shows up as a proposed action to *reconcile* back to config: `+` to recreate what's missing, `~`/`-/+` to fix a changed attribute. Terraform's philosophy is corrective, not alarmist: it doesn't page you, it plans the fix. (`terraform plan -refresh-only` exists to see drift *without* also planning config changes — pure "what moved?")

</details>

3. Walk me through all four plan symbols with a one-line example of each from this lab.

<details><summary>Answer (read after attempting aloud)</summary>

- **`+` create** — the hand-deleted redis container: config wants it, reality lacks it, add it.
- **`-` destroy** — any `terraform destroy` line, or a resource you removed from config.
- **`~` update in place** — adding `labels` blocks to a running container; the provider mutates it without recreating (here, effectively a metadata update).
- **`-/+` destroy and recreate** — renaming the redis container; `name` is an immutable identity the provider can't change live, flagged `# forces replacement`. This is the dangerous one — it means downtime and, for stateful resources, potential data loss. Always read the `# forces replacement` annotation to know *which* attribute triggered it.

</details>

4. Why split `main.tf` into `variables.tf` / `locals.tf` / `outputs.tf` at all — does Terraform care?

<details><summary>Answer (read after attempting aloud)</summary>

Terraform does **not** care — it loads and concatenates every `.tf` file in the directory regardless of name, and evaluation order is graph-derived, not file-order. The split is 100% for humans: reviewers know exactly where to look for the interface (variables/outputs) versus the implementation (main), and it scales — a real module's `main.tf` would be unreadable with everything inline. It's the same reason you don't put an entire service in one Python file even though the interpreter wouldn't mind.

</details>

## Clean up

```bash
terraform destroy -auto-approve
```

Same `keep_locally` behavior as Lab 2 — pulled images survive, the api image and the pgdata volume go. Commit `main.tf`, `variables.tf`, `locals.tf`, `outputs.tf`, and `.terraform.lock.hcl`. **Do NOT commit `terraform.tfvars`** (it holds the password and is gitignored) or `terraform.tfstate`. Quick check:

```bash
git status --short    # should list the .tf files, never *.tfvars or *.tfstate
```
