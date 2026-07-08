# Lab 5 — Values layering: the deployment interface Section 9 will turn

**Goal:** make the chart multi-environment without duplicating a single template. You'll add a `values-local.yaml` on top of the chart defaults, prove the exact precedence order (defaults < `-f` files < `--set`), trip the lists-replaced-whole gotcha on purpose, and define the one knob the whole rest of the course turns: **`image.tag`**. By the end, a committed values file *is* your deployment interface — changing one line in it, in a PR, is what "deploy a new version" will mean in Section 9.

## The mental map (read this first)

The same templates render differently depending on which values you feed them. Values arrive in **layers**, and later layers win:

```
   LOWEST priority                                        HIGHEST priority
   ┌───────────────┐   ┌──────────────────┐   ┌──────────────────┐   ┌──────────┐
   │ chart          │ < │ -f values-A.yaml │ < │ -f values-B.yaml │ < │  --set   │
   │ values.yaml    │   │  (first file)    │   │  (later file)    │   │ (CLI)    │
   │ (the defaults) │   │                  │   │  later -f wins   │   │ wins all │
   └───────────────┘   └──────────────────┘   └──────────────────┘   └──────────┘
             │                                                              │
             └────────────── merged into ONE value set ────────────────────┘
                                       │
                          MAPS deep-merge (keys combine)
                          LISTS replace whole (later list wins entirely)  ◀ the gotcha
```

Two merge rules, and the difference is the trap that catches everyone once:

- **Maps deep-merge.** Override `image.tag` in a layer and `image.repository` from the layer below *survives* — only the key you set changes. Keys combine across layers.
- **Lists replace wholesale.** Override `extraEnv` (a list) in a higher layer and the lower layer's list is *gone entirely*, not appended to. There is no "merge two lists" — the highest layer that mentions the list wins it completely.

The punchline of the whole section: **a committed values file becomes the deployment interface.** In Section 9, "deploy build 4f0b99e" is a one-line change to `image.tag` in a values file, in a PR, that Argo CD notices and rolls out. This lab builds and turns that knob by hand so the automation in S9 is just "a robot does what I did here."

Keep the Lab 4 release running; you'll re-target it through different value layers.

## Steps

### 1. See the current effective values (the base layer)

Before layering anything, look at what the chart's defaults resolve to for the running release:

```bash
cd capstone
helm get values capstone -a | head -20     # -a = all: defaults + any overrides, merged
```

Right now that's essentially your `chart/values.yaml` (replicaCount 2, image tag latest, redis/postgres enabled). That's **layer 0** — the floor every other layer stacks on. A chart should ship sane defaults so `helm install ./chart` with no flags does something reasonable; overrides are for *differences*, not for restating everything.

### 2. Write `values-local.yaml` — your local-dev layer

Create `capstone/chart/values-local.yaml`. This file holds only what differs from the defaults for *your machine* — the essence of a per-environment values file:

```yaml
# Local-dev overrides for the capstone chart.
# Only the DIFFERENCES from chart/values.yaml live here.

replicaCount: 1            # one replica is plenty on a laptop (default is 2)

image:
  tag: "0.1.0"            # pin an explicit tag locally instead of the floating :latest

extraEnv:                  # a list — watch how this behaves when layered (step 5)
  - name: LOG_LEVEL
    value: "debug"
  - name: ENV
    value: "local"
```

Apply it as a layer on top of the defaults:

```bash
helm upgrade capstone ./chart -f chart/values-local.yaml
```

Confirm the layer took effect — and, crucially, that it *only* changed what it mentioned:

```bash
helm get values capstone            # USER-SUPPLIED: replicaCount 1, image.tag 0.1.0, extraEnv [...]
kubectl get pods -l app.kubernetes.io/name=capstone       # 1 api pod now
helm get manifest capstone | grep -A1 "image:"            # repository STILL from defaults, tag now 0.1.0
```

**The map deep-merge, proved:** you set `image.tag` in the override, but `image.repository` still comes from `chart/values.yaml`. You didn't have to restate the repository — maps combine key-by-key across layers. That's what makes a values file a *diff*, not a full copy.

### 3. Prove `--set` beats `-f`

Layer a CLI override on top of the file and watch it win:

```bash
helm upgrade capstone ./chart -f chart/values-local.yaml --set replicaCount=3
kubectl get pods -l app.kubernetes.io/name=capstone       # 3 pods — --set (3) beat the file (1)
```

`--set` is the highest-priority layer — surgical, wins over every `-f` file and every default. It's for one-off tweaks and CI-injected values (like an image tag from a pipeline), *not* for config you want to keep — because it's invisible the moment the command scrolls off screen. The durable form of the same override is a line in a committed values file.

### 4. Prove later `-f` wins over earlier `-f`

Make a throwaway second file and stack it:

```bash
cat > /tmp/values-extra.yaml <<'EOF'
replicaCount: 4
EOF
helm template capstone ./chart -f chart/values-local.yaml -f /tmp/values-extra.yaml | grep "replicas:"
```

```
replicas: 4
```

`values-local.yaml` said 1, `/tmp/values-extra.yaml` said 4, and **4 won because it came later on the command line.** Rule: `-f` files apply left-to-right, each overriding the last. This is exactly how real setups layer `values.yaml` (base) → `values-staging.yaml` (env) → `values-team.yaml` (local) — most-general first, most-specific last.

### 5. Trip the lists-replaced-whole gotcha on purpose

Here's the trap. Make a file that sets `extraEnv` to a *different* list and layer it over `values-local.yaml` (which has two entries):

