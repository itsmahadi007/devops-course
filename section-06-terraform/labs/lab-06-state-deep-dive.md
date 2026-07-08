# Lab 6 — State deep dive: locking, import, state rm, remote backends

**Goal:** everything so far *used* state; this lab is about state itself — the thing half of all IaC interviews open with. You'll adopt a hand-created container into Terraform with `import` (the "our infra predates our Terraform" gig), remove a resource from management *without destroying it* with `state rm`, understand locking from first principles (why two applies corrupt state and what stops them), and know exactly when NOT to reach for Terraform. An **OPTIONAL** clearly-marked extra puts your state in a real AWS S3 backend with a same-day teardown, so the "why S3?" answer comes from your own hands.

## The mental map (read this first)

State is the ledger from Lab 1 — address → real-world ID + a snapshot of every attribute. This lab manipulates that ledger directly, and adds the two facts that only matter once state is *shared*:

```
   ┌──────────────────────── the state file ────────────────────────┐
   │  version   serial   lineage   [ resource → id + attributes … ]  │
   └─────────────────────────────────────────────────────────────────┘
        ▲            ▲              ▲                    ▲
        │            │              │                    │
   import ──────────┘              │              state rm ──────────┘
   "add an EXISTING real           │              "forget this from state,
    resource to the ledger"        │               leave reality alone"
                                    │
                       LOCKING ─────┘   "only one writer at a time, or the
                                         ledger corrupts" — matters the moment
                                         state is shared (remote backend)
```

