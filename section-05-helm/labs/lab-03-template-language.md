# Lab 3 — The template language: `if`, `range`, `default`, and the render-debug loop

**Goal:** grow the chart the way real charts grow — add postgres (a StatefulSet + PVC, conditional), an ingress (conditional), a `NOTES.txt`, and per-release extra env — using the template language properly. By the end you own the five constructs every chart is built from (`if/else`, `range`, `default`, `with`, named helpers) and the debug loop that makes template errors cheap: **edit → `helm template` → read → repeat**, never `install` blind.

## The mental map (read this first)

Go templates run **before** any YAML exists. The template is just text with `{{ }}` directives; Helm executes them, and *the string that comes out* is then parsed as YAML. So a template can't have "type errors" the way code does — it has **whitespace errors** (wrong indentation in the produced text) and **nil errors** (a directive reached for a value that isn't there). Both are caught locally by `helm template`, before the cluster is involved.

```
  template text  ──execute {{ }}──▶  a plain string  ──parse──▶  YAML manifest
       │                                  │                          │
   your edit                       nil / range / if                 the two failure
                                    decide what text                 modes live here:
                                    gets produced                    bad indent, bad key
                                          │
          helm template  ──────────── prints this ──────────▶  you read it, no cluster touched
```

The five constructs, one line each — you'll use all five in this lab:

