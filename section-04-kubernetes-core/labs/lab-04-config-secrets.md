# Lab 4 — ConfigMaps & Secrets: config out of the image, into the cluster

**Goal:** move the capstone's configuration out of the manifest and into cluster objects — `REDIS_URL` into a **ConfigMap**, the Postgres password into a **Secret** — then inject both as environment variables the same way compose's `environment:` block did. Along the way you'll prove the single most misunderstood fact about Kubernetes Secrets: **they are not encrypted.** By the end, `/visits` stops saying "REDIS_URL not set" and starts failing with a *connection* error instead — the proof your wiring works, waiting for Lab 6 to bring redis online.

## The mental map (read this first)

In compose you wrote config inline:

```yaml
    environment:
      REDIS_URL: redis://redis:6379/0
      POSTGRES_PASSWORD: localdev
```

That's fine for one machine. But it fuses three things that should be separate: the **image** (what to run), the **config** (per-environment values), and the **secrets** (credentials). The 12-factor rule you already know — *config in the environment, not baked into the image* — Kubernetes takes one step further: config and secrets become **their own objects**, stored in etcd, and *referenced* by the Deployment. Same image, swap the ConfigMap → different environment. Same image, swap the Secret → different credentials. Nothing rebuilt.

```
  ConfigMap "capstone-config"          Secret "capstone-secret"
    REDIS_URL: redis://redis:6379/0      POSTGRES_PASSWORD: <base64 of localdev>
          │                                    │
          │   envFrom / valueFrom               │
          └──────────────┬──────────────────────┘
                         ▼
              Deployment pod template
              env:  REDIS_URL=...  POSTGRES_PASSWORD=...
                         │
                         ▼
               your uvicorn process reads os.environ  (same as always)
```

Two object types, one job, split by *sensitivity*:

- **ConfigMap** — non-secret key/value config. Stored as plain text in etcd. `REDIS_URL`, feature flags, log levels, a whole config file.
- **Secret** — for credentials. Looks almost identical to a ConfigMap, with one infamous difference explored in step 4: the values are **base64-encoded**, which people mistake for encryption. It is not. It's just an encoding (so binary/newlines survive). The real protections are RBAC (who can read the object) and encryption-at-rest (a cluster setting you turn on separately).

The app doesn't change at all — it still does `os.environ.get("REDIS_URL")` (you saw the code: `/visits` returns "REDIS_URL not set" when the var is empty). We're only changing *where the value comes from*: from an inline compose line to a cluster object injected as env. That's the whole point of 12-factor config — the app is oblivious.

## Steps

### 1. Create the ConfigMap

Create `capstone/k8s/configmap.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: capstone-config
data:
  REDIS_URL: redis://redis:6379/0   # the "redis" hostname = the Service you'll create in Lab 6
```

```bash
kubectl apply -f capstone/k8s/configmap.yaml
kubectl get configmap capstone-config -o yaml
```

The `-o yaml` echoes it back so you see it's stored verbatim, in the clear:

```yaml
data:
  REDIS_URL: redis://redis:6379/0
```

Note the hostname `redis` — that Service doesn't exist yet (Lab 6 creates it). That's deliberate and fine: a ConfigMap is just stored data, it doesn't validate that `redis` resolves. Same as writing `redis://redis:6379` in compose before `docker compose up` had started the redis container — the *name* is a promise the DNS will keep later.

### 2. Create the Secret — two honest ways

You *can* hand-write a Secret YAML, but you'd have to base64-encode every value yourself, which teaches the wrong reflex (it makes base64 feel like a security step). The clean way is the imperative generator, then read what it produced. Create the Secret from a literal:

```bash
kubectl create secret generic capstone-secret \
  --from-literal=POSTGRES_PASSWORD=localdev      # lab-only placeholder — NEVER a real password in a public repo
```

```
secret/capstone-secret created
```

Now the reveal — dump it as YAML:

```bash
kubectl get secret capstone-secret -o yaml
```

```yaml
apiVersion: v1
kind: Secret
type: Opaque
metadata:
  name: capstone-secret
data:
  POSTGRES_PASSWORD: bG9jYWxkZXY=       # ← this is NOT encrypted
```

