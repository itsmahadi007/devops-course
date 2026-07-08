# Section 09 — GitOps with Argo CD

**Status:** in progress · **Time:** ~1 week at 2–4h/day · **Labs:** 5

Back in Section 1 Lab 4 you wrote it down yourself: *"`up` makes reality match the file"* — you describe the end state, Docker does the doing. Then, watching compose recreate only the drifted container, you wrote the line that turned out to be the whole course: *"that reconcile loop IS Kubernetes' whole personality."* Section 4 proved it — kill a pod, the Deployment controller brings it back, because the controller's only job is *close the gap between what-you-declared and what-is*.

**GitOps is that exact same reconcile loop, pointed at git.** Not "reality vs a file on your laptop" (compose) and not "reality vs an object in etcd" (Kubernetes) — but **reality vs a commit in a git repo**. A controller (Argo CD) watches your repo, watches your cluster, and whenever they disagree it makes the cluster match the repo. That's it. Everything else in this section is detail hanging off that one sentence.

Section 8 gave the capstone stack eyes (Prometheus/Grafana/Loki). This section changes *how the stack gets deployed at all*: the manual `kubectl apply` / `helm upgrade` you've done since Section 4 retires, and the repo becomes the single source of truth. Section 10 then bolts a real self-hosted LLM onto `/ask` — and because of this section, shipping it will be a pull request, not an SSH session.

## The mental model (read first)

### Push vs pull — who initiates the deploy?

Everything you've built so far is **push** deployment. Something *outside* the cluster (your laptop, or the Section 2 CI runner) holds the cluster's credentials, reaches *in*, and shoves the new version:

```
  PUSH (what you've done so far)
  ┌──────────┐   kubectl/helm/ssh   ┌───────────┐
  │ CI runner│ ───────────────────▶ │  cluster  │
  │ (holds   │   "here, run this"   │           │
  │  creds)  │                      └───────────┘
  └──────────┘
  Deploy happens WHEN the pipeline runs. Cluster is passive.
```

**Pull** deployment inverts the arrow. An agent *inside* the cluster (Argo CD) reaches *out* to git, reads the desired state, and applies it to its own cluster. Nobody outside ever gets cluster credentials:

```
  PULL (GitOps — this section)
  ┌──────────┐   git push (a PR)    ┌──────────────────────────┐
  │   you /  │ ───────────────────▶ │ git repo (desired state)  │
  │    CI    │                      └──────────────────────────┘
  └──────────┘                                 ▲
                                               │ "what should I be?"
                                               │ (polls / webhook)
                                      ┌────────┴────────┐
                                      │  Argo CD  ──────┼──▶ applies to
                                      │ (in cluster)    │    its own cluster
                                      └─────────────────┘
  Deploy happens WHEN git changes. Cluster pulls its own truth.
```

The difference sounds academic until you say it as an interview line: **in push, the deploy tool needs god-rights on prod; in pull, prod's credentials never leave prod.** That single property is why GitOps exists.

### Git as the desired-state store — and why that's the good part

You already trust git for code. GitOps says: put the *deployment manifests* (or Helm values) in git too, and treat the repo as the one true answer to "what is supposed to be running?" Every consequence that makes GitOps worth the setup falls straight out of that:

- **The deploy history IS the git history.** `git log` on the repo is your deploy log. Who changed prod, when, why (the PR), what exactly changed (the diff) — all already there, for free, with no separate audit system.
- **Rollback is `git revert`.** No special rollback tooling, no "which Helm revision was good?" archaeology — revert the commit, Argo syncs the cluster back. The Section 5 `helm rollback` still exists underneath, but you drive it from git.
- **Review gates come free.** Changing prod requires a merged PR → required reviewers, required CI checks (Section 2), branch protection. The cluster physically cannot change except through that funnel.
- **Disaster recovery is a re-clone.** Cluster gone? Point a fresh Argo CD at the same repo and it rebuilds every app. The repo is the backup.

### Drift detection is a *feature*, not a nag

"Drift" = the live cluster no longer matches git. Someone ran `kubectl edit deployment` at 3am to stop a fire and never told anyone; a `kubectl scale` during an incident stuck around. In push-world that change is *invisible* — nothing compares live-state to intended-state, so the hack silently becomes the new normal until it bites.

Argo CD is *continuously* diffing live-vs-git. So drift becomes a **first-class, visible status** (`OutOfSync`), and you get to choose the policy:

- **Show me** (manual sync): Argo flags the drift, you decide.
- **Fix it automatically** (self-heal): Argo reverts the cluster back to git within seconds — the 3am hack undoes itself, and the only durable way to change prod is to change git.

That is the reconcile loop from your Lab 4 notes, now with a UI and a revert button. Same personality, pointed at a repo.

### Why prod credentials should never sit in CI

Sit with the push diagram again. In Section 2, your CI runner had a deploy SSH key and shoved images onto vps-lab. Scale that mental model to a real company: the CI system ends up holding **write credentials to every environment including prod**. CI is also the single most attacked surface you own — it runs arbitrary code from every PR, pulls hundreds of third-party actions, and a leaked token there is a leaked token to prod. One compromised action = game over.

