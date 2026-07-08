# Lab 1 — First apply: init → plan → apply → destroy

**Goal:** run the full Terraform loop against the Docker daemon — one nginx container on host port 9070 — and then open `terraform.tfstate` and read Terraform's memory with your own eyes. Every later lab (and every Terraform interview) stands on what this lab makes concrete.

## The mental map (read this first)

Four commands, one loop. You'll run this loop thousands of times in a DevOps career:

```
   you edit .tf files
        │
        ▼
  terraform init      ← once per folder: download the PROVIDERS
        │                (translator plugins) + write a lockfile
        ▼
  terraform plan      ← dry run: refresh → diff(config, state) → proposal
        │                NOTHING changes yet. Read it like a code review.
        ▼
  terraform apply     ← do the proposal, then WRITE THE NEW STATE
        │
        ▼
  terraform destroy   ← plan-in-reverse: remove everything state says is yours
```

And the cast of characters in the folder you're about to create:

```
 infra/terraform/hello-nginx/
 ├── main.tf                  ← your desired state (the ONLY file you write)
 ├── .terraform/              ← init's downloads: the provider binary lives here (gitignored)
 ├── .terraform.lock.hcl      ← exact provider versions pinned (COMMIT this — it's uv.lock for providers)
 └── terraform.tfstate        ← Terraform's memory, appears after first apply (gitignored, NEVER commit)
```

The provider is the piece worth pausing on. Terraform core doesn't know what a container is — it only knows "resources, references between them, diff, apply." The **kreuzwerker/docker provider** is a separate Go binary that translates that into calls on the Docker daemon's socket — the same `/var/run/docker.sock` every `docker` CLI command you've ever typed went through. Swap the provider and the same four commands manage AWS, Kubernetes, GitHub, Cloudflare… That's the whole trick of Terraform: one workflow, pluggable translators.

## Steps

### 1. Install Terraform

Homebrew's core `terraform` formula is frozen at 1.5.7 — the last open-source (MPL) release before the BUSL license change — so the current version comes from HashiCorp's own tap:

```bash
brew tap hashicorp/tap
brew install hashicorp/tap/terraform
terraform -version
```

Expect `Terraform v1.15.x on darwin_arm64` (1.15.7 at the time of writing). If `terraform -version` prints a `Your version of Terraform is out of date` note later in the section, ignore it — patch releases move fast; anything 1.15+ runs every lab here.

### 2. Create the folder and write `infra/terraform/hello-nginx/main.tf`

From the repo root:

```bash
mkdir -p infra/terraform/hello-nginx
cd infra/terraform/hello-nginx
```

Now the config. The comments are the lesson — read them as you type/paste:

```hcl
terraform {                          # settings for terraform ITSELF (not for any resource)
  required_version = ">= 1.15.0"     # refuse to run under an older CLI — loud failure > silent drift

  required_providers {
    docker = {                       # the local nickname you'll use in this config
      source  = "kreuzwerker/docker" # registry address: namespace/name on registry.terraform.io
      version = "~> 4.0"             # "any 4.x" — same idea as pinning a major in pyproject
    }
  }
}

provider "docker" {                  # configure the translator
  host = "unix:///var/run/docker.sock"   # talk to the same socket the docker CLI uses
}

resource "docker_image" "nginx" {    # resource TYPE + a LOCAL NAME (like a variable name)
  name = "nginx:1.29-alpine"         # pull-by-tag, exactly like `docker pull`
}

resource "docker_container" "hello" {
  name  = "tf-hello"                          # the actual container name docker ps will show
  image = docker_image.nginx.image_id         # a REFERENCE — this line builds the dependency graph

  ports {
    internal = 80                    # container side — conventional, the image's business
    external = 9070                  # host side — our 9000-series rule, Section 6 block is 9070–9079
  }
}
```

#### Read it like a story — HCL anatomy in one pass

