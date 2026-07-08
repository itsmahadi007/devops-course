# Lab 2 — Install Argo CD + your first Application

**Goal:** put Argo CD *inside* the kind cluster, reach its UI on host port **9100**, log in the official way, and create one **Application** that points at `capstone/chart/`. By the end, a git repo — not your laptop — is deploying the capstone.

## The mental map (read this first)

Argo CD is not one binary. It's a small set of pods you install *into* the cluster, and they collectively run the reconcile loop:

```
        kind cluster (namespace: argocd)
  ┌───────────────────────────────────────────────────────────┐
  │  repo-server   ── clones git, runs `helm template` ──▶ desired YAML
  │       │                                                     │
  │  application-controller ── diffs desired vs live ──▶ applies│
  │       │                    (this IS the reconcile loop)     │
  │  argocd-server ── the API + web UI + gRPC (you talk here)   │
  │  redis         ── caches the rendered manifests             │
  │  dex           ── SSO (unused in our local setup)           │
  └───────────────────────────────────────────────────────────┘
                    ▲                         │
        port-forward│ 9100                    │ applies to
                    │                         ▼
             your browser              the SAME cluster's other namespaces
```

The one that matters is the **application-controller** — it's the piece doing the "diff git vs cluster, apply the difference" work you named in Section 1 as Kubernetes' whole personality. `argocd-server` is just the front door (UI + API). `repo-server` is the thing that clones your repo and runs `helm template`.

Two facts to hold:

1. **Argo installs a CRD called `Application`.** After install, `kubectl get applications -n argocd` is a real command. An Application is just a Kubernetes object — which means you can (and will, Lab 5) manage Applications *with* Argo, git-first, like any other manifest.
2. **The install manifest is huge because of the CRDs.** The Application/AppProject CRDs exceed Kubernetes' annotation-size limit for the normal client-side apply, so you install with `--server-side` (the apply happens *in* the API server, no annotation bloat). This is the one non-obvious flag — the failure without it (`metadata.annotations: Too long`) is pre-explained below.

## Steps

### 1. Install the `argocd` CLI

```bash
brew install argocd
argocd version --client     # prints the client version; server line will error until Lab 2 step 4 — fine
```

(Version — verify latest against the release notes; the course pins Argo CD **v3.3.12** for the server manifest below.)

### 2. Create the namespace and apply the install manifest

```bash
kubectl create namespace argocd
kubectl apply -n argocd --server-side --force-conflicts \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/v3.3.12/manifests/install.yaml
```

The URL pins an **exact version tag** (`v3.3.12`), not `stable` — same discipline as pinning a Docker base image by digest in Section 1: you want the same bytes every time, not whatever `stable` points at today. `(verify latest)` — bump the tag if a newer stable exists when you run this.

What scrolls past: dozens of `serverside-applied` lines — ServiceAccounts, Roles, RoleBindings, ConfigMaps, the CRDs (`applications.argoproj.io`, `applicationsets...`, `appprojects...`), Services, and the Deployments/StatefulSet for the pods in the diagram. It's a lot; that's normal for a whole control-plane component.

#### Why `--server-side --force-conflicts` and not a plain apply

Plain `kubectl apply` stores the entire object you applied in a `last-applied-configuration` **annotation** so it can compute future diffs client-side. Argo's CRDs are enormous (huge OpenAPI schemas), and that annotation would blow past Kubernetes' ~262 KB limit → `metadata.annotations: Too long: must have at most 262144 bytes`. Server-side apply moves diff-tracking *into* the API server using per-field ownership instead of one giant annotation, so size stops being an issue. `--force-conflicts` tells it "I own these fields, take them" on the second and later applies (upgrades). If you ever see that `Too long` error, you forgot `--server-side` — re-run with it.

### 3. Wait for the pods, and read what they are

```bash
kubectl -n argocd get pods -w      # Ctrl-C once everything is Running/Ready
```

Expected, after a minute or two (kind pulls the images first):

```
NAME                                  READY   STATUS    RESTARTS   AGE
argocd-application-controller-0       1/1     Running   0          90s   ← the reconcile loop
argocd-applicationset-controller-…    1/1     Running   0          90s   ← generates Apps (Lab 5)
argocd-dex-server-…                   1/1     Running   0          90s   ← SSO (unused locally)
argocd-notifications-controller-…     1/1     Running   0          90s   ← alerts (unused)
argocd-redis-…                        1/1     Running   0          90s   ← manifest cache
argocd-repo-server-…                  1/1     Running   0          90s   ← clones git, helm template
argocd-server-…                       1/1     Running   0          90s   ← UI + API (front door)
```

The `-0` suffix on `application-controller` is a giveaway it's a **StatefulSet** (Section 4: stable identity), because it holds the reconcile state. If a pod is stuck `Pending`, kind is still pulling images — give it time; `ImagePullBackOff` would mean no internet.