GitOps removes the credential from CI entirely. CI's job shrinks to what CI is good at: **build the image, run the tests, and open a pull request that changes git.** It never touches the cluster. The cluster's credentials live only inside the cluster, held by Argo CD. This is the honest, defensible reason the industry moved to pull-based deploys — not fashion, blast-radius.

### The pieces of Argo CD (names you'll use all section)

- **Application** — a Kubernetes custom resource (Argo installs the CRD) that says *"take the manifests at `repo@revision:path`, render them, and keep namespace X matching them."* One Application ≈ one deployable unit.
- **Sync** — the act of applying git's desired state to the cluster. **Manual** (you click / `argocd app sync`) or **automated** (Argo does it on every detected change).
- **Sync status** — `Synced` (live matches git) or `OutOfSync` (they differ). This is the *diff* result.
- **Health status** — `Healthy` / `Progressing` / `Degraded` / `Missing`. This is Argo's per-resource assessment of whether the thing actually *works* (a Deployment with all replicas available = Healthy; crash-looping = Degraded). Sync and health are **orthogonal**: you can be `Synced` but `Degraded` (git's version is broken), or `OutOfSync` but `Healthy` (someone hand-scaled it and it's fine, just not what git says).
- **App-of-apps** — one Application whose git path contains *other* Application manifests. Bootstrap the root, and it plants the whole orchard. This is how you manage many apps / many environments declaratively.

## Why this matters for jobs

- "Walk me through your deployment pipeline" — answering with *"CI builds and opens a PR, Argo CD reconciles the cluster from git, rollback is a revert"* signals senior-level thinking instantly. It's the expected answer at any shop hiring for Kubernetes in 2026.
- "How do you handle configuration drift?" and "how do you roll back?" are near-guaranteed platform-engineer screening questions — this section is the answer, with a live demo you can show from this repo.
- Argo CD is the most-used GitOps tool on the CNCF landscape (graduated project). Naming its Application CRD, sync waves, and self-heal from memory is a concrete résumé keyword and a portfolio artifact — the `gitops/` folder you build here is public evidence.
- The clean "credentials never leave the cluster" security story is exactly the reasoning a security-conscious interviewer wants to hear unprompted.

## Tools (latest stable — verify before installing)

| Tool | Version (verify latest) | Install |
|---|---|---|
| Argo CD (server, into cluster) | **v3.3.12** | `kubectl apply` the pinned manifest (Lab 2) |
| `argocd` CLI | latest | `brew install argocd` |
| Sealed Secrets controller | **v0.38.3** | `kubectl apply` the pinned manifest (Lab 5) |
| `kubeseal` CLI | **0.38.4** | `brew install kubeseal` |

You already have from earlier sections: `kubectl` + `kind` (S4), `helm` (S5), `gh` (S1/S2), and a running S4 kind cluster with the `capstone/chart/` Helm chart (S5) in this repo. This section adds *nothing to your Mac's port map beyond the 9100–9109 block* (Argo UI port-forward on **9100**, capstone verify port-forward on **9101**).

## Labs

| Lab | What you build | Proves |
|---|---|---|
| [1 — GitOps mental model + repo layout](labs/lab-01-gitops-mental-model.md) | the `gitops/` folder; push-vs-pull on paper | why pull-based deploys exist; where desired state lives |
| [2 — Install Argo CD + first Application](labs/lab-02-install-argocd.md) | Argo CD on kind, UI on 9100, an app pointing at `capstone/chart/` | Application CRD, sync/health status, manual sync |
| [3 — Sync policies + the drift experiment](labs/lab-03-sync-policies.md) | auto-sync + prune + self-heal | the reconcile loop's final form — hand-edit, watch it revert |
| [4 — The full loop: change git → PR → rollout](labs/lab-04-full-loop.md) | a values PR by hand, then CI that bumps the image tag via PR | push → build → PR → merge → cluster updates itself |
| [5 — App-of-apps, environments, secrets-in-git](labs/lab-05-app-of-apps-envs-secrets.md) | staging + prod via a root app; one Sealed Secret | multi-env at scale; the honest secrets story |

Do them in order. Each ends with **Verify** (proof it worked) and **Clean up**.

## Reading (curated, ~1.5h total)

- [Argo CD — Getting Started](https://argo-cd.readthedocs.io/en/stable/getting_started/) — the canonical install + first-app walkthrough
- [Application spec reference](https://argo-cd.readthedocs.io/en/stable/user-guide/application-specification/) — every field you'll write in a manifest
- [Automated sync policy](https://argo-cd.readthedocs.io/en/stable/user-guide/auto_sync/) — prune + self-heal, read until Lab 3 feels obvious
- [Sync waves & phases](https://argo-cd.readthedocs.io/en/stable/user-guide/sync-waves/) — how Argo orders what it applies
- [Cluster bootstrapping (app-of-apps)](https://argo-cd.readthedocs.io/en/stable/operator-manual/cluster-bootstrapping/) — the Lab 5 pattern
- [OpenGitOps principles](https://opengitops.dev/) — the four principles, one page, memorize them for interviews

## Done when

Every task in [checkpoint.md](checkpoint.md) passes from memory, and [notes.md](notes.md) is filled in your own words. Then the next section (S10 — LLM serving) gets written against your notes.