- **Everything is a block:** a *type* (`terraform`, `provider`, `resource`), zero or more *labels* (`"docker_image" "nginx"`), and a body of `key = value` arguments. That's the entire grammar; you already speak it.
- **`resource "docker_image" "nginx"`** — the second label is Terraform-internal, a variable name. It could be `"web"` or `"foo"`; nothing in Docker ever sees it. The pair `docker_image.nginx` is the resource's **address** — how state, plan output, and later `moved`/`import` blocks refer to it. Address ≠ real name: the *container's* name is the `name = "tf-hello"` argument.
- **`image = docker_image.nginx.image_id`** is the most important line in the file. It's not a string — it's a reference to another resource's *attribute*, one that only exists after the image is pulled. Terraform sees the reference and concludes: image first, then container. **References ARE the dependency graph** — nobody writes "step 1, step 2". You've met this exact idea before: BuildKit ran your Dockerfile stages as a dependency graph, not a script (Section 1, Lab 3). Same principle, bigger scope.
- **Why `image_id` and not just `name = "nginx:1.29-alpine"` twice?** `image_id` is the content digest (Section 1 Lab 6: the immutable hash, not the re-stickable tag). Pinning the container to the digest means a moved tag shows up as a *visible plan diff* instead of a silent surprise — the `:latest`-bit-me lesson, now enforced by tooling. (If `1.29` has aged out of Docker Hub by the time you run this, any current `nginx:<x>-alpine` tag works — pin whatever you pull.)
- **`ports {}` is a nested block** (no `=`) — HCL's way of grouping structured settings, same job as an indented YAML map in compose.

#### The socket line, pre-explained

`unix:///var/run/docker.sock` works on your Mac because Docker Desktop maintains that path as a symlink to the real per-user socket. If a later `plan` ever greets you with `Cannot connect to the Docker daemon`, the diagnosis order is: **(1)** is Docker Desktop actually running? **(2)** `docker context ls` — read the endpoint of the active context; if there's no `/var/run/docker.sock` on your machine, Docker Desktop → Settings → Advanced → "Allow the default Docker socket to be used", or point the provider at the per-user path it shows (`unix:///Users/<you>/.docker/run/docker.sock`).

### 3. `terraform init` — hire the translator

```bash
terraform init
```

What the output tells you, block by block:

```
Initializing the backend...          ← where state will live; silence = "local file", fine for now (Lab 6 upgrades this)
Initializing provider plugins...
- Finding kreuzwerker/docker versions matching "~> 4.0"...
- Installing kreuzwerker/docker v4.4.0...        ← downloading an actual Go binary into .terraform/
- Installed kreuzwerker/docker v4.4.0 (self-signed, key ID BD080C4571C6104C)
Terraform has created a lock file .terraform.lock.hcl ...
Terraform has been initialized!
```

