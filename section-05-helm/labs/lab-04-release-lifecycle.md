# Lab 4 — Release lifecycle: the ledger, rollback, a failed deploy, and drift

**Goal:** operate the release you built. Upgrade it and watch the ledger grow; crack open a revision and see it's just a Kubernetes Secret holding the whole chart; break an upgrade on purpose and let Helm auto-rescue it; roll back and prove it's `git revert`, not `git reset`; hit an immutable-field wall; and create + observe drift — the gap Section 9's Argo CD exists to close. No new templates: this lab is about the *release*, not the chart.

## The mental map (read this first)

Every `install` and `upgrade` appends one entry to a per-release, per-namespace **ledger**. An entry is a **revision** — an immutable snapshot. The README gave you the git analogy; here's the physical truth you'll see with your own eyes this lab:

```
 helm install/upgrade/rollback
        │  each one appends ONE revision
        ▼
 ledger (namespaced):
   sh.helm.release.v1.capstone.v1   ← a Kubernetes SECRET, type helm.sh/release.v1
   sh.helm.release.v1.capstone.v2   ← gzipped JSON: {full chart + values + rendered manifest + status}
   sh.helm.release.v1.capstone.v3
        │
        │  the ledger only ever moves FORWARD:
        ▼
   rollback to v1  ==  copy v1's snapshot into a NEW revision v4   (revert, never reset)
```

Three facts that fall out, each of which you'll verify:

