# Section 04 — Kubernetes Core

**Status:** ready · **Time:** ~2 weeks at 2–4h/day · **Labs:** 7

Section 1 ended with a one-liner in your own notes: *"that reconcile loop IS Kubernetes' whole personality."* Section 2 made the capstone image multi-arch on GHCR; Section 3 made you operate one server **by hand** — nginx, TLS, processes, firewall rules, all typed by you over SSH. This section hands that job to software. Kubernetes is the machine that does the operating: you write down what should exist, and a set of programs works *forever* to make reality match.

This is the center of gravity of the whole course — of DevOps interviews, of the CKA, of nearly every job description you'll apply to.

## The mental model (read first)

**Kubernetes = the compose reconcile loop, promoted to a full-time job across many machines.** Recall exactly what happened in Section 1, Lab 4 when you added a `logging:` block and ran `up -d`: compose diffed the file against reality and recreated *only* the api. That was one reconcile pass, triggered by you, on one machine. Kubernetes runs that same diff-and-fix loop **continuously, unprompted, across a fleet of machines**. Container dies at 3am → replaced. Machine dies → its containers rescheduled elsewhere. Someone hand-edits the live state → reverted. You already proved the philosophy with `up -d` ("make reality match the file"); K8s just never stops running it.

**Everything revolves around one idea: desired state.** You never tell Kubernetes *what to do* — you tell it *what should exist* ("3 copies of this image, reachable under this name, with this much memory"). You write that as YAML, hand it over with `kubectl apply`, and it gets stored in a database. Then controllers — little programs whose only job is "compare desired vs actual, fix the difference" — grind away at it forever. `kubectl apply` is `docker compose up -d` with the crucial difference that the reconcile never ends.

**The machinery splits into two halves — the office and the workers:**

```
        YOU
         │  kubectl apply -f deployment.yaml     "3 replicas of capstone, please"
         ▼
┌── CONTROL PLANE (the office — decides, never runs your app) ──────────┐
│                                                                        │
│  api-server   the ONLY door. kubectl, nodes, controllers — everyone   │
│               talks to the cluster exclusively through it (REST+auth) │
│  etcd         the notebook. Every object you apply is written here;   │
│               it IS the cluster's memory (a key-value store)          │
│  scheduler    the dispatcher. Sees a pod with no node assigned,       │
│               picks the best node for it (resources, constraints)     │
│  controller-  the reconcile loops. Dozens of them, one per object     │
│  manager      type: "desired 3 pods, see 2 → create 1"                │
└──────┬────────────────────────────────────────────────────────────────┘
       │ kubelets watch the api-server: "anything assigned to me?"
   ┌───┴────────────────┐
┌──▼───────────┐   ┌────▼─────────┐
│ node 1       │   │ node 2       │     ← in kind, each node is a
│  kubelet     │   │  kubelet     │        Docker container on your Mac
│  containerd  │   │  containerd  │
│  kube-proxy  │   │  kube-proxy  │
│  [your pods] │   │  [your pods] │
└──────────────┘   └──────────────┘
```

- **api-server** — the single front door. Nothing talks to etcd or to nodes directly; every read and write goes through it. That's why RBAC, auditing, and admission control are even possible: one choke point.
- **etcd** — where the desired state (and the observed state) physically lives. Lose etcd, lose the cluster's memory.
- **scheduler** — only decides *placement*. It never starts a container; it just writes "this pod → node 2" back into the notebook.
- **controller-manager** — the reconcile loops, the personality. Deployment controller, ReplicaSet controller, node controller… each one watches its object type and closes the gap between desired and actual.
- **kubelet** — the agent on every node; the babysitter role the Docker engine played in Section 1, now reporting to a head office. It watches the api-server for pods assigned to its node, tells the container runtime (containerd) to run them, runs the probes, reports status back.
- **kube-proxy** — the network plumber on every node. It writes the iptables rules (the exact kind you read by hand in Section 3, Lab 6) that make Service IPs work.
- **CoreDNS** — the cluster's phonebook, the cluster-scale version of compose's `127.0.0.11` DNS you proved with `socket.gethostbyname` in Section 1, Lab 4.

**The objects you'll write, mapped to what you already own.** Every K8s concept in this section is the cluster-scale version of something you proved with your own hands in Section 1:

| You proved in compose… | …becomes in Kubernetes |
|---|---|
| a `services:` block | **Deployment** (runs the containers) + **Service** (names them) |
| service name = DNS hostname (`redis://redis:6379`) | **Service** name resolved by CoreDNS — same habit, richer machinery |
| healthcheck + `service_healthy` (startup-only gate) | **readiness/liveness/startup probes** — the gate that finally works at *runtime* too |
| `environment:` / 12-factor env | **ConfigMap** (plain config) + **Secret** (credentials) |
| `pgdata` named volume (the parking spot) | **PersistentVolumeClaim** — a claim ticket for storage that outlives pods |
| `restart: unless-stopped` | the reconcile loop itself — self-healing is the default, not a flag |
| exit 137 / OOM | **OOMKilled** — same number, now triggered by a memory *limit you declare* |
| `docker compose up -d` | `kubectl apply -f` — declarative, idempotent, always safe |
| `docker compose ps` / `logs` / `exec` | `kubectl get` / `logs` / `exec` — the same muscle memory, new binary |

