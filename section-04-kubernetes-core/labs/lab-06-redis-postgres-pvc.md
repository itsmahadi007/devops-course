# Lab 6 — Redis + Postgres in-cluster: the PVC, and the payoff

**Goal:** stand up `redis` and `postgres` as in-cluster Services so the `REDIS_URL` you wired in Lab 4 finally resolves and `/visits` returns real numbers. Along the way, translate your Section 1 Lab 4 volume lesson to cluster scale: redis gets **no** persistent storage (stateless cache — same decision as compose), Postgres gets a **PersistentVolumeClaim** for `pgdata`. Then prove it the same way you proved it in compose — write data, delete the pod, watch the data survive. You'll also meet the **Deployment-vs-StatefulSet** decision every K8s interview asks about.

## The mental map (read this first)

Your compose stack had three services; you've rebuilt one (the api) on Kubernetes across Labs 2–5. Now the other two. The translation table from the README, made concrete:

```
   compose service        →   Kubernetes objects
   ─────────────────────      ─────────────────────────────────────────
   redis (no volume)      →   Deployment + Service          (stateless — nothing to persist)
   db (pgdata volume)     →   Deployment + Service + PVC    (stateful — the claim ticket for storage)
```

Two genuinely new ideas ride in on Postgres:

**1. The storage trio — PVC, PV, StorageClass.** In compose you wrote `volumes: pgdata:` and Docker created a managed parking spot. Kubernetes splits that one act into three roles so storage can be portable across clouds:

```
   PersistentVolumeClaim (PVC)   "I need 1Gi of storage"        ← YOU write this (a request)
              │  binds to
              ▼
   PersistentVolume (PV)         "here is an actual 1Gi disk"   ← PROVISIONED for you
              │  carved from
              ▼
   StorageClass                  "how to make disks on demand"  ← the local-path-provisioner
                                                                   you saw in Lab 1's pod list
```

You write only the **claim** (PVC) — "I want this much, this access mode." A **StorageClass** (kind ships `standard`, backed by the `local-path-provisioner` pod from Lab 1) hears the claim and *dynamically provisions* a matching **PersistentVolume** (an actual directory on the node), then binds them. This indirection is the whole point: your manifest says "I need storage," not "mount `/mnt/disk3` on this specific machine" — so the same PVC works on kind (local disk), on AWS (an EBS volume), on GCP (a persistent disk). The claim is portable; the provisioner is swappable. It's the Docker named-volume idea with a cloud-portability seam cut into the middle.

**2. Deployment vs StatefulSet.** You'll run Postgres as a **Deployment** here (one replica + one PVC), and that's correct for this lab — but you must be able to say *when* you'd reach for a **StatefulSet** instead:

- **Deployment** = interchangeable, anonymous pods (`...-6d9f7c-x4kq2`). Perfect for stateless apps and for a *single* database instance sharing one PVC. Scaling a DB Deployment to 2, though, would point two Postgres processes at the *same* disk → corruption. Deployments assume pods are interchangeable; databases are not.
- **StatefulSet** = pods with **stable identities** (`postgres-0`, `postgres-1`, ...), **stable per-pod storage** (each replica gets its *own* PVC via `volumeClaimTemplates`), and **ordered** startup/shutdown. That's what you need for a *clustered* database or anything where "which replica am I, and is my disk mine alone?" matters (Postgres replicas, Kafka, etcd itself).

The honest rule: **single instance → Deployment + PVC is fine and simpler; replicated stateful system → StatefulSet.** For a $0 local lab, one Postgres pod on one PVC teaches the PVC mechanics cleanly; production Postgres would use a StatefulSet (or, better, a managed database / an operator like CloudNativePG — the S7 "managed vs self-managed" conversation). Naming that tradeoff *is* the interview answer.

## Steps

### 1. Redis — stateless, no storage

Create `capstone/k8s/redis.yaml` with both the Deployment and its Service in one file (`---` separates documents — same as stacking compose services):

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis
  labels:
    app: redis
spec:
  replicas: 1
  selector:
    matchLabels:
      app: redis
  template:
    metadata:
      labels:
        app: redis
    spec:
      containers:
        - name: redis
          image: redis:8-alpine          # same tag as your compose stack
          ports:
            - containerPort: 6379
          readinessProbe:                 # redis is ready when it answers PING
            exec:
              command: ["redis-cli", "ping"]
            periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: redis                             # ← THIS name is why REDIS_URL says "redis://redis:6379"
spec:
  selector:
    app: redis
  ports:
    - port: 6379
      targetPort: 6379
```

```bash
kubectl apply -f capstone/k8s/redis.yaml
kubectl get pods -l app=redis            # redis-... 1/1 Running
```

#### Read it like a story

- **No PVC, no volume** — the exact same decision you made in compose, and your Lab 4 digest nailed the reasoning: "cache losing data on restart is correct, a database doing that is an incident." Redis here is a cache; if its pod dies, the counter resets, and that's fine (`/visits` starts over). Persistence is a *per-service decision*, not a default — same as compose.
- **The Service is named `redis`** — this is the linchpin. In Lab 4 your ConfigMap set `REDIS_URL: redis://redis:6379/0`. That hostname `redis` is a promise; *this* Service keeps it. CoreDNS (Lab 3) will now resolve `redis` → this Service's ClusterIP → the redis pod. The name you wrote days ago in a ConfigMap and the name you write here must match — that's the loose-coupling-by-name contract.
- **`readinessProbe` with `exec`** — the redis image ships no HTTP `/health`, so we use the `exec` probe type (Lab 5) to run `redis-cli ping` *inside* the container, exactly like the healthcheck you added in compose. Ready when it answers.