- **The snapshot is self-contained.** A revision Secret carries the *entire* chart, the values used, and the fully-rendered manifest. So `helm rollback` needs nothing from your laptop — the cluster already holds every past state. Your `capstone/chart/` folder could vanish and rollback would still work.
- **`helm get ...` reads the ledger, not the cluster.** `helm get manifest` shows what Helm *believes* is live (the last revision's rendered YAML). `kubectl get` shows what *is* live. **Drift is the gap between those two** — and you'll manufacture some.
- **An upgrade resets what the chart sets, leaves alone what it never set.** Helm 4 hands that reconciliation to the api-server via server-side apply (field ownership), but the rule of thumb is version-independent.

## Steps

### 1. Read the ledger you already built

Labs 2 and 3 left two revisions. Look:

```bash
helm history capstone
```

```
REVISION  UPDATED  STATUS      CHART           APP VERSION  DESCRIPTION
1         ...      superseded  capstone-0.1.0  0.1.0        Install complete
2         ...      deployed    capstone-0.1.0  0.1.0        Upgrade complete
```

`superseded` = an old revision the ledger has moved past; `deployed` = the one currently live. Now see the ledger's *physical* form — the thing most people never realize exists:

```bash
kubectl get secret -l owner=helm,name=capstone
```

```
NAME                          TYPE                 DATA   AGE
sh.helm.release.v1.capstone.v1  helm.sh/release.v1   1      ...
sh.helm.release.v1.capstone.v2  helm.sh/release.v1   1      ...
```

**That's the ledger — one Secret per revision.** Helm stores release state *in the cluster*, as Secrets, in the release's namespace. Crack one open (it's base64'd by Kubernetes, then base64+gzip'd by Helm — two layers):

```bash
kubectl get secret sh.helm.release.v1.capstone.v2 \
  -o jsonpath='{.data.release}' | base64 -d | base64 -d | gzip -d | head -c 500
```

You'll see JSON beginning with the chart metadata and containing the values and the rendered manifest — the whole self-contained snapshot from the mental map. This is *why* rollback needs nothing from your laptop: the cluster is holding a complete copy of every past deploy.

### 2. A real upgrade — change a value, grow the ledger

Bump replicas via a values override (don't edit the file — `--set` is fine for a lab):

```bash
helm upgrade capstone ./chart --set replicaCount=3
kubectl get pods -l app.kubernetes.io/name=capstone      # 3 api pods now
helm history capstone                                    # revision 3, "deployed"; 1 & 2 "superseded"
```

Confirm what Helm now *believes* is live, straight from the ledger (no cluster query):

```bash
helm get values capstone            # USER-SUPPLIED VALUES: replicaCount: 3
helm get manifest capstone | grep "replicas:"   # replicas: 3
```

`helm get values` shows only what *you* overrode; `helm get values capstone -a` (all) shows the merged result including chart defaults. `helm get manifest` is the rendered YAML of the current revision — Helm's belief about reality.

### 3. Manufacture drift — the gap Section 9 exists to close

Reach past Helm and hand-edit the live cluster, the way a panicking operator would at 3am:

```bash
kubectl scale deploy/capstone --replicas=5      # imperative — Helm knows nothing about this
kubectl get pods -l app.kubernetes.io/name=capstone   # 5 pods live
helm get manifest capstone | grep "replicas:"         # STILL says 3 — Helm's ledger is now WRONG
```

**That's drift**: live state (5) ≠ what Helm believes (3). Helm didn't notice; nothing watches continuously (that's exactly the hole Argo CD fills in S9). Now close the drift the Helm way — re-assert the chart:

```bash
helm upgrade capstone ./chart --set replicaCount=3
kubectl get pods -l app.kubernetes.io/name=capstone   # back to 3
```

The upgrade reset `replicas` because the chart *sets* that field — it owns it. Burn in the rule: **an upgrade reasserts what the chart declares, and leaves alone anything the chart never mentions** (a label some other controller added would survive). S9 automates this reassertion so drift can't live longer than a few seconds.

### 4. Break an upgrade on purpose — and let Helm auto-rescue

Ship a tag that doesn't exist, but this time ask Helm to *wait* for health and undo itself if it fails:

```bash
helm upgrade capstone ./chart \
  --set image.tag=9.9.9 \
  --wait --timeout 90s \
  --rollback-on-failure
```

- `--set image.tag=9.9.9` — not on GHCR (the point).
- `--wait` — Helm blocks until the new pods are actually Ready, instead of returning the moment it applied the manifest.
- `--rollback-on-failure` — **Helm 4's rename of the old `--atomic`** (README noted it): if the wait fails, automatically roll back to the last good revision.

Watch it try, fail, and self-heal. Expected:

```
Error: UPGRADE FAILED: ... timed out waiting for the condition
... Rolling back to revision N ...
Error: UPGRADE FAILED: an error occurred while rolling back ... (or: Rollback was a success)
```

New pods went `ImagePullBackOff` (the bad tag — same as S4 Lab 2), never became Ready, `--wait` timed out, and `--rollback-on-failure` reverted you. Confirm you're whole:

```bash
kubectl get pods -l app.kubernetes.io/name=capstone   # 3 pods Running the GOOD image
helm history capstone                                 # a "failed" revision, then a "deployed" rollback
curl -s localhost:9061/health   # (re-run port-forward if needed) still ok
```

Without `--rollback-on-failure` you'd be stuck with a failed revision and broken pods to clean up by hand — the flag is the seatbelt. (Note the failure *was still recorded* as a revision: the ledger logs failures too, so history tells the truth about what happened.)

### 5. Deliberate rollback — `git revert`, never `git reset`

Now roll back *by choice* to prove the append-only rule. Pick a healthy revision from `helm history` (say the replicaCount=3 upgrade), and roll to it:

```bash
helm history capstone                 # note a good revision number, e.g. 3
helm rollback capstone 3
helm history capstone
```

The new last line is a *fresh* revision (e.g. 7) whose description reads `Rollback to 3` — **not** a rewind that deletes 4/5/6. The ledger only grows. This is why rollback is safe and auditable: nothing is erased, and "roll back the rollback" is just another `helm rollback`. Same discipline as `git revert` — the history is the record, and you add to it, never rewrite it.

### 6. Hit an immutable-field wall

Some Kubernetes fields cannot change on a live object — you asserted this in Lab 2's answer about selector labels. StatefulSet storage is another. Try to grow postgres's disk:

```bash
helm upgrade capstone ./chart --set postgres.storage.size=2Gi
```

Expected failure (the api-server, via server-side apply, rejects it):

```
Error: UPGRADE FAILED: cannot patch "capstone-postgres" with kind StatefulSet:
  StatefulSet.apps "capstone-postgres" is invalid: spec: Forbidden:
  updates to statefulset spec for fields other than 'replicas', 'ordinals',
  'template', ... are forbidden
```

**Read what this is and isn't.** It's not a Helm bug — Helm faithfully rendered a new manifest; the *cluster* refused the change because `volumeClaimTemplates` is immutable once a StatefulSet exists (K8s can't safely resize a bound PVC by editing the template). The interview-grade point: **Helm can only ask; the api-server decides what's legal.** The fix in real life is to delete + recreate the StatefulSet (losing/migrating data) or use a storage class that supports expansion — never a plain `helm upgrade`. Roll the value back so the chart is clean:

```bash
helm upgrade capstone ./chart      # values.yaml still says 1Gi — this succeeds, no StatefulSet change
```

#### If you instead see an immutable *selector* error

If you ever edit `_helpers.tpl`'s `selectorLabels` and upgrade, you'll get `field is immutable` on the Deployment/Service selector — same class of wall, and the reason Lab 2 kept the selector set minimal and frozen. Selectors and StatefulSet storage are the two you'll meet most; the ritual is identical: read the error, recognize the *cluster* (not Helm) is refusing, and know the fix is recreate-not-patch.

## Verify

- `helm history capstone` shows a chain including a `failed` revision (the bad-tag upgrade), a rollback revision, and ends `deployed`.
- You decoded a `sh.helm.release.v1.capstone.vN` Secret and saw it contains chart + values + manifest.
- You created drift with `kubectl scale`, showed `helm get manifest` disagreed with `kubectl get`, and closed it with `helm upgrade`.
- The `postgres.storage.size=2Gi` upgrade failed with an immutable-field error you can explain.

Then answer aloud:

**1. Where does a Helm revision physically live, and why does that mean `helm rollback` needs nothing from your laptop?**

<details><summary>Answer (read after attempting aloud)</summary>

Each revision is a Kubernetes Secret (`sh.helm.release.v1.<name>.v<N>`, type `helm.sh/release.v1`) in the release's namespace, holding gzipped JSON of the *entire* chart, the values supplied, the fully-rendered manifest, and status. So the cluster itself carries a complete, self-contained copy of every past deploy. `helm rollback` just re-applies an old revision's stored manifest — it reads it from the cluster, not from your `chart/` folder, which could be deleted or on another machine entirely.

</details>

**2. `helm rollback capstone 3` — why does `helm history` afterward show a NEW revision instead of the list shrinking back to 3?**

<details><summary>Answer (read after attempting aloud)</summary>

Because the ledger is append-only — `git revert`, never `git reset`. Rolling back to 3 copies revision 3's stored snapshot forward into a brand-new revision (e.g. 7) with description "Rollback to 3." Nothing is deleted; revisions 4/5/6 remain as `superseded` history. This keeps the deploy log truthful and auditable, and means undoing a rollback is just another rollback — you can never lose the record of what was deployed when.

</details>

**3. `helm upgrade` with a bad StatefulSet change fails with "field is forbidden." Whose decision was that — Helm's or the cluster's — and what does that tell you about what Helm actually does?**

<details><summary>Answer (read after attempting aloud)</summary>

The cluster's (the api-server). Helm rendered a perfectly valid new manifest and asked the api-server to apply it; the api-server rejected the change because `volumeClaimTemplates` (like a selector) is immutable on a live StatefulSet. Helm doesn't mutate the cluster itself — it *submits* rendered manifests and the api-server enforces what's legal. So an "immutable field" error is never fixed by Helm flags; it's fixed by recreating the object (delete + reinstall) or using a storage class that supports expansion. Helm asks; Kubernetes decides.

</details>

**4. You `kubectl scale`d to 5, but `helm get manifest` still said 3. What is that gap called, why didn't Helm notice, and what closes it?**

<details><summary>Answer (read after attempting aloud)</summary>

Drift — the difference between live cluster state and what Helm's ledger believes. Helm didn't notice because it's not a running controller; it only reconciles when *you* run `upgrade`/`rollback`. Re-running `helm upgrade` reasserts the chart's declared fields (replicas back to 3) and closes the gap for fields the chart owns. The permanent fix is a controller that reconciles continuously — Section 9's Argo CD watches git and re-applies on any drift, so a hand-edit gets reverted within seconds instead of living until the next manual upgrade.

</details>

## Clean up

**Leave the release deployed and healthy** — Lab 5 opens here. Sanity check and reset any `--set` drift by re-applying the committed chart:

```bash
helm upgrade capstone ./chart          # back to the chart's committed values (replicaCount 2, tag latest)
helm list                              # capstone, deployed
kubectl get pods -l app.kubernetes.io/instance=capstone   # api ×2, redis ×1, postgres ×1, all Running
```

Nothing new to commit — this lab changed the *release*, not the chart. Lab 5 makes the chart multi-environment and defines the image-tag knob that Section 9's GitOps loop will turn.
