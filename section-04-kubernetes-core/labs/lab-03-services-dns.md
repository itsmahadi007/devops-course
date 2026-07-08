# Lab 3 — Services & DNS: a stable name in front of disposable pods

**Goal:** give your 2 capstone pods one stable address. You proved in Lab 2 that pods are cattle — killed pod, new IP, no warning. Nothing can hardcode a pod IP. A **Service** is the fix: a permanent name and a permanent virtual IP that always points at whichever pods currently wear the right label. You'll reach the app three different ways (port-forward, ClusterIP from inside, NodePort from your Mac), watch the cluster's phonebook resolve the Service name, and watch the endpoint list heal itself when you murder a pod.

## The mental map (read this first)

The problem, stated plainly: in Lab 2 you killed pod `...-x4kq2` (IP `10.244.1.2`) and the ReplicaSet replaced it with `...-tr8fn` (a *different* IP). Pod IPs are born and die with pods. So how does anything ever talk to "the capstone" if its address keeps changing? Same question you already answered once in compose — where you never wrote an IP, you wrote `redis://redis:6379`. Kubernetes' answer is the same idea with sturdier machinery: **a Service.**

A Service is two things fused together:

1. **A stable virtual IP** (the "ClusterIP") that never changes for the life of the Service, and a **DNS name** (`capstone-api`) that resolves to it. This is what clients talk to.
2. **A label selector** that continuously discovers which pods are behind that IP right now. Same `app: capstone-api` sticky-note match the Deployment uses — the Service doesn't care *which* pods, only that they wear the label.

```
        client says "capstone-api"
                 │
                 ▼
         CoreDNS (the phonebook)  ──▶  10.96.x.y   (the ClusterIP — NEVER changes)
                 │
                 ▼
     ┌─── Service capstone-api ───┐
     │  selector: app=capstone-api │   ← continuously re-evaluated
     │  Endpoints:                 │
     │    10.244.1.2:8000  ────────┼──▶ Pod A
     │    10.244.1.3:8000  ────────┼──▶ Pod B
     └─────────────────────────────┘
                 ▲
       kube-proxy writes iptables rules on every node so that
       "packet to 10.96.x.y:80" gets load-balanced to a live pod IP
```

The stable IP is a *fiction maintained by iptables* — there's no process listening on `10.96.x.y`. `kube-proxy` (the plumber from Lab 1, one per node) watches the Service and its Endpoints and rewrites each node's iptables rules — the exact same iptables you read by hand in Section 3, Lab 6 — so a packet aimed at the ClusterIP gets rewritten (DNAT'd) to one of the current pod IPs. Pods come and go; kube-proxy keeps the rules current; the ClipterIP and name stay frozen.

**Three ways to reach a Service — this whole lab is a tour of the three:**

| Type | Reachable from | Door | This lab uses it for |
|---|---|---|---|
| **ClusterIP** (default) | *inside* the cluster only | none — a virtual IP | pod-to-pod (how the api will reach redis in Lab 6) |
| **port-forward** | your Mac, temporarily | a tunnel through the api-server | day-to-day debugging on `9050` |
| **NodePort** | your Mac, via a node's host port | a real port on every node | the `9052` door you pre-mapped in Lab 1 |

There's a fourth, `LoadBalancer`, that asks a cloud for a real external IP — meaningless on a laptop, and the reason Ingress (Lab 7) exists for local/bare-metal. We'll name it and move on.

## Steps

### 1. Write the Service manifest

Create `capstone/k8s/service.yaml`:

```yaml
apiVersion: v1                 # core API group — Services predate the apps/v1 group Deployments live in
kind: Service
metadata:
  name: capstone-api           # THIS becomes the DNS name inside the cluster
spec:
  selector:
    app: capstone-api          # route to every pod wearing this label — same sticky note as the Deployment
  ports:
    - port: 80                 # the port the SERVICE listens on (what clients dial)
      targetPort: 8000         # the port on the POD to forward to (your uvicorn)
      protocol: TCP
```

#### Read it like a story

- **No `type:` line** → defaults to `ClusterIP`. That's the right default: most Services are internal plumbing, invisible to the outside world (just like redis/db had no `ports:` in compose).
- **`selector: app: capstone-api`** — the Service finds its pods the same way the Deployment does, by label match. Notice what's *decoupled*: the Service has no idea a Deployment exists. It matches labels. If you deleted the Deployment and hand-created pods with that label, the Service would route to them too. Loose coupling by matching — Kubernetes' whole personality.
- **`port` vs `targetPort`** — the one confusing pair. `port: 80` is the Service's own front-door port (clients say `capstone-api:80`, or just `capstone-api` since 80 is HTTP default). `targetPort: 8000` is where it forwards *on the pod* — your uvicorn still binds 8000 (Lab 2's `containerPort`). The Service is a remapping layer, exactly like the host:container split in `-p 9000:8000`, but living inside the cluster.

