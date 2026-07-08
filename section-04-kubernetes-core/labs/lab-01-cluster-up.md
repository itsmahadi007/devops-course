# Lab 1 — Cluster up + the grand tour

**Goal:** create a real two-node Kubernetes cluster on your Mac with kind, then walk through every control-plane piece from the README's diagram *running as an actual process you can see*. You leave with a working cluster (it stays up for the rest of the section) and the three kubectl verbs you'll use more than all others combined: `get`, `describe`, `explain`.

## The mental map (read this first)

kind's trick is shameless and brilliant: **a Kubernetes "node" is supposed to be a machine — so kind uses a Docker container as the machine.** Each node-container runs systemd, a kubelet, and containerd *inside* it; your pods become containers-inside-the-node-container. Docker Desktop's VM is the "datacenter", each kind node is a "server" in it:

```
 your Mac
 └── Docker Desktop VM
      ├── capstone-control-plane   ← a container PRETENDING to be a machine
      │     ├── kubelet, containerd (inside)
      │     └── the control-plane pods: api-server, etcd, scheduler, …
      ├── capstone-worker          ← another "machine"
      │     ├── kubelet, containerd (inside)
      │     └── (your app pods will mostly land here)
      └── (your compose stack, vps-lab, … — unrelated, untouched)
```

Two things must be decided **at cluster creation** and can't be changed later — which is why we create the cluster from a config file instead of a bare `kind create cluster`:

1. **Host port doors.** Remember from Section 1: a container's published ports are creation-time config. Same here — the node-containers publish host ports *now* or never. We pre-map two doors for later labs: host `9051` → node port 80 (Lab 7's ingress) and host `9052` → node port 30080 (Lab 3's NodePort demo).
2. **A node label** (`ingress-ready=true`) that Lab 7's ingress controller uses to pick which node to land on.

The 9050 door needs no mapping — `kubectl port-forward` tunnels through the api-server, no published port required. You'll feel that difference in Lab 3.

## Steps

### 1. Install the tools

```bash
brew install kind kubectl
kind version        # kind v0.32.0 …
kubectl version --client   # Client Version: v1.36.x
```

If brew says kubectl is already installed — fine, you have it from earlier work; just confirm the version is 1.36-ish. Two tools, two jobs: **kind** creates/destroys clusters; **kubectl** talks to any cluster (this one, and every cluster for the rest of your career — it's the one binary that follows you to every job).

### 2. Write the cluster config

Create `section-04-kubernetes-core/kind-config.yaml`:

```yaml
kind: Cluster                        # yes, the API field is literally named "kind" — awkward pun, ignore it
apiVersion: kind.x-k8s.io/v1alpha4
name: capstone                       # → context "kind-capstone", containers "capstone-control-plane" etc.
nodes:
  - role: control-plane
    kubeadmConfigPatches:            # inject settings into the node's bootstrap
      - |
        kind: InitConfiguration
        nodeRegistration:
          kubeletExtraArgs:
            node-labels: "ingress-ready=true"   # Lab 7's ingress controller looks for this label
    extraPortMappings:               # creation-time doors, host side in OUR 9050 block
      - containerPort: 80            # where the ingress controller will listen (Lab 7)
        hostPort: 9051
        protocol: TCP
      - containerPort: 30080         # a NodePort we'll open on purpose (Lab 3)
        hostPort: 9052
        protocol: TCP
  - role: worker                     # a second "machine" — so scheduling is real, not theater
```

Why two nodes? A single-node cluster hides half of Kubernetes: with a worker present, the control-plane node keeps its "don't schedule apps on me" marking (a **taint** — you'll see it in step 5), so your app pods genuinely get *placed* on another machine, and pod IPs vs node IPs stop being an abstraction.

### 3. Create the cluster

```bash
cd section-04-kubernetes-core
kind create cluster --config kind-config.yaml
```

First run downloads the node image (~900MB warehouse-side — it contains an entire Kubernetes, so this is honest) — give it a few minutes. Expected output, line by line:

```
Creating cluster "capstone" ...
 ✓ Ensuring node image (kindest/node:v1.36.1) 🖼      ← pulls the "machine" image (once, then cached)
 ✓ Preparing nodes 📦 📦                              ← two boxes = your two containers starting
 ✓ Writing configuration 📜                           ← kubeadm config, incl. your patches
 ✓ Starting control-plane 🕹️                          ← api-server, etcd, scheduler, controllers boot
 ✓ Installing CNI 🔌                                  ← pod networking (kindnet)
 ✓ Installing StorageClass 💾                         ← dynamic volumes — Lab 6 uses this
 ✓ Joining worker nodes 🚜                            ← worker registers with the control plane
Set kubectl context to "kind-capstone"
```

That last line matters: kind wrote credentials into `~/.kube/config` and pointed kubectl at this cluster. Check it:

```bash
kubectl config current-context     # kind-capstone
```

#### kubeconfig = your SSH config for clusters

`~/.kube/config` holds a list of clusters, users (credentials), and **contexts** (cluster+user pairs). `kubectl config use-context <name>` switches which cluster every subsequent command hits — at a real job you'll have staging/prod contexts side by side, and *checking your current context before typing `delete`* is a survival habit. kind manages these entries for you; `kind delete cluster --name capstone` removes them again.

**If create fails with `Cannot connect to the Docker daemon`** — Docker Desktop isn't running. Start it, re-run. **If it fails on the port mappings** (`address already in use`) — something on your Mac holds 9051/9052; `lsof -ti :9051` to find it. The 9050 block is this section's reserved lane, so this shouldn't happen — but now you know the diagnostic.

### 4. See your "machines"

```bash
docker ps --filter name=capstone-
```

```
CONTAINER ID  IMAGE                 …  PORTS                                              NAMES
1a2b3c4d5e6f  kindest/node:v1.36.1  …  0.0.0.0:9051->80/tcp, 0.0.0.0:9052->30080/tcp,     capstone-control-plane
                                       127.0.0.1:54321->6443/tcp
7g8h9i0j1k2l  kindest/node:v1.36.1  …                                                     capstone-worker
```

Read the control-plane's PORTS column — it's your whole future:

- `9051->80` and `9052->30080` — the doors you pre-mapped, waiting for Labs 7 and 3.
- `127.0.0.1:54321->6443` (random port) — **6443 is the api-server**. Every `kubectl` command you'll ever run against this cluster enters through this one published port. Loopback-only: your cluster's brain is not on your network.
- The worker publishes **nothing**. Traffic reaches it only from inside the cluster — same "no `ports:` = no door" pattern as redis/db in your compose file.

Now the same machines, as Kubernetes sees them:

```bash
kubectl get nodes
```

```
NAME                     STATUS   ROLES           AGE   VERSION
capstone-control-plane   Ready    control-plane   2m    v1.36.1
capstone-worker          Ready    <none>          90s   v1.36.1
```

`Ready` means each node's kubelet is reporting in healthily. If the worker says `NotReady` in the first ~30 seconds, that's pod networking still coming up — re-run, it flips to Ready.

### 5. The grand tour — the diagram, running

Everything in the README's control-plane diagram is itself just… pods. Kubernetes runs on Kubernetes:

```bash
kubectl get pods -A
```

`-A` = all **namespaces**. A namespace is a folder for objects — `kube-system` holds the cluster's own machinery, `default` is where your stuff goes when you don't say otherwise (all labs use `default`, so you rarely type `-n`). Expected, roughly:

```
NAMESPACE            NAME                                             READY   STATUS    RESTARTS   AGE
kube-system          coredns-<hash>-<hash>                            1/1     Running   0          3m   ← ×2: the phonebook (Lab 3)
kube-system          etcd-capstone-control-plane                      1/1     Running   0          3m   ← the notebook
kube-system          kindnet-<hash>                                   1/1     Running   0          3m   ← ×2: pod networking (one per node)
kube-system          kube-apiserver-capstone-control-plane            1/1     Running   0          3m   ← the only door
kube-system          kube-controller-manager-capstone-control-plane   1/1     Running   0          3m   ← the reconcile loops
kube-system          kube-proxy-<hash>                                1/1     Running   0          3m   ← ×2: the iptables plumber (one per node)
kube-system          kube-scheduler-capstone-control-plane            1/1     Running   0          3m   ← the dispatcher
local-path-storage   local-path-provisioner-<hash>                    1/1     Running   0          3m   ← makes volumes on demand (Lab 6)
```

Match each line to its diagram box before moving on. Notice the pattern in the names: the per-node agents (`kindnet`, `kube-proxy`) appear **twice** — once per node — while the brain pieces live only on the control-plane node.

### 6. Learn `describe` — the incident command

`get` lists; **`describe` explains one thing in full** — spec, status, and crucially **Events** at the bottom, which is where Kubernetes writes *why* things happened. It will be your first move in every debugging scenario for the rest of this course (and the CKA, and your career):

```bash
kubectl describe node capstone-control-plane
```

A wall of text — scan for three things:

- **Taints:** `node-role.kubernetes.io/control-plane:NoSchedule` — the "don't put apps on me" marking. This is why your pods will land on the worker. (A taint repels pods; a *toleration* on a pod lets it in anyway — Lab 7's ingress controller carries one.)
- **Labels:** find your `ingress-ready=true` — the config patch worked.
- **Allocatable:** how much CPU/memory this node offers pods — Lab 5's requests/limits get budgeted against this.

### 7. Learn `explain` — the offline manual

You will never memorize YAML schemas. You don't have to:

```bash
kubectl explain deployment.spec.replicas
```

```
FIELD: replicas <integer>

DESCRIPTION:
    Number of desired pods. This is a pointer to distinguish between explicit
    zero and not specified. Defaults to 1.
```

`kubectl explain` walks any field path of any object (`kubectl explain pod.spec.containers.livenessProbe` — try it). It reads the API schema from your own cluster, so it's never out of date and works without internet — which is exactly why it's the CKA's legal cheat sheet. Pair it with `kubectl api-resources` (the list of every object type your cluster knows, with short names — `po`, `deploy`, `svc`).

## Verify

- `kubectl get nodes` shows two `Ready` nodes; `docker ps` shows them as containers with `9051`/`9052` mapped on the control-plane.
- `kubectl get pods -A` shows all system pods `Running`, and you can say what each one is in the diagram.
- Answer aloud:

- Where does a `kubectl get pods` command physically go, and what answers it?

  <details><summary>Answer (read after attempting aloud)</summary>

  Through `127.0.0.1:<random>` on your Mac → the control-plane container's port 6443 → the **api-server**, the cluster's only door. It authenticates you (kubeconfig credentials), reads the current state out of **etcd**, and returns it. kubectl never talks to nodes, etcd, or containers directly — nothing does. One door = one place for auth, RBAC, and audit.

  </details>

- Your two "nodes" — what are they actually, and what runs *inside* each one?

  <details><summary>Answer (read after attempting aloud)</summary>

  Docker containers on your Mac, from the `kindest/node` image. Inside each: systemd, a **kubelet** (the node agent that watches the api-server for pods assigned to its node), and **containerd** (the runtime that actually runs pod containers — so your pods are containers *inside* the node container). On a real cluster each node is a VM or physical machine with exactly the same three residents; kind just substitutes the machine.

  </details>

- Why did the port mappings have to happen at `kind create cluster` time and not later?

  <details><summary>Answer (read after attempting aloud)</summary>

  Section 1 lesson resurfacing: published ports are **container-creation-time** config. The kind nodes are containers, so their host-port doors are stamped when they're created — adding one later means recreating the node = recreating the cluster. That's why the config file pre-maps 9051/9052 for labs we haven't reached yet.

  </details>

- What's a taint, and why do your app pods end up on the worker?

  <details><summary>Answer (read after attempting aloud)</summary>

  A taint is a repellent marking on a node — `control-plane:NoSchedule` means "scheduler, don't place ordinary pods here." Pods carrying a matching *toleration* are allowed anyway (system pods and Lab 7's ingress controller do). Your app pods carry no toleration, so the scheduler's only remaining choice is the worker. It keeps the cluster's brain isolated from noisy apps.

  </details>

## Clean up

Nothing — **the cluster stays up for the whole section.** It idles at modest CPU/memory; if you ever need your Mac back:

```bash
kind delete cluster --name capstone   # total teardown — containers, kubeconfig entry, everything
```

…and recreate it in two minutes with step 3. From Lab 2 onward your stack is manifest files, so a rebuilt cluster is one `kubectl apply` away from full state. That disposability is the declarative payoff — never nurse a broken lab cluster back to health, delete it.

Commit `section-04-kubernetes-core/kind-config.yaml`.
