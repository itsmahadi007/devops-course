# Lab 6 — Model server on Kubernetes (the flagship)

**Goal:** the payoff. Deploy the model server onto your kind cluster as a Deployment with a Service and — critically — **resource limits**, then grow the capstone Helm chart so the LLM is part of the same release your GitOps pipeline already deploys. When this works you can say the flagship sentence out loud: *"a self-hosted LLM, containerized, deployed to Kubernetes through my own chart, with resource limits and metrics."*

## The mental map (read this first)

Everything you learned about the model server now meets everything you learned about Kubernetes (Sections 4–5) and GitOps (Section 9). The pieces map cleanly:

```
 compose (Lab 3)                    Kubernetes (this lab)
 ─────────────────                  ─────────────────────
 model service            ──▶       Deployment (pod template) + Service (stable DNS name)
 healthcheck              ──▶       readiness + liveness probes on /health
 llmcache volume          ──▶       a mounted volume for the weights cache
 -hf init-download        ──▶       -hf into that volume, gated by the readiness probe
 (implicit RAM use)       ──▶       resources.requests / resources.limits  ← THE new discipline
 LLM_BASE_URL=model:8080  ──▶       LLM_BASE_URL=http://capstone-llm:8080/v1 (Service DNS)
```

The genuinely new discipline is **resource requests and limits**, and LLM serving is where they finally *bite*:

- **`requests`** = what the scheduler reserves for the pod ("this pod needs at least 1Gi RAM to be placed on a node"). Too low and the scheduler overcommits the node.
- **`limits`** = the hard ceiling. Exceed the memory limit and the kernel **OOM-kills** the container — **exit 137**, the exact signal from Section 1 (`128 + 9`, SIGKILL) and the Lab 1 mental-model warning made real. For a model server, memory = weights + KV cache (Lab 4), so a limit set below "weights + peak KV" is a latent 137 waiting for a busy moment.

This is the capacity math from Lab 4, now enforced by the platform instead of trusted to luck. And the honest caveat, again: **kind nodes are CPU-only** — no GPU. On a real cluster you'd add a GPU resource (`nvidia.com/gpu: 1`) and the device plugin; here the model runs on CPU like Lab 3's container. Same manifests, one extra resource line in prod.

```
 kind cluster
 ┌─────────────────────────────────────────────────────────────┐
 │  Deployment: capstone-api  ──env LLM_BASE_URL──▶ Service:     │
 │                                                 capstone-llm  │
 │  Deployment: capstone-llm  (resources: req/limit)  :8080      │
 │    container: llama-server -hf ... --metrics                  │
 │      → downloads GGUF into the cache volume, then serves      │
 └─────────────────────────────────────────────────────────────┘
   kubectl port-forward svc/capstone-llm 9111:8080  → test from your Mac
```

## Steps

### 1. Understand the raw manifest first (then the chart)

