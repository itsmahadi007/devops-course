# Lab 7 — Ingress: one front door, and the full packet path named

**Goal:** put a single, proper front door on your stack. Install the ingress-nginx controller onto the kind cluster (using the `ingress-ready` node and the `9051` door you pre-mapped back in Lab 1), write an **Ingress** resource that routes HTTP paths to the `capstone-api` Service, and reach the app at `http://localhost:9051/` — no port-forward, no ugly NodePort. Then trace a request hop by hop, from your Mac to a pod, naming every component you've met this section. This is the capstone of the capstone's networking.

## The mental map (read this first)

You now have three ways to reach a Service (Lab 3), and all three are unsatisfying for real traffic:

- **port-forward** — a babysat debug tunnel, one pod, dies on Ctrl-C.
- **NodePort** — a real port, but ugly (`:31742`) and one-per-service.
- **LoadBalancer** — asks a cloud for an external IP; meaningless on a laptop.

What you actually want for HTTP is one address (`myapp.com`), TLS terminated once, and *routing by hostname and URL path* to many backend Services — `/api` here, `/admin` there, `blog.myapp.com` somewhere else. That layer is **Ingress**, and it has two halves people constantly conflate:

```
   ┌─────────────────────────────────────────────────────────────┐
   │  1. the Ingress CONTROLLER  = a running reverse proxy         │
   │     (ingress-nginx: literally nginx in a pod, the same nginx  │
   │      you configured by hand in Section 3, now cluster-managed)│
   │                                                               │
   │  2. the Ingress RESOURCE    = a YAML object of routing RULES  │
   │     ("path / → Service capstone-api:80")                      │
   │     The controller WATCHES these and rewrites its own config. │
   └─────────────────────────────────────────────────────────────┘
```

**The controller does the work; the resource just tells it what to do.** Install one controller; write many Ingress resources. The controller watches the api-server for Ingress objects (the reconcile loop again) and continuously regenerates its nginx config to match — you *declare* routes, it *does* the proxying. This is exactly the nginx reverse-proxy you built by hand over SSH in Section 3, Lab 4 (`proxy_pass` to the app), except now a controller writes the nginx config for you from YAML, and re-writes it every time a route or a backend pod changes.

The full path this lab builds — memorize it, it's the "walk me through a request" interview answer:

```
  curl localhost:9051/health
        │
        │  Lab 1's extraPortMapping: host 9051 → control-plane container's port 80
        ▼
  control-plane node :80
        │  (the ingress-nginx controller pod listens here — it landed on THIS node
        │   because of the ingress-ready=true label + a toleration for the taint)
        ▼
  ingress-nginx controller (nginx)
        │  reads its rules (compiled from your Ingress resource): "/ → capstone-api:80"
        ▼
  Service capstone-api (ClusterIP)         ← Lab 3
        │  kube-proxy iptables DNAT to a live endpoint    ← Lab 3 endpoints
        ▼
  a capstone pod :8000                     ← Lab 2
        │
        ▼
  uvicorn → {"status":"ok"}
```

Every hop is something you built or met this section. Ingress is the piece that ties them into one address.

## Honest note before you install: ingress-nginx is retired

