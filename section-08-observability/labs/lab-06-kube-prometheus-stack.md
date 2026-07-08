# Lab 6 — kube-prometheus-stack on kind (OPTIONAL)

> **OPTIONAL and heavier on the Mac.** This lab reuses your **Section 4 (kind + kubectl)** and **Section 5 (Helm)** skills to install the *Kubernetes-native* version of everything you just built by hand. Do it only if you want the operator/`ServiceMonitor` mental model (it comes up in interviews for K8s-heavy shops) or the batteries-included contrast. It runs a lot of pods — check the warning in Step 0 first. **Same-day teardown is in Clean up; run it when done.**

**Goal:** `helm install` the `kube-prometheus-stack` chart on a kind cluster, see that one command deploy Prometheus + Grafana + Alertmanager + node-exporter + kube-state-metrics + a pile of prebuilt dashboards, and understand *why* the Kubernetes way discovers scrape targets automatically (the `ServiceMonitor` CRD) instead of a hand-edited `prometheus.yml`.

## The mental map (read this first)

In Labs 2–4 you wired everything yourself: a `prometheus.yml` with static targets, a Grafana data source by hand, dashboards panel by panel. That's the right way to *learn*. On a real cluster it doesn't scale — pods come and go with random IPs, so a static target list is obsolete the moment you save it.

The Kubernetes answer is the **Prometheus Operator**: a controller that watches for special resources (**Custom Resource Definitions**) called `ServiceMonitor` and `PrometheusRule`, and *rewrites Prometheus's config for you* whenever they change. You stop editing `prometheus.yml`; instead you drop a `ServiceMonitor` that says "scrape any Service with label `app=capstone` on port `metrics`," and the operator keeps Prometheus's target list in sync as pods scale.

```
   hand-built (Labs 2-4)          operator-driven (this lab)
   edit prometheus.yml      →     create a ServiceMonitor CRD
   restart/reload Prometheus →    Operator sees it, regenerates
                                   Prometheus config automatically
   static targets           →     targets auto-discovered by label,
                                   updated as pods come and go
```

`kube-prometheus-stack` is a Helm chart that bundles the operator **plus** Prometheus, Grafana (with dozens of curated Kubernetes dashboards preloaded), Alertmanager, `node-exporter` (node CPU/mem/disk — your **saturation** signal from Lab 5, finally proper), and `kube-state-metrics` (the health of every Deployment/Pod/PVC). One `helm install`, a whole observability platform. The trade vs your hand-built stack: you get everything instantly, but you no longer understand each piece — which is exactly why you built it by hand first.

## Steps

### 0. Check you can afford it, and have a cluster

This stack runs ~8–12 pods. On an 8GB Mac it's tight; on 16GB+ it's fine. If your Mac is busy with the cashlessai stack, stop the compose observability overlay first (`docker compose down`) to free RAM.

You need the Section 4/5 tools. If a cluster isn't already up:

```bash
kind create cluster --name obs         # from Section 4
kubectl config use-context kind-obs
helm version                           # from Section 5 — confirm helm is installed
```

### 1. Add the chart repo and install

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm install kps prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace \
  --set grafana.adminPassword=admin
