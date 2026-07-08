# Lab 1 — GitOps mental model + the `gitops/` repo layout

**Goal:** before installing anything, nail down *why* the deploy arrow flips (push → pull) and *where* desired state is going to live. You'll create the `gitops/` folder that every later lab fills in, and you'll look hard at the one thing Argo CD is about to start watching: the `capstone/chart/` you built in Section 5.

## The mental map (read this first)

You've deployed the capstone three ways so far, and every one was **push** — the deployer stands outside and shoves:

```
  S1 compose : you  ── docker compose up ──▶ Docker (your Mac)
  S2 CI      : runner ── ssh + docker run ──▶ vps-lab
  S4/S5 k8s  : you  ── kubectl apply / helm upgrade ──▶ kind cluster
                       └─ the deployer holds the cluster's keys ─┘
```

GitOps flips the last arrow. Instead of *you* running `helm upgrade` against the cluster, you'll **commit the desired state to git**, and an agent living *inside* the cluster will pull it and apply it to itself:

```
  GitOps (from Lab 2 on)
  you ── git commit + PR ──▶ devops-course repo (github, public)
                                   │
                                   │  capstone/chart/   ← the DESIRED state
                                   │  gitops/           ← the "which apps exist" wiring
                                   ▼
                            Argo CD (inside kind)  ── helm template + kubectl apply ──▶ its own cluster
```

Notice what *doesn't* move in the second picture: **the cluster's credentials.** In the push pictures the deployer needs them. In the pull picture only Argo (already inside the cluster) does. That's the entire security argument for GitOps, and it's the sentence to have ready in an interview: *"push deploys hand prod's keys to CI; pull deploys keep prod's keys inside prod."*

### The two folders, and why they're separate

Argo CD will watch **two different kinds of thing** in this one repo, and it helps to keep them mentally distinct from day one:

1. **`capstone/chart/`** — the *application* itself: templates + values. This already exists (Section 5, your hands). It answers *"what does one running copy of the capstone look like?"* Argo doesn't care that it's Helm — it'll just run `helm template` on it and apply the output.
2. **`gitops/`** — the *wiring*: a set of **Application** manifests that say *"an app called capstone-staging exists, it comes from `capstone/chart/` at revision main, and lives in namespace capstone-staging."* This is new, and it's what you scaffold today. It answers *"which apps exist, from where, in which environment?"*

Think of it like Section 4's split: the chart is the *Deployment spec* (one workload), `gitops/` is the *cluster inventory* (what's deployed where). Keeping them apart is what makes the app-of-apps pattern in Lab 5 possible — you'll point one root Application at `gitops/apps/` and it'll plant all the others.

```
  devops-course/                 (this repo — Argo watches it)
  ├── capstone/
  │   └── chart/                 ← S5: the app (templates + values.yaml)
  │       ├── Chart.yaml
  │       ├── values.yaml
  │       └── templates/...
  └── gitops/                    ← THIS LAB creates the skeleton
      ├── README.md              ← notes-to-future-you about the layout
      ├── apps/                  ← one Application manifest per app (Lab 2, 5)
      └── bootstrap/             ← the app-of-apps root (Lab 5)
```

## Steps

### 1. Confirm the two prerequisites are actually here

Nothing to build yet — just prove the ground is solid. Argo CD needs a cluster to live in and a chart to deploy.

```bash
kubectl config current-context     # should print kind-<something> — your S4 cluster
kubectl get nodes                  # nodes Ready — the cluster is up
```

Expected: the context name starts with `kind-` (kind prefixes every context that way) and every node shows `Ready`. If `kind get clusters` lists your cluster but the context is wrong, run `kubectl config use-context kind-<name>`. If there's no cluster at all, recreate it from your Section 4 kind config first — Argo has to live *somewhere*.

```bash
cd /Users/mahadihassan/Documents/plan/projects/devops-course
helm template capstone ./capstone/chart | head -40
```

`helm template` renders the chart to plain Kubernetes YAML **without touching the cluster** — it's the exact operation Argo CD will run internally on every sync (Section 5's debugging loop, now doing production work). Seeing real `Deployment`/`Service` YAML scroll past confirms the chart is renderable. If this errors, fix the chart *now* — Argo will hit the identical error later, just with a less obvious message buried in a UI.

#### Why this render step matters more than it looks

Argo CD is not "Helm-aware" in any deep way. When an Application says `path: capstone/chart`, Argo detects the `Chart.yaml`, shells out to `helm template` with your values, gets back a stream of plain manifests, and from that point on treats them like any other YAML to diff-and-apply. So **anything `helm template` can't render, Argo can't deploy.** Making this your pre-flight check — "does it template cleanly?" — is a habit that saves you from chasing phantom Argo bugs that are really chart bugs.

### 2. Create the `gitops/` skeleton

These folders start almost empty on purpose — Labs 2 and 5 fill them. Create the structure and a README that explains the layout to future-you (this repo is portfolio evidence; a stranger should understand it).

```bash
cd /Users/mahadihassan/Documents/plan/projects/devops-course
mkdir -p gitops/apps gitops/bootstrap
```