### 2. Apply it and read the two objects it creates

```bash
kubectl apply -f capstone/k8s/service.yaml
kubectl get svc capstone-api
```

```
NAME           TYPE        CLUSTER-IP     EXTERNAL-IP   PORT(S)   AGE
capstone-api   ClusterIP   10.96.148.30   <none>        80/TCP    5s
```

That `CLUSTER-IP` (`10.96.x.y`, from the *service* network — a different range than the `10.244.x.x` pod network) is the stable fiction. `EXTERNAL-IP: <none>` confirms it: nothing outside the cluster can reach this. Now the object that does the real work:

```bash
kubectl get endpoints capstone-api      # or: kubectl get endpointslices
```

```
NAME           ENDPOINTS                         AGE
capstone-api   10.244.1.2:8000,10.244.1.3:8000   5s
```

**This is the Service doing its job, made visible.** The Endpoints object is the live list of pod-IP:port pairs currently matching the selector — auto-maintained by the endpoints controller (another reconcile loop in the controller-manager). Compare it to `kubectl get pods -o wide`: those are your two pods' exact IPs. The Service watches labels; the Endpoints list is the answer; kube-proxy turns that answer into iptables rules. Three layers, same pattern as Deployment→ReplicaSet→Pod.

#### If ENDPOINTS shows `<none>` — the #1 Service bug in the field

An empty endpoints list means **the selector matched zero pods**. Almost always a label typo: `spec.selector` in the Service doesn't equal the `labels` on the pods. The Service still gets created (it's syntactically fine), the ClusterIP still exists — but connections to it hang or refuse, because there's nothing behind it. There's no error anywhere; the Service and the Deployment don't validate against each other (they're decoupled). Diagnosis reflex: **a Service that won't route → `kubectl get endpoints <svc>` first.** Empty = selector/label mismatch. Compare `kubectl get svc <svc> -o wide` (shows the SELECTOR) against `kubectl get pods --show-labels`.

### 3. Reach it with port-forward — the debugging workhorse (door 9050)

Your Mac can't reach a ClusterIP (`10.96.x.y` lives inside the cluster). `port-forward` opens a temporary tunnel *through the api-server* — no published port needed, which is exactly why Lab 1 didn't map a host door for 9050:

```bash
kubectl port-forward svc/capstone-api 9050:80
```

```
Forwarding from 127.0.0.1:9050 -> 8000
Forwarding from [::1]:9050 -> 8000
```

