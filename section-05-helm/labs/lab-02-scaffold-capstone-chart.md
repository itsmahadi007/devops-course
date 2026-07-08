# Lab 2 — Scaffold `capstone/chart/` from your S4 manifests

**Goal:** turn your Section 4 raw manifests (`capstone/k8s/deployment.yaml`, `service.yaml`, `configmap.yaml`, plus the in-cluster redis) into a proper Helm chart at `capstone/chart/` — the artifact Terraform installs in S6 and Argo CD watches in S9. You'll scaffold with `helm create`, throw away 90% of its boilerplate, and rebuild the templates from YAML you already understand. First install at the end.

## The mental map (read this first)

You're not learning new Kubernetes here — every object in this chart is one you wrote by hand in S4. You're doing one move: **lift the decisions out of the manifest into `values.yaml`, and leave a `{{ .Values.x }}` hole where each used to be.** A manifest with holes is a template; the values fill them; `helm template` glues them back into the same YAML you started with.

```
 S4 (raw)                          S5 (chart)
 capstone/k8s/deployment.yaml      capstone/chart/
   replicas: 2          ───lift──▶   values.yaml:  replicaCount: 2
   image: .../capstone:latest       templates/deployment.yaml:
   REDIS_URL: redis://redis:6379       replicas: {{ .Values.replicaCount }}
                                       image: {{ .Values.image.repository }}:{{ .Values.image.tag }}
                                          │
                                          └── helm template ──▶ identical YAML, cluster sees no difference
```

Three chart pieces you'll meet for the first time as an author (you read them in Lab 1's Grafana chart):

- **`Chart.yaml`** — the chart's identity card: its name, its own version, and `appVersion` (the app it ships).
- **`values.yaml`** — the defaults, i.e. the chart's public API. Every knob you lifted out lives here.
- **`_helpers.tpl`** — named template snippets (functions). One computes the resource name, one computes the standard label set — so every template names things consistently instead of copy-pasting strings. The leading `_` means "not a manifest, don't render me as an object."

