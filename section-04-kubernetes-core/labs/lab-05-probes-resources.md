# Lab 5 — Probes & resources: the healthcheck grows up, and 137 comes back

**Goal:** turn the single Docker healthcheck from Section 1 into Kubernetes' **three probes** — liveness, readiness, startup — each with a different consequence, and prove you understand which is which by watching a bad readiness probe pull a pod out of rotation *without* restarting it. Then declare CPU/memory **requests and limits**, and deliberately trigger an **OOMKilled** — exit code **137**, the exact number you met in Section 1 Lab 1 (`docker stop` timeout / OOM), now fired by a memory ceiling *you* set. This is the CrashLoopBackOff you were promised in Lab 2, on purpose.

## The mental map (read this first)

Your image already has ONE health signal, from Section 1 Lab 3:

```dockerfile
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
  CMD ["python","-c","...urlopen('http://127.0.0.1:8000/health')..."]
```

In compose that fed exactly one consumer: `depends_on: service_healthy`, a **startup-only** gate (your Lab 4 digest: "gate exists only at startup; if redis dies later the api is on its own"). Kubernetes fixes that limitation by splitting the one healthcheck into **three probes that answer three different questions and trigger three different actions**:

```
              ┌─ startup probe ──▶  "has it finished BOOTING yet?"
              │                     while failing: hold off the other two probes.
              │                     never passes → kill & restart. (for slow starters)
   kubelet ───┤
   runs these │─ readiness probe ▶  "should it get TRAFFIC right now?"
   on a timer │                     fails → pod REMOVED from Service endpoints (Lab 3).
              │                     NO restart. Comes back → re-added. (temporary/degraded)
              │
              └─ liveness probe ──▶  "is it DEADLOCKED / wedged?"
                                    fails → kubelet RESTARTS the container.
                                    (last resort — a restart is disruptive)
```

The insight that makes them click — **readiness controls the Service door, liveness controls the container's life:**

- **Readiness fails** → the endpoints controller drops this pod's IP from the Service (Lab 3's endpoints list), so no new requests route to it — but the process keeps running, untouched. Use it for "temporarily can't serve" (warming a cache, a dependency is down, overloaded). This is the runtime gate compose never had: a sick pod stops receiving traffic *automatically*, and rejoins when it recovers.
- **Liveness fails** → kubelet kills and restarts the container. Use it *only* for "wedged beyond recovery" (deadlock, event loop stuck). A too-aggressive liveness probe is a classic self-inflicted outage: it restarts pods that were merely slow, turning a hiccup into a restart storm.
- **Startup** exists for apps that boot slowly: it *suspends* the other two until boot finishes, so a slow start doesn't get misread as "dead" and killed. Ours boots fast, but you'll wire it to learn the shape.

Then **resources** — the other half of the lab. Every container should declare:

- **`requests`** — what the scheduler *reserves* for it. This is how the scheduler decides which node a pod fits on (Lab 1's "Allocatable" line is the budget). Requests are a promise the pod gets *at least* this much.
- **`limits`** — the hard ceiling the runtime *enforces*. Exceed the **memory** limit → the kernel's OOM killer terminates the process → **exit 137** (128 + signal 9 = SIGKILL), status **OOMKilled**. Exceed the **CPU** limit → you get *throttled* (slowed), never killed — CPU is compressible, memory isn't. That asymmetry is a favorite interview question.

137 is not a new number for you. Section 1 Lab 1: "`Exited (137)` = 128+9 = SIGKILLed (stop timeout or OOM)." Same kernel mechanism, same exit code — the difference is that in K8s the OOM is triggered by a **limit you wrote in YAML**, and the kubelet reports the cause by name: `OOMKilled`.

## Steps

### 1. Add the three probes to the Deployment

Open `capstone/k8s/deployment.yaml` and add a probe block to the container (alongside the `env` from Lab 4). All three hit the same `/health` endpoint your Docker healthcheck already used:

```yaml
      containers:
        - name: api
          image: ghcr.io/itsmahadi007/capstone:latest
          ports:
            - containerPort: 8000
          env:
            # ... (the REDIS_URL + POSTGRES_PASSWORD block from Lab 4 stays) ...
          startupProbe:                 # "still booting?" — guards the other two until it passes
            httpGet:
              path: /health
              port: 8000
            failureThreshold: 30        # 30 tries × 2s = up to 60s to boot before giving up
            periodSeconds: 2
          readinessProbe:               # "send traffic?" — controls Service endpoints, no restart
            httpGet:
              path: /health
              port: 8000
            periodSeconds: 5
            failureThreshold: 3
          livenessProbe:                # "wedged?" — restarts the container on failure
            httpGet:
              path: /health
              port: 8000
            periodSeconds: 10
            failureThreshold: 3
```

#### Read it like a story

- **`httpGet` instead of your Docker `CMD python -c urllib`** — the kubelet has a built-in HTTP prober, so you don't ship a probe *command* inside the image; you *describe* the check and the kubelet performs it from outside the container. (The other probe types: `exec` — run a command in the container, closest to your Docker healthcheck; `tcpSocket` — just check the port opens; `grpc` — for gRPC services.) Same target as always: `GET /health` on `8000`.
- **`failureThreshold` × `periodSeconds`** — the same "N consecutive fails" logic as your Docker healthcheck's `retries`, but per-probe. Startup gets a generous 30×2s window; liveness a tight 3×10s.
- **Why all three point at `/health`** — for this tiny app one endpoint is honest. In a bigger service you'd split them: readiness would also check "can I reach my database?" (so a DB outage pulls the pod from rotation), while liveness stays a *shallow* "is my process responsive?" that does NOT depend on the DB — because you never want a database blip to trigger a restart storm. Knowing to keep liveness shallow and readiness deep is senior-level probe design; say it in an interview.

```bash
kubectl apply -f capstone/k8s/deployment.yaml
kubectl get pods
```

New pods roll out (template changed again). Watch the `READY` column: it reads `0/1` for a beat while the startup+readiness probes pass, then flips to `1/1`. That `0/1 → 1/1` transition is the readiness probe doing its job — the pod isn't in the Service's endpoints until it's `1/1`.

### 2. Break readiness on purpose — watch traffic get cut, no restart

The clearest way to feel readiness-vs-liveness: point the **readiness** probe at a path that doesn't exist, and watch what happens (and what doesn't). Temporarily change *only* the readiness probe's path:

