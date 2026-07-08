# Lab 1 — Chart archaeology: read before you trust

**Goal:** install Grafana on your kind cluster with one command — but *earn* that command first. Before you run someone else's chart, you'll pull it apart, read its `values.yaml` like a contract, and use `helm template` to see the exact YAML it will fire at your cluster. This is the habit that separates "I ran a chart off the internet" from "I vetted a chart and know what it does" — a real supply-chain skill, freshly relevant (read the mental map).

## The mental map (read this first)

A **chart** is a folder of templated manifests plus a `values.yaml` of defaults — an image, but for a whole app instead of one container. Installing it creates a **release** (a named instance in a namespace). You met that vocabulary in the README; this lab makes it physical against a chart you didn't write.

The one idea that carries the lab: **`helm template` runs the factory locally and prints the YAML — without touching the cluster.** No release, no api-server, no side effects. It's the chart equivalent of reading a Dockerfile before `docker run`. Two other read-only commands complete the toolkit:

```
 helm repo add / update     ← subscribe to a warehouse of charts (like apt sources)
        │
        ▼
 helm search repo <name>    ← what's in the warehouse, and which versions
        │
        ▼
 helm show values <chart>   ← the chart's PUBLIC API: every knob + its default
        │
        ▼
 helm pull --untar <chart>  ← download the chart folder and READ it (templates + values)
        │
        ▼
 helm template <chart>      ← render templates+values → plain YAML, cluster untouched
        │                     THIS is the manifest that would hit the cluster
        ▼
 helm install <name> <chart> -n <ns>   ← finally: create the release, for real
```

**Why the paranoia is the point.** A chart you install runs with your cluster credentials and can create anything — Deployments, Secrets, RBAC roles, even cluster-admin bindings. "It's just `helm install`" hides that you're executing a stranger's manifests. Two 2025–2026 reminders that reading charts is a job skill, not fussiness:

- **August 2025 — Bitnami.** Broadcom moved the images most community charts depended on behind a paid catalog; the free `bitnamilegacy` images stopped getting patches. Teams who could read a chart's `values.yaml` and see which image it pulled migrated in a day; teams who couldn't got paged.
- **January 2026 — Grafana.** The Grafana chart you're about to use *moved repositories* — from `grafana/helm-charts` to `grafana-community/helm-charts`. The old repo still resolves, so a copy-pasted 2024 tutorial "works" while silently pulling a chart that no longer gets updates. Knowing to check *where* a chart comes from is the whole lesson.

So: subscribe, read, render, *then* install. You'll do exactly that.

## Steps

### 1. Install Helm and subscribe to the chart repo

```bash
brew install helm
helm version     # version.BuildInfo{Version:"v4.2.2", ...} — any 4.x is fine
```

Now add the **current** Grafana community repo (the post-migration one — see the mental map for why this URL and not the old `grafana/helm-charts`):

```bash
helm repo add grafana-community https://grafana-community.github.io/helm-charts
helm repo update
```

`repo add` writes the warehouse URL into `~/Library/Preferences/helm/repositories.yaml` — like adding a line to apt sources. `repo update` fetches each repo's **index** (a big YAML listing every chart and version it offers). Expected:

```
"grafana-community" has been added to your repositories
...
Update Complete. ⎈Happy Helming!⎈
```

If `repo add` says the name already exists, you (or a past you) added it — `helm repo list` shows what you're subscribed to.

### 2. Find the chart and read its public API

```bash
helm search repo grafana-community/grafana --versions | head
```

`search repo` reads the *local* index you just fetched — no network. `--versions` lists every chart version, newest first (chart version ≠ the Grafana app version inside it; the `APP VERSION` column is the app):

```
NAME                          CHART VERSION   APP VERSION   DESCRIPTION
grafana-community/grafana     10.5.x          12.x.x        The leading tool for querying and visualiz...
```

Now the single most important command for consuming any chart — its **values are its public API**, the only supported way to configure it:

```bash
helm show values grafana-community/grafana | less
```

