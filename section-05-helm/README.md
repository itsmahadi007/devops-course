# Section 05 — Helm

**Status:** written — not started · **Time:** ~4–6 days at 2–4h/day · **Labs:** 5

Section 4 left you with `capstone/k8s/` — a folder of raw YAML you apply by hand. It works, and it taught you every object in it. But look at it as an operator: deploying to a second environment means copy-paste-edit across seven files; changing the image tag means finding every place it's written; and `kubectl apply` keeps no history — there is no "what was running yesterday" and no `rollback`. This section fixes all three at once, and produces the artifact the rest of the course revolves around: `capstone/chart/` — the thing Terraform installs in Section 6 and Argo CD watches in Section 9.

## The mental model (read first)

**"Helm is apt for Kubernetes" is the shallow take.** It's true for about one lab (you'll install Grafana with one command, like `apt install`). The deeper truth is that Helm is two machines bolted together, and interviews probe the second one:

**Machine 1: a manifest factory.** A **chart** is your S4 manifests with the decisions pulled out. Templates (`templates/*.yaml`) are manifests with holes; `values.yaml` fills the holes. Render = templates + values → plain YAML, the same YAML you wrote by hand in S4 — Helm adds *nothing* the cluster sees; the cluster only ever receives rendered manifests. `helm template` runs the factory and prints the output without touching the cluster — that's your debugging loop all section.

**Machine 2: a release ledger.** Installing a chart creates a **release** — a *named instance* of the chart in a namespace. Map it to Section 1 Lab 6 vocabulary and it clicks instantly:

| docker (S1 Lab 6) | helm | nature |
|---|---|---|
| image | chart | inert, versioned, shippable recipe |
| container | release | named running instance of the recipe |
| `-e` / compose env | values | per-instance config, not baked in |
| digest / commit sha | **revision** (v1, v2, v3…) | immutable snapshot, append-only |
| tag (sticky note) | release *name* | mutable pointer → the current revision |

Every `install` and every `upgrade` appends a **revision** to the ledger. Physically, each revision is a Kubernetes Secret in the release's namespace (`sh.helm.release.v1.<name>.v<N>`, type `helm.sh/release.v1`) holding gzipped JSON of: the entire chart, the values you supplied, the fully-rendered manifest, and status. Three consequences worth owning:

- **Rollback needs nothing from your laptop.** The cluster carries every past revision's full chart + values + manifest. `helm rollback` re-applies an old snapshot — and writes it as a *new* revision. It's `git revert`, never `git reset`: the ledger only moves forward.
- **`helm get manifest` shows what Helm *believes* is live** (the ledger), not what *is* live (`kubectl get`). Drift lives in the gap between those two — Lab 4 makes you create and observe it, Section 9's Argo CD exists to close it.
- The ledger is namespaced and capped (default `--history-max 10`) — it's a deploy log, not an archive.

**What `helm upgrade` actually computes** — the part "apt for clusters" hides. Helm 2 naively diffed old render vs new render, blind to anything changed on the cluster. Helm 3 did a client-side **three-way merge**: ledger's last manifest ⊕ new render ⊕ live state — so a field your chart never set (added by some controller or a `kubectl annotate`) survives the upgrade, while fields the chart *does* set get reasserted. **Helm 4 (what you're running) hands that merge to the API server**: new releases use **server-side apply**, where the API server tracks *field ownership* (`managedFields`) — Helm owns the fields the chart renders, other actors own theirs, and conflicts are resolved by ownership rather than client-side diff math. Same question ("who wins for each field?"), better bookkeeping. Rule of thumb that survives all versions: **an upgrade resets what the chart sets, and leaves alone what it never set.**

**Values are a layer cake.** Chart defaults (`values.yaml`) < `-f your-file.yaml` (repeatable, later files win) < `--set` (surgical, wins over everything). Maps deep-merge across layers; lists get replaced whole — a gotcha Lab 5 makes you trip on deliberately. The punchline of the whole section: a committed values file becomes the *deployment interface* — in Section 9, "deploy a new version" = a one-line change to `image.tag` in a values file, in a PR. That file is the knob; CI's hand turns it.