### 4. Get the initial admin password — the official way

Argo generates a random admin password on install and stores it in a Secret. **Read it, don't guess it:**

```bash
argocd admin initial-password -n argocd
```

This prints the password (and a reminder to delete the secret after you've changed it). Under the hood it's reading the `argocd-initial-admin-secret` Secret — the manual equivalent, worth knowing:

```bash
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d ; echo
```

Copy the password. Username is `admin`. **Never commit this** — it's a real credential; it stays in your terminal only.

### 5. Open the UI on host port 9100

`argocd-server` listens on 8080 (HTTPS) inside the cluster. Forward it to your Mac's **9100** (your S9 block):

```bash
kubectl port-forward -n argocd svc/argocd-server 9100:443
```

Leave this running in its own terminal (it holds the tunnel open — same idea as the compose `logs -f` follow). Open **https://localhost:9100** in a browser. You'll get a **certificate warning** — expected: Argo serves a self-signed cert (exactly the Section 3 TLS lesson — the browser doesn't trust a cert nobody vouched for). Click through ("Advanced → Proceed"). Log in as `admin` + the password from step 4.

Now log the CLI in too (a second terminal), so you can drive Argo both ways:

```bash
argocd login localhost:9100 --username admin --password '<paste>' --insecure
```

`--insecure` = "don't verify the self-signed cert" (same reason as the browser click-through). `argocd version` should now print **both** client and server versions.

#### If port 9100 says "address already in use"

Something else grabbed 9100 (a stale port-forward from a previous attempt). Find and kill it — `lsof -i :9100` shows the PID; `kill <pid>`. This is the Section 1 "port already allocated" lesson at the kubectl layer: the host side is a scarce resource, the container side isn't.

### 6. Create your first Application

Two ways — do it via a **manifest** (declarative, git-friendly, the way you'll actually work), and understand it field by field. Create `gitops/apps/capstone.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application                 # the CRD Argo installed in step 2
metadata:
  name: capstone                  # the app's name in Argo (and `kubectl get app`)
  namespace: argocd               # Applications themselves live in the argocd namespace
spec:
  project: default                # AppProject = a bucket of apps with shared guardrails; default is fine for now
  source:
    repoURL: https://github.com/itsmahadi007/devops-course.git
    targetRevision: main          # branch/tag/commit that IS the truth
    path: capstone/chart          # where the chart lives in the repo
    helm:
      valueFiles:
        - values.yaml             # which values file(s) to render with (relative to path)
  destination:
    server: https://kubernetes.default.svc   # "this same cluster" — the in-cluster API
    namespace: capstone           # where the rendered manifests land
  syncPolicy:
    syncOptions:
      - CreateNamespace=true       # make the `capstone` namespace if it doesn't exist
    # NOTE: no `automated:` block yet — this app syncs ONLY when you tell it to (Lab 3 adds auto)
```

Read it like the Lab 1 table come to life: **source** = the four git coordinates (repo/revision/path/values), **destination** = which cluster + namespace, **syncPolicy** = the rules. Leaving out `automated` means **manual sync** on purpose — Lab 2 is about *seeing* the sync happen with your own hand before you let Argo do it automatically.

**Commit and push** — Argo reads git from GitHub, not your local disk, so the file must be on `main`:

```bash
git add gitops/apps/capstone.yaml
git commit -m "feat(gitops): capstone Application (manual sync)"
git push
```

Then register the Application with Argo by applying it to the cluster (this one apply is the bootstrap; Lab 5 automates even this):

```bash
kubectl apply -f gitops/apps/capstone.yaml
```

### 7. Read the status — `OutOfSync` is expected, not an error

```bash
argocd app get capstone
```

Expected first output:

```
Name:               argocd/capstone
Project:            default
Sync Status:        OutOfSync from main (abc1234)
Health Status:      Missing
...
GROUP  KIND        NAMESPACE  NAME      STATUS     HEALTH   HOOK  MESSAGE
       Service     capstone   capstone  OutOfSync  Missing
apps   Deployment  capstone   capstone  OutOfSync  Missing
```

Do **not** panic at `OutOfSync` / `Missing` — read it literally: Argo has *diffed* git against the cluster and found the objects git wants (`Service`, `Deployment`) don't exist in the cluster yet (`Missing`). That's the correct state for an app you haven't synced. `OutOfSync` = "git and cluster disagree"; `Missing` = "this resource isn't live at all." Sync and health, both saying the same true thing: nothing's deployed yet.

In the UI (refresh the browser) you'll see the `capstone` app tile as a **yellow/OutOfSync** card. Click it → a tree of the resources git wants, all ghosted/outlined = not yet applied.

### 8. Sync — apply git's desired state, by hand

```bash
argocd app sync capstone
```

Watch it stream: Argo renders the chart (`repo-server` runs `helm template`), then applies each resource. Output ends with a table where each resource flips to `Synced` and a sync result of `Synced`. Then:

```bash
argocd app get capstone
```

Now expect:

```
Sync Status:   Synced to main (abc1234)
Health Status: Healthy
GROUP  KIND        NAMESPACE  NAME      STATUS  HEALTH   ...
       Service     capstone   capstone  Synced  Healthy
apps   Deployment  capstone   capstone  Synced  Healthy
```

- **`Synced`** — live cluster now matches git's rendered manifests. The diff is empty.
- **`Healthy`** — Argo's per-resource health assessment passed: the Deployment reports all replicas available (it reads `status.availableReplicas` vs `spec.replicas`), the Service exists. *Health* is "does it work," *sync* is "does it match git" — orthogonal, both green now.

In the UI the tile turns **green**, and the resource tree fills in solid: `capstone` Deployment → ReplicaSet → Pod, plus the Service. Click the Pod to see live logs *in the browser* — Argo surfaces the same stdout you've been reading with `kubectl logs`.

#### If the Deployment goes `Progressing` then `Degraded`

`Progressing` = pods still starting (pulling the image, readiness probe not passing yet) — normal for the first few seconds; Argo's health rollup waits. If it settles on **`Degraded`**, the workload genuinely isn't coming up — almost always the image or a probe. Diagnose exactly like Section 4: `kubectl -n capstone get pods`, then `kubectl -n capstone describe pod <name>` (look for `ImagePullBackOff` → wrong image ref in values, or `CrashLoopBackOff` → app erroring), then `kubectl -n capstone logs <name>`. Argo's `Degraded` is just the aggregate of what those commands show — it never hides the real Kubernetes error, it summarizes it.

### 9. Prove the app actually runs

Forward the capstone Service to host **9101** (a *second* forward — 9100 is Argo's UI):

```bash
kubectl port-forward -n capstone svc/capstone 9101:8000
# in another terminal:
curl -s localhost:9101/health      # {"status":"ok"} — the S5 chart, now deployed BY ARGO
```

That health JSON is the S1 healthcheck endpoint, the S5 chart, the S4 cluster — all still true — but the thing that put it there was **git + Argo**, not your `helm install`. That's the whole lab.

## Verify

```bash
argocd app get capstone --refresh    # --refresh forces a fresh git+cluster compare
kubectl get application capstone -n argocd
```

Sync `Synced`, Health `Healthy`, and `curl localhost:9101/health` returns ok.

Then answer aloud:

**1. The install manifest needs `--server-side`. What breaks without it, and why?**

<details><summary>Answer (read after attempting aloud)</summary>

Without it, plain `kubectl apply` stores the whole applied object in a `last-applied-configuration` annotation for client-side diffing. Argo's CRDs are so large that annotation exceeds Kubernetes' ~262 KB limit → `metadata.annotations: Too long`. Server-side apply tracks field ownership *in the API server* instead of one giant annotation, so size isn't a problem. `--force-conflicts` claims field ownership on re-applies (upgrades).

</details>

**2. Right after creating the Application it said `OutOfSync` / `Missing`. Was that an error? What do those two words each mean?**

<details><summary>Answer (read after attempting aloud)</summary>

Not an error — the correct initial state. Argo diffed git against the cluster: `OutOfSync` = git and cluster disagree; `Missing` = the resources git wants don't exist in the cluster yet. Because there was no `automated:` policy, Argo flagged the difference and waited for a manual sync rather than applying it.

</details>

**3. Sync status and health status — give an example of each combination of green/not-green and what it means.**

<details><summary>Answer (read after attempting aloud)</summary>

They're orthogonal. `Synced`+`Healthy` = matches git and works (normal). `Synced`+`Degraded` = matches git but git's version is broken (a bad image you committed). `OutOfSync`+`Healthy` = someone hand-changed the cluster and it works, but it no longer matches git (drift — Lab 3). `OutOfSync`+`Missing` = git wants resources that aren't deployed (fresh app before first sync). Sync = "matches git", health = "actually works".

</details>

**4. Which Argo component actually does the reconcile, and which one clones the repo and runs `helm template`?**

<details><summary>Answer (read after attempting aloud)</summary>

The **application-controller** (a StatefulSet — it holds reconcile state) does the diff-git-vs-cluster-and-apply loop. The **repo-server** clones the git repo and renders manifests (`helm template`, kustomize, or plain YAML). `argocd-server` is just the front door (UI/API/gRPC); redis caches rendered manifests.

</details>

## Clean up

**Leave Argo CD installed and the `capstone` app synced** — Labs 3–5 build directly on it. Just stop the port-forwards when you're done (`Ctrl-C` in their terminals); re-run them next session. Nothing to delete.

If you had a hand-installed Helm release from Lab 1 step 3 and see *two* capstones now, uninstall the manual one so Argo is the sole owner: `helm uninstall <release> -n <its-namespace>`. From here, Argo owns the deploy.