### 3. Wire both into the Deployment

Open `capstone/k8s/deployment.yaml` (from Lab 2) and add an `env` block to the container. The container spec becomes:

```yaml
      containers:
        - name: api
          image: ghcr.io/itsmahadi007/capstone:latest
          ports:
            - containerPort: 8000
          env:                              # ── NEW: pull values from cluster objects ──
            - name: REDIS_URL
              valueFrom:
                configMapKeyRef:            # "read this env var from a ConfigMap key"
                  name: capstone-config
                  key: REDIS_URL
            - name: POSTGRES_PASSWORD
              valueFrom:
                secretKeyRef:               # "read this one from a Secret key"
                  name: capstone-secret
                  key: POSTGRES_PASSWORD
```

```bash
kubectl apply -f capstone/k8s/deployment.yaml
```

```
deployment.apps/capstone-api configured
```

`configured`, not `unchanged` — you changed the pod template, so the Deployment rolls out **new pods** with the env baked in. This is the reconcile loop again: changing the template creates a new ReplicaSet and shifts pods over (Lab 2's rollout, triggered by an env change instead of an image change). Watch it if you like: `kubectl get pods -w` shows two new pods appear and the old two terminate.

#### `valueFrom` (one var) vs `envFrom` (the whole map)

You wired each var by name with `valueFrom` — explicit, and it lets you rename (`REDIS_URL` in the app could read from a differently-named key). The bulk alternative, worth knowing for the CKA:

```yaml
          envFrom:
            - configMapRef:
                name: capstone-config       # injects EVERY key in the map as an env var, same names
            - secretRef:
                name: capstone-secret
```

`envFrom` is "dump the whole ConfigMap/Secret in as env vars." Convenient, but you lose the explicit list — a new key in the map silently becomes a new env var. For a config with many keys it's tidy; for two vars, the explicit `valueFrom` is clearer. Either is correct; know both exist.

### 4. Prove the injection — and prove Secrets aren't secret

First, confirm the app now sees the values. Exec into a pod and read its environment:

```bash
kubectl exec deploy/capstone-api -- env | grep -E 'REDIS_URL|POSTGRES_PASSWORD'
```

```
REDIS_URL=redis://redis:6379/0
POSTGRES_PASSWORD=localdev            ← decoded back to plain text inside the container
```

There it is: the Secret arrived in the container as **plain text**. Kubernetes base64-*decodes* it on the way in. So what did base64 protect? **Nothing about confidentiality.** Decode the stored value yourself — no key, no permission, just an encoding:

```bash
echo 'bG9jYWxkZXY=' | base64 -d      # localdev
```

Anyone who can `kubectl get secret -o yaml` can read every credential in one `base64 -d`. Say this precisely in an interview, because it's a classic gotcha: **a Kubernetes Secret is not encrypted — it's base64-encoded, which is an encoding, not a cipher.** What actually protects a Secret is three things you add *around* it:

1. **RBAC** — restrict who can `get`/`list` Secrets (most humans and pods should not be able to).
2. **Encryption at rest** — a cluster config that encrypts Secret values *in etcd* (off by default in vanilla clusters; managed providers often enable it).
3. **Keeping them out of git** — which is why in Section 9 you'll meet Sealed Secrets / SOPS: encrypt the secret *before* it touches the repo, decrypt only inside the cluster.

Why bother with the Secret type at all, then, if it's just base64? Because it's a *different object type* that RBAC, audit logs, and encryption-at-rest all treat specially — and because it stops the value from showing up in `kubectl describe`/`get` output the way a ConfigMap does (values are elided as `<hidden>` unless you ask for `-o yaml`). It's a **marker of intent** that the rest of the system respects; it is not, by itself, protection.

### 5. See the env change take effect on `/visits`

In Lab 2, `/visits` returned a clean JSON message: `{"visits":null,"detail":"REDIS_URL not set"}` — because `REDIS_URL` was empty. Now it's set. Port-forward and hit it (Lab 3's tool):