```
   templates/*.yaml  +  values.yaml ◀─ -f overrides ◀─ --set
          │                 │
          └──── render ─────┘         THE FACTORY
                  │
                  ▼
        plain YAML manifests ──── server-side apply ────▶ cluster
                  │                                    (live state)
                  ▼
   ledger: sh.helm.release.v1.capstone.vN   THE LEDGER
   v1 install · v2 upgrade · v3 rollback(→v1) · …
```

## Why this matters for jobs

- Helm is on effectively every Kubernetes JD. Nobody runs raw manifests at scale; the real question is "Helm or Kustomize or both", and you should be able to argue it.
- "Walk me through what `helm upgrade` does" and "how does rollback behave when someone kubectl-edited the cluster?" are standard screeners — the ledger + merge story above IS the answer.
- Vetting third-party charts is a supply-chain skill with a fresh cautionary tale: in August 2025 Broadcom moved the Bitnami images most charts depended on behind a paid catalog (`bitnamilegacy` gets no patches). Teams that could read a chart before trusting it migrated in a day; teams that couldn't got paged. Lab 1 builds exactly that reading habit.
- CKA expects you to install things with Helm under time pressure; Sections 6 and 9 both *consume* what you build here.

## Tooling

```bash
brew install helm     # Helm 4 — current stable is v4.2.2 (June 2026); any 4.x is fine
helm version          # → version.BuildInfo{Version:"v4.2.x", ...}
```

You're learning on **Helm 4** (released Nov 2025; Helm 3 leaves security support Nov 2026). Charts are unchanged between 3 and 4 (`apiVersion: v2`), so the internet's mountain of v3-era tutorials still applies — with two renamed flags worth knowing on sight: `--atomic` → `--rollback-on-failure`, `--force` → `--force-replace`.

## Labs

| Lab | What you build | Proves |
|---|---|---|
| [1 — Chart archaeology](labs/lab-01-community-chart-archaeology.md) | Grafana on kind via its community chart | consuming + vetting charts, values as the public API |
| [2 — Scaffold the capstone chart](labs/lab-02-scaffold-capstone-chart.md) | `capstone/chart/` from your S4 manifests | Chart.yaml, templates, helpers, first install |
| [3 — Template language](labs/lab-03-template-language.md) | postgres/ingress/NOTES added, all conditional | values/default/if/range/helpers, the render-debug loop |
| [4 — Release lifecycle](labs/lab-04-release-lifecycle.md) | upgrades, a rollback, a failed deploy, drift | the ledger, revision anatomy, immutable fields |
| [5 — Values layering](labs/lab-05-values-layering.md) | `values-local.yaml` + the image-tag knob | layer precedence, the GitOps interface for S9 |

- [ ] Lab 1 · [ ] Lab 2 · [ ] Lab 3 · [ ] Lab 4 · [ ] Lab 5

Do them in order — each lab leaves the release in the state the next one opens with. Host ports in this section: **9060 (Grafana), 9061 (capstone api)** — the 9060–9069 block belongs to S5.

## Reading (curated, ~1.5h total)

- [Charts](https://helm.sh/docs/topics/charts/) — the chart format, `Chart.yaml`, dependencies
- [Chart template guide — getting started](https://helm.sh/docs/chart_template_guide/getting_started/) — read through "Values Files"; Lab 3 drills it
- [Values files](https://helm.sh/docs/chart_template_guide/values_files/) — the layering rules Lab 5 proves
- [Helm 4 released](https://helm.sh/blog/helm-4-released/) — what changed and why (server-side apply is the headline)
- [helm upgrade reference](https://helm.sh/docs/helm/helm_upgrade/) — skim the flags once; you'll recognize half of them after Lab 4

## Done when

Every task in [checkpoint.md](checkpoint.md) passes from memory, and [notes.md](notes.md) is filled in your own words. Then Section 6 gets written — where Terraform installs this exact chart and the "who owns what: TF vs Helm vs Argo" question gets named.