```yaml
          readinessProbe:
            httpGet:
              path: /nope              # 404 — this will fail every time
              port: 8000
```

```bash
kubectl apply -f capstone/k8s/deployment.yaml
kubectl get pods -w
```

```
capstone-api-<new>   0/1   Running   0   20s     ← Running, but NOT ready
```

Read that carefully: **`STATUS: Running`, `READY: 0/1`, `RESTARTS: 0`.** The process is alive and untouched — readiness failing does *not* restart it. But check the endpoints:

```bash
kubectl get endpoints capstone-api
```

```
NAME           ENDPOINTS   AGE
capstone-api   <none>      ...
```

**Empty.** The pod was pulled out of the Service's rotation the instant readiness failed — exactly the runtime gate compose lacked. A real client hitting the Service now gets no backend (that's why you'd normally do this to *one* pod of many, so the healthy ones keep serving). Now put the path back to `/health` and re-apply — the pod flips to `1/1` and its IP reappears in endpoints. That round trip *is* the readiness concept.

```bash
# edit readinessProbe path back to /health, then:
kubectl apply -f capstone/k8s/deployment.yaml
kubectl get endpoints capstone-api    # the pod IP is back
```

### 3. Add resource requests and limits

Now the resource half. Add a `resources` block to the same container:

```yaml
          resources:
            requests:                   # what the scheduler RESERVES (the fit decision)
              cpu: "50m"                # 50 millicores = 0.05 of one CPU
              memory: "64Mi"            # 64 mebibytes reserved
            limits:                     # the hard ceiling the runtime ENFORCES
              cpu: "250m"               # throttled above this — never killed for CPU
              memory: "128Mi"           # exceed this → OOMKilled (exit 137)
```

```bash
kubectl apply -f capstone/k8s/deployment.yaml
kubectl describe pod -l app=capstone-api | grep -A4 Limits
```

Read the units aloud, because the CKA tests them:

- **CPU `50m`** — `m` = millicores, thousandths of a CPU. `1000m` = one full core. CPU is **compressible**: over the limit, the scheduler throttles the process (it runs slower), it is never killed.
- **Memory `64Mi`** — `Mi` = mebibytes (1024-based; `M` without the `i` = megabytes, 1000-based — mixing them is a real bug). Memory is **incompressible**: you can't "run slower" on RAM. Over the limit, the only option is to kill.
- **requests ≤ limits**, always. The scheduler budgets against `requests` (does this fit on a node given what's already reserved?); the runtime polices `limits`.

### 4. Trigger a real OOMKill — 137, again

Time to earn the CrashLoopBackOff from Lab 2 honestly. Create a throwaway pod with a tiny memory limit and a process that deliberately eats more than that — `capstone/k8s/oom-demo.yaml` (a standalone pod, not part of the app, so you can delete it after):

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: oom-demo
spec:
  containers:
    - name: hog
      image: python:3.14-slim
      command:                          # allocate a 200MB bytearray, then sleep
        - python
        - -c
        - "x = bytearray(200 * 1024 * 1024); import time; time.sleep(300)"
      resources:
        limits:
          memory: "100Mi"               # ceiling is 100Mi; the process wants ~200MB → over the wall
```

```bash
kubectl apply -f capstone/k8s/oom-demo.yaml
kubectl get pod oom-demo -w
```

```
oom-demo   0/1   ContainerCreating   0   0s
oom-demo   0/1   OOMKilled           0   3s     ← the kernel killed it the moment it crossed 100Mi
oom-demo   0/1   CrashLoopBackOff    1   8s     ← kubelet restarts it, it OOMs again → backoff grows
```

There it is — **`OOMKilled`, then `CrashLoopBackOff`**, the second BackOff from Lab 2's pair. Unlike `ImagePullBackOff` (image never arrived, logs empty), here the container *started and died*, repeatedly, kubelet restarting with growing delays. Now diagnose it exactly like the ritual says — **status → describe → logs --previous:**

```bash
kubectl describe pod oom-demo | grep -A6 'Last State'
```

```
    Last State:     Terminated
      Reason:       OOMKilled
      Exit Code:    137           ← 128 + 9 (SIGKILL) — the same number from Section 1 Lab 1
```

**Exit code 137 = 128 + signal 9 (SIGKILL).** Your Section 1 note said it verbatim: "137 = SIGKILLed (stop timeout or OOM)." Back then it came from `docker stop`'s 10-second patience running out. Here it came from the kernel's OOM killer enforcing a *memory limit you wrote in YAML*. Same signal, same code, new trigger — and Kubernetes labels the reason for you (`OOMKilled`), which `docker` never did. This is why declaring memory limits is a double-edged tool: it protects the node from a runaway container (a leak can't take the whole machine down — your Section 1 Lab 4 "chatty logs fill the disk, host-wide outage" fear, applied to RAM), but set it too low and you kill healthy pods. Right-sizing limits is a real ops skill; observability (Section 8) is how you measure to get it right.

### 5. Clean up the OOM demo

```bash
kubectl delete -f capstone/k8s/oom-demo.yaml
```

The capstone Deployment keeps its probes and resources — those are permanent, sensible config now.

## Verify

- `kubectl get pods` shows the capstone pods `1/1 Running`; you saw the `0/1 → 1/1` readiness transition on rollout.
- You broke the readiness probe and watched the pod go `0/1` and drop from endpoints **with zero restarts**, then recover when you fixed it.
- You triggered `OOMKilled` / exit `137` on purpose and found the reason in `describe` under `Last State`.
- Answer aloud:

- Liveness vs readiness — different question, different action. State both, and give the one rule about what liveness must *not* depend on.

  <details><summary>Answer (read after attempting aloud)</summary>

  Readiness = "should I get traffic?" — failing removes the pod's IP from the Service endpoints (no new requests route to it) but does **not** restart it; it rejoins when it passes. Liveness = "am I wedged?" — failing makes the kubelet **restart** the container. Rule: liveness must stay *shallow* — it must not depend on external things like the database. A deep liveness probe turns a dependency blip into a restart storm; put the dependency check in *readiness* instead (pull the pod from rotation, don't kill it).

  </details>

- What does the scheduler use `requests` for, and what does the runtime use `limits` for? Why does exceeding a CPU limit behave differently from exceeding a memory limit?

  <details><summary>Answer (read after attempting aloud)</summary>

  `requests` = what the **scheduler reserves** when deciding which node a pod fits on (budgeted against the node's Allocatable). `limits` = the hard ceiling the **runtime enforces** on the running container. CPU is *compressible*: over the limit you're throttled (run slower), never killed. Memory is *incompressible*: you can't run on less RAM than you allocated, so the only enforcement is the OOM killer terminating the process (exit 137, OOMKilled).

  </details>

- A pod is in `CrashLoopBackOff` with `Reason: OOMKilled`, exit code 137. Explain the number and your next two diagnostic moves.

  <details><summary>Answer (read after attempting aloud)</summary>

  137 = 128 + 9 = the process was killed by SIGKILL — here, the kernel's OOM killer because the container crossed its memory limit. Moves: `kubectl describe pod` and read `Last State → Reason/Exit Code` (confirms OOMKilled and 137), then `kubectl logs <pod> --previous` to see what the *last* attempt was doing before it was killed (the current container is a fresh restart, often empty). Fix = raise the memory limit or fix the leak — measure with real metrics before guessing (Section 8).

  </details>

- This is the runtime gate compose never had. Connect it to your Section 1 Lab 4 note about `service_healthy`.

  <details><summary>Answer (read after attempting aloud)</summary>

  In compose, `depends_on: service_healthy` gated only *startup* — once running, if a dependency died the api was on its own (your own note). Kubernetes' **readiness probe** is that gate at *runtime*: a pod that becomes unhealthy is automatically pulled from the Service's endpoints (stops receiving traffic) and re-added when it recovers, continuously, with no human. Liveness adds the "restart if wedged" behavior compose's `restart:` policy hinted at, but scoped to a real health signal instead of just "process exited."

  </details>

## Clean up

The `oom-demo` pod is already deleted (step 5). The capstone Deployment keeps its probes and `resources` — they're part of the manifest from here on.

Commit the updated `capstone/k8s/deployment.yaml`. You can keep `capstone/k8s/oom-demo.yaml` in the repo as a teaching artifact (it's harmless — it only runs when applied). Update the capstone evolution log: "Section 4: three probes (startup/readiness/liveness) + requests/limits; proved OOMKilled=137 at cluster scale."