**Why bother, when the raw YAML worked?** Three things the chart buys you, all of which S4 lacked: one place to change the image tag (S9's deploy knob), a second environment from the same templates with a different values file (S5 Lab 5), and a release ledger with history + rollback (S5 Lab 4). This lab builds the skeleton; the next three make those three payoffs real.

## Steps

### 1. Scaffold — then look at what `helm create` gives you

```bash
cd capstone
helm create chart
```

This generates `capstone/chart/` pre-filled with a *working example* chart (an nginx-ish web app). Look at the tree — this is the standard chart layout, worth seeing once from the horse's mouth:

```bash
find chart -type f
```

```
chart/Chart.yaml
chart/values.yaml
chart/.helmignore
chart/templates/_helpers.tpl
chart/templates/deployment.yaml
chart/templates/service.yaml
chart/templates/serviceaccount.yaml
chart/templates/ingress.yaml
chart/templates/hpa.yaml
chart/templates/NOTES.txt
chart/templates/tests/test-connection.yaml
```

The scaffold is a teaching tool, not a starting point — its deployment template is generic and carries features you don't want yet (autoscaling, service accounts, tests). **We keep the two `_helpers.tpl` conventions and rewrite everything else** to match manifests you actually understand. Clear the templates you won't use in this lab:

```bash
rm chart/templates/hpa.yaml \
   chart/templates/serviceaccount.yaml \
   chart/templates/ingress.yaml \
   chart/templates/NOTES.txt \
   chart/templates/tests/test-connection.yaml
rmdir chart/templates/tests
```

(`ingress.yaml` and `NOTES.txt` come back in Lab 3 — written *your* way.)

### 2. Write `Chart.yaml` — the identity card

Overwrite `capstone/chart/Chart.yaml` with:

```yaml
apiVersion: v2                 # chart format v2 (Helm 3 AND 4 — unchanged across the major bump)
name: capstone                 # the chart's name; used by the fullname helper
description: The capstone FastAPI service — the course's flagship deployable
type: application              # "application" (deployable) vs "library" (shared helpers only)
version: 0.1.0                 # the CHART's own version — bump when the chart changes
appVersion: "0.1.0"            # the APP version this chart ships (your capstone image tag family)
```

The two versions trip everyone once: **`version` is the chart's version** (bump it when you edit templates), **`appVersion` is the app's version** (your capstone release). They move independently — a template-only fix bumps `version`, not `appVersion`. This is the same `CHART VERSION` / `APP VERSION` split you saw in Lab 1's `helm search` output.

### 3. Write `values.yaml` — lift every S4 decision here

Overwrite `capstone/chart/values.yaml`. This is the whole point of the chart — every hardcoded choice from your S4 manifests, pulled out into one file:

```yaml
# ── the capstone image (your GHCR image from S1/S2) ──
image:
  repository: ghcr.io/itsmahadi007/capstone
  tag: "latest"               # QUOTED — an unquoted numeric tag like 0.1 would become a YAML float
  pullPolicy: Always          # :latest re-checks the registry every pull (S4 Lab 2 lesson)

replicaCount: 2               # was S4's `replicas: 2`

service:
  type: ClusterIP             # was S4's service.yaml
  port: 8000                  # the port the Service exposes (container still binds 8000)

# ── the in-cluster redis /visits talks to (S4 Lab 6) ──
redis:
  enabled: true
  image: redis:8-alpine
```

Every one of these keys is a hole waiting in a template below. Change a value here → `helm upgrade` → the chart re-renders → the cluster changes. That indirection is the deploy interface Section 9 turns via git.

### 4. Write `_helpers.tpl` — name and label everything consistently

Overwrite `capstone/chart/templates/_helpers.tpl`. Helm's scaffold wrote a verbose version; here's the trimmed, readable core — read the comments, this is your first template code:

```
{{/* The base name: the chart name, overridable. Used everywhere as the app's identity. */}}
{{- define "capstone.name" -}}
{{- .Chart.Name -}}
{{- end -}}

{{/* The full resource name: release name + chart name, but collapse if the release already
     contains the chart name (so `helm install capstone ./chart` yields "capstone", not
     "capstone-capstone"). This is the standard Helm fullname idiom. */}}
{{- define "capstone.fullname" -}}
{{- if contains .Chart.Name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{/* Selector labels: the MINIMAL, STABLE set a Service/Deployment matches pods by.
     These must never change for a running release (they're immutable — Lab 4 proves it). */}}
{{- define "capstone.selectorLabels" -}}
app.kubernetes.io/name: {{ include "capstone.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/* Full labels: selector labels PLUS informational ones (version, managed-by).
     Safe to change anytime; not used for matching. */}}
{{- define "capstone.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{ include "capstone.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}
```

Two ideas worth owning now, because Lab 4 leans on them:

- **`define` makes a named template you `include` elsewhere** — a function. `.Chart`, `.Release`, `.Values` are the objects Helm hands every template: chart metadata, release info (name/namespace/revision), and your values.
- **selector labels vs full labels.** The *selector* set (`name` + `instance`) is how a Deployment finds its pods and a Service finds its endpoints — that mapping is baked in at creation and **cannot change** on a running object (S4 taught you `selector.matchLabels` must equal the pod template's labels). The *full* set adds version/managed-by info that's safe to churn. Splitting them keeps the immutable part small and stable.

### 5. Write the templated Deployment

Overwrite `capstone/chart/templates/deployment.yaml`. Compare it mentally to your S4 `deployment.yaml` — same object, holes where the decisions were:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "capstone.fullname" . }}       # helper → "capstone" for release "capstone"
  labels:
    {{- include "capstone.labels" . | nindent 4 }}   # full label set, indented 4 spaces
spec:
  replicas: {{ .Values.replicaCount }}            # ◀ the hole S4's `2` used to fill
  selector:
    matchLabels:
      {{- include "capstone.selectorLabels" . | nindent 6 }}   # the immutable matching set
  template:
    metadata:
      labels:
        {{- include "capstone.selectorLabels" . | nindent 8 }} # pod labels MUST match the selector
    spec:
      containers:
        - name: api
          image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
          imagePullPolicy: {{ .Values.image.pullPolicy }}
          ports:
            - containerPort: 8000                 # container side stays conventional
          envFrom:
            - configMapRef:
                name: {{ include "capstone.fullname" . }}-config   # REDIS_URL comes from here
