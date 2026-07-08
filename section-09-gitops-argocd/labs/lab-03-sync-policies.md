# Lab 3 — Sync policies + the drift experiment

**Goal:** turn the manual sync from Lab 2 into a fully automated reconcile loop — `automated` + `prune` + `selfHeal` — then break the cluster by hand and watch Argo put it back. This is the Section 1 Lab 4 reconcile loop in its final form, and the demo that makes GitOps click.

## The mental map (read this first)

Lab 2's app synced *only when you told it to*. That's training wheels. In production you want the loop to run itself, and there are exactly three knobs that decide how aggressive it is:

```
  syncPolicy.automated:
     enabled  ── "when git changes, apply it — don't wait for a human"
     prune    ── "if git DELETES a resource, delete it from the cluster too"
     selfHeal ── "if the CLUSTER drifts from git, force it BACK to git"
```

The three knobs answer three different questions:

```
  git changed  ─────────────▶  automated   ── pushes the new desired state out
  git removed a resource ────▶  prune       ── cluster stops keeping orphans
  cluster changed (drift) ───▶  selfHeal    ── cluster loses the argument, git wins
```

Default Argo behavior is deliberately timid, and understanding *why* is the lab:

- **Without `prune`**, deleting a resource from git leaves it running in the cluster (Argo won't delete things unless you opt in — deleting is dangerous). You just get an `OutOfSync` warning.
- **Without `selfHeal`**, a hand-edit to the cluster shows as `OutOfSync` but Argo *leaves it* — it tells you about the drift and waits. Useful when you're mid-incident and hand-patching on purpose.
- **With `selfHeal`**, the same hand-edit gets **reverted within seconds** — the cluster physically cannot hold a change that isn't in git. This is the "3am hack undoes itself" property from the lesson, and the single best live demo of GitOps.

### First principles: how Argo decides *what* and *in what order*

Three internal machines you should be able to name in an interview:

1. **Diffing.** Argo renders desired state (`helm template`), normalizes both sides (drops server-managed noise like `status`, defaulted fields, and configured `ignoreDifferences`), and does a structural compare. Result → `Synced` / `OutOfSync`, per resource.
2. **Health assessment.** Per *kind*, Argo has a health rule. Deployment = Healthy when `updatedReplicas`/`availableReplicas` meet `spec.replicas` and `observedGeneration` is current; Pod = Healthy when Running/Ready; Service = basically always Healthy; PVC = Healthy when Bound. Custom resources can ship Lua health checks. The app's health = the rollup of its resources.
3. **Sync waves.** When applying, Argo orders resources: first by *kind* (Namespaces and CRDs before things that live in them), then by the `argocd.argoproj.io/sync-wave` annotation (an integer, default `0`, applied low→high), then by name. Between waves Argo waits for the previous wave's resources to be **Healthy**. This is how you say "create the database before the app that needs it" — the database gets `sync-wave: "-1"`. Sync *hooks* (`PreSync`/`Sync`/`PostSync`) are the same idea for one-off Jobs like migrations.

You won't need waves until the app grows dependencies (S10's LLM subchart), but naming them is interview gold, so they're in the checkpoint.

## Steps

### 1. Turn on automated sync (in git, where else)

Edit `gitops/apps/capstone.yaml` — add the `automated` block under `syncPolicy`:

```yaml
  syncPolicy:
    automated:
      prune: true        # git deletes a resource → Argo deletes it from the cluster
      selfHeal: true     # cluster drifts from git → Argo forces it back
    syncOptions:
      - CreateNamespace=true
```

Because Argo deploys *from git*, the honest way to change the policy is to change git and let Argo pick it up — but the Application object *itself* isn't managed by Argo yet (Lab 5 fixes that with app-of-apps). So for now, push **and** apply:

```bash
git add gitops/apps/capstone.yaml
git commit -m "feat(gitops): enable auto-sync, prune, self-heal on capstone"
git push
kubectl apply -f gitops/apps/capstone.yaml    # register the new policy with Argo
```

