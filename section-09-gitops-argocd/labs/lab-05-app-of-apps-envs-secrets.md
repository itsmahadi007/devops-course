# Lab 5 — App-of-apps, environments, and the secrets-in-git problem

**Goal:** scale from one app to *many, declaratively*. You'll build an **app-of-apps** root that plants staging + prod capstone environments from git, then confront the one thing you must never commit — secrets — and solve it honestly with **Sealed Secrets**. This is the layout a real platform team ships.

## The mental map (read this first)

So far one Application = one `kubectl apply` by you. That doesn't scale — a real cluster has dozens of apps across several environments, and applying each by hand is the manual push-model creeping back in. The fix is to **manage Applications with Argo, the same way Argo manages everything else**: put the Application manifests in git, and point *one* root Application at the folder that holds them.

```
  gitops/bootstrap/root-app.yaml   ← you apply THIS once, ever
        │  (an Application whose path is gitops/apps/)
        ▼
  Argo syncs gitops/apps/ → finds three Application manifests → creates them:
        ├── capstone-staging  ──▶ capstone/chart + values-staging.yaml → ns capstone-staging
        ├── capstone-prod     ──▶ capstone/chart + values-prod.yaml    → ns capstone-prod
        └── capstone-secrets  ──▶ gitops/secrets/staging (a SealedSecret) → ns capstone-staging
```

This is called **app-of-apps**: the root app's "resources" *are other apps*. Add a new app to the platform? Drop a manifest in `gitops/apps/`, and the root app creates it on the next sync — no bootstrap step, no `kubectl apply`. The reconcile loop now manages the *inventory of apps* itself. It's turtles all the way down, and that's the point.

**Environments = the same chart, different values.** staging and prod both render `capstone/chart/`; they differ only in a values file (`values-staging.yaml` vs `values-prod.yaml` — replica count, resource limits, image tag) and a target namespace. This is exactly the Section 5 values-layering lesson (`values.yaml` base + overlay), now used to separate environments. No copy-pasted charts.

### The secrets problem, stated honestly