**Locking, from first principles.** `apply` is read-modify-write on the whole state file: read current state, compute the diff, do the actions, write new state. If two people apply at once, they both read the *same* starting state, both write, and the second write clobbers the first — now state believes resources exist that were destroyed, or forgets ones that were created. Corruption. The defense is a **lock**: before writing, a backend acquires an exclusive lock; a second apply blocks (or errors `Error acquiring the state lock`) until the first releases. The local backend locks with a tiny `.terraform.tfstate.lock.info` file on disk; a remote backend needs a *distributed* lock (historically a DynamoDB table for S3; now S3's own conditional-write locking). No lock + shared state = the classic way a team destroys prod.

**Remote state, in one sentence:** move the file off your laptop to a shared, versioned, encrypted, *lockable* store so a team (and CI) share one source of truth — because the local file model breaks the instant more than one person or machine applies.

## Steps

### 1. Re-open Lab 1's memory and read the whole ledger

```bash
cd infra/terraform/hello-nginx
terraform apply -auto-approve       # bring the nginx-on-9070 back
```

Now read state's bookkeeping header — the three fields that make sharing safe:

```bash
jq '{version, serial, lineage, terraform_version}' terraform.tfstate
```

```json
{
  "version": 4,               ← STATE FORMAT version (Terraform's, not your app's)
  "serial": 3,                ← bumped on EVERY write; a backend rejects a write whose serial is stale
  "lineage": "b1a2…-uuid",    ← this state's identity, born at first init; rejects a write from a DIFFERENT lineage
  "terraform_version": "1.15.7"
}
```

`serial` + `lineage` are how a backend catches a stale or foreign write even beyond locking: "you're trying to write serial 3 but state is already at serial 5" → refused. Also notice a sibling file appeared:

```bash
ls terraform.tfstate*        # terraform.tfstate  AND  terraform.tfstate.backup
```

`terraform.tfstate.backup` is the *previous* state, kept automatically — your one-step undo if a write goes wrong. Both are gitignored.

### 2. `import` — adopt a resource Terraform didn't create

This is the freelance-gig core skill: infrastructure exists, but no Terraform knows about it. Simulate it — create a container **by hand**, the way a predecessor would have:

```bash
docker run -d --name legacy-cache -p 9073:6379 redis:8-alpine
docker ps --filter name=legacy-cache        # running, but NO terraform anywhere knows it exists
```

Now adopt it. Add an `import` block to a new file `infra/terraform/hello-nginx/import.tf`:

```hcl
import {
  to = docker_container.legacy_cache          # the ADDRESS you want it to live at in state
  id = "legacy-cache"                          # the real-world ID the provider imports by (name works for docker)
}
```

The `import` block (Terraform 1.5+) is the modern, declarative way — reviewable in a PR, unlike the old imperative `terraform import` command. But you still need a `resource` block for it to import *into*. Let Terraform write a first draft for you:

```bash
terraform plan -generate-config-out=generated.tf
```

```
docker_container.legacy_cache: Preparing import... [id=legacy-cache]
docker_container.legacy_cache: Refreshing state... [id=…]

Terraform will perform the following actions:

  # docker_container.legacy_cache will be imported
  # (config generated in generated.tf)
    resource "docker_container" "legacy_cache" { ... }

Plan: 1 to import, 0 to add, 0 to change, 0 to destroy.
```

`1 to import` — a fifth kind of plan line you hadn't met. Open `generated.tf`: Terraform reverse-engineered a full resource block from the live container (image, ports, all of it). **This draft is a starting point, not gospel** — it's verbose and includes read-only attributes you'd trim. In real work you move the useful parts into your real config and delete the generated noise. For the lab, it's fine as-is. Apply the import:

```bash
terraform apply -auto-approve
terraform state list          # now includes docker_container.legacy_cache
```

The container never restarted — `import` only wrote to state; reality was already correct. That's the whole point: you brought an orphan under management with zero downtime.

#### Why import matters, and its honest limit

Every "help, our Terraform drifted / half our infra is clickops" gig is import work: reconcile the ledger with reality without recreating anything. The limit to state in interviews: import brings a resource into *state*, but you still have to hand-write (or generate + clean) matching *config* — import doesn't author good HCL for you, it just stops Terraform from wanting to create a duplicate. Config-generation (`-generate-config-out`) got this from "tedious" to "tolerable" in 1.5+.

### 3. `terraform state rm` — the exact inverse

Sometimes you want Terraform to *stop managing* something without destroying it — handing it to another team, or excising a resource you'll manage elsewhere. That's `state rm`: delete the ledger entry, leave reality untouched.

```bash
terraform state rm docker_container.legacy_cache
```

```
Removed docker_container.legacy_cache
Successfully removed 1 resource instance(s).
```

```bash
docker ps --filter name=legacy-cache     # STILL RUNNING — reality untouched
terraform state list                     # legacy_cache GONE from the ledger
```

**`state rm` ≠ `destroy`.** Destroy removes reality *and* the ledger entry; `state rm` removes only the ledger entry. Now Terraform has amnesia about `legacy-cache` again — if you `plan` with the import block still present it'd re-import, or without it, it's simply an orphan once more. (Remove `import.tf` and `generated.tf` now so the next plan is clean.) Pair this with its cousins: `terraform state mv` (relabel an address — the imperative version of Lab 4's `moved` block) and `terraform state show` (read one resource). These three are your ledger-surgery kit.

Clean the orphan up by hand since Terraform no longer owns it:

```bash
docker rm -f legacy-cache
rm -f infra/terraform/hello-nginx/import.tf infra/terraform/hello-nginx/generated.tf
```

### 4. Locking — see the lock, know the recovery command

The local backend locks during every operation; it's just usually too fast to catch. Understand the shape and, crucially, the recovery:

```bash
terraform force-unlock -help        # read it — DON'T run an unlock without a lock ID
```

The failure you're preparing for: an `apply` crashes (laptop sleeps, CI killed) mid-write and leaves a **stale lock** — the next apply refuses with `Error acquiring the state lock` and prints a lock ID. `terraform force-unlock <LOCK_ID>` clears it. The danger is using force-unlock while *someone else's apply is genuinely running* — you'd re-enable the double-write corruption locking exists to prevent. Rule: force-unlock only when you're certain no operation is actually in flight.

For a *remote* backend this lock is distributed — which is the whole reason the S3 backend historically paired with a DynamoDB table (the table row *was* the lock), and now supports native S3 locking (`use_lockfile = true`) so the extra table is no longer required. Interview-ready sentence: *"S3 stores the state, and locking prevents concurrent writes from corrupting it — DynamoDB historically, S3 conditional writes now."*

### 5. Remote state — the concept, and the cross-team pattern

You won't need a remote backend locally, but you must be able to explain it. A `backend` block replaces the implicit local file:

```hcl
terraform {
  backend "s3" {
    bucket       = "my-org-tfstate"
    key          = "capstone/terraform.tfstate"   # path WITHIN the bucket → one bucket, many states
    region       = "us-east-1"
    encrypt      = true                            # server-side encryption (state has secrets — Lab 3)
    use_lockfile = true                            # native S3 locking, no DynamoDB table needed (1.11+)
  }
}
```

The three properties a real state store must have, and why: **shared** (team + CI apply against one truth, not divergent laptop copies), **locked** (no concurrent-write corruption), **versioned + encrypted** (recover from a bad apply; state holds plaintext secrets so encryption at rest is mandatory). One more pattern worth naming — the **`terraform_remote_state` data source**: one root *reads another root's outputs* through its remote state ("the networking team's root outputs the VPC ID; the app team's root consumes it"). It's how large orgs compose many small states instead of one terrifying monolith — the outputs from Lab 3, crossing team boundaries.

### 6. When NOT to use Terraform (the maturity answer)

Being able to say where the tool *doesn't* fit is a senior signal:

- **Fast-changing app deployments** → that's Helm/Argo's job (Lab 5's ownership rule). Terraform is for slow-moving infra, not per-commit rollouts.
- **Imperative one-offs / data operations** → running a DB migration, rotating a key, draining a node. Terraform describes desired *state*, not *procedures*; use a script or a purpose-built tool (Ansible for config-management-style tasks).
- **Things with no provider / no stable API** → if there's no API to diff against, there's nothing to reconcile.
- **When the blast radius of a bad plan is unacceptable and nobody reads plans** → Terraform is only as safe as the discipline of reading `plan` before `apply`. Without that culture, a `-/+` on a database is a real outage.

## OPTIONAL extra — real AWS S3 backend (same-day teardown)

> **Not $0 in the strict sense**, but S3 storage for one tiny state file is fractions of a cent and stays inside the AWS Free Tier for a new account. Do this only if you have an AWS account and the `aws` CLI configured. **Tear it down the same day** (steps below). Skipping this loses nothing required — the concept above is the interview content; this just makes it muscle memory.

Bootstrap chicken-and-egg: the bucket that holds state can't itself be created by the state-using config, so make it with the CLI first.

```bash
# 1. Create a globally-unique, versioned, encrypted bucket (pick your own suffix)
BUCKET="mahadi-tfstate-$(date +%s)"
aws s3api create-bucket --bucket "$BUCKET" --region us-east-1
aws s3api put-bucket-versioning --bucket "$BUCKET" \
  --versioning-configuration Status=Enabled
aws s3api put-bucket-encryption --bucket "$BUCKET" \
  --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
echo "$BUCKET"      # note this name
```

Add the backend to `hello-nginx` (a new file `backend.tf`), using your bucket name:

```hcl
terraform {
  backend "s3" {
    bucket       = "PASTE-YOUR-BUCKET-NAME"
    key          = "hello-nginx/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}
```

Migrate the existing local state up to S3 — Terraform detects the backend change and offers to copy:

```bash
terraform init -migrate-state
#   "Do you want to copy existing state to the new backend?"  → yes
```

Prove it's remote now:

```bash
ls terraform.tfstate                      # GONE locally (or now just a stale copy)
aws s3 ls "s3://$BUCKET/hello-nginx/"      # terraform.tfstate lives in the bucket
terraform plan                            # still works — reads state from S3, acquires an S3 lock
```

You just did the single most common real-world Terraform setup step. **Same-day teardown (do this now):**

```bash
terraform destroy -auto-approve           # remove the nginx container while state is still reachable
rm -f backend.tf                          # drop the backend block
terraform init -migrate-state             # migrate the (now empty) state back to local; yes
aws s3 rm "s3://$BUCKET" --recursive      # empty the bucket
aws s3api delete-bucket --bucket "$BUCKET" --region us-east-1
aws s3 ls | grep "$BUCKET" || echo "bucket gone — teardown complete"
```

## Verify

- You imported `legacy-cache` (`1 to import` in the plan), then `state rm`'d it and confirmed the container kept running.
- You can explain `serial`/`lineage` and what `terraform.tfstate.backup` is for.
- You can state, in one sentence each, what locking prevents and the three properties a remote state store must have.

**Answer aloud** (then check):

1. What's the difference between `terraform destroy`, `terraform state rm`, and deleting the state file — for one resource?

<details><summary>Answer (read after attempting aloud)</summary>

- **`destroy`** removes the resource from **reality** *and* from state — the container is gone, the ledger entry is gone. Intentional teardown.
- **`state rm`** removes only the **ledger entry** — the container keeps running, but Terraform now has amnesia about it (it becomes an orphan). Used to hand a resource to another owner without downtime.
- **Deleting the state file** removes the ledger for **everything** at once — reality keeps running, but Terraform forgets *all* of it and, on next apply, tries to *recreate* it all (usually failing on name/ID collisions). It's `state rm` for the whole root, and it's how people accidentally end up with duplicate infra or a terrifying `plan`. State rm is surgical; deleting the file is a lobotomy.

</details>

2. Two engineers run `terraform apply` against the same S3-backed state at the same moment, and there's no locking. Walk through how state corrupts.

<details><summary>Answer (read after attempting aloud)</summary>

`apply` is read-modify-write on the entire state file. Both engineers read the *same* starting state (say serial 5). Engineer A creates a resource and writes serial 6. Engineer B, who never saw A's change, computes a diff from serial 5, does *their* actions, and writes *their* serial 6 — overwriting A's. Now state has lost A's resource: Terraform believes it doesn't exist, so a future plan will try to create it again (duplicate) or a destroy will orphan it (leak). The ledger no longer matches reality — corruption. Locking prevents it by making B's apply block until A's finishes and releases; `serial`+`lineage` are the backstop that rejects a stale/foreign write even if a lock is bypassed. This is *the* reason shared state needs a locking backend, not a shared file on a drive or in git.

</details>

3. A client's infrastructure was all built by clicking in a console. They want it in Terraform without downtime. What's your workflow?

<details><summary>Answer (read after attempting aloud)</summary>

`import`, resource by resource (or with `import` blocks in bulk). For each real resource: write (or `-generate-config-out` then clean up) a matching `resource` block, add an `import { to = <address>  id = <real-id> }` block, `terraform plan` and confirm it shows `import` with **no** changes to reality (`0 to add/change/destroy` beyond the import) — if the plan wants to change or replace something, my config doesn't match the real resource yet, so I fix the HCL until the plan is import-only. Apply. Repeat until `terraform state list` covers everything and `plan` is clean. Import writes to state only, so nothing restarts — zero downtime. The hard part isn't the import mechanic, it's authoring config that *exactly* matches the drifted reality so the first plan isn't a destructive surprise.

</details>

4. Where would you push back on "let's put everything in Terraform"?

<details><summary>Answer (read after attempting aloud)</summary>

Terraform is for slow-moving, declarative infrastructure with a real API to diff against. I'd push back on: (a) **app deployments that change every commit** — that's Helm/Argo, and co-owning them with Terraform starts a drift war (Lab 5); (b) **imperative one-offs** — DB migrations, key rotation, node draining — Terraform models desired *state*, not *procedures*; (c) **anything without a provider/stable API** — nothing to reconcile; (d) **environments with no plan-review discipline** — Terraform is only as safe as the habit of reading `plan` before `apply`, and a `-/+` on a stateful resource is a real outage. Naming the boundary is the maturity signal; "everything in Terraform" is the junior answer.

</details>

## Clean up

```bash
cd infra/terraform/hello-nginx
terraform destroy -auto-approve          # if the OPTIONAL extra already destroyed it, this is a no-op
docker ps -a --filter name=legacy-cache  # ensure the hand-made container is gone (docker rm -f if not)
```

Confirm no stray labs are running:

```bash
docker ps --filter name=tf-        # nothing from this section left up
```

Commit the section's Terraform: `hello-nginx/`, `capstone-stack/`, `modules/service/`, `k8s-capstone/` — all `.tf` files and `.terraform.lock.hcl` files, **never** `*.tfstate`, `*.tfvars`, `.terraform/`, or `generated.tf`/`backend.tf` if you kept them around. `infra/terraform/` is now portfolio evidence: a real, multi-root, module-using Terraform codebase.
