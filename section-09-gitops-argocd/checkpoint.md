# Checkpoint — Section 09: GitOps with Argo CD

Pass every task **from memory** — no peeking at the labs. If you have to peek, the section isn't done yet; redo that lab tomorrow and try again.

## Practical tasks

- [ ] **1.** From a blank cluster (or a fresh kind cluster), install Argo CD with the correct flags, retrieve the initial admin password the official way, and reach the UI on host port 9100. Target: under 10 minutes, no references.
- [ ] **2.** Write an `Application` manifest from scratch that points at `capstone/chart/` on `main`, deploys to a namespace it creates, and syncs it — get it to `Synced` / `Healthy`.
- [ ] **3.** Enable auto-sync + prune + self-heal. Then `kubectl scale` the Deployment to 4 replicas and prove, without touching anything else, that it returns to the git-declared count. Explain what happened as it happens.
- [ ] **4.** Change a value (e.g. replica count) through a git branch → PR → merge, and show Argo rolling it out. Then roll it back with `git revert` and show the cluster following.
- [ ] **5.** Build an app-of-apps root that plants a staging and a prod environment of the capstone (same chart, two value overlays, two namespaces) from a single `kubectl apply`.
- [ ] **6.** Seal a secret with `kubeseal`, commit the `SealedSecret`, let Argo deploy it, and show the decrypted `Secret` appearing in the cluster — with the plaintext never committed.

## Explain aloud (interview drill — answer in 60–90 seconds each)

- [ ] Push vs pull deployment — draw both arrows and say which side holds the cluster's credentials in each, and why that difference is the whole reason GitOps exists.
- [ ] "The deploy history IS the git history." Unpack that: how do you answer who/when/what/why-changed, and how do you roll back — with no separate tooling?
- [ ] Why should prod credentials never sit in CI? What is CI allowed to do in a proper GitOps setup, and what is it forbidden from doing?
- [ ] Sync status vs health status — define each, and give a concrete example of every green/not-green combination and what it means.
- [ ] Walk through the three `automated` knobs (auto-sync, prune, self-heal) — the distinct trigger each one answers, and why prune and self-heal are opt-in rather than default.
- [ ] Drift detection is called "a feature." Explain the 3am-hack scenario and how self-heal turns an invisible push-model problem into a self-correcting one.
- [ ] Name Argo's three internal machines: what diffing does (and what it normalizes away), how health is assessed per resource and rolled up, and what sync waves order.
- [ ] What is app-of-apps, and what problem does it solve that a pile of individual `kubectl apply`s doesn't?
- [ ] How do you run staging and prod off one chart without copying it? Which Section 5 idea is that?
- [ ] Why can't you commit a Kubernetes `Secret` to a public repo? Explain Sealed Secrets as public-key crypto (map it to SSH keys from Section 1), and what the namespace+name scope protects against.
- [ ] "CI opens a PR instead of pushing to main or touching the cluster." Why is that split the safe design, and why did you choose it over Argo Image Updater?

### From-memory recall

- [ ] Why does the Argo install need `--server-side --force-conflicts`? What exact error appears without it, and what's the root cause (hint: annotation size)?
- [ ] Which Argo component runs the reconcile loop, which one clones git + runs `helm template`, and which one is just the front door?
- [ ] Why is a public repo enough for the git→cluster read path with zero secrets, and what would change on a private repo (and what would NOT change)?
- [ ] The `:latest` → `sha-<commit>` tag policy in the CI bump — which Section 1 lesson is that, and why does pinning matter for GitOps specifically?

## Gate

- [ ] `notes.md` filled in my own words
- [ ] Everything committed (`gitops/` layout, env value overlays, the `bump-image-tag` workflow, the `SealedSecret` — no plaintext secrets, no admin password, no private keys)

When all boxes are checked, say so — the next section (S10 — LLM Serving Infrastructure) gets written against your notes.