GitOps says "git is the source of truth for everything the cluster runs." But some of what the cluster runs is **secret** — a database password, an API key. And this repo is **public**. You cannot commit a plaintext `Secret` (a Kubernetes `Secret` is only base64-*encoded*, not encrypted — Section 4's "Secrets aren't secret" lesson; anyone can `base64 -d` it). So there's a real tension:

```
  GitOps wants:  everything in git
  Security wants: secrets never in git (esp. a PUBLIC repo)
  ───────────────────────────────────────────────────────
  Resolution: commit secrets ENCRYPTED. Only the cluster can decrypt.
```

The two mainstream answers:

| Approach | How it works | Trade-off |
|---|---|---|
| **Sealed Secrets** (this lab) | A controller in the cluster holds a private key. `kubeseal` encrypts your Secret with the matching *public* key into a `SealedSecret` CRD you commit. Only that controller (that cluster) can decrypt it into a real Secret. | Dead simple, self-contained, $0. Encrypted blob is scoped to one namespace+name by default. |
| **SOPS + age** | Encrypt files with an `age` key; a plugin decrypts at sync time. Key lives outside the cluster (in a KMS ideally). | More flexible (multi-tool, KMS integration) but more moving parts and key management. |

We pick **Sealed Secrets** because it's the simplest currently-maintained option and needs zero external key store: install one controller, install one CLI, done. The mental model that makes it click: **it's public-key crypto, exactly like your SSH keys in Section 1.** The controller publishes a *public* key (safe to share, safe to encrypt with); it keeps the *private* key inside the cluster (never leaves, does the decrypting). You seal with the public key; only the cluster unseals. A sealed blob on a public repo is useless to everyone except the one cluster holding the private half.

## Steps

### 1. Add per-environment values to the chart

Two small overlay files. Create `capstone/chart/values-staging.yaml`:

```yaml
# staging: cheap and loud — one replica, tight limits
replicaCount: 1
resources:
  requests: { cpu: 50m, memory: 64Mi }
  limits:   { cpu: 200m, memory: 128Mi }
```

Create `capstone/chart/values-prod.yaml`:

```yaml
# prod: more headroom — two replicas, higher limits
replicaCount: 2
resources:
  requests: { cpu: 100m, memory: 128Mi }
  limits:   { cpu: 500m, memory: 256Mi }
```

(Match the field names to your S5 chart; the point is *the same chart, two value overlays*.) Each environment Application will render `values.yaml` **then** its overlay — later files win, exactly like S5's layering.

### 2. Write the two environment Applications

Create `gitops/apps/capstone-staging.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: capstone-staging
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/itsmahadi007/devops-course.git
    targetRevision: main
    path: capstone/chart
    helm:
      valueFiles:
        - values.yaml            # base
        - values-staging.yaml    # overlay — later file wins
  destination:
    server: https://kubernetes.default.svc
    namespace: capstone-staging
  syncPolicy:
    automated: { prune: true, selfHeal: true }
    syncOptions:
      - CreateNamespace=true
```

Create `gitops/apps/capstone-prod.yaml` — identical except the three lines that differ:

```yaml
metadata:
  name: capstone-prod
# ...
    helm:
      valueFiles:
        - values.yaml
        - values-prod.yaml       # ← prod overlay
  destination:
    namespace: capstone-prod     # ← prod namespace
```

(Write it out in full — copy `capstone-staging.yaml` and change `name`, the overlay filename, and `namespace`.)

### 3. Retire the single-namespace app from Labs 2–4

The old `capstone` app (namespace `capstone`) was the training vehicle; staging/prod replace it. Remove its manifest and delete the app so the root app is the sole manager:

```bash
git rm gitops/apps/capstone.yaml
argocd app delete capstone --cascade      # --cascade also deletes the resources it created
```

`--cascade` tells Argo to delete the app *and* the Deployment/Service it deployed (otherwise they'd orphan). Confirm: `kubectl get ns capstone` — the namespace's workloads are gone.

### 4. Write the app-of-apps root

Create `gitops/bootstrap/root-app.yaml` — the one manifest you apply by hand, whose job is to manage all the others:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: root
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/itsmahadi007/devops-course.git
    targetRevision: main
    path: gitops/apps           # ← the folder full of Application manifests
    directory:
      recurse: true             # read every manifest in the folder
  destination:
    server: https://kubernetes.default.svc
    namespace: argocd           # the child Applications live in argocd, like all Apps
  syncPolicy:
    automated: { prune: true, selfHeal: true }
```

Notice `path: gitops/apps` and no Helm block — this app deploys **plain manifests** (the `.yaml` Application files), so Argo just applies them as-is. `prune: true` here means: delete a manifest from `gitops/apps/` and the root app deletes that child Application (and, cascading, its workloads). The inventory is now git-managed end to end.

**Commit and push everything, then apply the root once:**

```bash
git add gitops/ capstone/chart/values-staging.yaml capstone/chart/values-prod.yaml
git commit -m "feat(gitops): app-of-apps root + staging/prod environments"
git push
kubectl apply -f gitops/bootstrap/root-app.yaml     # the ONE manual apply, forever
```

### 5. Watch the orchard plant itself

```bash
argocd app list
```

Expected, after a sync cycle:

```
NAME               SYNC STATUS   HEALTH   ...
root               Synced        Healthy       ← manages the two below
capstone-staging   Synced        Healthy       ← created BY root, not by you
capstone-prod      Synced        Healthy       ← created BY root, not by you
```

In the UI the `root` app's resource tree shows **two Application tiles as its children** — click through and you drill into each environment's Deployment/Service. You applied one file; three apps exist. That's app-of-apps.

```bash
kubectl get deploy -A | grep capstone
# capstone-staging   capstone   1/1   ← one replica (staging overlay)
# capstone-prod      capstone   2/2   ← two replicas (prod overlay)
```

Same chart, two environments, replica counts straight from the overlay files. Verify prod runs:

```bash
kubectl port-forward -n capstone-prod svc/capstone 9101:8000
curl -s localhost:9101/health      # {"status":"ok"}
```

### 6. Install Sealed Secrets (controller + CLI)

The controller lives in the cluster and holds the private key; `kubeseal` is your local encrypt tool.

```bash
# controller into the cluster (kube-system) — pin the version (verify latest: v0.38.3)
kubectl apply -f https://github.com/bitnami/sealed-secrets/releases/download/v0.38.3/controller.yaml
kubectl -n kube-system rollout status deploy/sealed-secrets-controller

# the CLI (verify latest: 0.38.4)
brew install kubeseal
kubeseal --version
```

On first start the controller **generates a keypair and stores it in a Secret in kube-system**. That private key is the one thing that must never leave the cluster — it's the SSH-private-key equivalent. (In prod you'd back it up securely; lose it and every SealedSecret becomes undecryptable.)

### 7. Seal a secret — the crypto in three commands

Make a normal Secret manifest *locally* (never committed), pipe it through `kubeseal`, commit only the sealed output.

```bash
# 1. Build a plaintext Secret — this file NEVER touches git. --dry-run means it isn't created either.
kubectl create secret generic capstone-config \
  --namespace capstone-staging \
  --from-literal=API_KEY=super-secret-demo-value \
  --dry-run=client -o yaml > /tmp/capstone-secret.yaml

# 2. Seal it: kubeseal fetches the controller's PUBLIC key and encrypts.
kubeseal --format yaml \
  --controller-namespace kube-system \
  --controller-name sealed-secrets-controller \
  < /tmp/capstone-secret.yaml \
  > gitops/secrets/staging/sealed-secret.yaml    # (mkdir -p this path first)

# 3. Look at what you're about to commit — the API_KEY is now ciphertext:
cat gitops/secrets/staging/sealed-secret.yaml
```

The output is a `kind: SealedSecret` with an `encryptedData.API_KEY` field full of base64 gibberish. **This is safe to commit to a public repo** — it's encrypted with the cluster's public key; only the controller's private key can turn it back into a Secret, and by default only in the `capstone-staging` namespace under the name `capstone-config` (the "strict scope" — the blob is bound to that namespace+name so it can't be copied elsewhere). Delete the plaintext:

```bash
rm /tmp/capstone-secret.yaml
```

#### Why sealing is namespace+name scoped (and what breaks if you ignore it)

By default `kubeseal` binds the ciphertext to the exact namespace and name in your Secret. Move the SealedSecret to a different namespace, or rename it, and the controller **refuses to decrypt** — this stops someone from lifting your sealed prod secret into a namespace they *can* read and unsealing it there. It's why we seal for `capstone-staging` specifically. If you later want one sealed blob usable in several namespaces you'd re-seal with `--scope namespace-wide` or `cluster-wide`, trading a bit of that safety for reuse. For now, strict scope is the right default.

### 8. Let Argo deploy the SealedSecret

Add one more child app so the root plants it too. Create `gitops/apps/capstone-secrets.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: capstone-secrets
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/itsmahadi007/devops-course.git
    targetRevision: main
    path: gitops/secrets/staging     # the SealedSecret manifest
    directory: { recurse: true }
  destination:
    server: https://kubernetes.default.svc
    namespace: capstone-staging
  syncPolicy:
    automated: { prune: true, selfHeal: true }
    syncOptions:
      - CreateNamespace=true
```

```bash
git add gitops/apps/capstone-secrets.yaml gitops/secrets/staging/sealed-secret.yaml
git commit -m "feat(gitops): sealed API_KEY for capstone-staging, deployed via Argo"
git push
```

The root app sees the new child manifest and creates `capstone-secrets`, which deploys the `SealedSecret`. Then the **sealed-secrets controller** notices the `SealedSecret`, decrypts it with its private key, and produces a real `Secret` in the namespace:

```bash
argocd app get capstone-secrets                       # Synced / Healthy — the SealedSecret is applied
kubectl -n capstone-staging get sealedsecret          # capstone-config (what git holds)
kubectl -n capstone-staging get secret capstone-config -o jsonpath='{.data.API_KEY}' | base64 -d ; echo
# → super-secret-demo-value   ← the controller decrypted it INSIDE the cluster
```

Trace the whole chain out loud: plaintext existed only on your laptop for one command → sealed with a public key → committed as ciphertext → Argo deployed the ciphertext → the in-cluster controller (holding the private key) decrypted it into a usable Secret. **The plaintext never touched git, and the ciphertext on the public repo is useless to anyone but this cluster.** That's the honest resolution to the secrets-in-git tension.

#### If the Secret never appears (only the SealedSecret)

The controller isn't decrypting. Check `kubectl -n kube-system logs deploy/sealed-secrets-controller` — the usual cause is a **scope mismatch**: the SealedSecret's namespace/name doesn't match what you sealed it for (you sealed for `capstone-staging`/`capstone-config` — deploying it anywhere else silently fails to decrypt, by design). Re-seal for the right namespace+name.

## Verify

```bash
argocd app list         # root, capstone-staging, capstone-prod, capstone-secrets — all Synced/Healthy
kubectl get deploy -A | grep capstone          # staging=1 replica, prod=2 — from the overlays
kubectl -n capstone-staging get secret capstone-config -o jsonpath='{.data.API_KEY}' | base64 -d ; echo
```

One `kubectl apply` (the root) created the whole platform; the two environments differ only by values file; a real secret rode through a public repo encrypted.

Then answer aloud:

**1. What is app-of-apps, and what problem does it solve that Lab 2's single `kubectl apply` didn't?**

<details><summary>Answer (read after attempting aloud)</summary>

App-of-apps is one root Application whose git path contains *other* Application manifests — so its "resources" are apps. You apply the root once; it creates and manages all the children. It solves the fact that applying each Application by hand is the manual push-model returning: now the inventory of apps is itself in git and reconciled, so adding an app is just committing a manifest to the watched folder.

</details>

**2. staging and prod run the *same* chart. How do they differ, and which Section 5 idea is that?**

<details><summary>Answer (read after attempting aloud)</summary>

They render the same `capstone/chart/` but with different value overlays (`values-staging.yaml` vs `values-prod.yaml` — replica count, resource limits) and target different namespaces. That's Section 5's values layering: a base `values.yaml` plus a per-environment overlay where the later file wins. No duplicated charts.

</details>

**3. Why can't you commit a plain Kubernetes `Secret`, and how does Sealed Secrets fix it? Map it to something from Section 1.**

<details><summary>Answer (read after attempting aloud)</summary>

A Kubernetes Secret is only base64-*encoded*, not encrypted — anyone can `base64 -d` it, and this repo is public. Sealed Secrets uses public-key crypto (like SSH keys in Section 1): the in-cluster controller publishes a public key you encrypt with (`kubeseal`), producing a `SealedSecret` safe to commit; only the controller's private key — which never leaves the cluster — can decrypt it back into a real Secret. Seal with the public half, unseal only inside the cluster.

</details>

**4. Your sealed blob is scoped to `capstone-staging`/`capstone-config`. What does that scope protect against?**

<details><summary>Answer (read after attempting aloud)</summary>

Strict scope binds the ciphertext to one namespace+name, so the controller refuses to decrypt it anywhere else. That stops an attacker (or a mistake) from copying your sealed secret into a namespace they *can* read and unsealing it there. Reuse across namespaces requires re-sealing with `namespace-wide`/`cluster-wide` scope, which trades some of that protection for flexibility.

</details>

## Clean up

Leave the whole platform running — it's the portfolio artifact and Section 10 builds on it. If your Mac feels heavy, scale prod down via a values PR (the Lab 4 flow) rather than by hand — self-heal would revert a hand-edit anyway. Nothing to delete.

### Section wrap

You now have the end-to-end story to tell in an interview and in a LinkedIn post: **push code → CI builds and pushes the image → CI opens a PR bumping the tag → merge → Argo CD reconciles the cluster from git → drift self-heals → rollback is a revert → secrets ride through a public repo encrypted.** The `gitops/` folder is public evidence you can link. Fill in `notes.md` in your own words, clear the checkpoint from memory, and Section 10 (a real self-hosted LLM behind this exact GitOps platform) gets written against your notes.
