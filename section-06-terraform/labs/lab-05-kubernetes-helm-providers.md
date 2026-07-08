# Lab 5 — Kubernetes & Helm providers: Terraform installs the chart

**Goal:** point Terraform at a Kubernetes cluster and have it (a) create a namespace with the **kubernetes provider** and (b) install your Section 5 capstone Helm chart into it with the **helm provider** — proving the "one workflow, pluggable translators" claim from Lab 1 across three totally different APIs (Docker → Kubernetes → Helm). Then the senior conversation this whole section has been building toward: **who owns what?** Terraform, Helm, and (Section 9) Argo CD can all deploy to the same cluster — and if two of them own the same object, they *fight*. You'll leave able to answer "Terraform or Helm?" like someone who's felt the drift war, not read about it.

> **Prerequisites:** this lab assumes Section 4 left you fluent with **kind** + `kubectl`, and Section 5 left a chart at `capstone/chart/`. If you're running labs out of order, Step 1 spins up a throwaway kind cluster, and any local chart path works to follow along. Everything here is still $0 and local — kind is containers-as-nodes on the Docker Desktop you already have.

## The mental map (read this first)

Same four commands (`init`/`plan`/`apply`/`destroy`), two new translators. But there's a subtlety that doesn't exist with the Docker provider: these providers need a **live cluster to connect to at plan time**, and one of them (helm) *contains* the other's connection settings:

```
                                  ~/.kube/config
                            (context: kind-tf-capstone)
                                        │
                 ┌──────────────────────┴───────────────────────┐
                 ▼                                               ▼
        provider "kubernetes"                          provider "helm"
        talks the K8s API directly                     { kubernetes = { ... } }  ← helm needs K8s creds too:
                 │                                        it runs Helm's engine, which talks to the same API
                 ▼                                               ▼
        kubernetes_namespace "capstone"   ───────────▶  helm_release "capstone"
        (one API object)                    (installs   (renders your chart's templates → applies
                                             INTO it)     many objects: Deployment, Service, …)
```

**The layered-ownership idea, stated now because it's the point of the lab.** A running cluster is a shared substrate. Three tools want to write to it:

- **Terraform** — great at the *platform*: the cluster itself, namespaces, cluster-wide operators (ingress-nginx, cert-manager), CRDs, cloud resources around the cluster. Declarative, stateful, one plan for everything.
- **Helm** — great at *one app's* lifecycle: install/upgrade/rollback a release, its own release history (Section 5).
- **Argo CD** (Section 9) — great at *continuous* app delivery: git is the desired state, Argo syncs forever and self-heals drift.

The failure mode is two tools owning the *same* object. If Terraform's `helm_release` installs the capstone chart **and** Argo CD also syncs the capstone chart, every time one reconciles it "fixes" what the other did — an endless drift war, each `terraform plan` showing changes Argo just made, each Argo sync reverting Terraform. **The rule seniors state in interviews: one owner per layer.** This lab deliberately has Terraform own an app release (the helm provider) *because it's the fastest bootstrap* — and names, out loud, that this is exactly the ownership you hand off to Argo in Section 9. Feeling the tension now is why Section 9 will make sense.

## Steps

### 1. Ensure a kind cluster exists

If your Section 4 cluster is up, note its context and skip the create:

```bash
kubectl config current-context      # e.g. kind-capstone — use whatever this prints below
```

Otherwise make a throwaway one (no special config needed — we reach the app with port-forward, not ingress):

```bash
kind create cluster --name tf-capstone
kubectl config current-context      # kind-tf-capstone
kubectl get nodes                   # one node, STATUS Ready — a "node" that's really a container
```

Whatever `current-context` prints is the value you'll put in the provider blocks below. This lab uses `kind-tf-capstone`; **substitute yours.**

### 2. New root — `infra/terraform/k8s-capstone/`

```bash
mkdir -p infra/terraform/k8s-capstone
cd infra/terraform/k8s-capstone
```

### 3. Write `infra/terraform/k8s-capstone/main.tf`