Watch the UI: the app tile gains an **auto-sync** badge. From now on, any change to git under `capstone/chart/` (or the values it renders) gets applied without you clicking anything.

### 2. Drift experiment #1 — scale by hand, watch it snap back

This is the money demo. Simulate the 3am incident hack: someone scales the Deployment directly on the cluster, bypassing git.

```bash
kubectl -n capstone scale deployment capstone --replicas=3
kubectl -n capstone get pods -w      # watch — 3 pods appear... then vanish
```

What you'll see: three pods spin up (`0/1`→`1/1`), and within a few seconds **two of them terminate** and you're back to one. You didn't do that — **self-heal did.** Argo's controller noticed live-state (`replicas: 3`) ≠ git-state (`replicas: 1` from the chart's values), declared the app `OutOfSync`, and — because `selfHeal: true` — immediately re-applied git's `replicas: 1`, scaling it back down.

Check the app events to see it in Argo's own words:

```bash
argocd app get capstone
# Sync Status briefly showed OutOfSync, then Synced again
kubectl -n argocd get events --field-selector involvedObject.name=capstone --sort-by=.lastTimestamp | tail
```

The lesson, out loud: **the cluster is no longer a place you can durably change.** The only edit that survives is an edit to git. That's not a limitation — it's the entire point. Your kubectl-scale was treated exactly like a disk error: something that drifted from declared truth, so the controller closed the gap.

#### If it does NOT snap back

Two usual causes. (a) `selfHeal` isn't actually applied — `argocd app get capstone` shows the sync policy near the top; if it doesn't say self-heal is on, your `kubectl apply` in step 1 didn't take (re-apply, check for typos in the YAML). (b) Self-heal has a short back-off (a few seconds) so it doesn't thrash — give it ~5–10s. It also only reacts to drift it *detects*; a manual `argocd app get --refresh` forces an immediate compare.

### 3. Drift experiment #2 — edit a field, same result

Scaling is dramatic; a field edit is subtler and more realistic (someone hand-patches an env var during a fire):

```bash
kubectl -n capstone set env deployment/capstone HACKED=true
kubectl -n capstone get deployment capstone -o jsonpath='{.spec.template.spec.containers[0].env}' ; echo
```

Within seconds, re-run that `jsonpath` — the `HACKED` var is **gone**. Self-heal reverted the whole pod template to what the chart renders. Same loop, any field: Argo doesn't diff "the thing you touched," it diffs the *entire desired manifest* against live and reconciles all of it.

### 4. Prune experiment — delete a resource *from git*

Now the other knob. `prune` governs what happens when git wants *fewer* resources than exist. Temporarily add a throwaway resource to the chart so you can watch it be pruned. Create `capstone/chart/templates/scratch-configmap.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: scratch-demo
  namespace: {{ .Release.Namespace }}
data:
  note: "this exists only to demonstrate prune"
```

```bash
git add capstone/chart/templates/scratch-configmap.yaml
git commit -m "chore(capstone): add scratch configmap to demo prune"
git push
```

Auto-sync applies it within the poll interval (~3 min by default, or click **Refresh → Sync** in the UI to hurry). Confirm it's live:

```bash
kubectl -n capstone get configmap scratch-demo    # exists
```

Now **delete it from git** and watch prune remove it from the cluster:

```bash
git rm capstone/chart/templates/scratch-configmap.yaml
git commit -m "chore(capstone): remove scratch configmap (demo prune)"
git push
# force a refresh instead of waiting for the poll:
argocd app sync capstone
kubectl -n capstone get configmap scratch-demo    # Error: not found — PRUNED
```

`prune: true` is what let Argo *delete* it. With prune off, that ConfigMap would linger in the cluster forever as an `OutOfSync` orphan, and you'd get a warning instead of a cleanup. Prune is opt-in precisely because "automatically delete cluster resources" is a foot-gun worth an explicit yes.

#### The scary version of prune (know it, don't trigger it)

`prune` deletes *anything* Argo owns that leaves git — including, if you fat-finger a path or point an app at an empty directory, **every resource the app manages**. Argo has a `prune=false` per-resource annotation and a `PruneLast` option for exactly this fear, and production setups often gate prune behind a manual confirm. For this lab it's safe because the blast radius is one namespace of a demo app.

### 5. See the diff Argo sees

When an app is `OutOfSync`, ask Argo *what exactly* differs — the same `helm template` output, diffed against live:

```bash
# create drift again, then look:
kubectl -n capstone scale deployment capstone --replicas=2
argocd app diff capstone      # prints a red/green diff: live replicas:2 vs desired replicas:1
```

(Self-heal will revert it right after, so run the `diff` quickly, or temporarily `argocd app set capstone --self-heal=false` to freeze the drift while you inspect — then turn it back on.) This `diff` is the exact structural compare from the "diffing" first-principle above, made visible. It's your everyday tool for "why does Argo think this is OutOfSync?"

## Verify

```bash
argocd app get capstone     # Sync: Synced, Health: Healthy, policy shows auto-sync + prune + self-heal
kubectl -n capstone get deployment capstone -o jsonpath='{.spec.replicas}' ; echo   # 1 — self-heal holds it
```

Best proof: run `kubectl -n capstone scale deployment capstone --replicas=5`, wait 10 seconds, re-check replicas — it's back to 1, and you did nothing.

Then answer aloud:

**1. Name the three `automated` knobs and the distinct question each answers.**

<details><summary>Answer (read after attempting aloud)</summary>

`automated` (enabled): *git changed* → apply it without waiting for a human. `prune`: *git removed a resource* → delete it from the cluster too (opt-in because deleting is dangerous). `selfHeal`: *the cluster drifted from git* → force it back to git. Three different triggers: new desired state, removed desired state, live drift.

</details>

**2. You `kubectl scale`d to 3 replicas and it snapped back to 1. Walk through what Argo did, step by step.**

<details><summary>Answer (read after attempting aloud)</summary>

The application-controller compared live state (replicas 3) against desired state rendered from git (replicas 1), found they differ → marked the app `OutOfSync`. Because `selfHeal: true`, it didn't just warn — it re-applied the git-desired manifest, setting replicas back to 1, so two pods were terminated. The cluster can't durably hold a change that isn't in git; the only surviving edit is an edit to git.

</details>

**3. You deleted a template from git. With `prune: true` vs `false`, what happens to the live resource?**

<details><summary>Answer (read after attempting aloud)</summary>

With `prune: true`, Argo deletes the live resource because it's no longer in git's desired state. With `prune: false` (default), Argo won't delete it — the orphan keeps running and the app shows `OutOfSync` with a warning until you clean it up manually. Prune is opt-in because auto-deleting cluster resources is a foot-gun.

</details>

**4. What are sync waves, and give a concrete case where you'd need one.**

<details><summary>Answer (read after attempting aloud)</summary>

Sync waves order how Argo applies resources: kind ordering first (Namespaces/CRDs before their contents), then the `argocd.argoproj.io/sync-wave` integer annotation low→high, waiting for each wave to be Healthy before the next. Concrete case: put a database (or a DB migration Job as a PreSync hook) in an earlier wave than the app that depends on it, so the app doesn't start before its dependency is ready — e.g. the LLM model server before the API that calls it in Section 10.

</details>

## Clean up

Leave auto-sync, prune, and self-heal **on** — that's the desired end state for the rest of the section. If you set `--self-heal=false` in step 5, turn it back on: `argocd app set capstone --self-heal=true` (or just re-`kubectl apply` the manifest). The scratch ConfigMap is already gone (you pruned it). App stays running for Lab 4.