Two artifacts appeared. `.terraform/` holds the provider binary (~20MB — this is why it's gitignored, and why a fresh clone always needs `init`). `.terraform.lock.hcl` records the **exact** provider version + checksums that got resolved — the same job `uv.lock` does for Python deps, and the same `--frozen` philosophy: teammates and CI get *identical* providers, not "whatever `~> 4.0` resolves to this week". It gets committed.

### 4. Gitignore state BEFORE anything else exists

The state file you're about to create will eventually hold real resource attributes — in Lab 3, a database password in plaintext. This is a public repo; make the mistake impossible now. Add to the **repo-root** `.gitignore`:

```gitignore
# terraform — state is secret, providers are re-downloadable, tfvars will hold real values
**/.terraform/
*.tfstate
*.tfstate.*
*.tfvars
crash.log
```

Note what's *not* listed: `.terraform.lock.hcl` stays committed, and so do all `.tf` files — they're the point of the exercise. (Some teams do commit non-secret `.tfvars`; ours will contain a password in Lab 3, so blanket-ignore is the right call here.)

### 5. `terraform plan` — read the proposal

```bash
terraform plan
```

The output, annotated — this format is the thing to become fluent in:

```
Terraform used the selected providers to generate the following execution plan.
Resource actions are indicated with the following symbols:
  + create                                ← the legend; you'll also meet  ~  -  and  -/+  in Lab 3

Terraform will perform the following actions:

  # docker_image.nginx will be created
  + resource "docker_image" "nginx" {
      + image_id    = (known after apply)  ← can't know a digest before pulling — a promise, not a value
      + name        = "nginx:1.29-alpine"
      ...
    }

  # docker_container.hello will be created
  + resource "docker_container" "hello" {
      + name        = "tf-hello"
      + image       = (known after apply)  ← inherits the promise via your reference
      ...dozens of attributes...           ← every knob the provider COULD set, mostly defaults — normal noise
    }

Plan: 2 to add, 0 to change, 0 to destroy.
```

Three things to internalize: **(1)** the summary line `2 to add, 0 to change, 0 to destroy` is what you check first, always — a deploy that should change one thing but plans 14 is how outages get caught before they happen; **(2)** `(known after apply)` marks values that only exist once reality does; **(3)** absolutely nothing has happened — `docker ps` right now shows no `tf-hello`. Plan is a pure read.

### 6. `terraform apply` — make reality match the file

```bash
terraform apply
```

It re-prints the plan and stops at `Do you want to perform these actions?` — type `yes` (in CI you'd use `-auto-approve` or apply a saved plan file; interactively, the prompt is the code-review moment). Then:

```
docker_image.nginx: Creating...
docker_image.nginx: Still creating... [10s elapsed]     ← pulling layers; the provider is doing `docker pull`
docker_image.nginx: Creation complete after 12s [id=sha256:...nginx:1.29-alpine]
docker_container.hello: Creating...                     ← note: STARTED ONLY AFTER the image finished
docker_container.hello: Creation complete after 1s [id=<64-hex container id>]

Apply complete! Resources: 2 added, 0 changed, 0 destroyed.
```

The ordering you just watched — image fully created *before* the container began — is the dependency graph executing. You never specified an order; the `image_id` reference did.

```bash
docker ps --filter name=tf-hello     # Up …  0.0.0.0:9070->80/tcp
curl -s localhost:9070 | head -4     # nginx welcome page HTML
```

To Docker, this container is 100% ordinary — made by the same API calls the CLI would make. The only difference is who remembers it, which brings us to:

### 7. Open the memory — `terraform.tfstate`

```bash
terraform state list                 # the inventory, by address
#   docker_image.nginx
#   docker_container.hello

terraform state show docker_container.hello   # every attribute state recorded for one resource
```

Now the raw file (read-only look — you never hand-edit state):

```bash
jq '{version, serial, lineage, resources: [.resources[] | {type, name}]}' terraform.tfstate
```

Expect something like:

```json
{
  "version": 4,                       ← state FORMAT version (not your app's)
  "serial": 1,                        ← increments on every state change — an edit counter
  "lineage": "3f8c…-uuid",            ← identity of this state's lifeline, born at first write;
                                        backends use serial+lineage to refuse stale/foreign overwrites
  "resources": [ {"type":"docker_container","name":"hello"}, {"type":"docker_image","name":"nginx"} ]
}
```

And the punchline — the claim ticket itself:

```bash
jq -r '.resources[] | select(.name=="hello") | .instances[0].attributes.id' terraform.tfstate
docker inspect -f '{{.ID}}' tf-hello
```

**Same 64-hex ID, twice.** That mapping — address `docker_container.hello` → real-world ID `9a55…` — is what state fundamentally *is*. Config says *what you want*, reality *is what exists*, state is the only thing that knows **which pieces of reality are yours**. Delete this file and `tf-hello` keeps running, but Terraform would plan to create a second one — it has amnesia about the first. (Lab 6 is entirely about the care and feeding of this file.)

### 8. Prove idempotence, then watch a change

```bash
terraform plan
```

`No changes. Your infrastructure matches the configuration.` — the refresh looked at the real container, compared with config, found agreement. This is `docker compose up` on an unchanged file, printing "everything up-to-date". Safe to run any time, as often as you like.

Now change one thing. Add inside the `docker_container` block:

```hcl
  restart = "unless-stopped"
```

```bash
terraform plan
```

Expect the third symbol:

```
  ~ resource "docker_container" "hello" {
      ~ restart = "no" -> "unless-stopped"
        name    = "tf-hello"
        ...
    }

Plan: 0 to add, 1 to change, 0 to destroy.
```

`~` = update in place — the provider can flip a restart policy on a live container (it's `docker update` under the hood). If your provider version instead shows `-/+ destroy and then create replacement`, read the attribute list for the `# forces replacement` annotation — that marker is exactly how you find out *why* something can't be changed in place. Either way: apply it, and note the container kept running (or was replaced) precisely as the symbols promised.

## Verify

- `curl -s localhost:9070` returns nginx HTML; `terraform plan` says `No changes.`
- `terraform state list` shows both resources, and you matched the container ID in state to `docker inspect`'s.
- `git status` shows `main.tf` + `.terraform.lock.hcl` as the only new tracked files — no `.terraform/`, no `*.tfstate`.

**Answer aloud** (then check):

1. What did `terraform init` actually download, and why does the lock file get committed while the state file never does?

<details><summary>Answer (read after attempting aloud)</summary>

`init` downloaded the **provider** — a standalone Go binary (kreuzwerker/docker) into `.terraform/` — plus wrote `.terraform.lock.hcl` pinning its exact version and checksums. The lock file is committed for the same reason `uv.lock` is: everyone (and CI) must resolve the *identical* provider, not "some 4.x" — reproducibility. The state file is never committed because (1) it contains real resource attributes, eventually including secrets in plaintext, and (2) git is the wrong concurrency model for it — two people applying from different clones with different state copies corrupt each other's view of reality. Sharing state is a job for a locking backend (Lab 6), not version control.

</details>

2. `terraform plan` printed `(known after apply)` for `image_id`. Why can't it know, and what does that tell you about what plan is?

<details><summary>Answer (read after attempting aloud)</summary>

`image_id` is the image's content digest — a hash of bytes that haven't been pulled yet. No pull has happened because **plan is a pure read**: refresh reality's picture, diff against config, print a proposal. Values born during creation (digests, cloud-assigned IDs, IPs) are shown as promises. It's the same content-addressing lesson from Section 1: you can't know a hash before the content exists.

</details>

3. Nothing in your file says "pull the image before starting the container." How does Terraform know the order — and where have you seen this exact idea before?

<details><summary>Answer (read after attempting aloud)</summary>

The expression `image = docker_image.nginx.image_id` is a *reference*, and references are edges in a dependency graph. Terraform walks that graph — dependencies first, independent resources in parallel. Same principle as BuildKit in Section 1 Lab 3: what looks like a top-to-bottom file is actually a graph, and order is *derived*, never scripted. (When there's no natural reference but order still matters, `depends_on` states the edge explicitly — Lab 2 uses it.)

</details>

4. If someone deleted `terraform.tfstate` right now, what would `terraform apply` do, and why is that the whole argument for state's existence?

<details><summary>Answer (read after attempting aloud)</summary>

Apply would plan `2 to add` and create a **duplicate** image reference and a container (failing on the name collision, in this case — `tf-hello` exists). Terraform has amnesia: config still says what you want, reality still has the old container, but the *link* between them — "that specific container is mine, here's its ID" — lived only in state. State exists because most APIs (unlike compose's single-daemon label trick) give you no universal way to ask "which of these thousands of resources belong to this config?" The ticket book is the ownership record.

</details>

## Clean up

```bash
terraform destroy
```

Read its plan — same format, all `-` symbols, `Plan: 0 to add, 0 to change, 2 to destroy` — then `yes`. Note the order: container first, *then* image — the dependency graph walked in reverse. Then two observations worth 10 seconds:

```bash
docker ps -a --filter name=tf-hello    # gone
docker images nginx                    # 1.29-alpine is GONE TOO
```

Destroy removed the *image from your machine*, not just the container — `docker_image` was a managed resource, and its default is delete-on-destroy. Harmless here; rude in Lab 2, where redis/postgres images are shared with your still-running compose stack — which is exactly what `keep_locally = true` is for. Remember this moment.

Keep the folder (`main.tf`, lock file) — commit both. `terraform.tfstate` should now be empty-ish (`"resources": []`) and stays gitignored regardless.