```

The one piece of syntax that bites everyone — **`nindent`**:

- `include "capstone.labels" .` returns a multi-line block starting at column 0.
- `| nindent 4` means "newline, then indent every line 4 spaces" — so the block lands correctly *under* `labels:`.
- The `{{-` (dash) trims the whitespace/newline *before* the tag, so you don't get a blank line where the template directive sat. Without the dash you get stray blank lines; without `nindent` you get YAML-indentation errors. **Whitespace is the #1 source of Helm frustration** — `nindent N` + leading `{{-` is the reliable combo.

### 6. Write the Service and the ConfigMap

Overwrite `capstone/chart/templates/service.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: {{ include "capstone.fullname" . }}
  labels:
    {{- include "capstone.labels" . | nindent 4 }}
spec:
  type: {{ .Values.service.type }}
  selector:
    {{- include "capstone.selectorLabels" . | nindent 4 }}   # routes to pods wearing these labels
  ports:
    - port: {{ .Values.service.port }}    # the Service's port
      targetPort: 8000                    # the container's port (S4: name or number)
      protocol: TCP
```

Create `capstone/chart/templates/configmap.yaml` — this holds `REDIS_URL`, pointed at the redis service you define next. Note the name references the redis service by *computed* name, not a hardcoded string:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "capstone.fullname" . }}-config
  labels:
    {{- include "capstone.labels" . | nindent 4 }}
data:
  REDIS_URL: "redis://{{ include "capstone.fullname" . }}-redis:6379/0"
```

`{{ include "capstone.fullname" . }}-redis` renders to `capstone-redis` — the redis Service's DNS name. Same idea as S4: the app finds redis by service name, never an IP. Because the name is *computed*, a second release named `staging` automatically points its api at `staging-redis` — no string to forget to change.

### 7. Write the in-cluster redis (Deployment + Service)

Create `capstone/chart/templates/redis-deployment.yaml`:

```yaml
{{- if .Values.redis.enabled }}
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "capstone.fullname" . }}-redis
  labels:
    {{- include "capstone.labels" . | nindent 4 }}
spec:
  replicas: 1
  selector:
    matchLabels:
      {{- include "capstone.selectorLabels" . | nindent 6 }}
      component: redis            # extra label so redis pods ≠ api pods under the same selector base
  template:
    metadata:
      labels:
        {{- include "capstone.selectorLabels" . | nindent 8 }}
        component: redis
    spec:
      containers:
        - name: redis
          image: {{ .Values.redis.image }}
          ports:
            - containerPort: 6379
{{- end }}
```

Create `capstone/chart/templates/redis-service.yaml`:

```yaml
{{- if .Values.redis.enabled }}
apiVersion: v1
kind: Service
metadata:
  name: {{ include "capstone.fullname" . }}-redis
  labels:
    {{- include "capstone.labels" . | nindent 4 }}
spec:
  selector:
    {{- include "capstone.selectorLabels" . | nindent 4 }}
    component: redis              # route only to redis pods, not the api pods
  ports:
    - port: 6379
      targetPort: 6379
{{- end }}
```

The `{{- if .Values.redis.enabled }}` wrapper is your first conditional: set `redis.enabled: false` in values and these two files render to *nothing* — the objects simply don't exist. Lab 3 leans on this pattern hard for postgres and ingress.

### 8. Lint, render, THEN install

Never install a chart you haven't rendered — the Lab 1 discipline, now on your own chart:

```bash
cd capstone
helm lint chart                    # static checks: valid YAML, required Chart.yaml fields, obvious mistakes
```

```
==> Linting chart
1 chart(s) linted, 0 chart(s) failed
```

```bash
helm template capstone ./chart | less   # render everything — read it like you read Grafana's
```

Scroll through: you should see your Deployment (2 replicas, the GHCR image), Service, ConfigMap (REDIS_URL pointing at `capstone-redis:6379`), and the redis Deployment+Service — **the exact objects you wrote by hand in S4, now generated.** If anything looks wrong, fix it here; the cluster is still untouched.

#### The failure you'll probably hit first: an indentation error

If `helm template` prints `error converting YAML to JSON: yaml: line N: did not find expected key`, you have a whitespace bug — almost always a missing `nindent` or a `{{ include ... }}` without the `-` dash, leaving a block at the wrong column. Render just the offending file to see the raw output:

```bash
helm template capstone ./chart -s templates/deployment.yaml
```

`-s` (show only) prints one template's rendered YAML so you can *see* the broken indentation directly. Fix the `nindent`/dash, re-render. This tight edit → `helm template -s` → read loop is the debugging rhythm Lab 3 formalizes.

Now install for real:

```bash
helm install capstone ./chart
```

```
NAME: capstone
LAST DEPLOYED: ...
NAMESPACE: default
STATUS: deployed
REVISION: 1
```

`REVISION: 1` — the first entry in your capstone release ledger. Confirm and reach it:

```bash
helm list                                   # capstone, deployed, revision 1
kubectl get deploy,svc,cm -l app.kubernetes.io/instance=capstone
kubectl port-forward svc/capstone 9061:8000 &   # your api door for this section
curl -s localhost:9061/health                # {"status":"ok"}
curl -s localhost:9061/visits                # {"visits":1} — REDIS_URL wired, redis reachable by name
curl -s localhost:9061/visits                # {"visits":2}
```

`/visits` incrementing proves the whole chart wired up: the ConfigMap set `REDIS_URL`, the api read it, and DNS resolved `capstone-redis` to the redis Service — all from templates, all from one `helm install`.

## Verify

- `helm list` shows release `capstone`, `STATUS deployed`, `REVISION 1`.
- `/health` returns ok and `/visits` increments through `http://localhost:9061`.
- `helm template capstone ./chart` renders the full S4-equivalent stack, and you can point to three `{{ .Values.* }}` holes and name the S4 value each replaced.

Then answer aloud:

**1. `helm template` and `kubectl apply -f capstone/k8s/` produce the same objects. So what did the chart actually buy you?**

<details><summary>Answer (read after attempting aloud)</summary>

The cluster sees identical YAML either way — Helm adds nothing at runtime. What the chart buys is *authoring* leverage: (1) one place (`values.yaml`) to change a decision that was scattered across seven files; (2) the same templates render a *second* environment from a different values file (Lab 5); (3) `install`/`upgrade` record a versioned release with history and one-command rollback (Lab 4). Raw manifests have none of that — no history, no `rollback`, and every environment is copy-paste-edit.

</details>

**2. Why split `_helpers.tpl` into `selectorLabels` and `labels`?**

<details><summary>Answer (read after attempting aloud)</summary>

Selector labels (`name` + `instance`) are the immutable matching key — the Deployment finds its pods and the Service finds its endpoints by them, and that mapping is fixed at object creation (S4: `selector.matchLabels` must equal the pod template labels, and you can't change it later). Full labels add informational fields (chart version, managed-by) that are safe to churn on every upgrade. Keeping the immutable set minimal and separate means an upgrade can freely update version labels without touching the fields that would trigger an immutable-field error (Lab 4).

</details>

**3. The ConfigMap's `REDIS_URL` uses `{{ include "capstone.fullname" . }}-redis` instead of the literal `capstone-redis`. Why is the computed form better?**

<details><summary>Answer (read after attempting aloud)</summary>

Because the fullname helper derives from the *release name*. Install the same chart as release `staging` and the api's `REDIS_URL` automatically becomes `staging-redis`, matching the redis Service that release also created — no hardcoded string to forget. Two releases of the same chart coexist without colliding or cross-wiring. A literal `capstone-redis` would break the moment the release isn't named `capstone`. That's the whole reason charts compute names from `.Release` instead of hardcoding.

</details>

## Clean up

**Leave the release installed** — Labs 3, 4, and 5 each open on the state the previous one left. Just stop the port-forward when you step away:

```bash
kill %1        # stops the backgrounded port-forward; the release keeps running
```

Commit the chart:

```bash
git add capstone/chart
git commit -m "feat(capstone): scaffold helm chart from s4 manifests"
```

Update the capstone evolution log: "Section 5: S4 manifests parameterized into `capstone/chart/` — first Helm release." Lab 3 adds postgres, ingress, and NOTES — and teaches the template language that makes them conditional.