```hcl
terraform {
  required_version = ">= 1.15.0"
  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 3.0"          # v3 (2026) — plugin-framework rewrite; provider config below is v3 form
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 3.0"          # v3 changed syntax: `kubernetes = {}` nested object + `set = [ ]` list
    }
  }
}

# ── the kubernetes provider: talk to the cluster's API directly ──
provider "kubernetes" {
  config_path    = "~/.kube/config"
  config_context = "kind-tf-capstone"      # ← your `kubectl config current-context`
}

# ── the helm provider: runs Helm's own engine, so it ALSO needs cluster creds ──
# v3 form: `kubernetes` is a nested OBJECT (= { ... }), not a block ({ ... }).
provider "helm" {
  kubernetes = {
    config_path    = "~/.kube/config"
    config_context = "kind-tf-capstone"
  }
}

# ── kubernetes provider makes ONE object: a namespace ──
resource "kubernetes_namespace" "capstone" {
  metadata {
    name = "capstone"
    labels = {
      "managed-by" = "terraform"
    }
  }
}

# ── helm provider installs the WHOLE chart into that namespace ──
resource "helm_release" "capstone" {
  name      = "capstone"
  namespace = kubernetes_namespace.capstone.metadata[0].name   # reference → order: namespace first

  chart = abspath("${path.module}/../../../capstone/chart")    # your Section 5 chart, local path
  # if your chart declares redis/postgres subchart dependencies, TF must fetch them first:
  dependency_update = true

  # v3 SET SYNTAX: a list of objects, NOT repeated `set { }` blocks.
  # These are the same --set overrides you'd pass to `helm install` on the CLI —
  # the knob CI/GitOps turns later (Section 5's "image tag override" lesson).
  set = [
    {
      name  = "image.repository"
      value = "ghcr.io/itsmahadi007/capstone"
    },
    {
      name  = "image.tag"
      value = "latest"
    }
  ]

  wait    = true      # block until the release's pods are Ready — the health-gate the Docker provider LACKED
  timeout = 180       # seconds; fail loudly if it never gets healthy
}

output "port_forward_cmd" {
  value = "kubectl port-forward -n capstone svc/capstone 9072:8000"
}
```

#### The two version notes that will bite if you skip them

- **helm v3 `set` is a list, not blocks.** In helm provider v2 you wrote repeated `set { name=… value=… }` blocks. v3 (the 2026 default) moved to the plugin framework, so it's `set = [ { name=…, value=… } ]` — a real list attribute. If you paste a v2-era example from a blog you'll get `Blocks of type "set" are not expected here`. Same story for the provider's `kubernetes = { }` (object, was a block) and `registries = [ ]`.
- **The helm provider needs cluster creds too.** It's not obvious: the helm provider doesn't shell out to your `helm` CLI — it embeds Helm's engine, which itself talks to the K8s API. So it needs its own `kubernetes = {}` connection block, duplicating the kubernetes provider's. Two providers, same cluster, configured independently.

#### `wait = true` — the thing Lab 2 wished it had

Remember Lab 2's honest gap: the Docker provider's `depends_on` was order-only, so api could start before redis was ready. Here `wait = true` tells the helm provider to **block until the release's pods report Ready** (their Kubernetes readiness probes pass — the probes you built in Section 4 from the Docker healthcheck). This is a genuine health gate, and it exists because Kubernetes has a first-class readiness concept the raw Docker API doesn't. When `apply` returns, the app is actually serving. (Set `timeout` so a chart that never goes healthy fails your pipeline instead of hanging forever.)

### 4. `terraform init` — two providers this time

```bash
terraform init
```

```
- Installing hashicorp/kubernetes v3.2.1...
- Installing hashicorp/helm v3.2.0...
Terraform has been initialized!
```