Now create `gitops/README.md` with this content:

```markdown
# gitops/ — Argo CD desired state

This folder is the **wiring**, not the app. Argo CD (running inside the kind
cluster) watches this repo and reconciles the cluster to match what's here.

- `apps/`      — one Argo CD `Application` manifest per deployable unit.
                 Each points at `capstone/chart/` with an environment's values.
- `bootstrap/` — the "app-of-apps" root `Application`. Applying this one file
                 makes Argo manage everything under `apps/` automatically.

The application itself (Helm chart) lives in `../capstone/chart/`.
Deploy history = git history. Rollback = `git revert`. Nobody runs
`kubectl apply` or `helm upgrade` by hand anymore — you change git.
```

`.gitkeep` the empty dirs so git tracks them until the real manifests land:

```bash
touch gitops/apps/.gitkeep gitops/bootstrap/.gitkeep
```

### 3. Look at what a push-deploy leaves behind (the thing you're replacing)

Quick reality check on how you deploy *today*, so the change is concrete. If the capstone is currently running on kind from Section 5:

```bash
helm list -A | grep -i capstone     # a Helm release you installed BY HAND
```

If you see a release here, that's the push-model artifact: *you* ran `helm install`, holding the cluster's context, from your laptop. In Lab 2, Argo takes over that exact release relationship — the difference is that from then on the *repo* decides what's installed, and your laptop's kubeconfig stops being the thing that changes prod.

> **Don't uninstall it yet.** Lab 2 will either adopt or replace it cleanly. Just notice it exists and that *you* are the one who created it — that's the workflow retiring.

### 4. Write down the desired-state target you'll use in Lab 2

You don't create the Application manifest yet (that's Lab 2), but decide its coordinates now so Lab 2 is copy-paste. Argo needs four facts to define an Application:

| Fact | Value for us | Why |
|---|---|---|
| **repoURL** | `https://github.com/itsmahadi007/devops-course.git` | the public repo — no credentials needed to *read* it (the $0, no-secrets win) |
| **targetRevision** | `main` | which branch/tag/commit is "the truth" |
| **path** | `capstone/chart` | where in the repo the manifests live |
| **destination namespace** | `capstone` (Lab 2), later `capstone-staging` / `capstone-prod` | where in the cluster it lands |

That the repo is **public** is doing quiet work here: Argo can clone it read-only with no token, so there's genuinely zero secret involved in the git→cluster path. On a private company repo you'd add a read-only deploy key — still read-only, still no cluster credentials leaving the cluster.

## Verify

```bash
find gitops -type f | sort
git -C /Users/mahadihassan/Documents/plan/projects/devops-course status --short gitops/
```

You should see `gitops/README.md`, `gitops/apps/.gitkeep`, `gitops/bootstrap/.gitkeep` listed as new/untracked. That's the skeleton in place.

Then answer aloud:

**1. Push vs pull deployment — draw the arrow and say which side holds the cluster's credentials in each.**

<details><summary>Answer (read after attempting aloud)</summary>

Push: an external deployer (laptop, CI runner) reaches *into* the cluster — `kubectl`/`helm`/`ssh` — so the deployer must hold the cluster's write credentials. Pull: an agent *inside* the cluster (Argo CD) reaches *out* to git, reads desired state, and applies it to its own cluster — so only the in-cluster agent holds credentials, and they never leave the cluster. GitOps is pull.

</details>

**2. Argo is about to watch two folders in this repo. What's the difference between `capstone/chart/` and `gitops/`?**

<details><summary>Answer (read after attempting aloud)</summary>

`capstone/chart/` is the *application* — templates + values describing what one running copy looks like (the "Deployment spec"). `gitops/` is the *wiring* — Application manifests declaring which apps exist, from which repo/revision/path, into which namespace (the "cluster inventory"). Separating them is what lets one root app-of-apps manage all the others in Lab 5.

</details>

**3. Why does it matter that the repo is public for the git→cluster read path?**

<details><summary>Answer (read after attempting aloud)</summary>

A public repo can be cloned read-only with no credentials, so the desired-state read involves zero secrets — perfect for a $0, no-secrets lab. On a private repo you'd give Argo a *read-only* deploy key; it's still read-only and still contains no cluster credentials. The security property GitOps protects (cluster creds never leaving the cluster) is unaffected either way.

</details>

**4. `helm template ./capstone/chart` renders fine but you haven't touched the cluster. Why is that the right pre-flight check for Argo?**

<details><summary>Answer (read after attempting aloud)</summary>

Argo isn't deeply Helm-aware — on sync it just runs `helm template` with your values and treats the output as plain YAML to diff-and-apply. So anything `helm template` can't render, Argo can't deploy. Checking "does it template cleanly?" locally catches chart bugs before they show up as confusing Argo errors in a UI.

</details>

## Clean up

Nothing to tear down. Commit the skeleton — it's the foundation for the rest of the section:

```bash
git add gitops/
git commit -m "feat(gitops): scaffold gitops/ repo layout for Argo CD"
```

Leave it uncommitted-pushed for now if you like; Lab 2 pushes it when Argo needs to read it from GitHub.