```

`helm install kps ...` = "create a release named `kps` from this chart in the `monitoring` namespace." Helm renders hundreds of manifests (the operator, CRDs, all the components) and applies them. This is the Section 5 `helm install` you know, pointed at a big community chart — the same "consume a community chart, read its values" muscle.

> **If CRDs error** on first install (`no matches for kind "ServiceMonitor"`) — the chart installs CRDs and resources together and can race on a slow machine; re-run the same `helm install` (Helm is declarative — safe to repeat) or `helm upgrade --install kps ...`.

### 2. Watch it come up

```bash
kubectl -n monitoring get pods -w        # -w = watch; Ctrl-C when all are Running/Ready
```

You'll see the reconcile loop from Section 4 in action — pods appear as `Pending` → `ContainerCreating` → `Running`. Give it 2–4 minutes. Then look at what you got for free:

```bash
kubectl -n monitoring get servicemonitors    # the auto-discovery rules the operator watches
kubectl -n monitoring get prometheusrules     # prepackaged alert rules (Kubernetes health, etc.)
```

Dozens of each — alerting and scrape rules for the whole cluster, that you'd never want to write by hand.

### 3. Reach Grafana and Prometheus (port-forward)

kind runs the cluster inside a container, so reach the services with `kubectl port-forward` (Section 4's habit). Stay in this section's **9090–9099** block — use 9095/9096 to avoid clashing with the compose stack's 9090/9091:

```bash
kubectl -n monitoring port-forward svc/kps-grafana 9095:80 &
kubectl -n monitoring port-forward svc/kps-kube-prometheus-stack-prometheus 9096:9090 &
```

- **Grafana → http://localhost:9095** (login `admin` / `admin`). Left menu → **Dashboards**: it's already full — "Kubernetes / Compute Resources / Namespace", "Node Exporter / Nodes", etc. This is the batteries-included contrast to your hand-built single dashboard. Open the Node Exporter one: there's your **saturation** signal (CPU, memory, disk) that RED alone couldn't show.
- **Prometheus → http://localhost:9096/targets**: every cluster component auto-discovered — kubelet, node-exporter, kube-state-metrics, the operator itself — none of which you configured.

### 4. (Concept) how you'd scrape the capstone here

You won't wire it end-to-end unless the capstone is deployed on this cluster (that's Section 4/5's job), but know the shape: you'd deploy the capstone, put a `ServiceMonitor` next to it —

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: capstone
  namespace: monitoring
  labels:
    release: kps                 # the operator only picks up monitors with this label by default
spec:
  selector:
    matchLabels:
      app: capstone              # match the capstone Service's labels
  endpoints:
    - port: http                 # the named Service port that serves /metrics
      path: /metrics
      interval: 15s
```

— and the operator would add it to Prometheus automatically. No `prometheus.yml` edit, no reload. *That's* the whole point of the operator model: you declare intent as a Kubernetes object, a controller reconciles the config.

## Verify

```bash
kubectl -n monitoring get pods | grep -E 'prometheus|grafana|operator|node-exporter|kube-state'
```

**Proof it worked:** all those pods are `Running`/`Ready`, Grafana at :9095 shows prebuilt Kubernetes dashboards, and Prometheus at :9096/targets lists auto-discovered targets you never configured.

Answer aloud:

**Q1. On the compose stack you edited `prometheus.yml` to add a target. What replaces that on Kubernetes, and why is the static-file approach unworkable in a cluster?**
<details><summary>Answer (read after attempting aloud)</summary>
A `ServiceMonitor` (a CRD) replaces it: you declare "scrape Services matching these labels on this port," and the **Prometheus Operator** watches for those objects and regenerates Prometheus's config automatically. A static target list is unworkable because pods are ephemeral — they get new IPs on every reschedule/scale event, so any hand-written target list is stale immediately. Label-based auto-discovery is the only thing that keeps up.
</details>

**Q2. What does `kube-prometheus-stack` give you that your hand-built stack didn't — and what did you lose by using it?**
<details><summary>Answer (read after attempting aloud)</summary>
Gained: the operator, Alertmanager, node-exporter (node saturation), kube-state-metrics (K8s object health), and dozens of curated dashboards + alert rules — a whole platform from one `helm install`. Lost: understanding of each piece. You can't debug what you didn't build, which is exactly why building the compose stack by hand first (Labs 1–5) was the right order — now the magic chart is legible instead of opaque.
</details>

## Clean up (do this the same day — it's heavy)

```bash
helm uninstall kps -n monitoring        # remove the release
kubectl delete namespace monitoring     # sweep up anything left (CRDs may linger — see below)
# CRDs are cluster-scoped and Helm won't delete them by default:
kubectl get crd | grep -E 'monitoring.coreos.com' | awk '{print $1}' | xargs -r kubectl delete crd
kill %1 %2 2>/dev/null                   # stop the port-forwards
kind delete cluster --name obs           # nuke the whole cluster if you made it just for this
```

Nothing to commit — this lab left no files in the repo (the `ServiceMonitor` above is illustrative). Your section artifacts are the compose overlay and dashboard JSON from Labs 1–4.