This prints the chart's default `values.yaml` — hundreds of lines. You're not memorizing it; you're learning to *navigate* it. Search (`/` in `less`) for the knobs you'll actually turn:

- `service:` → `type: ClusterIP`, `port: 80` — how you'll reach it.
- `persistence:` → `enabled: false` — Grafana will use ephemeral storage (fine for a lab; its dashboards die on pod restart, and that's a *choice this chart's defaults made for you* — now you know).
- `adminUser: admin` and `adminPassword:` (empty → the chart auto-generates one into a Secret).
- `image:` → `repository: docker.io/grafana/grafana` — vet exactly which image runs. (This is the line that mattered in the Bitnami incident.)

Everything you might override lives here with its default. `q` to quit `less`.

### 3. Pull the chart open and read the templates

`show values` shows the knobs; to see the *machinery* the knobs drive, download the chart folder itself:

```bash
cd /tmp
helm pull grafana-community/grafana --untar
ls grafana/
```

```
Chart.yaml   values.yaml   templates/   charts/   dashboards/   README.md
```

Read the anatomy — every chart is this shape (Lab 2 you build one):

- **`Chart.yaml`** — the chart's identity card: `name`, `version` (the chart's own version), `appVersion` (the app it installs), `dependencies` (other charts it pulls in — Grafana has a few).
- **`values.yaml`** — the defaults you just read via `show values`.
- **`templates/`** — the manifests-with-holes. Open one:

```bash
sed -n '1,25p' grafana/templates/deployment.yaml
```

You'll see plain Kubernetes YAML sprayed with `{{ ... }}` — `{{ .Values.image.repository }}`, `{{ include "grafana.fullname" . }}`, `{{- if .Values.persistence.enabled }}`. That's the templating language Lab 3 drills. Right now just register the shape: **a template is a manifest where the decisions have been lifted out into `.Values`.**

### 4. Render it — see the exact YAML before it touches the cluster

This is the archaeology payoff. Run the factory locally:

```bash
helm template grafana grafana-community/grafana \
  --set persistence.enabled=false \
  --set service.port=80 | less
```

`helm template <release-name> <chart>` renders templates + values into finished manifests and prints them — **nothing is sent anywhere**. Scroll through and confirm you can *predict* what the install will create:

- a `Deployment` running `grafana/grafana:<appVersion>`
- a `Service` of type `ClusterIP` on port 80
- a `ConfigMap` with Grafana's config
- a `Secret` holding the admin credentials
- a `ServiceAccount` + RBAC objects

Every `--set` you passed shows up substituted in the output. **This is the diff you'd send in a PR to justify installing a chart.** If a rendered object surprised you (an unexpected `ClusterRoleBinding`, say), *this* is where you'd catch it — before it existed, not after.

#### If `helm template` errors instead of rendering

You'll meet real render errors in Lab 3, but know the shape now: a template that references a value you didn't provide can fail with `nil pointer evaluating interface {}.someField`. It means a `{{ .Values.x.y }}` found no `x`. With a community chart it usually means you disabled a section but not cleanly; the fix is reading `show values` for what that block expects. The key point: **the error happens in the factory, on your laptop — the cluster never saw a broken manifest.**

### 5. Install for real — into its own namespace

Now you've earned it. Create a namespace (charts should live in their own folder, not `default`) and install:

```bash
helm install graf grafana-community/grafana \
  --namespace monitoring --create-namespace \
  --set persistence.enabled=false
```

`graf` is the **release name** (your instance); `--create-namespace` makes `monitoring` if absent. Expected tail:

```
NAME: graf
LAST DEPLOYED: ...
NAMESPACE: monitoring
STATUS: deployed
REVISION: 1
NOTES:
  1. Get your 'admin' user password by running:
     kubectl get secret --namespace monitoring graf-grafana -o jsonpath="{.data.admin-password}" | base64 --decode ...
```

Those **NOTES** are `templates/NOTES.txt` from the chart, rendered — a chart's built-in "what to do next" (you'll write one in Lab 3). `REVISION: 1` is the first entry in this release's ledger.

