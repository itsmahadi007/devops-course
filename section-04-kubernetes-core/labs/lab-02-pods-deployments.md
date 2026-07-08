# Lab 2 — Pods & Deployments: capstone on the cluster

**Goal:** run the capstone from GHCR as a Deployment — then poke it the way production will: kill a pod and watch self-healing, scale it, push a broken rollout and rescue it with one command. By the end, `Section 1 Lab 4's reconcile loop` isn't a spoiler anymore — you'll have watched it fight you and win.

## The mental map (read this first)

You never run "a container" on Kubernetes. You run a **Deployment**, and three layers of machinery unfold beneath it:

```
 Deployment "capstone-api"            ← YOUR file. Owns the pod TEMPLATE + a history
     │  "keep 2 replicas of template rev.1 running"
     ▼
 ReplicaSet capstone-api-6d9f7c…      ← the reconcile loop. Counts pods matching the
     │  "desired 2, actual 2 ✓"          label, creates/deletes to close the gap
     ├──────────────┐
     ▼              ▼
 Pod …-x4kq2     Pod …-9wz7l          ← disposable. Each = your container + an IP.
 (worker)        (worker)                Never healed, always REPLACED
```

Why three layers instead of one? Separation of jobs:

- A **Pod** is the unit of running — your container plus a network identity. Pods are cattle: they get random-suffix names, they die, and nothing ever "fixes" a pod — a fresh one replaces it. (A pod *can* hold multiple containers sharing localhost + volumes — the sidecar pattern. Ours holds one.)
- A **ReplicaSet** is a counter with a vengeance — the literal reconcile loop: *desired N, observed M, act on the difference, forever.* Compose ran that comparison once per `up -d`; this runs it continuously.
- A **Deployment** exists for *change*. When you update the template (new image, new env), it doesn't edit pods — it creates a **new ReplicaSet** and shifts pods from old to new gradually. Old ReplicaSets stick around at size 0 as **history**, which is what makes one-command rollback possible.

The image comes from GHCR — the same `ghcr.io/itsmahadi007/capstone` you pushed in Section 1 Lab 6 and made multi-arch in Section 2. Multi-arch pays off here quietly: your kind node's containerd asks the registry for the image, gets the manifest *list*, and picks the arm64 variant to match the node. On an amd64 CI runner the same YAML pulls the amd64 variant. The `exec format error` class of bug is structurally gone — the manifest is arch-agnostic, the registry serves the right bytes.

## Steps

### 1. Write the Deployment manifest

Create the folder that will hold the whole stack's manifests, and the first file, `capstone/k8s/deployment.yaml`:

```yaml
apiVersion: apps/v1            # which API group+version this object type lives in
kind: Deployment               # what we're declaring
metadata:
  name: capstone-api           # the object's name inside the cluster
  labels:
    app: capstone-api
spec:                          # ── desired state starts here ──
  replicas: 2                  # keep TWO pods alive at all times
  selector:                    # how the Deployment finds "its" pods:
    matchLabels:
      app: capstone-api        #   any pod wearing this label is mine
  template:                    # ── the pod recipe — everything below = one pod ──
    metadata:
      labels:
        app: capstone-api      # every pod is born wearing the label (MUST match selector)
    spec:
      containers:
        - name: api
          image: ghcr.io/itsmahadi007/capstone:latest   # your image, from Section 1/2
          ports:
            - containerPort: 8000   # documentation, like EXPOSE — publishes nothing
```

#### Read it like a story