The README told you the strategic version; here's the two-sentence interview version, because you'll be asked. **The ingress-nginx project was retired and its repo archived in March 2026** (`controller-v1.15.1` is the final release — no more bug fixes or security patches), with **Gateway API** anointed as the successor. We learn it anyway on purpose: it still runs in the overwhelming majority of existing production clusters (someone has to operate and *migrate* those — that's literally a job), the CKA and interviews still test it, and every Ingress concept here maps 1:1 onto Gateway API's `HTTPRoute`. Knowing *why* it was retired (a maintainer/security-model problem, not a "the idea was wrong" problem) is itself something to say in an interview. When you build real clusters after this course, reach for Gateway API or a maintained controller (Traefik, HAProxy, cloud-native ones) — but the muscle memory you build now transfers.

## Steps

### 1. Install the ingress-nginx controller (kind flavor)

kind publishes an ingress-nginx manifest pre-patched for exactly this setup — it tolerates the control-plane taint and uses `hostPort` so it binds the node's port 80 (which Lab 1 mapped to your `9051`). Apply the pinned version:

```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.15.1/deploy/static/provider/kind/deploy.yaml
```

> Version note (verify latest): `controller-v1.15.1` is the final ingress-nginx release (repo archived March 2026). If the raw URL 404s because the archived repo's raw hosting ever changes, the same file is mirrored in the release assets on the GitHub releases page for that tag.

You'll see a burst of objects created — a `Namespace ingress-nginx`, a Deployment (the controller), a Service, RBAC (ServiceAccount/Role/ClusterRole), and crucially an **admission webhook** (`ValidatingWebhookConfiguration`) that will *validate your Ingress resources before they're accepted*. That webhook matters in the next step.

Wait for the controller to be ready — this is the one install that takes a minute:

```bash
kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=120s
```

```
pod/ingress-nginx-controller-<hash> condition met
```

Confirm where it landed:

```bash
kubectl get pods -n ingress-nginx -o wide
```

```
NAME                             READY   STATUS    ...   NODE
ingress-nginx-controller-<hash>  1/1     Running   ...   capstone-control-plane
```

It's on **`capstone-control-plane`** — the node your app pods were *repelled* from (Lab 1's taint). Two reasons it can be here: it carries a **toleration** for the control-plane taint (so the scheduler allows it), and it targets the node with `ingress-ready=true` (the label you set in Lab 1's kind config). This is the payoff of those two lines you wrote before you knew why: the controller lands on the exact node whose port 80 is mapped to `9051`.

#### If pods hang in `admission` / your Ingress apply is rejected later

The admission webhook needs its own pod ready before it can validate Ingress resources. If you `apply` an Ingress in step 3 and get `failed calling webhook ... connection refused`, the controller isn't ready yet — wait for the `kubectl wait` above to pass, then re-apply. It's not your YAML; it's a race with the webhook coming up.

### 2. Write the Ingress resource

Create `capstone/k8s/ingress.yaml`:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: capstone
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /   # send the matched path through unchanged
spec:
  ingressClassName: nginx            # which controller handles this — "nginx" = ingress-nginx
  rules:
    - http:                          # no host: → match any hostname (fine for localhost testing)
        paths:
          - path: /
            pathType: Prefix         # "/" as a PREFIX matches everything under it
            backend:
              service:
                name: capstone-api   # route to the Service from Lab 3…
                port:
                  number: 80         # …on its port 80 (the Service port, not the pod's 8000)
```

#### Read it like a story

- **`ingressClassName: nginx`** — a cluster can run several ingress controllers (nginx for some apps, another for others). This line says "the nginx controller owns this resource." Without it, no controller may claim the Ingress and nothing routes — a common "my Ingress does nothing" cause.
- **`rules` → `paths` → `backend.service`** — the routing table. This one rule says "prefix `/` goes to Service `capstone-api:80`." You'd add more entries for more routes: `path: /admin` → a different Service, or a second rule with `host: blog.example.com`. This is the nginx `location` blocks from Section 3, expressed as data instead of a config file.
- **`backend` points at a Service, never at pods** — Ingress routes to the *Service*, and the Service (via its endpoints + kube-proxy) load-balances to live pods. Every layer you built stacks: Ingress → Service → Endpoints → Pod. Ingress does not know or care how many pods exist.
- **`pathType: Prefix`** — `/` as a prefix matches every path. The alternatives: `Exact` (only that exact path) and `ImplementationSpecific`. Prefix is what you want for "route the whole app."
- **The `rewrite-target` annotation** — annotations are how you reach nginx features the generic Ingress schema doesn't cover (rewrites, timeouts, body size, auth). Here it's a no-op passthrough; it's in the file so you recognize the pattern — controller-specific behavior lives in annotations.

```bash
kubectl apply -f capstone/k8s/ingress.yaml
kubectl get ingress capstone
```

```
NAME       CLASS   HOSTS   ADDRESS     PORTS   AGE
capstone   nginx   *       localhost   80      15s
```

`ADDRESS: localhost` (may take a few seconds to populate) means the controller has accepted the resource and is advertising where it's reachable.

### 3. Walk through the front door

No port-forward, no NodePort — just the mapped host port from Lab 1:

```bash
curl -s localhost:9051/health          # {"status":"ok"}
curl -s localhost:9051/visits          # {"visits":N} — through Ingress → Service → pod → redis
curl -s localhost:9051/ask?q=hello      # the canned placeholder answer
```

Every one of those requests took the full path from the mental map: your Mac's `9051` → (Lab 1 port map) → control-plane node `:80` → the ingress-nginx pod → it matched `/` → forwarded to `capstone-api:80` (the Service) → kube-proxy DNAT'd to a live pod endpoint → uvicorn answered. **One address now fronts the whole stack**, and if you scaled the api to 5 replicas the Ingress wouldn't change one character — it routes to the Service, and the Service already load-balances. That decoupling is the entire point.

Look at the controller's own logs to *see* your request arrive at nginx:

```bash
kubectl logs -n ingress-nginx deploy/ingress-nginx-controller | tail -3
```

You'll see access-log lines — the same nginx access log you read by hand in Section 3, Lab 4, now emitted by the controller pod. `GET /health HTTP/1.1" 200` proves the proxy is doing exactly what you configured it to, from YAML.

#### The two failures you'll actually hit

- **`503 Service Temporarily Unavailable`** — nginx got your request but has **no healthy backend**. Root cause is downstream: the `capstone-api` Service has no endpoints (pods not ready, or the Lab 3 selector bug). Diagnose *away* from Ingress: `kubectl get endpoints capstone-api` — empty means fix the Service/pods, not the Ingress. Ingress is working fine; it has nothing to route to.
- **`404 Not Found`** (from nginx, not FastAPI) — no rule matched. Usually `ingressClassName` missing/wrong (no controller claimed the resource), a `host:` set that doesn't match how you're calling it, or a `path`/`pathType` mismatch. `kubectl describe ingress capstone` shows the rules the controller actually parsed. Tell the two 404s apart by the body: FastAPI's JSON `{"detail":"Not Found"}` = your app was reached and *it* said no (routing worked); nginx's HTML `404` = the request never left the proxy (routing failed).

### 4. (Optional, marked) Where TLS and a real hostname would slot in

$0 and local, so this stays a *reading*, not a step. On a real box you'd add a `tls:` block to the Ingress referencing a Secret that holds a certificate + key, and the controller would **terminate TLS** at the edge (decrypt once, forward plain HTTP to the Service) — the exact TLS-termination role you gave nginx by hand in Section 3, Lab 5, now driven by an Ingress field. In production, **cert-manager** watches Ingress resources and auto-obtains/renews Let's Encrypt certificates into those Secrets, so `https://` Just Works and never expires. You have all the pieces conceptually (Section 3's chain-of-trust + this lab's Ingress); wiring real TLS is a same-day exercise on a real domain, out of scope for the laptop.

## Verify

- `kubectl get pods -n ingress-nginx` shows the controller `1/1 Running` on the control-plane node.
- `kubectl get ingress capstone` shows class `nginx` and an address; `curl localhost:9051/health` and `/visits` both work with no port-forward running.
- You can trace a `curl localhost:9051/visits` through every hop, naming the component at each one.
- Answer aloud:

- Ingress controller vs Ingress resource — what's the difference, and which one do you install once vs write many times?

  <details><summary>Answer (read after attempting aloud)</summary>

  The **controller** is a running reverse proxy (ingress-nginx = nginx in a pod) — you install *one* per cluster. The **resource** is a YAML object of routing rules ("path `/` → Service X") — you write *many*, one per app/route. The controller watches the api-server for resources and continuously regenerates its own proxy config to match. Declaring a route (the resource) is separate from doing the proxying (the controller) — same declare-vs-do split as every Kubernetes object.

  </details>

- Walk a `curl localhost:9051/visits` from your keyboard to a Redis increment, naming each component.

  <details><summary>Answer (read after attempting aloud)</summary>

  Mac `:9051` → Lab 1's kind extraPortMapping → control-plane container's `:80` → the **ingress-nginx controller** pod (which is there because of a toleration for the control-plane taint + the `ingress-ready` label) → it matches the `/` prefix rule from the **Ingress resource** → forwards to the **`capstone-api` Service** on port 80 → **kube-proxy** iptables DNATs to a live **endpoint** (pod IP) → **uvicorn** in a capstone pod → the app reads `REDIS_URL`, resolves `redis` via **CoreDNS** → increments the counter in the **redis** pod → response returns back up the same chain.

  </details>

- You get a `503` from nginx hitting `/health` through the Ingress. Where is the fault, and what's your first command?

  <details><summary>Answer (read after attempting aloud)</summary>

  A 503 means the controller received the request but has **no healthy backend** to forward to — the fault is *downstream* of Ingress, in the Service/pods. First command: `kubectl get endpoints capstone-api`. Empty endpoints = the Service's selector matches no ready pods (pods down, not ready per readiness probe, or a label mismatch). Fix the Service/pods; the Ingress itself is fine. (Contrast a 404 from nginx, which means no *rule* matched — an Ingress-side problem.)

  </details>

- ingress-nginx is retired. Why learn it, and what replaces it?

  <details><summary>Answer (read after attempting aloud)</summary>

  Retired and archived March 2026 (final release controller-v1.15.1), with **Gateway API** as the successor. Worth learning because it still runs in most existing production clusters (operating and migrating them is real work), the CKA and interviews still test it, and every concept maps 1:1 onto Gateway API's `HTTPRoute`. The retirement was about the project's maintenance/security model, not a flaw in the Ingress idea — knowing that distinction is itself interview currency. For new clusters, reach for Gateway API or a maintained controller (Traefik, HAProxy, cloud-native).

  </details>

## Clean up

The Ingress and controller can stay — they're the finished shape of the section, and Section 5's Helm chart will template this same Ingress resource. To fully reset your Mac:

```bash
kind delete cluster --name capstone      # removes the whole cluster: nodes, controller, PVs, everything
```

Rebuild anytime with Lab 1 step 3, then `kubectl apply -f capstone/k8s/` for the app stack, then re-run this lab's step 1 for the controller. The manifests are the truth; the cluster is cattle.

Commit `capstone/k8s/ingress.yaml`. Update the capstone evolution log: "Section 4 complete: full stack on Kubernetes behind one Ingress front door on 9051." **Section 4 is done** — the entire compose stack now runs on a real cluster, reconciled continuously, reachable at one address. Section 5 (Helm) turns every manifest in `capstone/k8s/` into a parameterized chart.