One genuinely new unit: the **Pod** — the smallest thing K8s schedules. A pod is one or more containers that share a network namespace and volumes (usually one container; the "sidecar" pattern adds helpers). You almost never create pods directly — a **Deployment** manages a **ReplicaSet** which manages pods. Why three layers? Pods are disposable (they die and are *replaced*, never healed); the ReplicaSet is the reconcile loop keeping N of them alive; the Deployment manages ReplicaSets so that *upgrades* can roll out gradually and roll back instantly. You'll watch all three layers move in Lab 2.

**The tool: kind — Kubernetes IN Docker.** A real multi-node cluster where each "machine" is a Docker container on your Mac. `docker ps` will literally show you your nodes. It's what Kubernetes uses to test Kubernetes, it's free, it's disposable — `kind delete cluster` and every trace is gone; recreate it in two minutes. Disposability is a feature you should exploit: if your cluster ever gets into a weird state, delete it and re-apply your manifests. The manifests are the truth; the cluster is cattle.

## Why this matters for jobs

- **Kubernetes is the DevOps interview.** "Pod is CrashLooping — walk me through your debugging" and "explain what happens when you run `kubectl apply`" are the two most common scenario questions in the field. Labs 2 and 5 make you fail and fix both, on purpose.
- **CKA is a practical exam** — a terminal, a broken cluster, a timer. Every lab here builds the exact reflexes it grades: `kubectl describe`, `kubectl explain`, `--dry-run=client -o yaml`, reading Events. Section 11 turns this into a cert plan.
- **The AI-infra angle:** every serious model-serving stack (vLLM, KServe, Ray) ships as Kubernetes manifests. Section 10 puts your self-hosted LLM on this exact cluster — "I run LLM inference on Kubernetes" is the hardest-to-fill sentence on a 2026 CV.

## Versions pinned for this section (July 2026)

| Tool | Version | Install |
|---|---|---|
| kind | **v0.32.0** | `brew install kind` |
| kubectl | **v1.36.x** | `brew install kubectl` (you may already have it) |
| Kubernetes (node image) | **v1.36.1** — kind v0.32.0's default | pulled automatically |
| ingress-nginx | **controller-v1.15.1** (the final release — see below) | manifest URL in Lab 7 |
| capstone image | `ghcr.io/itsmahadi007/capstone` — multi-arch since Section 2 | pulled from GHCR |
| redis / postgres | `redis:8-alpine` / `postgres:18-alpine` — same tags as your compose file | pulled automatically |

**Honest note on ingress-nginx:** the project was retired and its repo archived in March 2026; v1.15.1 is the last release, and Gateway API is the anointed successor. We still learn it deliberately: it's what runs in the overwhelming majority of existing clusters (someone has to operate — and migrate — those, which is a *job*), it's what the CKA and interviews still ask about, and the Ingress concepts transfer 1:1 to Gateway API. Knowing the retirement story is itself interview currency — Lab 7 gives you the two-sentence version.

**Host ports:** this section owns the 9050 block — `9050` for every `kubectl port-forward`, `9051` for ingress HTTP, `9052` for the NodePort demo. Container/cluster-side ports stay conventional.

## Labs

Do them in order — each builds on the cluster state the previous one leaves behind.

- [ ] [Lab 1 — Cluster up + the grand tour](labs/lab-01-cluster-up.md) — kind cluster from a config file; meet every control-plane piece running as a real pod; `kubectl get/describe/explain`
- [ ] [Lab 2 — Pods & Deployments](labs/lab-02-pods-deployments.md) — capstone from GHCR; replicas, self-healing live, rollout/rollback, ImagePullBackOff on purpose
- [ ] [Lab 3 — Services & DNS](labs/lab-03-services-dns.md) — ClusterIP/NodePort, the cluster phonebook vs compose DNS, port-forward on 9050
- [ ] [Lab 4 — ConfigMaps & Secrets](labs/lab-04-config-secrets.md) — `REDIS_URL` moves to a ConfigMap; why Secrets aren't secret
- [ ] [Lab 5 — Probes & resources](labs/lab-05-probes-resources.md) — your Lab 3 healthcheck becomes three probes; requests/limits; OOMKilled = 137, again
- [ ] [Lab 6 — Redis + Postgres in-cluster](labs/lab-06-redis-postgres-pvc.md) — the promise of Lab 4 kept; PVC = the pgdata lesson at cluster scale
- [ ] [Lab 7 — Ingress](labs/lab-07-ingress.md) — ingress-nginx on kind, one front door on 9051, the full packet path named hop by hop

## Reading (curated, ~2h total)

- [Kubernetes Components](https://kubernetes.io/docs/concepts/overview/components/) — the official version of the diagram above
- [Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/) — read after Lab 2; the rollout section especially
- [Service](https://kubernetes.io/docs/concepts/services-networking/service/) — read after Lab 3
- [Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/) — read after Lab 5
- [kind Quick Start](https://kind.sigs.k8s.io/docs/user/quick-start/) — skim; you'll have done most of it in Lab 1
- [kubectl Quick Reference](https://kubernetes.io/docs/reference/kubectl/quick-reference/) — bookmark; this is the CKA cheat sheet too

## Done when

Every task in [checkpoint.md](checkpoint.md) passes from memory, and [notes.md](notes.md) is filled in your own words. Then Section 05 (Helm) parameterizes the exact manifests you wrote here into a chart.