```bash
kubectl port-forward svc/capstone-api 9050:80        # leave running; new terminal for the curl
```

```bash
curl -si localhost:9050/visits | head -1
```

```
HTTP/1.1 500 Internal Server Error
```

**A 500 is the expected, correct result right now — and it's the proof your wiring works.** Read the app's logic (you saw the code): with `REDIS_URL` empty it returned the clean "not set" message; with `REDIS_URL` *set* it actually tries `redis.Redis.from_url(...).incr("visits")`. But the `redis` Service doesn't exist yet (Lab 6), so the name doesn't resolve, the connection fails, and FastAPI turns the unhandled exception into a 500. The message *changed* from "REDIS_URL not set" to a connection failure — that transition is the whole point: **the config is now flowing from the ConfigMap into the app.** Lab 6 stands up the `redis` Service and this same curl flips to `{"visits":1}` with nothing else changed. Ctrl-C the port-forward.

## Verify

- `kubectl get configmap capstone-config` and `kubectl get secret capstone-secret` both exist.
- `kubectl exec deploy/capstone-api -- env` shows `REDIS_URL` and `POSTGRES_PASSWORD` with the expected values.
- You decoded the Secret with `base64 -d` and can explain why that's trivial and what actually protects a Secret.
- `/visits` returns a 500 (connection error), no longer "REDIS_URL not set" — proving the env is wired.
- Answer aloud:

- ConfigMap vs Secret — what's the actual technical difference, and what is it emphatically *not*?

  <details><summary>Answer (read after attempting aloud)</summary>

  A ConfigMap stores plain-text key/values; a Secret stores **base64-encoded** key/values and is a distinct object type. The difference is *not* encryption — base64 is a reversible encoding anyone can `base64 -d`. The Secret type is a marker of intent that RBAC, audit logging, encryption-at-rest, and output-elision (`kubectl get`/`describe` hide the values) treat specially. Real confidentiality comes from those surrounding controls, not from the base64 itself.

  </details>

- The app code never changed, but `/visits` behaves differently after this lab. What moved, and why is "the app is oblivious" the goal?

  <details><summary>Answer (read after attempting aloud)</summary>

  Only the *source* of `REDIS_URL` moved — from nowhere (unset) to a ConfigMap injected as an env var. The app still just calls `os.environ.get("REDIS_URL")`; it has no idea a ConfigMap exists. That obliviousness is 12-factor config: the same image runs unchanged on your Mac, in CI, and in every cluster — only the injected env differs. Swapping config never means rebuilding or editing the app.

  </details>

- Three ways to actually protect a Kubernetes Secret. Name them.

  <details><summary>Answer (read after attempting aloud)</summary>

  (1) **RBAC** — restrict who/what can `get`/`list` Secret objects. (2) **Encryption at rest** — configure the api-server to encrypt Secret values in etcd (off by default in vanilla clusters). (3) **Keep them out of git** — encrypt before commit with Sealed Secrets or SOPS, decrypt only in-cluster (Section 9). Base64 does none of these.

  </details>

- After you added the `env` block and re-applied, `kubectl apply` said `configured` and new pods appeared. Why new pods rather than an in-place edit?

  <details><summary>Answer (read after attempting aloud)</summary>

  Environment is part of the **pod template**, and pods are immutable in the ways that matter — you don't edit a running pod's env. Changing the template makes the Deployment mint a new ReplicaSet and roll pods from old to new (the same rollout mechanism as an image change in Lab 2). It's the reconcile loop: desired template changed, so actual pods get replaced to match. Same instinct as compose recreating the api container when you added the `logging:` block in Section 1.

  </details>

## Clean up

Everything here stays — the ConfigMap, the Secret, and the `env` block in the Deployment are all load-bearing for Lab 6. Nothing to remove.

Commit `capstone/k8s/configmap.yaml` and the updated `deployment.yaml`. **Do NOT commit a Secret manifest** — you created the Secret imperatively on purpose, so no credential (not even the `localdev` placeholder in base64) lands in the public repo. Note in the capstone evolution log: "Section 4: config via ConfigMap, credentials via Secret; Secret created imperatively, never committed."