Two provider binaries into `.terraform/`, both pinned in `.terraform.lock.hcl`. (Versions shown are the July 2026 latest; `~> 3.0` will resolve to whatever 3.x is current — commit the lock so it's identical everywhere.)

### 5. `terraform plan`

```bash
terraform plan
```

```
  # kubernetes_namespace.capstone will be created
  + resource "kubernetes_namespace" "capstone" {
      + metadata { + name = "capstone" ... }
    }

  # helm_release.capstone will be created
  + resource "helm_release" "capstone" {
      + name              = "capstone"
      + namespace         = "capstone"
      + chart             = "/…/capstone/chart"
      + set               = [ { name = "image.repository" ... }, { ... } ]
      + status            = (known after apply)
      ...
    }

Plan: 2 to add, 0 to change, 0 to destroy.
```

Only **two** resources — but note that `helm_release` is a *single Terraform resource* that will create *many* Kubernetes objects (Deployment, Service, ConfigMap…) when it renders your chart. Terraform tracks the release as one unit; the individual objects live inside Helm's own release secret, not in Terraform state. That's a boundary worth seeing: **Terraform owns "the release exists and is at these values"; Helm owns "which objects that release expands to."** (This is also why `terraform plan` can't show you a diff of individual K8s objects the way a raw `kubernetes_manifest` resource would — a real tradeoff of managing Helm *through* Terraform.)

### 6. `terraform apply`

```bash
terraform apply
```

`yes`, then:

```
kubernetes_namespace.capstone: Creating...
kubernetes_namespace.capstone: Creation complete after 0s [id=capstone]
helm_release.capstone: Creating...
helm_release.capstone: Still creating... [30s elapsed]     ← wait=true: blocking on pods going Ready
helm_release.capstone: Creation complete after 42s [id=capstone]

Apply complete! Resources: 2 added, 0 changed, 0 destroyed.
```

Verify from the cluster's side, then reach the app:

```bash
kubectl get pods -n capstone            # capstone-… Running, READY 1/1
helm list -n capstone                   # the SAME release, visible to the helm CLI — TF used Helm's own machinery
terraform output -raw port_forward_cmd  # prints the port-forward command
kubectl port-forward -n capstone svc/capstone 9072:8000    # in one terminal (blocks)
# in another:
curl -s localhost:9072/health           # {"status":"ok"}
```

`helm list` showing the release is the punchline of the whole "who owns what" setup: **Terraform installed it using Helm's real release mechanism**, so the `helm` CLI sees it as an ordinary release. Two tools, one release record. Which is exactly why letting a *third* (Argo) also manage it would start a fight.

#### If apply fails

- **`Kubernetes cluster unreachable` / `context "kind-…" does not exist`** — the `config_context` doesn't match `kubectl config current-context`. Fix the two provider blocks. This is the #1 failure; the providers connect at plan time, so a wrong context fails before anything is created.
- **`chart "…/capstone/chart" not found`** — the chart path is wrong or the chart isn't built yet (Section 5). Confirm `ls ../../../capstone/chart/Chart.yaml`.
- **release times out going Ready** — `kubectl get pods -n capstone` then `kubectl describe pod -n capstone <pod>`. Usual suspects: image pull (is `ghcr.io/itsmahadi007/capstone:latest` public and multi-arch? — the Section 2 fix), or a probe failing. `wait=true` surfaced a real problem; that's it doing its job.

### 7. Feel the ownership tension — cause drift, watch TF fight for control

Edit the release *outside* Terraform, the way Argo CD (or a panicked teammate) would:

```bash
kubectl scale deployment -n capstone capstone --replicas=3
kubectl get pods -n capstone            # 3 pods now
```

Now ask Terraform:

```bash
terraform plan
```

If your chart's `values.yaml` sets `replicaCount: 1` and you didn't override it, Terraform's refresh sees the release drifted and proposes to pull it **back** to the chart's declared value — it wants to reassert *its* idea of the release. `terraform apply` would scale you back to 1. **Now imagine Argo CD is also watching this release and also wants its git-declared replica count.** Every `kubectl scale`, every TF apply, every Argo sync would yank the number around. That is the drift war, and it is why the answer to "should Terraform manage our app deployments?" is *"only if nothing else does — pick one owner per object."* Scale it back and re-settle:

```bash
kubectl scale deployment -n capstone capstone --replicas=1
terraform apply -auto-approve
```

## Verify

- `kubectl get pods -n capstone` shows the app Running 1/1, and `helm list -n capstone` shows the release.
- `curl -s localhost:9072/health` returns `{"status":"ok"}` through port-forward.
- You can state the "one owner per layer" rule and name what Terraform owns vs Helm vs Argo.

**Answer aloud** (then check):

1. The helm provider has its own `kubernetes = {}` block even though you already configured a `kubernetes` provider. Why doesn't it just reuse it?

<details><summary>Answer (read after attempting aloud)</summary>

Providers in Terraform are independent plugins with independent configuration — there's no shared "cluster connection" they draw from. The helm provider embeds Helm's *own* engine (it does not call your `helm` CLI), and that engine needs to authenticate to the Kubernetes API itself to install/upgrade releases. So it carries its own connection settings, which happen to duplicate the kubernetes provider's `config_path`/`config_context`. Two plugins, same cluster, configured separately. (In real setups you'd often DRY this with a shared variable or by deriving both from a cluster resource's outputs — but they remain two configurations.)

</details>

2. `terraform plan` showed `2 to add`, but the running app has a Deployment, a Service, maybe a ConfigMap. Where did those go, and what does Terraform actually track?

<details><summary>Answer (read after attempting aloud)</summary>

Terraform tracks the `helm_release` as **one resource** — "release named capstone, in namespace capstone, at these `set` values, status deployed." The individual Kubernetes objects the chart expands to (Deployment/Service/ConfigMap) are rendered and applied by Helm's engine and recorded in *Helm's* release storage (a Secret in the namespace), **not** in Terraform state. So Terraform's granularity is the release, not the object. The tradeoff: you get Helm's clean upgrade/rollback semantics, but `terraform plan` can't show you a per-object diff the way managing raw `kubernetes_manifest` resources would. It's the "Terraform owns *that the release exists at these values*; Helm owns *what it expands to*" boundary.

</details>

3. Give the 60-second answer to "Terraform, Helm, or Argo CD for deploying our apps?"

<details><summary>Answer (read after attempting aloud)</summary>

They operate at different layers, and the cardinal rule is **one owner per object** — two tools reconciling the same object start a drift war. **Terraform** owns the *platform*: the cluster, namespaces, cluster-wide operators (ingress, cert-manager), CRDs, surrounding cloud resources — the stuff that's set up once and rarely churns. **Helm** packages an app and gives it install/upgrade/rollback + release history. **Argo CD** does *continuous* delivery: git is the desired state, Argo syncs forever and self-heals drift — best for apps that change often. Common mature setup: Terraform bootstraps the cluster and installs Argo CD itself; Argo (pulling Helm charts from git) then owns the apps. Using Terraform's helm provider to deploy apps is a fine *bootstrap*, but it's the exact ownership you hand to Argo when GitOps arrives — which is why running both against the same release is the thing you don't do.

</details>

4. `wait = true` gave you a real readiness gate here, but Lab 2's Docker `depends_on` couldn't. What's the underlying difference?

<details><summary>Answer (read after attempting aloud)</summary>

Kubernetes has a **first-class readiness concept** — every pod reports Ready/NotReady based on its readiness probe (the probes built in Section 4 from the Docker healthcheck). The helm provider's `wait = true` simply blocks until the release's pods report Ready, so `apply` returning means the app is actually serving. The raw Docker daemon API has no equivalent "is this ready?" signal that the kreuzwerker provider can poll — `depends_on` only sequences creation. So the gate isn't a Terraform feature, it's a *platform* feature Terraform can lean on: the more capable the underlying API, the more the provider can promise. It's a concrete example of why "same workflow, pluggable translators" still means capabilities vary by translator.

</details>

## Clean up

```bash
terraform destroy -auto-approve
```

Destroys the release (Helm uninstall) and the namespace. Confirm:

```bash
helm list -n capstone            # empty
kubectl get ns capstone          # NotFound (or Terminating → gone)
```

If you created a throwaway cluster just for this lab, tear it down too (this is the expensive-to-leave-running part on a laptop):

```bash
kind delete cluster --name tf-capstone
```

Commit `main.tf` + `.terraform.lock.hcl`. State stays gitignored.