### 2. The api can now reach redis — `/visits` comes alive

Nothing to change on the api — the wiring was done in Lab 4, it was just pointing at a Service that didn't exist. Now it does. Port-forward and hit `/visits`:

```bash
kubectl port-forward svc/capstone-api 9050:80      # leave running; second terminal for curl
```

```bash
curl -s localhost:9050/visits      # {"visits":1}
curl -s localhost:9050/visits      # {"visits":2}
```

**There's the payoff.** In Lab 4 this same curl returned a 500 (name didn't resolve). The only thing that changed is that the `redis` Service now exists, CoreDNS resolves the name, and the connection succeeds — the full Lab 4 → Lab 6 arc closing exactly as promised. The counter climbs because the api and redis are talking over the cluster network by *name*, the same way `curl localhost:9000/visits` worked in your compose stack. Ctrl-C the port-forward.

### 3. Postgres — the PVC, mounted at the Section-1 path

Now the stateful one. Create `capstone/k8s/postgres.yaml` with three documents: the PVC, the Deployment, and the Service.

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: pgdata                            # the claim ticket — same name spirit as compose's "pgdata" volume
spec:
  accessModes:
    - ReadWriteOnce                       # "mountable read-write by ONE node at a time" — right for a single DB
  resources:
    requests:
      storage: 1Gi                        # how much you're claiming (kind's provisioner gives you a dir)
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres
  labels:
    app: postgres
spec:
  replicas: 1                             # NEVER >1 for a Deployment+shared-PVC database — see mental map
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
        - name: postgres
          image: postgres:18-alpine       # same tag as compose
          ports:
            - containerPort: 5432
          env:
            - name: POSTGRES_PASSWORD
              valueFrom:
                secretKeyRef:              # reuse the Secret from Lab 4 — credentials never inline
                  name: capstone-secret
                  key: POSTGRES_PASSWORD
          volumeMounts:
            - name: pgdata
              mountPath: /var/lib/postgresql   # ← the Section-1 Lab 4 rule: mount HERE, not .../data
          readinessProbe:
            exec:
              command: ["pg_isready", "-U", "postgres"]
            periodSeconds: 5
      volumes:
        - name: pgdata
          persistentVolumeClaim:
            claimName: pgdata              # attach the claim above to this pod
---
apiVersion: v1
kind: Service
metadata:
  name: db                                # hostname "db" — matches your compose service name
spec:
  selector:
    app: postgres
  ports:
    - port: 5432
      targetPort: 5432