Before templating, see the plain Kubernetes objects — this is what the chart will generate. A Deployment + Service for the model (don't apply yet; step 2 does it via the chart):

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: capstone-llm
spec:
  replicas: 1
  selector:
    matchLabels: { app: capstone-llm }
  template:
    metadata:
      labels: { app: capstone-llm }
    spec:
      containers:
        - name: llama-server
          image: ghcr.io/ggml-org/llama.cpp:server
          # -hf downloads the weights into the cache volume on first start, THEN serves.
          # Same init-download pattern as Lab 3's compose service — the readiness probe
          # (below) gates traffic until the download+load finishes.
          args: ["-hf", "Qwen/Qwen3-0.6B-GGUF:Q8_0",
                 "--host", "0.0.0.0", "--port", "8080",
                 "-c", "4096", "--jinja", "--metrics"]
          ports:
            - containerPort: 8080
          volumeMounts:
            - { name: model-cache, mountPath: /root/.cache/llama.cpp }
          resources:
            requests: { memory: "1Gi", cpu: "500m" }   # scheduler reserves this
            limits:   { memory: "2Gi", cpu: "2" }       # exceed memory → OOMKilled (137)
          readinessProbe:                                # don't send traffic until loaded
            httpGet: { path: /health, port: 8080 }
            initialDelaySeconds: 10
            periodSeconds: 5
            failureThreshold: 30                         # long: first boot may download
          livenessProbe:                                 # restart if it wedges
            httpGet: { path: /health, port: 8080 }
            initialDelaySeconds: 120
            periodSeconds: 15
      volumes:
        - name: model-cache
          emptyDir: {}          # lab: re-downloads if the pod is rescheduled. Prod: a PVC.
---
apiVersion: v1
kind: Service
metadata:
  name: capstone-llm
spec:
  selector: { app: capstone-llm }
  ports:
    - { port: 8080, targetPort: 8080 }
```

#### The lines that carry the lesson

- **`args: ["-hf", ...]` on the main container** — the Kubernetes form of Lab 3's init-download: the server downloads the GGUF into the `model-cache` volume on first start, then serves. The **readiness probe** (below) is what gates traffic until that download+load finishes. (Why not a true `initContainer`? An initContainer must *terminate* for the pod to proceed — and `llama-server` runs forever, so booting it as an init step would hang the pod. A real initContainer download uses a tool that exits, like `huggingface-cli download` or `wget`, writing into the shared volume before the server container starts. For the lab, `-hf` on the main container is simpler and robust; the "prepare-state-first" initContainer pattern is worth knowing for DB migrations and pre-baked caches.)
- **`resources.requests` vs `limits`** — the whole point of the lab. `requests` is the scheduler's reservation; `limits` is the kill ceiling. Memory limit `2Gi` = weights (~0.64Gi) + KV headroom + download buffer + overhead. Set `limits.memory` too tight and a burst of concurrent requests fills the KV cache past the ceiling → **OOMKilled, exit 137** — Section 1's SIGKILL, now delivered by the kubelet. Reading `kubectl describe pod` after a 137 shows `Reason: OOMKilled` — the single most common LLM-on-k8s incident.
- **`readinessProbe` with `failureThreshold: 30`** — readiness gates whether the Service sends traffic to the pod (Section 4's probe lesson). The threshold is generous because first boot may download the model — same reasoning as Lab 3's long `start_period`. Liveness (restart-if-wedged) has an even longer `initialDelaySeconds` so it never fires *during* a legitimate slow load.
- **`emptyDir` vs PVC** — `emptyDir` lives and dies with the pod, so a reschedule re-downloads. Fine for a disposable kind lab; the comment names the prod fix (a PersistentVolumeClaim so weights survive, or bake the image). This is Section 1's stateful-vs-stateless decision at cluster scale.
- **The `Service` gives a stable DNS name** — `capstone-llm` resolves cluster-wide (Section 4's kube-dns, the successor to compose DNS). The api's `LLM_BASE_URL` points at `http://capstone-llm:8080/v1`; pod IPs churn, the Service name doesn't. Same "never hardcode IPs" rule, third framework running.

### 2. Grow the Helm chart

Add the model to the capstone chart from Section 5 so it deploys as part of the same release. Create `capstone/chart/templates/llm.yaml` with the objects above, but parameterized, and gate it behind a values flag. Add to `capstone/chart/values.yaml`:

```yaml
llm:
  enabled: true
  image: ghcr.io/ggml-org/llama.cpp:server
  model: "Qwen/Qwen3-0.6B-GGUF:Q8_0"    # ← swap models here, one place
  contextSize: 4096
  resources:
    requests: { memory: "1Gi", cpu: "500m" }
    limits:   { memory: "2Gi", cpu: "2" }
```

Wrap the `llm.yaml` templates in `{{- if .Values.llm.enabled }} … {{- end }}` and substitute `{{ .Values.llm.image }}`, `{{ .Values.llm.model }}`, `{{ .Values.llm.contextSize }}`, and the resources block — the Section 5 templating skills, applied to a new component. Then point the api Deployment's env at the Service:

```yaml
        - name: LLM_BASE_URL
          value: "http://capstone-llm:8080/v1"
```

#### Why a values flag instead of always-on

`llm.enabled` makes the LLM an **optional dependency of the release** — staging can run it, a CI smoke-test environment can set `llm.enabled: false` and skip the heavy download. This is the values-layering lesson from Section 5 (base + per-environment overrides), now deciding whether an *expensive* component exists. A subchart is the heavier alternative (`charts/llm/`); a gated template is the right weight for one component.

### 3. Deploy and watch resources bite

Render first (the Section 5 debugging loop — see the YAML before the cluster does):

```bash
cd capstone
helm template . | grep -A5 "kind: Deployment" | head -40   # eyeball the generated objects
helm upgrade --install capstone . --wait --timeout 5m
```

Then watch the model pod come up:

```bash
kubectl get pods -w                       # capstone-llm: Running 0/1 → 1/1, api waits on readiness
kubectl describe pod -l app=capstone-llm  # scroll to Events + the resources block
```

#### What you'll see

```
NAME                            READY   STATUS     RESTARTS
capstone-llm-xxxx               0/1     Running               ← up + downloading, not READY yet
capstone-llm-xxxx               1/1     Running               ← /health passed → Service routes to it
capstone-api-xxxx               1/1     Running
```

The `0/1 Running` phase is the readiness probe doing its job — the pod is up but the Service withholds traffic until `/health` answers (model fully loaded). That's Section 4's probe lesson protecting the LLM's slow start.

**Now deliberately trigger an OOMKill** to feel the limit (optional but educational): temporarily set `llm.resources.limits.memory: "300Mi"` (below the 640MB weights), `helm upgrade`, and watch:

```bash
kubectl get pods -l app=capstone-llm
# capstone-llm-xxxx  0/1  OOMKilled  → CrashLoopBackOff
kubectl describe pod -l app=capstone-llm | grep -A3 "Last State"
# Last State: Terminated  Reason: OOMKilled  Exit Code: 137
```

There it is — **exit 137, Reason: OOMKilled**, the Section 1 SIGKILL delivered by the kubelet because the container tried to allocate past its memory limit before the weights even finished loading. Set the limit back to `2Gi` and `helm upgrade` to recover. That five-minute experiment is a better answer to "have you debugged OOMKilled pods?" than any amount of reading.

### 4. Prove the end-to-end flagship

```bash
kubectl port-forward svc/capstone-llm 9111:8080 &   # direct model access from your Mac
curl -s localhost:9111/health                        # {"status":"ok"} — the model, in-cluster

# and through the api (use your S4 ingress or port-forward the api service):
kubectl port-forward svc/capstone-api 9112:8000 &
curl -s "localhost:9112/ask?q=what+is+kubernetes%3F" | python3 -m json.tool
```

A real answer from `/ask` means the whole chain runs on Kubernetes: **api pod → `capstone-llm` Service → model pod → answer**, all from one Helm release. If Argo CD (Section 9) is watching this chart, a `values.yaml` change to `llm.model` merged to git would roll a new model onto the cluster automatically — the flagship loop, complete.

## Verify

- `kubectl get pods` shows `capstone-llm` reach `1/1 Running`; `/ask` through the api returns a model answer; you've seen an `OOMKilled` / exit 137 when the memory limit was set below the weights.
- You can answer, out loud, without looking:

- `requests` vs `limits` for a model pod — what does each control, and what happens at the memory limit?

  <details><summary>Answer (read after attempting aloud)</summary>

  `requests` is what the scheduler reserves to place the pod (minimum guaranteed). `limits` is the hard ceiling the kernel enforces. Exceed the memory limit and the container is OOM-killed — exit 137 (SIGKILL, 128+9), surfaced as `Reason: OOMKilled` in `kubectl describe`, then CrashLoopBackOff. For an LLM, memory = weights + KV cache, so the limit must cover weights + peak concurrent KV, or a busy moment kills it.

  </details>

- How does the model pod get its weights, why not a true initContainer running `llama-server`, and what's the emptyDir trade-off?

  <details><summary>Answer (read after attempting aloud)</summary>

  The main container runs with `-hf`, which downloads the GGUF into the mounted cache volume on first start, then serves; the readiness probe gates traffic until it's loaded (the k8s form of Lab 3's init-download). You can't boot `llama-server` as an initContainer because an initContainer must *terminate* for the pod to proceed and the server runs forever — a real initContainer would use a tool that exits (`huggingface-cli`/`wget`) to pre-fill the volume. `emptyDir` lives/dies with the pod, so a reschedule re-downloads; fine for a disposable lab, but prod uses a PVC (weights survive) or bakes them into the image. Stateful-vs-stateless, at cluster scale.

  </details>

