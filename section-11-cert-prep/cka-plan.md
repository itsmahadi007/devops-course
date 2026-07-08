# CKA plan — 4 weeks to a pass

**Goal:** pass the Certified Kubernetes Administrator exam within 4 weeks of starting this plan, spending most of the time on genuine gaps and speed — not re-learning what sections 4–10 already taught you.

## Exam facts (verified 2026-07 — re-check the [official page](https://training.linuxfoundation.org/certification/certified-kubernetes-administrator-cka/) the week you book)

| Fact | Value |
|---|---|
| Price | **$445** exam-only (LF runs 30–40% sales constantly — buy on sale; 12 months to schedule after purchase) |
| Format | **Performance-based**: ~15–20 tasks in a live cluster environment, **2 hours**, online proctored (PSI) |
| Passing | **66%** |
| Kubernetes version | **v1.35** (env tracks upstream within ~4–8 weeks of each release) |
| Retake | **One free retake** included |
| Included prep | **Two killer.sh simulator sessions**, 36 hours of access each — still bundled, confirmed |
| Allowed resources | Firefox *inside the remote desktop*, restricted to `kubernetes.io/docs`, `kubernetes.io/blog`, and Helm docs. Nothing on your own machine. |

**The environment, honestly:** since 2024 the exam runs in a PSI remote desktop (XFCE on their machine, streamed to yours). You get their terminal, their Firefox, their copy-paste quirks (`Ctrl+Shift+C/V` in the terminal). One monitor only, webcam room scan, clean desk, ID check. It's clunkier than your own iTerm — which is exactly why killer.sh (same style of environment) matters more than any video course.

## The mental map (read this first)

```
CKA domain                     weight   your coverage (S = section)
─────────────────────────────  ──────   ────────────────────────────────
Troubleshooting                 30%     ████████░░  S1 S3 S4 S8 — strong
Cluster Architecture,           25%     ████░░░░░░  S4 S5 concepts — but
  Installation & Config                 kubeadm/etcd/RBAC = REAL GAPS
Services & Networking           20%     ██████░░░░  S3 S4 — NetworkPolicy,
                                        Gateway API = gaps
Workloads & Scheduling          15%     ███████░░░  S4 — scheduling controls
                                        = gap
Storage                         10%     ███████░░░  S1 S4 — StorageClass
                                        details = gap
```

Read the shape of that chart: **you're strongest in the highest-weighted domain** (troubleshooting is 30% and it's just sections 1–8 instincts under a timer), and your biggest genuine gap (cluster lifecycle) sits inside a 25% domain where the *other* half — Helm, CRDs-as-concepts, RBAC-as-concept — you already half-own. This is a gap-filling exam for you, not a course.

One more framing that changes how you prep: **the exam is scored per task, and tasks have visible weights.** You don't need elegance, you need working answers on 66% of the points. Triage is a skill you'll train in week 3.

## Domain map: covered vs gaps

The curriculum below is the current (2025-refresh, v1.35) official competency list, mapped line by line.

### Domain 1 — Troubleshooting (30%)

