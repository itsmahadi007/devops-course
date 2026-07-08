# Checkpoint — Section 05: Helm

Pass every task **from memory** — no peeking at the labs. If you have to peek, the section isn't done yet; redo that lab tomorrow and try again.

## Practical tasks

- [ ] **1.** Add a community chart repo, then — *before* installing — read its public API (`helm show values`), pull it open (`helm pull --untar`), and render it (`helm template`). Point to two `{{ .Values.* }}` holes in a template and name the value that fills each.
- [ ] **2.** From a blank folder, `helm create` a chart, strip the boilerplate, and rebuild a Deployment + Service + ConfigMap that render (via `helm template`) to the same objects as a set of raw manifests. Target: chart lints clean and installs to `deployed`.
- [ ] **3.** Write a `_helpers.tpl` with a `fullname` helper and split `selectorLabels` / `labels`, and explain out loud why the split exists (which set is immutable).
- [ ] **4.** Make one object in a chart conditional on a value (`{{- if .Values.x.enabled }}`), and prove with `helm template --set x.enabled=false` that it disappears from the render.
- [ ] **5.** Install a release, upgrade it twice, then `helm rollback` to an earlier revision. Show `helm history` and explain why rollback produced a *new* revision instead of shrinking the list.
- [ ] **6.** Given chart defaults + a values file + a `--set` flag that all set the same key, predict the winning value before running `helm template`, then confirm.
- [ ] **7.** Change `image.tag` via a committed values file and render the new image string — the S9 deploy knob, by hand.

## Explain aloud (interview drill — answer in 60–90 seconds each)

- [ ] "Helm is apt for Kubernetes" — where is that true, and what does it miss? Describe Helm's two machines (the manifest factory and the release ledger).
- [ ] What does `helm template` do, and what does it deliberately *not* do? Why is it your whole debugging loop?
- [ ] Walk through what `helm upgrade` actually computes. What does "an upgrade resets what the chart sets and leaves alone what it never set" mean, and how does Helm 4's server-side apply implement it?
- [ ] How does `helm rollback` behave when someone `kubectl`-edited the cluster between deploys? Is it `git revert` or `git reset`, and why?
- [ ] Where does a Helm revision physically live? What's inside it, and why does that mean rollback needs nothing from your laptop?
- [ ] State the values precedence order (defaults, `-f` files, `--set`). What wins, and how do multiple `-f` files resolve?
- [ ] Maps vs lists when layering values — which merges, which replaces, and which one is the classic "my override deleted things" bug?
- [ ] A chart's `values.yaml` is called its "public API." Why? How do you configure a chart you didn't write, and what do you never do?
- [ ] `helm upgrade` fails with "field is immutable / forbidden" on a StatefulSet or a selector. Whose decision was that — Helm's or the cluster's — and what's the real fix (not a Helm flag)?
- [ ] What is drift, why doesn't Helm notice it on its own, and what closes it — this section's manual way and Section 9's automatic way?
- [ ] Why is `capstone/chart/` the deployable artifact the rest of the course points at? What is the single knob a deploy turns, and where does it live?
- [ ] You're handed a third-party chart to install in prod. What do you read, in what order, before you trust it? (Name the Bitnami/Grafana cautionary tales.)

## Gate

- [ ] `notes.md` filled in my own words
- [ ] `capstone/chart/` committed (Chart.yaml, values.yaml, values-local.yaml, templates, `_helpers.tpl` — no secrets; the postgres password is a placeholder only)

When all boxes are checked, say so — the next section (Terraform) gets written against your notes, and it installs this exact chart.