```

```bash
kubectl apply -f capstone/k8s/postgres.yaml
kubectl get pvc
kubectl get pods -l app=postgres
```

```
NAME     STATUS   VOLUME            CAPACITY   ACCESS MODES   STORAGECLASS   AGE
pgdata   Bound    pvc-a1b2c3...     1Gi        RWO            standard       10s
```

`STATUS: Bound` = the StorageClass heard your claim, provisioned a PersistentVolume, and bound them. The pod comes up `1/1` once `pg_isready` passes.

#### Two Section-1 traps that transfer directly

- **`mountPath: /var/lib/postgresql`, NOT `/var/lib/postgresql/data`.** This is the *exact* Postgres-18 trap you hit live in Section 1 Lab 4 (your digest: "18 moved data to a version subdir; mount at `/var/lib/postgresql`"). Mount at the legacy `.../data` path and the container dies with `exit 1` and a lecture in the logs — same behavior, now inside a pod. If you see `postgres` in `CrashLoopBackOff`, `kubectl logs <pod> --previous` will show that same lecture. The fix is the mount path, identical to compose.
- **`accessModes: ReadWriteOnce`** — "one node can mount this read-write." It's why you must never scale this Deployment past 1: two Postgres pods sharing one RWO volume can't both mount it (and even if they could, two writers = corruption). This constraint is *why* clustered databases need StatefulSets with per-pod volumes.

#### If the PVC is stuck `Pending`

On a real cluster a `Pending` PVC usually means no StorageClass can satisfy the claim (no provisioner, or wrong `storageClassName`). On kind it should bind instantly because the `local-path-provisioner` (Lab 1's pod list) ships as the default StorageClass. If it hangs: `kubectl describe pvc pgdata` → Events will name the reason. `kubectl get storageclass` should show `standard (default)`.

### 4. Prove persistence — the compose down/up test, at cluster scale

The whole reason Postgres has a PVC and redis doesn't. Write data into Postgres, destroy its pod, prove the data outlives the pod. Exec in and create a table (same `psql` move as compose, `kubectl exec` instead of `docker compose exec`):

```bash
kubectl exec deploy/postgres -- psql -U postgres -c 'CREATE TABLE survivors(id int);'
kubectl exec deploy/postgres -- psql -U postgres -c '\dt'      # survivors is listed
```

Now murder the pod — the ReplicaSet will replace it (Lab 2's self-healing), and the replacement re-attaches the *same* PVC:

```bash
kubectl delete pod -l app=postgres            # kill it; a fresh pod replaces it
kubectl get pods -l app=postgres -w           # wait for the new one to reach 1/1, then Ctrl-C
kubectl exec deploy/postgres -- psql -U postgres -c '\dt'      # survivors is STILL THERE
```

**`survivors` survived a pod death.** A brand-new pod, new name, new IP, fresh writable layer — but it re-mounted the same PersistentVolume through the PVC, and Postgres found its data exactly where the old pod left it. This is your Section 1 Lab 4 proof (`docker compose down`+`up`, the `survivors` table persisting via the named volume) translated one-for-one to Kubernetes: **the pod is cattle, the PVC is the parking spot that outlives it.** Contrast redis: kill its pod and `/visits` resets to 1, because a cache has no PVC — persistence remains a per-service decision, and you made the same two decisions here as you did in compose.

The stack is now whole on Kubernetes: api + redis + db, wired by Service names, config from a ConfigMap, credentials from a Secret, health from three probes, storage from a PVC. Everything your compose file did, now reconciled continuously by controllers.

## Verify

- `kubectl get pods` shows `capstone-api` (2), `redis` (1), `postgres` (1), all `Running` and ready.
- `curl localhost:9050/visits` (through a port-forward) returns climbing numbers — the api is talking to in-cluster redis by name.
- `kubectl get pvc pgdata` shows `Bound`; you created a table, deleted the Postgres pod, and the table survived on the replacement.
- Answer aloud:

- PVC, PV, StorageClass — three objects for what compose did with one `volumes:` line. What is each one's job, and why the indirection?

  <details><summary>Answer (read after attempting aloud)</summary>

  PVC = the *claim* you write ("I need 1Gi, ReadWriteOnce") — a request, not a disk. StorageClass = the recipe for making disks on demand (kind's `local-path-provisioner`; on AWS it'd provision EBS). PV = the actual provisioned storage the class carves out and binds to your claim. The indirection makes storage **portable**: your manifest asks for capacity/access-mode, not a specific machine's disk path, so the same PVC works on kind, AWS, or GCP — only the StorageClass/provisioner underneath changes.

  </details>

- You ran Postgres as a Deployment with one replica. When must you switch to a StatefulSet, and why would scaling this Deployment to 2 be a disaster?

  <details><summary>Answer (read after attempting aloud)</summary>

  Switch to a StatefulSet when pods need **stable identity + their own per-pod storage + ordered startup** — clustered databases, Kafka, replicated stateful systems. Scaling this Deployment to 2 is a disaster because both pods would point at the *same* ReadWriteOnce PVC: RWO only allows one node to mount it (so the second pod can't schedule), and two Postgres processes on one data directory means corruption. Deployments assume pods are interchangeable; stateful replicas are not — each needs its own volume, which is exactly what a StatefulSet's `volumeClaimTemplates` gives.

  </details>

- Why does redis get no PVC while Postgres does — and how is this the same decision you made in compose?

  <details><summary>Answer (read after attempting aloud)</summary>

  Redis here is a cache: losing its data on restart is fine, even correct — it refills, and `/visits` just restarts from 1. Postgres is the system of record: losing its data is an incident. So persistence is a **per-service decision**, and it's the identical call from compose (redis got no volume, `pgdata` got a named volume). The Kubernetes version just replaces the named volume with a PVC and adds the portability seam.

  </details>

- `/visits` returned a 500 at the end of Lab 4 and returns `{"visits":1}` now. Exactly what changed, and what did NOT?

  <details><summary>Answer (read after attempting aloud)</summary>

  What changed: the `redis` **Service** now exists, so CoreDNS resolves the `redis` hostname in `REDIS_URL` to a live redis pod, and the app's `redis.incr()` connection succeeds. What did NOT change: the app image, the ConfigMap, the `REDIS_URL` value, the Deployment's env wiring — all identical since Lab 4. The 500 was a connection failure to a name that didn't resolve yet; standing up the named Service was the only missing piece. That's the loose-coupling-by-name contract paying off.

  </details>

## Clean up

Everything stays — the full stack (api + redis + postgres + PVC) is the state Lab 7 puts an Ingress in front of, and the state Section 5 turns into a Helm chart. To reclaim your Mac between sessions you can `kind delete cluster --name capstone` and rebuild: recreate the cluster (Lab 1 step 3), then `kubectl apply -f capstone/k8s/` re-applies every manifest at once — the whole stack back in one command (the `survivors` table won't return, though; deleting the *cluster* deletes the PV too).

Commit `capstone/k8s/redis.yaml` and `capstone/k8s/postgres.yaml`. Update the capstone evolution log: "Section 4: redis + postgres in-cluster; PVC for pgdata; full stack reconstructed on Kubernetes."