It holds the terminal open (it's a live tunnel — Ctrl-C closes it). Leave it running; in a **second terminal**:

```bash
curl -s localhost:9050/health          # {"status":"ok"}
curl -s localhost:9050/ask?q=hello      # the canned Section-10 placeholder answer
```

The path of that packet: your Mac `:9050` → the api-server (over its 6443 door) → the api-server opens a stream to the pod's kubelet → into the pod's `:8000`. It's a *debug* tunnel, not a real network route — single connection, dies when you Ctrl-C, and it talks to **one** pod (port-forwarding a Service picks one backing pod; it is not load-balanced). Perfect for "let me poke this thing from my laptop", wrong for anything permanent. That's what NodePort and Ingress are for.

Ctrl-C the port-forward when you've seen the `curl`s work.

### 4. Prove the cluster phonebook — CoreDNS resolving the Service name

This is the cluster-scale version of your Section 1, Lab 4 `socket.gethostbyname('redis')` moment. Run a throwaway pod and ask it to resolve the Service name:

```bash
kubectl run dnstest --image=busybox:1.36 --rm -it --restart=Never -- nslookup capstone-api
```

`--rm -it --restart=Never` = "run one interactive pod, delete it when the command exits" — the kubectl equivalent of `docker run --rm`. Expected:

```
Server:    10.96.0.10           ← CoreDNS's own ClusterIP (the phonebook's address)
Address:   10.96.0.10:53

Name:      capstone-api.default.svc.cluster.local
Address:   10.96.148.30         ← your Service's ClusterIP — the name resolved!
```

Two things to burn in:

- **`10.96.0.10` is CoreDNS** — the cluster's DNS server, itself a Service (you saw the `coredns` pods in Lab 1's `get pods -A`). Every pod is born configured to ask it. It is the `127.0.0.11` from compose, promoted to a real cluster service.
- **The full name is `capstone-api.default.svc.cluster.local`** — `<service>.<namespace>.svc.cluster.local`. Inside the same namespace you can say just `capstone-api`; across namespaces you'd need `capstone-api.default`. This is *exactly* the name the api will use to find redis in Lab 6: `redis://redis:6379` works because `redis` is a Service in the same namespace. Your compose DNS habit transfers with the namespace suffix bolted on.

### 5. Watch the Endpoints heal — the Service survives what pods can't

The payoff of the whole design. Watch endpoints in one terminal:

```bash
kubectl get endpoints capstone-api -w
```

In a second terminal, kill a pod (use a real name from `kubectl get pods`):

```bash
kubectl delete pod <one-capstone-api-pod>
```

The watch terminal shows the endpoints list *change* — the dead pod's IP drops out, and seconds later the replacement pod's fresh IP appears:

```
capstone-api   10.244.1.2:8000,10.244.1.3:8000
capstone-api   10.244.1.3:8000                    ← killed pod's IP removed instantly
capstone-api   10.244.1.3:8000,10.244.1.5:8000    ← replacement's NEW IP joins
```

But run `kubectl get svc capstone-api` again — the **ClusterIP is unchanged.** That's the entire point: pods churned, their IPs churned, the endpoints list churned to match — and the address clients use never moved. Compose gave you a stable *name*; Kubernetes gives you a stable name *and* a stable IP *and* automatic load-balancing across whatever's alive, healed continuously by a controller. Ctrl-C the watch.

### 6. NodePort — a real door on your Mac (9052)

Sometimes you want to hit a Service from outside without a babysat tunnel. `NodePort` opens the *same* high port (30000–32767 range) on *every* node, and the node forwards it to the Service. In Lab 1 you pre-mapped host `9052` → node port `30080`, so a NodePort on 30080 becomes reachable at `localhost:9052`. Add a second, small manifest — `capstone/k8s/service-nodeport.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: capstone-api-nodeport
spec:
  type: NodePort               # open a port on every node
  selector:
    app: capstone-api          # same pods as the ClusterIP service
  ports:
    - port: 80
      targetPort: 8000
      nodePort: 30080          # the node-side port — MUST match Lab 1's extraPortMapping (30080→9052)
```

```bash
kubectl apply -f capstone/k8s/service-nodeport.yaml
curl -s localhost:9052/health          # {"status":"ok"} — from your Mac, no port-forward running
```