- Why does the api pod reach the model via `http://capstone-llm:8080` and not a pod IP?

  <details><summary>Answer (read after attempting aloud)</summary>

  `capstone-llm` is a Service — a stable DNS name (kube-dns) that load-balances to the current model pods. Pod IPs churn on every reschedule; the Service name doesn't. Same "never hardcode IPs, resolve by name" rule as compose DNS (`redis://redis`) and Docker networks — third framework, identical principle.

  </details>

- The model pod is `Running` but `0/1 READY` for a while. Why, and what's protecting you?

  <details><summary>Answer (read after attempting aloud)</summary>

  The readiness probe hasn't passed yet — the process is up but the model is still loading/downloading, so `/health` isn't answering 200. Until readiness passes, the Service withholds traffic from the pod, so no request hits a not-yet-loaded model. That's the probe lesson from Section 4 shielding the LLM's slow cold start (hence the generous `failureThreshold`).

  </details>

## Clean up

```bash
kill %1 %2 2>/dev/null                 # stop the port-forwards
helm uninstall capstone               # remove the release
# kind delete cluster --name <name>   # only if you're done with the cluster entirely
```

Commit the chart changes (`templates/llm.yaml`, `values.yaml`, the api env addition). Update the capstone evolution log: "Section 10: model server on Kubernetes via the Helm chart — Deployment + Service + resource limits, gated by `llm.enabled`." This is the last capstone evolution — the flagship is complete.

## The flagship writeup (do this — it's the portfolio)

You now have the full story. Write it up (README section, LinkedIn post, CV bullet source):

> Self-hosted a quantized LLM (`llama-server`, GGUF) behind a FastAPI service; containerized it; deployed it to Kubernetes via a Helm chart with resource limits and readiness probes; instrumented per-request token/cost/latency metrics into Prometheus/Grafana; the whole platform ships through a GitOps pipeline (Argo CD). Serving is engine-agnostic and hosted-or-self-hosted is a single env var.

That paragraph is the AI-infra positioning from `docs/why-this-course.md`, earned with your hands.