```bash
cat > /tmp/values-listtest.yaml <<'EOF'
extraEnv:
  - name: ONLY_ME
    value: "yes"
EOF
helm template capstone ./chart -f chart/values-local.yaml -f /tmp/values-listtest.yaml \
  | grep -A6 "env:"
```

You'll see **only `ONLY_ME`** — not `LOG_LEVEL`, not `ENV`. The higher layer's list *replaced* the lower one entirely; nothing merged:

```
          env:
            - name: ONLY_ME
              value: "yes"
```

**Why this matters and bites:** you'd expect "add one more env var" but you got "throw away the other two." There is no built-in list-merge in Helm values. The practical consequences: (1) an environment file that overrides a list must repeat *every* item it wants, not just the new one; (2) this is the #1 "my override deleted things I didn't touch" bug in real charts. Contrast it with the map behavior from step 2 (where `image.repository` survived) and you've got the whole rule: **maps merge, lists replace.**

### 6. The knob — override `image.tag` the way CI will

This is the payoff the entire section built toward. A deploy of a new build is *nothing but* changing `image.tag`. Two forms, and the difference is the whole GitOps lesson:

**The CI/imperative form** — a pipeline injects the freshly-built tag with `--set`:

```bash
helm upgrade capstone ./chart -f chart/values-local.yaml --set image.tag=0.1.0
```

**The GitOps/declarative form** — the tag is a committed line a human (or a bot's PR) edits:

```bash
# edit chart/values-local.yaml: image.tag: "0.1.0"  →  image.tag: "0.2.0"
# git commit -m "deploy: bump capstone to 0.2.0"
# → in S9, Argo CD sees the commit and rolls it out. No kubectl, no helm, from a human.
```

Prove the knob turns by rendering (offline, no bad-tag pull needed):

```bash
helm template capstone ./chart -f chart/values-local.yaml --set image.tag=0.2.0 \
  | grep "image:"
# → image: "ghcr.io/itsmahadi007/capstone:0.2.0"
```

That single string is the seam between "code built" and "code running." Section 2's CI builds an image and tags it (sha + semver); Section 9's Argo CD watches a values file for that tag to change. **This values file is the interface between them** — the reason the chart, committed to the repo, is the deployable artifact the rest of the course points at. Reset to the good tag so the release stays healthy:

```bash
helm upgrade capstone ./chart -f chart/values-local.yaml
curl -s localhost:9061/health    # (re-run port-forward if needed) → ok
```

## Verify

- `helm get values capstone` shows your `values-local.yaml` overrides merged over the defaults; `image.repository` still comes from the defaults (map deep-merge).
- You demonstrated `--set` beating `-f`, and a later `-f` beating an earlier one.
- You showed that layering a second `extraEnv` list *replaced* rather than merged the first.
- `helm template ... --set image.tag=0.2.0` renders the api image with `:0.2.0`.

Then answer aloud:

**1. State the values precedence order, lowest to highest, and where `--set` and multiple `-f` files sit.**

<details><summary>Answer (read after attempting aloud)</summary>

Chart `values.yaml` defaults (lowest) < each `-f` file in command-line order (later files override earlier ones) < `--set` on the CLI (highest, wins over everything). All layers merge into one effective value set before rendering. `--set` is for surgical/one-off or CI-injected values; durable config belongs in a committed `-f` file so it's visible and reviewable, not lost when the command scrolls away.

</details>

**2. You override `image.tag` in a values file and `image.repository` keeps its default, but overriding `extraEnv` wipes the previous list. Why the different behavior?**

<details><summary>Answer (read after attempting aloud)</summary>

Maps deep-merge across layers — keys combine, so setting `image.tag` leaves `image.repository` intact from the layer below. Lists replace wholesale — the highest layer that mentions a list wins it entirely; there's no element-wise merge. So an env file overriding `extraEnv` must repeat every item it wants to keep. "Maps merge, lists replace" is the rule, and the list half is the classic "my override silently deleted things" bug.

</details>

**3. "Deploying a new version" reduces to changing one value. Which one, and why does that make a committed values file the deployment interface for Section 9?**

<details><summary>Answer (read after attempting aloud)</summary>

`image.tag`. Because the templates are fixed and everything else is stable, the only thing that changes between "build N running" and "build N+1 running" is the image tag the chart renders into the Deployment. Commit that tag in a values file and editing it (in a PR) becomes the entire deploy action: CI builds+tags an image, a PR bumps `image.tag` in the values file, and Argo CD (S9) sees the git change and rolls it out — no human running `kubectl` or `helm` against the cluster. The values file is the reviewable, audited seam between "built" and "running."

</details>

## Clean up

The section is complete — decide whether to keep the release idling or free the resources. Either is fine:

```bash
# Keep it running (Section 6's Terraform will manage this exact chart):
helm list

# — or — tear the release down (recreate any time with `helm install capstone ./chart -f chart/values-local.yaml`):
# helm uninstall capstone
```

Commit the deployment interface:

```bash
git add capstone/chart/values-local.yaml
git commit -m "feat(capstone): add values-local layer and image-tag deploy knob"
```

Update the capstone evolution log: "Section 5 complete: `capstone/chart/` is the deployable artifact — layered values, image-tag knob ready for GitOps." 

The kind cluster and this release are the ground Section 6 stands on: Terraform's kubernetes/helm providers will install *this chart*, and the question "who owns what — Terraform vs Helm vs Argo?" gets named for the first time. You've built the thing all three of them fight over.
