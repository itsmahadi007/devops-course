# Checkpoint — Section 06: Terraform

Pass every task **from memory** — no peeking at the labs. If you have to peek, the section isn't done yet; redo that lab tomorrow and try again.

## Practical tasks

- [ ] **1.** From a blank folder, write `main.tf` for one Docker container (image + container + a published port in the 9070 block), then run the full `init → plan → apply → destroy` loop. Target: under 10 minutes, no references.
- [ ] **2.** Open a `terraform.tfstate` and, out loud, point to the `serial`, `lineage`, and one resource's real-world `id` — and match that id to `docker inspect`.
- [ ] **3.** Reproduce all four plan symbols on demand: cause a `+`, a `~`, a `-/+` (rename something), and a `-`, explaining each before you apply it.
- [ ] **4.** Cause drift by hand (`docker rm -f` a TF-managed container), run `terraform plan`, and explain what refresh did before the diff — then heal it.
- [ ] **5.** Take a plain resource and extract it into a child module; add the `moved` block so `plan` shows `0 to add, 0 to change, 0 to destroy`, and prove the container ID didn't change.
- [ ] **6.** Create a container by hand with `docker run`, then `import` it into Terraform (import block + generate-config), confirm the plan is import-only, then `state rm` it and show it's still running.

## Explain aloud (interview drill — answer in 60–90 seconds each)

- [ ] What is Terraform state, physically, and why does it exist when `docker compose` never needed a memory? (The valet-ticket / single-daemon-labels contrast.)
- [ ] Why is the lock file (`.terraform.lock.hcl`) committed but the state file never is? Two independent reasons for state.
- [ ] Walk me through what `terraform plan` actually does — the three steps — and why nothing changes until `apply`.
- [ ] The four plan symbols: `+ - ~ -/+`. What does each mean, and which one do you read most carefully before approving, and why?
- [ ] `(known after apply)` — what is it, and what does its existence tell you about what `plan` can and can't know?
- [ ] Nothing in a config says "do X before Y," yet order is respected. How does Terraform derive order, and where did you see this exact idea in Section 1?
- [ ] What is a provider, and why does "learn it on free local Docker, it transfers to AWS" actually hold?
- [ ] The Terraform license story (BUSL, IBM, OpenTofu) in 60 seconds — and the one practical consequence you hit installing it.

### From the capstone-stack labs (2–4)

- [ ] You already have a working compose file for this stack. Name two things Terraform adds and two it takes away — and give the honest verdict for a single-host dev stack.
- [ ] `docker_image` is a managed resource. Why did that make `terraform destroy` dangerous for the redis/postgres images, and what single argument defends against it?
- [ ] Compose had `depends_on: condition: service_healthy`; the Docker provider's `depends_on` is order-only. What race comes back, and what's the honest fix?
- [ ] You built the api image with a `build {}` block but the tag never changes. Why does that make Terraform ship stale bytes, and what does `triggers` fix? (Tie it to Section 1's `:latest` bite.)
- [ ] `variable` vs `local` — the exact distinction, with an example of each from your stack.
- [ ] `sensitive = true` on a password: a teammate says "great, it's protected now." Give the precise correction, and where the value actually still sits in plaintext.
- [ ] There's no `terraform drift` command. So how is drift detected, and what does Terraform do about it (corrective, not alarmist)?
- [ ] What crosses the root↔child module boundary in each direction, and what deliberately can't? Why is that encapsulation the whole value?
- [ ] You moved three resources into modules and `plan` said `3 to add, 3 to destroy`. Why — and what exactly does a `moved` block change (state or reality)?
- [ ] How does one `service` module express "redis publishes no port, api publishes 9071"? (The object-or-null + dynamic-block pattern.)

### From the K8s/Helm and state labs (5–6)

- [ ] "Terraform, Helm, or Argo CD for our apps?" — the one-owner-per-layer answer: what does each own, and what happens if two own the same object?
- [ ] The helm provider has its own `kubernetes = {}` block even with a `kubernetes` provider already configured. Why doesn't it reuse it?
- [ ] `terraform plan` showed `2 to add` but the app has a Deployment + Service + ConfigMap. Where did those go, and what does Terraform actually track vs what Helm tracks?
- [ ] `wait = true` gave a real readiness gate that Lab 2's Docker `depends_on` couldn't. What's the underlying reason — and what does that say about "same workflow, different translators"?
- [ ] Locking, from first principles: how does shared state corrupt without it, and what role do `serial`/`lineage` play as the backstop?
- [ ] The three properties a remote state store must have, and why state specifically needs encryption at rest.
- [ ] `destroy` vs `state rm` vs deleting the state file — for one resource, and for the whole root.
- [ ] A client's infra was all built by clicking in a console. Your zero-downtime workflow to get it into Terraform — and the genuinely hard part.
- [ ] Where do you push back on "put everything in Terraform"? At least three places.

## Gate

- [ ] `notes.md` filled in my own words (all five sections)
- [ ] Everything committed (`infra/terraform/` — all `.tf` files + `.terraform.lock.hcl`; **no** `*.tfstate`, `*.tfvars`, `.terraform/`)

When all boxes are checked, say so — the next section (AWS Core) gets written against your notes, where this exact workflow meets the real cloud.