- **`if / else`** — include a block (or a whole file) only when a value says so. You met `if` on redis in Lab 2; now `if/else`.
- **`range`** — loop over a list or map, emitting a block per item. This is how a chart turns `extraEnv: [ {name,value}, ... ]` into many `env:` entries.
- **`default`** — `{{ .Values.x | default "y" }}` — supply a fallback so an unset value doesn't blow up.
- **`with`** — rebind `.` to a sub-object so you can write `.size` instead of `.Values.postgres.storage.size` five times. (Comes with a scope trap — you'll hit it.)
- **named helpers** (`define`/`include`) — the functions from Lab 2's `_helpers.tpl`.

Keep the Lab 2 release running; you'll `upgrade` it at the end and watch the new objects appear.

## Steps

### 1. Add the new knobs to `values.yaml`

Append these blocks to `capstone/chart/values.yaml` (keep everything from Lab 2):

```yaml
# ── postgres, in-cluster (S4 Lab 6's StatefulSet + PVC) ──
postgres:
  enabled: true
  image: postgres:18-alpine
  password: localdev          # local lab only — Lab 5 shows the real-secret path
  storage:
    size: 1Gi                 # the PVC size the StatefulSet requests

# ── ingress (off by default — needs the S4 ingress-nginx controller on kind's 9051 door) ──
ingress:
  enabled: false
  className: nginx
  host: capstone.local

# ── arbitrary extra env vars injected into the api container (demonstrates range) ──
extraEnv: []
  # - name: LOG_LEVEL
  #   value: "info"
```

### 2. `default` — make the image tag fall back to the chart's appVersion

Open `capstone/chart/templates/deployment.yaml` and change the image line from Lab 2's hardcoded `.Values.image.tag` to a defaulted one:

```yaml
          image: "{{ .Values.image.repository }}:{{ .Values.image.tag | default .Chart.AppVersion }}"
```

`| default .Chart.AppVersion` reads: "use `image.tag` if set, otherwise fall back to `Chart.yaml`'s `appVersion`." This is the idiom real charts use so that *not setting a tag* pins to the version the chart shipped with, instead of exploding. Your `values.yaml` still sets `tag: "latest"`, so nothing changes yet — but now an empty tag is safe, not broken.

### 3. `range` — inject a list of extra env vars

Still in `deployment.yaml`, extend the container's env. Right now the api gets env only via `envFrom` (the ConfigMap). Add an explicit `env:` block that loops over `extraEnv`:

```yaml
          envFrom:
            - configMapRef:
                name: {{ include "capstone.fullname" . }}-config
          {{- with .Values.extraEnv }}
          env:
            {{- range . }}
            - name: {{ .name }}
              value: {{ .value | quote }}
            {{- end }}
          {{- end }}
```

Read it slowly — this pattern is on every chart you'll ever touch:

- **`{{- with .Values.extraEnv }}`** — if `extraEnv` is empty (`[]`), the whole block is skipped, so no empty `env:` key is emitted. If it's non-empty, `with` also rebinds `.` to point *at* `extraEnv` for the block inside.
- **`{{- range . }}`** — loops over the list. Inside the loop, `.` rebinds *again* to the current item, so `.name` and `.value` read that item's fields.
- **`| quote`** — wraps the value in quotes, so a value like `"true"` or `"8000"` stays a string instead of becoming a YAML bool/int.

#### The scope trap `range` sets — learn it before it bites

Inside `range` (and `with`), `.` no longer means "the root" — it means "the current item." So a naive `{{ .Values.something }}` *inside* a range fails with `nil pointer`, because the current list item has no `.Values`. The escape hatch is **`$`** — it always means the root context, no matter how deep you are:

```
{{- range .Values.extraEnv }}
  # .name works (current item); .Values would FAIL here; $.Values.image.tag works ($ = root)
{{- end }}
```

You don't need `$` in this lab's loop, but you *will* the first time you reference a top-level value inside a range — and the error (`nil pointer evaluating interface {}.Values`) is baffling until you know this. That's why it's here now.

### 4. `with` + a Secret — postgres credentials, base64-encoded

Create `capstone/chart/templates/postgres-secret.yaml`:

```yaml
{{- if .Values.postgres.enabled }}
apiVersion: v1
kind: Secret
metadata:
  name: {{ include "capstone.fullname" . }}-postgres
  labels:
    {{- include "capstone.labels" . | nindent 4 }}
type: Opaque
data:
  POSTGRES_PASSWORD: {{ .Values.postgres.password | b64enc | quote }}
{{- end }}
```

`| b64enc` base64-encodes the value — Kubernetes Secrets store `data:` fields base64-encoded (this is *encoding, not encryption* — Lab 5 and S9 return to "Secrets aren't secret"). The whole file is wrapped in `if .Values.postgres.enabled`, so disabling postgres removes the Secret too.

### 5. The StatefulSet + PVC — `with` to cut repetition

Create `capstone/chart/templates/postgres-statefulset.yaml`. This is the S4 stateful lesson as a template — note the `with` block scoping into `.Values.postgres`:

```yaml
{{- if .Values.postgres.enabled }}
{{- with .Values.postgres }}
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: {{ include "capstone.fullname" $ }}-postgres      # note $ — root context inside `with`
  labels:
    {{- include "capstone.labels" $ | nindent 4 }}
spec:
  serviceName: {{ include "capstone.fullname" $ }}-postgres
  replicas: 1
  selector:
    matchLabels:
      {{- include "capstone.selectorLabels" $ | nindent 6 }}
      component: postgres
  template:
    metadata:
      labels:
        {{- include "capstone.selectorLabels" $ | nindent 8 }}
        component: postgres
    spec:
      containers:
        - name: postgres
          image: {{ .image }}                 # `.` is .Values.postgres here (the `with`)
          env:
            - name: POSTGRES_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: {{ include "capstone.fullname" $ }}-postgres
                  key: POSTGRES_PASSWORD
          ports:
            - containerPort: 5432
          volumeMounts:
            - name: pgdata
              mountPath: /var/lib/postgresql    # 18+ rule: mount HERE, not .../data (S1 Lab 4)
  volumeClaimTemplates:                         # StatefulSet's per-pod PVC — the pgdata lesson
    - metadata:
        name: pgdata
      spec:
        accessModes: ["ReadWriteOnce"]
        resources:
          requests:
            storage: {{ .storage.size }}        # `.storage.size` — short, thanks to `with`
{{- end }}
{{- end }}
```

The `with .Values.postgres` block is why `.image` and `.storage.size` work without the `.Values.postgres.` prefix — `with` rebound `.` to that sub-object. But everything that needs the *root* context — `include "capstone.fullname" $`, the label helpers — uses **`$`**, because inside `with`, plain `.` no longer reaches the root. This is the same scope rule as `range`, and the single most common reason a `with` block errors. `volumeClaimTemplates` is the StatefulSet feature from S4: each pod gets its own PVC for `pgdata`, surviving pod restarts.

Create `capstone/chart/templates/postgres-service.yaml`:

```yaml
{{- if .Values.postgres.enabled }}
apiVersion: v1
kind: Service
metadata:
  name: {{ include "capstone.fullname" . }}-postgres
  labels:
    {{- include "capstone.labels" . | nindent 4 }}
spec:
  selector:
    {{- include "capstone.selectorLabels" . | nindent 4 }}
    component: postgres
  ports:
    - port: 5432
      targetPort: 5432
{{- end }}
```

### 6. `if/else` — the ingress, only when asked for

Create `capstone/chart/templates/ingress.yaml`. It renders to nothing unless `ingress.enabled` is true — so it costs nothing while off, and is ready for S9:

```yaml
{{- if .Values.ingress.enabled }}
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {{ include "capstone.fullname" . }}
  labels:
    {{- include "capstone.labels" . | nindent 4 }}
spec:
  ingressClassName: {{ .Values.ingress.className }}
  rules:
    - host: {{ required "ingress.host is required when ingress.enabled=true" .Values.ingress.host }}
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: {{ include "capstone.fullname" . }}
                port:
                  number: {{ .Values.service.port }}
{{- end }}
```

**`required "msg" .Values.x`** is the guard rail: if someone enables the ingress but forgets `host`, the render fails *with your message* instead of producing a broken Ingress with an empty host. Fail loud at render time, not silently on the cluster — the same "`--frozen` / postgres-18 `exit 1`" philosophy from Section 1.

### 7. `NOTES.txt` — the chart's "what next", conditional

Create `capstone/chart/templates/NOTES.txt`. Unlike every other template, this renders to *text shown to the user* after install/upgrade, not a manifest:

```
Capstone release "{{ .Release.Name }}" is deployed (revision {{ .Release.Revision }}).

Reach the API from your Mac:
  kubectl port-forward svc/{{ include "capstone.fullname" . }} 9061:{{ .Values.service.port }}
  curl -s localhost:9061/health
  curl -s localhost:9061/visits

{{ if .Values.postgres.enabled -}}
Postgres is running in-cluster as {{ include "capstone.fullname" . }}-postgres (StatefulSet + PVC).
{{- else -}}
Postgres is DISABLED for this release.
{{- end }}
{{- if .Values.ingress.enabled }}
Ingress is on: add "127.0.0.1 {{ .Values.ingress.host }}" to /etc/hosts, then browse http://{{ .Values.ingress.host }}:9051
{{- end }}
```

You saw Grafana's NOTES in Lab 1 (the "get your admin password" text). Now you know it's just another template — `.Release`, `.Values`, `if/else` all work the same.

### 8. The render-debug loop — three tools, sharpest first

Before upgrading, exercise the whole debugging toolkit on your own chart:

```bash
cd capstone

# (a) render everything, offline — the default loop
helm template capstone ./chart | less

# (b) render ONE file when hunting a specific bug
helm template capstone ./chart -s templates/postgres-statefulset.yaml

# (c) flip a value at render time to see the conditional fire
helm template capstone ./chart --set postgres.enabled=false | grep -c StatefulSet   # → 0
helm template capstone ./chart --set ingress.enabled=true                          # Ingress now appears
helm template capstone ./chart --set ingress.enabled=true --set ingress.host=""     # required error fires
```

The last one *should fail* with your message:

```
Error: ... execution error at (capstone/templates/ingress.yaml:...): ingress.host is required when ingress.enabled=true
```

That's `required` doing its job — proof the guard works. Now the fourth tool, the one that also checks the cluster:

```bash
helm install capstone ./chart --dry-run=server > /dev/null && echo "server-validated OK"
```

`--dry-run=server` renders like `helm template` **and** sends the result to the api-server for validation (schema, admission) *without persisting* — it catches errors `helm template` can't, like "that field was removed in this Kubernetes version." Three tools, escalating: `helm template` (offline, fastest) → `--dry-run=server` (validated, no changes) → `install`/`upgrade` (real).

#### The two errors you'll actually hit, and how to read them

- **`nil pointer evaluating interface {}.something`** — a directive reached for a value that isn't in your `values.yaml` (typo, or a `.` scope issue inside `range`/`with` where you needed `$`). Fix: check the path exists in values, or swap `.` for `$` if you're inside a loop/with.
- **`error converting YAML to JSON: ... did not find expected key`** — a whitespace bug: the produced text isn't valid YAML. Render the single file with `-s` and *look at the indentation* — nearly always a missing `nindent` or a `{{ include }}` missing its leading `-` dash.

### 9. Upgrade the running release and watch the new objects appear

```bash
helm upgrade capstone ./chart
```

```
Release "capstone" has been upgraded. Happy Helming!
NAME: capstone
REVISION: 2
...
NOTES:
Capstone release "capstone" is deployed (revision 2).
...
Postgres is running in-cluster as capstone-postgres (StatefulSet + PVC).
```

`REVISION: 2` — your ledger grew (Lab 4 dissects exactly what that revision stored). Confirm the new stuff:

```bash
kubectl get statefulset,pvc,secret -l app.kubernetes.io/instance=capstone
kubectl get pods -l component=postgres      # capstone-postgres-0 → Running (note the -0: StatefulSet names are stable, not random)
```

The api and redis from Lab 2 were untouched (their templates didn't change); postgres and its PVC are new. That surgical behavior — change only what the template diff changed — is Lab 4's whole subject.

## Verify

- `helm template capstone ./chart --set postgres.enabled=false | grep -c StatefulSet` prints `0`; with it enabled, the StatefulSet renders.
- `--set ingress.enabled=true --set ingress.host=""` fails with your `required` message.
- After `helm upgrade`, `kubectl get statefulset,pvc` shows `capstone-postgres` and its `pgdata` PVC bound; the release is at `REVISION 2`.

Then answer aloud:

**1. A template runs "before YAML exists." What are the two failure modes that follow from that, and which command catches both without touching the cluster?**

<details><summary>Answer (read after attempting aloud)</summary>

A template is text-substitution that produces a *string*, which is *then* parsed as YAML. So the failures are: (1) **whitespace/indentation** errors — the produced string isn't valid YAML (`did not find expected key`), usually a missing `nindent` or `{{-` dash; (2) **nil errors** — a `{{ .Values.x }}` reached for a value that isn't there (`nil pointer`), often a `.` scope issue inside `range`/`with` where `$` was needed. `helm template` (offline) catches both — it runs the factory and either prints YAML or the error, cluster untouched.

</details>

**2. Inside a `with .Values.postgres` block, `include "capstone.fullname" .` breaks but `include "capstone.fullname" $` works. Explain.**

<details><summary>Answer (read after attempting aloud)</summary>

`with` (like `range`) rebinds `.` to the sub-object — inside `with .Values.postgres`, `.` means the postgres map, so `.image` and `.storage.size` work. But the helper needs the *root* context (it reads `.Release`, `.Chart`), which the postgres map doesn't have — so `.` fails there. `$` always refers to the root context regardless of nesting, so `include ... $` hands the helper what it needs. Rule: inside `with`/`range`, use `.` for the local object and `$` for anything top-level.

</details>

**3. What's the difference between `helm template` and `helm install --dry-run=server`, and when do you reach for the second?**

<details><summary>Answer (read after attempting aloud)</summary>

`helm template` renders locally and stops — pure offline string→YAML, no api-server, catches template/whitespace/nil errors. `--dry-run=server` renders the same way *and* sends the result to the api-server for validation (schema checks, admission webhooks) without persisting anything. Reach for the server dry-run to catch things only the cluster knows — a field removed in this K8s version, a validating webhook that would reject the object — before a real install. Escalation: `template` → `--dry-run=server` → `install`.

</details>

## Clean up

**Leave the release running at REVISION 2** — Lab 4 opens here and dissects the ledger you just grew. Stop any port-forward you left open.

Commit the growth:

```bash
git add capstone/chart
git commit -m "feat(capstone): add postgres, ingress, notes; template conditionals"
```

Update the capstone evolution log: "Section 5: chart gains postgres (StatefulSet+PVC), conditional ingress, NOTES — full template language." Lab 4 stops adding objects and starts operating the release: upgrade, rollback, history, and the immutable-field error.
