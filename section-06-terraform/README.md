# Section 06 — Terraform

**Status:** written — not started · **Time:** ~1 week at 2–4h/day · **Labs:** 6

Section 5 ended with the capstone packaged as a chart — the *app* is now declared in files. But everything **under** the app is still hand-made: you typed `docker network create`, you typed `kind create cluster`, you clicked things. This section makes the infrastructure itself a file too — and introduces the one idea that makes Terraform different from every tool so far: **a state file, Terraform's memory of what it built for you.**

You already own the core mental model. Your own Section 1 notes line: *"`up` is declarative, `start` is imperative — `up -d` = make reality match the file."* Terraform IS that sentence, generalized to anything with an API: Docker today, Kubernetes and Helm in Lab 5, AWS in Section 7. Same philosophy, one new ingredient.

## The mental model (read first)

**Three things exist at all times, and Terraform's whole job is keeping them in agreement:**

```
   CONFIG (.tf files)          STATE (terraform.tfstate)         REALITY
  "what I want to exist"      "what I built last time,          the actual containers,
                               and its real-world IDs"           networks, clusters…
        │                            │                              │
        └──────────┬─────────────────┴──────────────┬───────────────┘
                   │        terraform plan          │
                   │  refresh state from reality,   │
                   │  then diff config vs state     │
                   ▼                                ▼
             "here's what I'd            terraform apply = do it,
              create/change/destroy"      then UPDATE THE STATE
```

**Why does state exist at all?** Compose never needed a memory — it finds "its" containers by asking Docker for everything labeled with the project name, and reality itself is the record. That trick doesn't scale past one Docker daemon. Terraform manages *hundreds* of resource types across APIs that have no universal labeling scheme, so it keeps its own ledger: **config name → real-world ID**. Think of a valet's ticket book: config is the cars you asked for, the parking lot is reality, and state is the ticket book linking your name to the exact spots. Lose the ticket book and the cars still exist — but nobody remembers which ones are yours. That's why state is sacred, why teams store it remotely, and why "tell me about Terraform state" opens half of all IaC interviews.

**`plan` is a three-way diff.** Refresh (peek at reality, update state's picture of it) → diff (state vs config) → print a proposal with four symbols you'll learn to read like a code review: `+` create, `-` destroy, `~` update in place, `-/+` destroy-and-recreate. Nothing happens until `apply`, and `apply` ends by writing the new state. Drift — someone changed reality behind Terraform's back — is just this diff finding a surprise (Lab 3 makes you cause one on purpose).

**Providers are translators.** Terraform core only understands "desired graph of resources"; a *provider* is a plugin that speaks one API's dialect — the Docker provider speaks to the daemon socket, the AWS provider to AWS endpoints, the helm provider runs Helm's own code. `terraform init` downloads them. Same core workflow, any infrastructure — which is why everything you learn against free local Docker this week transfers 1:1 to AWS in Section 7.

**Versions this section uses** (latest stable, July 2026): Terraform **1.15.x** (1.15.7 at writing), provider `kreuzwerker/docker` **4.x**, `hashicorp/kubernetes` **3.x**, `hashicorp/helm` **3.x** (the v3 providers changed syntax — labs use the new form).

**One honest paragraph on licensing, because interviews ask:** in August 2023 HashiCorp moved Terraform from open source (MPL) to the **Business Source License (BUSL)** — free to use, but competitors can't build competing hosted products on it; IBM then acquired HashiCorp (closed 2025). The community forked the last MPL version into **OpenTofu** (Linux Foundation, currently 1.12.x) — a drop-in replacement for everything in this section: same HCL, same providers, `tofu` instead of `terraform`. Learn Terraform (it's what job ads say), be able to say that story in 60 seconds, and know `brew install opentofu` exists. Practical fallout you'll hit in Lab 1: Homebrew's core `terraform` formula is frozen at the last MPL version, so installation goes through HashiCorp's own tap.

## Why this matters for jobs

- **"What is Terraform state and why do teams store it in S3?"** is the single most reliable IaC interview question. After Lab 6 you'll have *opened* a state file, caused and read drift, held a lock, and adopted a foreign resource with `import` — answers from scars, not blog posts.
- Reading a `plan` diff before approving it is the actual daily job. "Walk me through this plan output" is a common live-screen exercise — Lab 3 drills exactly the `+`/`~`/`-/+` literacy it needs.
- "Terraform manages the platform, Helm/Argo manage the apps — one owner per layer" (Lab 5) is a senior-signal answer to the messy "Terraform or Helm?" question.
- Freelance infra gigs are frequently "our Terraform is a mess / drifted / state is broken — help." Modules, `moved` blocks, and import are precisely that toolkit.

## Labs

- [ ] [Lab 1 — First apply](labs/lab-01-first-apply.md) — init/plan/apply/destroy with the Docker provider; HCL anatomy; the state file opened and read
- [ ] [Lab 2 — Capstone stack as code](labs/lab-02-capstone-stack-as-code.md) — the compose stack rebuilt in HCL: images, network, volume, three containers; compose vs Terraform, honestly compared
- [ ] [Lab 3 — Variables, outputs, drift](labs/lab-03-variables-outputs-drift.md) — parameterize the stack; cause drift on purpose and read every plan symbol
- [ ] [Lab 4 — Modules](labs/lab-04-modules.md) — extract a reusable `service` module and refactor into it **without destroying anything** (`moved` blocks)
- [ ] [Lab 5 — Kubernetes & Helm providers](labs/lab-05-kubernetes-helm-providers.md) — Terraform installs the capstone chart on kind; who owns what: TF vs Helm vs Argo (the Section 9 tension, named now)
- [ ] [Lab 6 — State deep dive](labs/lab-06-state-deep-dive.md) — state anatomy, locking, import/state rm, remote backends; OPTIONAL real-AWS S3 backend with same-day teardown

Do them in order. Each ends with **Verify** (proof it worked) and **Clean up**. Everything lands in `infra/terraform/` at the repo root — by the end of the section that folder is portfolio evidence.

## Reading (curated, ~1.5h total)

- [Purpose of Terraform state](https://developer.hashicorp.com/terraform/language/state/purpose) — the single most important page; read until "why not just query reality?" feels obvious
- [Plan command & the resource lifecycle](https://developer.hashicorp.com/terraform/cli/commands/plan) — the symbols and what refresh really does
- [kreuzwerker/docker provider docs](https://registry.terraform.io/providers/kreuzwerker/docker/latest/docs) — skim `docker_container` and `docker_image`; you'll use both constantly
- [Modules](https://developer.hashicorp.com/terraform/language/modules) + [`moved` blocks](https://developer.hashicorp.com/terraform/language/modules/develop/refactoring) — the refactor-without-destroy trick from Lab 4
- [Import blocks](https://developer.hashicorp.com/terraform/language/import) — the modern (1.5+) adopt-existing-infrastructure workflow
- [OpenTofu](https://opentofu.org/) — ten minutes, so the license answer is yours

## Done when

Every task in [checkpoint.md](checkpoint.md) passes from memory, and [notes.md](notes.md) is filled in your own words. Then Section 7 (AWS Core) gets written — where this exact workflow meets the real cloud.
