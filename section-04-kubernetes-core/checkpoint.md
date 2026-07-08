# Checkpoint — Section 04: Kubernetes Core

Pass every task **from memory** — no peeking at the labs. If you have to peek, the section isn't done yet; redo that lab tomorrow and try again. These are CKA-shaped on purpose: the exam is a terminal, a broken cluster, and a timer, and it rewards exactly these reflexes.

## Practical tasks

- [ ] **1.** From nothing, create a two-node kind cluster from a config file with a host-port door mapped, and confirm both nodes are `Ready` and the api-server pod is running. Target: under 5 minutes.
- [ ] **2.** Deploy `ghcr.io/itsmahadi007/capstone` as a Deployment with 2 replicas, then: delete a pod and watch it heal, scale to 4 imperatively, and snap it back to 2 by re-applying the file. Explain why the file won.
- [ ] **3.** Break a rollout with a non-existent image tag, prove the old pods kept serving, read the reason in `describe` Events, and rescue with `kubectl rollout undo`.
- [ ] **4.** Put a ClusterIP Service in front of the Deployment, reach it via `port-forward` on 9050, then resolve its DNS name from a throwaway `busybox` pod (`nslookup`). Then produce an empty-endpoints Service on purpose and diagnose it.
- [ ] **5.** Move `REDIS_URL` into a ConfigMap and `POSTGRES_PASSWORD` into a Secret, inject both as env, then `base64 -d` the Secret to prove it isn't encrypted. Say what actually protects it.
- [ ] **6.** Add startup/readiness/liveness probes, then break *only* readiness and show the pod goes `0/1` and drops from endpoints with **zero restarts**; fix it and watch it rejoin.
- [ ] **7.** Trigger an `OOMKilled` on purpose with a memory limit, find exit code `137` in `describe`, and explain the number without looking it up.
- [ ] **8.** Stand up redis (no PVC) and postgres (PVC at `/var/lib/postgresql`), get `/visits` returning real numbers through the Ingress, then delete the postgres pod and prove a created table survived.
- [ ] **9.** Install the ingress-nginx controller, write an Ingress routing `/` to the api Service, and `curl localhost:9051/health` with no port-forward running.
- [ ] **10.** Delete the whole cluster, recreate it, and bring the entire stack back with `kubectl apply -f capstone/k8s/`. (The old data won't return — say why.)

## Explain aloud (interview / CKA drill — answer in 60–90 seconds each)

- [ ] Walk `kubectl apply -f deployment.yaml` through the control plane, component by component — api-server, etcd, the three controllers, scheduler, kubelet. Every arrow goes through one door; name it.
- [ ] Deployment, ReplicaSet, Pod — why three layers, and what is each one's single job? What makes `rollout undo` instant (no rebuild, no re-pull)?
- [ ] "Self-healing" — mechanically, what happens when a pod dies? Why is it *replacement to spec*, not resurrection, and which controller does it?
- [ ] `ImagePullBackOff` vs `CrashLoopBackOff` — cause of each, and where the evidence lives (and which flag gets the *previous* container's logs)?
- [ ] What exactly stays constant when a Service fronts a set of pods, and which two components keep that promise as pods churn?
- [ ] `port-forward` vs `NodePort` vs `ClusterIP` vs `LoadBalancer` — when do you reach for each, and why is NodePort not how you expose things in production?
- [ ] A Service exists with a ClusterIP but connections hang; `kubectl get endpoints` is empty. What's wrong, and why was there no error anywhere?
- [ ] What is `capstone-api.default.svc.cluster.local`, who answers it, and how does it relate to `redis://redis:6379` from your compose file?
- [ ] ConfigMap vs Secret — the actual technical difference, and the three things that actually protect a Secret (since base64 doesn't)?
- [ ] Liveness vs readiness — different question, different action for each. Why must a liveness probe stay *shallow* and never depend on the database?
- [ ] `requests` vs `limits` — who uses each (scheduler vs runtime)? Why does exceeding a CPU limit throttle you but exceeding a memory limit kill you?
- [ ] Exit code `137`, reason `OOMKilled` — decode the number, and give your two diagnostic moves.
- [ ] PVC, PV, StorageClass — three objects for compose's one `volumes:` line. What is each, and why the indirection (think portability across clouds)?
- [ ] Deployment + PVC vs StatefulSet for a database — when must you switch, and why would scaling a Postgres Deployment to 2 replicas corrupt data?
- [ ] Why does redis get no PVC while postgres does, and how is that the identical decision you made in compose?
- [ ] Ingress controller vs Ingress resource — install-once vs write-many; what does the controller watch, and what does it regenerate?
- [ ] Trace `curl localhost:9051/visits` from keyboard to a redis increment, naming every hop (port map, controller, taint/toleration, Service, kube-proxy, endpoint, CoreDNS).
- [ ] A `503` from the Ingress vs a `404` from the Ingress — which side is the fault on for each, and your first command?
- [ ] Why did the port mappings and node labels have to be set at `kind create cluster` time and not added later? (Callback to a Section 1 rule.)
- [ ] What is a taint, what is a toleration, and why do your app pods land on the worker while the ingress controller lands on the control-plane?
- [ ] ingress-nginx is retired — why learn it anyway, and what's the successor?

## Gate

- [ ] `notes.md` filled in my own words (the five sections — not just the session digests)
- [ ] Everything committed (`kind-config.yaml`, all `capstone/k8s/*.yaml` manifests — **no Secret manifest, no keys**)
- [ ] The whole stack comes back from a deleted cluster with one `kubectl apply -f capstone/k8s/`

When all boxes are checked, say so — the next section (Helm) gets written against your notes, and it parameterizes the exact manifests you wrote here into a chart.