Trace it: your Mac `:9052` → (Lab 1's kind port map) → control-plane node's `:30080` → kube-proxy's NodePort iptables rule → a capstone pod's `:8000`. A real, persistent route this time — no tunnel process, survives your terminal closing.

Why is NodePort still not how you expose things in production? Two reasons you can say in an interview: the port range is ugly and high (nobody wants `myapp.com:31742`), and you'd need one NodePort per service, hand-managed. The grown-up answer — one front door, name/path-based routing, TLS — is **Ingress**, Lab 7. NodePort is the honest primitive underneath a lot of it.

## Verify

- `kubectl get svc capstone-api` shows a stable ClusterIP; `kubectl get endpoints capstone-api` lists both pod IPs.
- `curl localhost:9050/health` works while a `port-forward` runs; `curl localhost:9052/health` works via the NodePort with no tunnel.
- You watched the endpoints list change when a pod died while the ClusterIP stayed frozen.
- Answer aloud:

- A pod's IP changes every time it's replaced. What exactly stays constant when you put a Service in front, and which component keeps the promise alive?

  <details><summary>Answer (read after attempting aloud)</summary>

  The Service's **ClusterIP and its DNS name** stay constant for the Service's whole life. Behind them, the **endpoints controller** continuously rebuilds the list of matching pod IPs (by label selector), and **kube-proxy** rewrites each node's iptables rules so a packet to the ClusterIP gets DNAT'd to one of the currently-live pod IPs. Pods and their IPs churn freely underneath; the address clients use never moves. It's compose's stable *name* plus a stable *IP* plus load-balancing, healed by a loop.

  </details>

- `port-forward`, `NodePort`, `ClusterIP` — when do you reach for each?

  <details><summary>Answer (read after attempting aloud)</summary>

  ClusterIP = internal-only, pod-to-pod (the api reaching redis) — the default, invisible to the host. port-forward = a temporary, single-pod debug tunnel through the api-server from your laptop, needs no published port, dies on Ctrl-C. NodePort = a real persistent port opened on every node, reachable from outside, but ugly high ports and one-per-service — the primitive Ingress sits on top of. LoadBalancer (the fourth) asks a cloud for a real external IP; meaningless on a laptop.

  </details>

- Your Service exists, has a ClusterIP, but connections to it hang and `kubectl get endpoints` shows `<none>`. What's wrong and why was there no error?

  <details><summary>Answer (read after attempting aloud)</summary>

  The `spec.selector` on the Service matches zero pods — a label mismatch between the Service's selector and the pods' actual labels. There's no error because Services and pods are **decoupled**: nothing validates a selector against existing pods (the pods might not exist yet — that's legal). The Service is syntactically valid, so it's created with an empty endpoints list. Reflex: a Service that won't route → check `kubectl get endpoints` first; empty means fix the selector/label match.

  </details>

- What is `capstone-api.default.svc.cluster.local`, who answers it, and how does it relate to the `redis://redis:6379` you wrote in compose?

  <details><summary>Answer (read after attempting aloud)</summary>

  It's the fully-qualified DNS name of the `capstone-api` Service in the `default` namespace (`<service>.<namespace>.svc.cluster.local`). **CoreDNS** answers it — the cluster's DNS server, running as a Service at `10.96.0.10`, that every pod is configured to query. It's the exact same idea as compose's built-in DNS at `127.0.0.11` resolving `redis` — just cluster-wide, namespaced, and backed by a real controller. Inside one namespace the short name (`capstone-api`) is enough; that's why `redis://redis:6379` will Just Work in Lab 6.

  </details>

## Clean up

Keep `capstone/k8s/service.yaml` applied — the api needs a stable name for the rest of the section. The NodePort was a demo; you can leave it or drop it:

```bash
kubectl delete -f capstone/k8s/service-nodeport.yaml   # optional — removes only the extra NodePort service
kubectl get svc                                         # capstone-api (ClusterIP) should remain
```

Commit `capstone/k8s/service.yaml` (and `service-nodeport.yaml` if you keep it). Update the capstone evolution log: "Section 4: capstone reachable by stable Service name + ClusterIP."