| Competency | Where you covered it | Gap? |
|---|---|---|
| Troubleshoot clusters and nodes | S4 `describe`/events/self-healing demo | **Partial** — node NotReady / kubelet-down drills |
| Troubleshoot cluster components | — | **GAP** — control plane pods, static pod manifests |
| Monitor cluster and application resource usage | S8 Prometheus/Grafana; `kubectl top` | Thin: `kubectl top` + metrics-server specifics |
| Manage and evaluate container output streams | S1 logs deep-dive (a log line's life), S4 log slicing flags | Covered — just map to `kubectl logs` flags |
| Troubleshoot services and networking | S4 service DNS, S3 networking toolbox (ss/dig/curl) | **Partial** — endpoints-empty debugging, CoreDNS checks |

Your S1 instincts transfer directly: exit 137 = OOMKilled (128+9, the same arithmetic from Lab 1), `CrashLoopBackOff` = the PID-1-exits story on a restart loop, probes = the healthcheck stamp with a kubelet acting on it. Troubleshooting tasks are "read `describe`, read logs, read events, fix the YAML" — you've been doing that since Lab 2.

### Domain 2 — Cluster Architecture, Installation & Configuration (25%)

| Competency | Where you covered it | Gap? |
|---|---|---|
| Manage RBAC | S4 mentioned; never hands-on | **GAP** — the big one with NetworkPolicy |
| Prepare underlying infrastructure | S3 Linux fluency covers the substance | Mostly covered |
| Create and manage clusters with kubeadm | kind did this *for* you all course | **GAP** — the single biggest |
| Manage cluster lifecycle (upgrades, etcd backup/restore) | — | **GAP** — classic exam tasks live here |
| Implement HA control plane | — | **GAP** (concept-level questions; know the shape) |
| Use Helm and Kustomize to install cluster components | S5 entirely (Helm); Kustomize never | **Half-gap** — Kustomize only |
| Understand extension interfaces (CNI, CSI, CRI) | S4 concepts, S10 runtime intuition | Concept refresh only |
| Understand CRDs, install and configure operators | S9 Argo CD *is* CRDs+operator in production use | Name the mechanism explicitly + one drill |

### Domain 3 — Services & Networking (20%)

| Competency | Where you covered it | Gap? |
|---|---|---|
| Understand pod-to-pod connectivity | S4 cluster networking, S3 ip/ss foundations | Covered |
| Define and enforce Network Policies | — | **GAP** |
| ClusterIP / NodePort / LoadBalancer + endpoints | S4 services lab | Covered — add endpoints inspection |
| Use the Gateway API to manage ingress traffic | — (S4 used Ingress) | **GAP** — new in the current curriculum |
| Ingress controllers and resources | S4 ingress-nginx on kind | Covered |
| Understand and use CoreDNS | S4 "kube-dns vs compose DNS" | **Partial** — the Corefile, config edits |

### Domain 4 — Workloads & Scheduling (15%)

| Competency | Where you covered it | Gap? |
|---|---|---|
| Deployments, rolling updates, rollbacks | S4 rollout/rollback lab, S5 Helm releases | Covered |
| ConfigMaps and Secrets | S4 config lab | Covered |
| Configure workload autoscaling | — | **GAP** — HPA + metrics-server |
| Robust, self-healing deployments (probes, etc.) | S1 healthchecks → S4 probes — your strongest thread | Covered |
| Pod admission and scheduling (limits, node affinity, …) | S4 requests/limits | **GAP** — taints/tolerations, affinity, nodeSelector, priorityClass |

### Domain 5 — Storage (10%)

| Competency | Where you covered it | Gap? |
|---|---|---|
| StorageClasses, dynamic provisioning | kind's default SC did it invisibly in S4 | **Partial** — write one, understand `volumeBindingMode` |
| Volume types, access modes, reclaim policies | S1 volumes intuition, S4 PVC | **Partial** — `Retain` vs `Delete`, RWO/RWX/ROX table |
| Manage PVs and PVCs | S4 pgdata PVC (the S1 volume lesson at cluster scale) | Covered — add *static* PV→PVC binding drill |

## Gap-filling drills (weeks 1–2)

Each drill: do it, then re-do it from memory the next day in under the target time. Most run on your existing kind cluster — the two marked **[VMs]** need real machines because kind can't do in-place cluster surgery.

**Drill environment note:** kind's "nodes" are containers, but they run systemd and kubelet *inside* — `docker exec -it <node> bash` then `systemctl status kubelet` works. So kubelet-breakage and etcd-snapshot drills work on kind. What kind can't do: `kubeadm init/join/upgrade` on a fresh machine. For those two drills: `brew install multipass`, launch two Ubuntu VMs (`multipass launch -n cp -c 2 -m 4G && multipass launch -n worker -c 2 -m 2G`). Free, local, disposable — the vps-lab idea with a real kernel each.

1. **RBAC** (kind) — create a ServiceAccount, a Role allowing `get/list` on pods in one namespace, a RoleBinding; prove with `kubectl auth can-i --as=system:serviceaccount:<ns>:<sa>`. Then the cluster-scoped variant (ClusterRole/ClusterRoleBinding). Then the classic exam twist: a *user* via CertificateSigningRequest — generate a key+CSR, approve it, build a kubeconfig context for it. Target when re-done: 15 min total.
2. **NetworkPolicy** (kind — needs a CNI that enforces; install Calico on a fresh kind cluster, the default kindnet does NOT enforce policies) — default-deny-all in a namespace, then allow only api→redis on 6379 (your own capstone shape). Verify with a `kubectl run` test pod + `nc`. This is a *guaranteed* exam topic. Target: 15 min.
3. **Gateway API** (kind) — install the Gateway API CRDs + a gateway controller, replicate your S4 ingress route as `Gateway` + `HTTPRoute`. Once. It's new in the curriculum; tasks are likely "create an HTTPRoute matching X" — pattern-matching from docs, not depth. Target: know where the docs page is and copy fast.
4. **Scheduling controls** (kind) — taint a node, watch pods avoid it, add a toleration; `nodeSelector` then `nodeAffinity` (required + preferred); a priorityClass. Then the reverse drill: "why is this pod Pending?" → `describe` → read the scheduling failure events. Target: 20 min.
5. **HPA** (kind) — install metrics-server (needs `--kubelet-insecure-tls` on kind), `kubectl autoscale deployment`, load it with a busybox `wget` loop, watch it scale. Target: 15 min.
6. **Storage** (kind) — write a StorageClass; create a *static* PV (hostPath) + a PVC that binds it (match size/accessModes/storageClassName — the binding rules ARE the task); flip reclaim policy Retain↔Delete and explain aloud what happens on PVC delete in each. Target: 15 min.
7. **Kustomize** (anywhere) — take your S4 raw manifests, add a `kustomization.yaml`, one overlay that patches replicas + image tag. `kubectl apply -k`. You know Helm deeply (S5); Kustomize is "the same job, patch-based, built into kubectl" — one evening.
8. **CRDs + operators** (kind) — you *ran* an operator all of S9 (Argo CD). Now name the mechanism: `kubectl get crds`, `kubectl explain <crd>`, write a trivial CRD YAML + a custom resource of it. Connect it aloud to S9: Argo's `Application` object was exactly this.
9. **etcd backup/restore** (kind) — exec into the control-plane node; `etcdctl snapshot save` with the three cert flags (read them out of the etcd static-pod manifest in `/etc/kubernetes/manifests/etcd.yaml` — the exam gives you the same file); restore to a new data dir; repoint the manifest. **The classic CKA task.** Target: 10 min from memory.
10. **[VMs] kubeadm init/join** — on multipass VMs: container runtime prereqs, `kubeadm init`, install CNI, `kubeadm join` the worker. Feel every step kind was hiding. Once slowly, once fast. Target on redo: 30 min.
11. **[VMs] Cluster upgrade** — `kubeadm upgrade plan` → upgrade the control plane one minor version → `kubectl drain` worker → upgrade kubelet → `uncordon`. Drain/cordon/uncordon is also a standalone exam task — drill it separately on kind too. Target: 25 min.
12. **Break-and-fix set** (kind — do these blind; break with one terminal, fix in another, or better: script the breaks and shuffle):
    - `systemctl stop kubelet` on a node → find via `get nodes` → NotReady → exec in → status → start
    - Edit the kube-apiserver static pod manifest to an invalid flag → apiserver dies → fix from the node (you can't use kubectl when the apiserver is down — that's the lesson)
    - Scale CoreDNS to 0 → service names stop resolving → your S4 DNS debugging run
    - A Service with a selector typo → endpoints empty → the #1 real-world networking task

## kubectl speed training (daily, weeks 1–4)

The exam is a typing-speed exam wearing a Kubernetes costume. **Rule zero: never write YAML from scratch.** Generate it, or copy it from the docs.

**Exam env setup (first 60 seconds of the real exam, practice until automatic):**

```bash
# alias k=kubectl and completion are usually pre-configured — verify, don't assume
export do="--dry-run=client -o yaml"    # k run x --image=nginx $do > pod.yaml
export now="--force --grace-period=0"   # k delete pod x $now
# ~/.vimrc:  set ts=2 sw=2 et           # tabs would break your YAML
```

**The imperative reflexes** — drill this list until each is muscle memory (write the command from the prompt, no docs; a full pass of all of them should take under 10 minutes):

```bash
k run web --image=nginx $do > pod.yaml
k create deployment api --image=ghcr.io/x/y --replicas=3 $do
k expose deployment api --port=80 --target-port=8000 --type=NodePort
k create configmap cfg --from-literal=K=V --from-file=app.conf
k create secret generic s --from-literal=PASS=x
k create sa deployer
k create role r --verb=get,list --resource=pods
k create rolebinding rb --role=r --serviceaccount=ns:deployer
k create ingress ing --rule="host/path*=svc:80"
k create job j --image=busybox -- date
k create cronjob cj --image=busybox --schedule="*/5 * * * *" -- date
k set image deployment/api api=ghcr.io/x/y:v2
k scale deployment api --replicas=5
k rollout status/undo/history deployment/api
k taint node w1 key=val:NoSchedule          # remove: key=val:NoSchedule-
k cordon / drain --ignore-daemonsets / uncordon w1
k top pods --sort-by=memory
k explain deployment.spec.strategy           # the offline docs — use it
k get pods -o jsonpath='{.items[*].metadata.name}'
k get pods -o custom-columns=NAME:.metadata.name,IP:.status.podIP
```

**The context habit:** every exam task begins by telling you which cluster/context it runs on. Copy-paste that `kubectl config use-context …` line from the task text *every single task*, even when you think you're already there. Points die from this more than from ignorance.

**Docs bookmarks to know cold** (you get kubernetes.io/docs in the exam): the NetworkPolicy page, the PV/PVC page, the kubeadm upgrade page, the etcd backup section, the affinity page. Practice *finding* each in under 20 seconds — in the exam you search the docs, not your memory.

## killer.sh strategy

Two sessions are included with registration (confirmed 2026-07). What most people don't know until too late:

- **Both sessions contain the same questions.** So they're not two mocks — they're one mock you get to take twice. Plan: session 1 = diagnostic, session 2 = confirmation.
- **It's deliberately harder than the real exam** — longer tasks, meaner edge cases. Scoring ~60–70% on killer.sh under time = comfortably passing the real thing. Do not let the score demoralize you; let the *solutions* teach you — every question ships a detailed walkthrough.
- Each activation gives **36 hours of environment access**. Take the timed 2-hour run at the *start* of the window, then spend the rest of the window dissecting: redo every missed task, read every solution even for tasks you got right (their way is usually faster).
- **Session 1: end of week 2 / start of week 3** — after gap drills, before speed week peaks. It tells you where week 3 goes.
- **Session 2: 3–4 days before the exam** — same questions, so treat it purely as a speed-and-calm rehearsal in the exam-like remote environment. If you can't clear ~80% on questions you've *seen before*, move the exam date (rescheduling is free up to 24h before).

## 4-week schedule

Relative time: **week 1 = the week you start this plan.** Daily commitment ~2.5–4h (your standing course budget). Every day, cert-lane or not, opens with the same 20-minute warmup: **one full pass of the imperative-reflexes list, timed.**

### Week 1 — gap drills, part 1 (all on kind)

| Day | Block A (~90 min) | Block B (~60–90 min) |
|---|---|---|
| 1 | Drill 1: RBAC (SA → Role → Binding → can-i) | RBAC round 2: CSR user + kubeconfig |
| 2 | Drill 2: NetworkPolicy (Calico kind cluster, default-deny, allow api→redis) | Drill 6: Storage (SC, static PV/PVC binding, reclaim policies) |
| 3 | Drill 4: Scheduling (taints, affinity, "why Pending?") | Drill 5: HPA + metrics-server |
| 4 | Drill 3: Gateway API once + Drill 7: Kustomize | Drill 8: CRDs (+ say the Argo CD connection aloud) |
| 5 | Redo drills 1, 2, 6 *from memory*, timed against targets | Drill 9: etcd backup/restore, first slow pass |
| 6–7 | Light: one redo of whatever missed its target · read the [candidate handbook](https://docs.linuxfoundation.org/tc-docs/certification/lf-handbook2) once | Rest is allowed |

### Week 2 — cluster lifecycle + troubleshooting (the VM week)

| Day | Block A | Block B |
|---|---|---|
| 1 | multipass up · Drill 10: kubeadm init/join, slow pass | Read what every step did (`/etc/kubernetes/`, static pods, certs dir) |
| 2 | Drill 10 again, fast, from notes | Drill 11: upgrade + drain/cordon/uncordon |
| 3 | Drill 9 redo: etcd backup/restore ≤ 10 min from memory | Drill 11 drain/uncordon redo on kind, timed |
| 4 | Drill 12: break-and-fix — kubelet, apiserver manifest | Drill 12: CoreDNS, empty-endpoints |
| 5 | Full break-and-fix gauntlet, shuffled, timed | Weak-spot redo |
| 6–7 | **killer.sh session 1**: 2h timed run at window start… | …then dissect inside the same 36h window: every miss redone, every solution read |

### Week 3 — speed week

- **Daily (2–3h):** self-built timed task sets — pick 6 tasks across all five domains (write tomorrow's set today, from the curriculum lines, so you can't pre-solve mentally), 45-minute timer, exam rules (docs allowed, nothing else). Then review misses.
- Re-drill the two or three domains killer.sh session 1 exposed — go back to the relevant week-1/2 drills, not videos.
- One session on **triage practice**: given 17 tasks with weights, order them cheapest-first; flag-and-skip anything stuck for >6 minutes. 66% means you can *abandon a third of the exam* and still pass — internalize that; it removes the panic.
- End of week: **book the exam** for the end of week 4 (you bought it on sale weeks ago — booking is the commitment device).

### Week 4 — exam week

| Day | Work |
|---|---|
| 1 | **killer.sh session 2**, timed. Target: ≥80% (seen questions). Below that → reschedule the exam, repeat week 3, no shame — the retake-free window is for real emergencies, not skipped prep |
| 2 | Dissect session 2; final weak-spot drills |
| 3 | Logistics rehearsal: PSI system check on the exact machine/room, ID ready, desk cleared, one monitor, know the copy-paste keys · light imperative-reflex passes only |
| 4 | Rest day. Seriously. Speed exams punish tired brains more than underprepared ones |
| 5 | **Exam.** First 60 seconds: env setup. Every task: use-context line first. Cheap tasks first. Flag, skip, return |

**After the pass:** cert line onto both CVs the same day (see `market-entry.md`), LinkedIn post the same week — a cert announcement is the single highest-engagement post format on the platform; point it at the repo, per the posting plan.