Watch it come up, then confirm Helm's own bookkeeping:

```bash
kubectl get pods -n monitoring -w      # graf-grafana-... → Running, Ctrl-C when ready
helm list -n monitoring                # STATUS deployed, REVISION 1, CHART grafana-10.5.x
```

`helm list` is scoped to a namespace by default (`helm list -A` for all) — it reads the release ledger, not the cluster. It's telling you what *Helm believes* it installed here.

### 6. Reach Grafana on your 9060 door

Grafana's Service is `ClusterIP` — no host door, exactly like redis/db in your compose stack. `port-forward` tunnels through the api-server (no cluster port mapping needed — the same trick S4 Lab 3 used):

```bash
kubectl port-forward -n monitoring svc/graf-grafana 9060:80
```

Leave that running. In another terminal, grab the auto-generated admin password the NOTES told you about:

```bash
kubectl get secret -n monitoring graf-grafana \
  -o jsonpath="{.data.admin-password}" | base64 --decode; echo
```

Open `http://localhost:9060`, log in as `admin` / that password. You installed a real, non-trivial app — and you can point to the rendered YAML that says exactly what it put on your cluster.

## Verify

- `helm list -n monitoring` shows release `graf`, `STATUS deployed`, `REVISION 1`.
- Grafana's login page loads at `http://localhost:9060` and the auto-generated password logs you in.
- You can open `/tmp/grafana/templates/deployment.yaml` and point to at least two `{{ .Values.* }}` holes and say which `values.yaml` key fills each.

Then answer aloud:

**1. What does `helm template` do that `helm install` also does — and what does it deliberately NOT do?**

<details><summary>Answer (read after attempting aloud)</summary>

Both run the *factory*: templates + values → finished Kubernetes YAML. `helm template` stops there and prints it — no api-server call, no release created, no cluster state changed. `helm install` takes that same rendered YAML and additionally sends it to the cluster (server-side apply in Helm 4) and records a release revision in the ledger. So `helm template` is your safe, offline "what *would* this do?" — the read-before-you-trust command, and your whole debugging loop in Lab 3.

</details>

**2. A chart's `values.yaml` — why call it the chart's "public API"?**

<details><summary>Answer (read after attempting aloud)</summary>

Because it's the only supported surface for configuring the chart. The templates are the private implementation (the chart author can rewrite them between versions); `values.yaml` is the documented contract of every knob and its default. You configure a chart by overriding values (`-f` files or `--set`), never by editing its templates — same discipline as calling a library's public functions instead of reaching into its internals. `helm show values` prints that contract.

</details>

**3. You copy-paste a 2024 tutorial's `helm repo add grafana https://grafana.github.io/helm-charts` and it works. Why might that still be the wrong thing to do in 2026?**

<details><summary>Answer (read after attempting aloud)</summary>

The Grafana chart migrated to `grafana-community/helm-charts` on 2026-01-30. The old repo URL still resolves, so the command *succeeds* — but it subscribes you to a chart location that no longer receives updates and fixes. "It ran without error" is not the same as "it's the maintained source." Vetting *where* a chart comes from — and whether that source is current — is part of reading a chart before trusting it, same class of lesson as the Bitnami image move.

</details>

## Clean up

Grafana isn't part of the capstone stack — remove the release and its namespace so it doesn't idle on your Mac. (Section 8 brings observability back properly.)

```bash
# Ctrl-C the port-forward first, then:
helm uninstall graf -n monitoring
kubectl delete namespace monitoring
rm -rf /tmp/grafana                 # the pulled chart folder
```

`helm uninstall` deletes every object the release created **and** the release's ledger entries — the inverse of install. `helm list -n monitoring` should come back empty. Keep the `grafana-community` repo subscription; it costs nothing and you may want it in Section 8.

Nothing to commit — this lab touched only your cluster and `/tmp`. Lab 2 is where your hands start building the chart this course revolves around.