- **`apiVersion` + `kind` + `metadata.name`** — the address label on every K8s object ever: what type, what version of that type's schema, what name. Muscle-memorize the trio; every manifest in your future starts with it.
- **Labels are the sticky notes of Kubernetes** — arbitrary key/values stuck on objects. Nothing about `app: capstone-api` is special; what's special is that *everything in K8s finds everything else by matching labels*. The Deployment finds its pods by label. Tomorrow the Service (Lab 3) finds pods to route to by label. `kubectl get pods -l app=capstone-api` filters by label. Loose coupling by matching, not by hardcoded references — the same reason compose used *names* instead of IPs.
- **`selector.matchLabels` must equal `template.metadata.labels`** — the one YAML trap in this file. The selector says "I own pods wearing this"; the template says "pods are born wearing this." If they differ, `apply` rejects the Deployment outright (`selector does not match template labels`) — a loud failure, since a mismatch would mean spawning pods it could never find again.
- **`replicas: 2`** — the desired-state number the ReplicaSet will defend with its life. Notice what's *absent* compared to your compose file: no `restart:` policy needed (reconcile is the default), no port publishing (the cluster has its own doors — Labs 3 and 7), no container names to manage (pods get generated names, because they're cattle).
- **`:latest`** — honest warning up front: in real deployments a floating tag is an anti-pattern (you can't tell *what* is deployed, and a rollback to "the same tag" might pull different bytes — Lab 3 of Section 1 taught you tags move). We start with it because it's what's on GHCR; the fix (immutable sha/semver tags driven by CI) is exactly what Sections 5 and 9 build. One side effect to know today: `:latest` defaults `imagePullPolicy` to `Always` — every new pod re-checks the registry, so pod creation needs internet.

### 2. Apply it — and see all three layers

```bash
kubectl apply -f capstone/k8s/deployment.yaml
```

```
deployment.apps/capstone-api created
```

`apply` is `up -d`'s sibling: declarative, idempotent — run it twice, second run says `unchanged` and does nothing. Now look at each layer the README diagram promised:

```bash
kubectl get deploy,rs,pods -o wide
```

```
NAME                           READY   UP-TO-DATE   AVAILABLE   AGE
deployment.apps/capstone-api   2/2     2            2           30s

NAME                                      DESIRED   CURRENT   READY   AGE
replicaset.apps/capstone-api-6d9f7c85b4   2         2         2       30s

NAME                                READY   STATUS    RESTARTS   AGE   IP           NODE
pod/capstone-api-6d9f7c85b4-x4kq2   1/1     Running   0          30s   10.244.1.2   capstone-worker
pod/capstone-api-6d9f7c85b4-9wz7l   1/1     Running   0          30s   10.244.1.3   capstone-worker
```

Read the naming chain: Deployment `capstone-api` → ReplicaSet `capstone-api-<template-hash>` → pods `<replicaset-name>-<random>`. The hash in the ReplicaSet name fingerprints the pod template — change the template, get a new hash, get a new ReplicaSet. Also read the `-o wide` extras: each pod has its **own IP** (from the pod network, `10.244.x.x`) and a **NODE** — both landed on the worker, because the control-plane's taint repelled them (Lab 1). The first pull of your image takes ~15–30s (`STATUS: ContainerCreating`); after that the node has it cached.

What just happened between your Enter key and `Running`, in control-plane terms — this is *the* interview answer, watch it map to Lab 1's tour: **kubectl** POSTs the object to the **api-server** → written to **etcd** → the Deployment controller (in **controller-manager**) sees a Deployment with no ReplicaSet, creates one → the ReplicaSet controller sees desired 2 / actual 0, creates 2 pod objects → the **scheduler** sees 2 pods with no node, binds them to `capstone-worker` → the worker's **kubelet** sees pods bound to it, tells containerd to pull and run → kubelet reports status back up. Every arrow goes through the api-server; nobody talks to anybody directly.

### 3. Prove the app is actually alive

The pods have IPs, but they're on the cluster's internal network — your Mac can't reach `10.244.x.x`. Proper doors come in Lab 3; for now, two tools that need no door:

```bash
kubectl logs deploy/capstone-api
```

Familiar uvicorn startup lines — `Uvicorn running on http://0.0.0.0:8000` — captured exactly like `docker logs`: kubelet reads the container's stdout/stderr. (`deploy/capstone-api` picks one pod for you; `kubectl logs -l app=capstone-api --tail 5 --prefix` streams *all* matching pods with name prefixes — the `compose logs` view.)

```bash
kubectl exec deploy/capstone-api -- python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health').read())"
```

```
b'{"status":"ok"}'
```

Same `exec` mechanism as Section 1 (inject a process into the running container — not SSH), same `python -c urllib` trick as your image's HEALTHCHECK (slim image, no curl). And check `/visits`:

```bash
kubectl exec deploy/capstone-api -- python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/visits').read())"
```

```
b'{"visits":null,"detail":"REDIS_URL not set"}'
```

Correct and expected: no environment wired yet. That's Lab 4's job — and the app degrading gracefully instead of crashing is what makes this staged build-up possible.

### 4. Watch self-healing — the reconcile loop, live

The moment Section 1 has been building toward. Open a second terminal and leave this watching (`-w` = watch, like `docker events` but per-object):

```bash
kubectl get pods -w
```

In the first terminal, murder a pod (use one of YOUR pod names from step 2):

```bash
kubectl delete pod capstone-api-6d9f7c85b4-x4kq2
```

The watch terminal narrates the whole drama:

```
capstone-api-6d9f7c85b4-x4kq2   1/1   Terminating   0     5m    ← your kill
capstone-api-6d9f7c85b4-tr8fn   0/1   Pending       0     0s    ← replacement, INSTANTLY
capstone-api-6d9f7c85b4-tr8fn   0/1   ContainerCreating   0     0s
capstone-api-6d9f7c85b4-tr8fn   1/1   Running       0     2s
```

Nobody asked you anything. The ReplicaSet controller saw desired 2 / actual 1 and closed the gap — new name (cattle), new IP, same template. That's what "self-healing" means mechanically: not resurrection, **replacement to spec**. In compose, a crashed container needed `restart:` policy and the same container came back; here the *object count* is defended by a loop that never sleeps. This loop is what pages stop firing for at 3am. Ctrl-C the watch when done.

### 5. Scale — and learn who the boss is

Imperative scale, the CKA-speed way:

```bash
kubectl scale deploy/capstone-api --replicas=5
kubectl get pods
```

Five pods within seconds. But here's the sharper lesson — your **file still says 2**. Live state and file have drifted. Now re-apply the unchanged file:

```bash
kubectl apply -f capstone/k8s/deployment.yaml
kubectl get pods        # three pods enter Terminating — back to 2
```

The file won. `apply` sets the object back to what's written, and the ReplicaSet culls the extras. Burn this in: **imperative commands are for emergencies and exams; the file is the truth.** (Section 9 weaponizes this exact behavior — Argo CD will run `apply` against git continuously, so *any* hand-edit to the cluster gets reverted. Your compose instinct — "`up -d` makes reality match the file" — scaled to a whole company.)

### 6. Break a rollout on purpose — then rescue it

Production scenario: someone ships a tag that doesn't exist. Do it to yourself, with the watch terminal running again (`kubectl get pods -w`):

```bash
kubectl set image deploy/capstone-api api=ghcr.io/itsmahadi007/capstone:0.2.0
```

(`api=` names which container in the pod; `:0.2.0` doesn't exist on GHCR — that's the point.) The watch shows the new ReplicaSet trying:

```
capstone-api-7b8d9e0f1a-k2m4p   0/1   Pending             0   0s     ← ONE new pod appears…
capstone-api-7b8d9e0f1a-k2m4p   0/1   ErrImagePull        0   3s     ← registry: "manifest unknown"
capstone-api-7b8d9e0f1a-k2m4p   0/1   ImagePullBackOff    0   16s    ← retrying, with growing pauses
```

**Read what did NOT happen: your 2 old pods are still `Running`.** The rolling update's defaults (`maxSurge: 25%`, `maxUnavailable: 25%` — with 2 replicas that rounds to "may add 1 extra, may kill 0") mean K8s adds one new-version pod, waits for it to become ready, and *only then* starts retiring old ones. The new pod never becomes ready → the rollout stalls → **the broken deploy cannot take your service down.** Confirm the stall and diagnose like an operator:

```bash
kubectl rollout status deploy/capstone-api    # "Waiting for deployment... 1 out of 2 new replicas..." — hangs; Ctrl-C
kubectl describe pod capstone-api-7b8d9e0f1a-k2m4p
```

Bottom of `describe`, the **Events** section — the single most valuable debugging real estate in Kubernetes:

```
  Warning  Failed   ... Failed to pull image "ghcr.io/itsmahadi007/capstone:0.2.0":
                        ... ghcr.io/itsmahadi007/capstone:0.2.0: not found
  Normal   BackOff  ... Back-off pulling image ...
```

#### The two BackOffs — learn to tell them apart now

- **`ImagePullBackOff`** — the container **never started**: registry says no (typo'd tag, private image without credentials, wrong registry). The logs are empty — there's nothing to log. Diagnosis lives in `describe` Events, like above.
- **`CrashLoopBackOff`** — the image pulled fine, the container **starts and then dies**, repeatedly; kubelet restarts it with growing delays (10s, 20s, 40s… capped at 5m). Diagnosis lives in the *logs of the previous attempt*: `kubectl logs <pod> --previous` — the flag interviews love, because the current container may be seconds old and empty. You'll trigger a real one in Lab 5 (OOM).

Same triage ritual for both, worth saying aloud: **status → describe (Events) → logs (`--previous` if crashing)**.

Now the rescue — one command, the whole reason Deployments keep ReplicaSet history:

```bash
kubectl rollout undo deploy/capstone-api
kubectl rollout status deploy/capstone-api    # "deployment ... successfully rolled out"
kubectl rollout history deploy/capstone-api   # revision 3 = revision 1's template, re-activated
```

Under the hood: no files restored, no images rebuilt — the Deployment just scaled the old ReplicaSet (whose template still says `:latest`) back up and the broken one down to 0. `kubectl get rs` shows the corpse: the `0.2.0` ReplicaSet sitting at `DESIRED 0`, kept as history. One more honest note: `kubectl set image` was imperative drift again (your file never said `0.2.0` — which here worked in your favor). The grown-up flow is: edit file → commit → apply; rollback = revert the commit. That's Section 9's whole religion.

## Verify

- `kubectl get deploy capstone-api` shows `READY 2/2`; both pods sit on the worker with pod-network IPs.
- You watched a deleted pod get replaced without your help, and can name which controller did it.
- You broke a rollout with a bad tag, proved the old pods kept serving, and rescued with `rollout undo`.
- Answer aloud:

- Deployment, ReplicaSet, Pod — why three layers? What is each one's single job?

  <details><summary>Answer (read after attempting aloud)</summary>

  Pod = the disposable unit of running (container + IP + name); it's never repaired, only replaced. ReplicaSet = the reconcile loop: keep N pods matching a label alive, forever. Deployment = the change manager: template updates create a *new* ReplicaSet and shift pods over gradually; old ReplicaSets stay at 0 as history, which is what makes `rollout undo` instant. Separating "keep N alive" from "manage change between versions" is what lets a broken rollout stall harmlessly instead of taking the service down.

  </details>

- Walk `kubectl apply -f deployment.yaml` through the control plane, component by component.

  <details><summary>Answer (read after attempting aloud)</summary>

  kubectl → **api-server** (auth, validation) → object stored in **etcd** → **Deployment controller** notices, creates a ReplicaSet → **ReplicaSet controller** notices desired>actual, creates pod objects → **scheduler** notices unbound pods, writes a node assignment → that node's **kubelet** notices pods bound to it, has containerd pull+run, runs probes, reports status → api-server writes status to etcd. Every step is watch-and-react through the one door; no component calls another directly.

  </details>

- `ImagePullBackOff` vs `CrashLoopBackOff` — cause, and where the evidence lives for each?

  <details><summary>Answer (read after attempting aloud)</summary>

  ImagePullBackOff: the image never arrived (bad tag, missing credentials, wrong registry) — container never ran, so logs are empty; evidence is in `kubectl describe pod` → Events (the registry's error verbatim). CrashLoopBackOff: image ran and the process keeps dying — evidence is in `kubectl logs <pod> --previous` (the *last* attempt's output; the current container is often too young to have any). Ritual: status → describe → logs.

  </details>

- Why did the broken `:0.2.0` rollout not cause downtime, and what exactly did `rollout undo` do?

  <details><summary>Answer (read after attempting aloud)</summary>

  RollingUpdate defaults: add up to 25% extra pods (surge 1 here), take at most 25% below desired (0 here) — and old pods are only retired when new ones report ready. The new pod never got ready (no image), so retirement never began; both old pods kept serving throughout. `undo` scaled the previous ReplicaSet back to 2 and the broken one to 0 — no rebuild, no re-pull, just shifting counts between two recipes it already had.

  </details>

- You ran `kubectl scale --replicas=5`, then `kubectl apply` of the unchanged file dropped it to 2. Why is that behavior a feature?

  <details><summary>Answer (read after attempting aloud)</summary>

  Because the file is the single source of truth and `apply` enforces it — same contract as `up -d`. Imperative edits are drift; drift that survives silently becomes "why is prod different from the repo" at the worst moment. GitOps (Section 9) turns this into policy: a controller applies git continuously, so all drift is reverted within seconds — hand-edits included.

  </details>

## Clean up

Nothing to remove — the Deployment (2 replicas, `:latest`, healthy) is the base every following lab builds on. Just make sure the drill debris is gone:

```bash
kubectl rollout history deploy/capstone-api   # fine if it lists a few revisions — that's history, not debris
kubectl get pods                              # exactly 2, Running, RESTARTS 0
```

Commit `capstone/k8s/deployment.yaml`. Update the capstone evolution log: "Section 4: first Kubernetes manifests — Deployment on kind."
