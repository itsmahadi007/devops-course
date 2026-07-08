# Lab 4 — The full loop: change git → PR → Argo rolls it out

**Goal:** deploy a change the way you will for the rest of your career — edit values, open a PR, merge, and watch Argo roll it out with nobody touching the cluster. Then automate the tedious half: make the Section 2 CI **open the image-bump PR for you** on every build. This closes the whole pipeline: push code → CI builds image → CI opens a PR bumping the tag → you merge → Argo deploys.

## The mental map (read this first)

Two halves of one loop. First, the **human half** you drive by hand today:

```
  edit capstone/chart/values.yaml   (change a value)
        │  git commit + push to a branch
        ▼
  open a PR  ── review, CI checks, branch protection ──▶ merge to main
        │
        ▼
  Argo CD sees main changed ──▶ helm template with new values ──▶ rollout
        │
        ▼
  cluster now matches the merged commit.   Deploy = the merge. Rollback = git revert.
```

Then the **machine half** — the piece that makes it ergonomic. Right now, when Section 2's CI builds a new image (say tag `sha-abc1234`), *someone* has to edit `values.yaml` to point at that new tag. Doing it by hand defeats the automation. So CI does it:

```
  git push code
        ▼
  CI (S2): test → build → push ghcr.io/itsmahadi007/capstone:sha-abc1234
        ▼
  CI: open a PR that bumps image.tag → sha-abc1234   ← the new job you add
        ▼
  you merge the PR (the human gate stays)
        ▼
  Argo deploys sha-abc1234.
```

The crucial design choice, and the reason this is the "simple variant" the spec asks for: **CI opens a PR, it does not push to main and it never touches the cluster.** CI's power stays boxed to "build an image and propose a git change." The human merge is the deploy gate; Argo is the only thing with cluster rights. Every property from the lesson (audit = git log, rollback = revert, creds never in CI) holds.

> There's a fancier variant — **Argo Image Updater**, a controller that watches the registry and bumps tags automatically. It's more magic and less visible. The PR variant is deliberately chosen because the diff is reviewable and the trigger is explicit; you'll mention Image Updater in interviews as "the auto option I chose *not* to use, because a reviewable PR is the safer default."

## Steps

### 1. The human half — change a value via PR

Pick a visible, safe knob. The capstone chart's `values.yaml` has a `replicaCount` (from the S5 chart). Change it through a proper PR so you feel the whole path.

```bash
cd /Users/mahadihassan/Documents/plan/projects/devops-course
git checkout -b bump-replicas
```

Edit `capstone/chart/values.yaml` — change `replicaCount` from `1` to `2` (if your chart names it differently, edit the equivalent; the point is one reviewable value change).

```bash
git add capstone/chart/values.yaml
git commit -m "feat(capstone): run 2 replicas"
git push -u origin bump-replicas
gh pr create --fill --title "Run 2 replicas" --body "Scale capstone to 2 replicas via GitOps."
```

`gh pr create` opens the PR from your terminal (the `gh` you've used since Section 1). Because `main` is the branch Argo watches, **nothing deploys yet** — the change is on a branch, invisible to Argo. That's correct: unreviewed changes don't reach prod.

Merge it (in a real team a reviewer would; solo, you merge your own):

```bash
gh pr merge --squash --delete-branch
git checkout main && git pull
```

The instant that merge lands on `main`, the deploy clock starts — not because you ran anything, but because git changed.

### 2. Watch Argo roll it out

```bash
kubectl -n capstone get pods -w
```

Within the poll interval (default ~3 min; click **Refresh** in the UI or `argocd app sync capstone` to hurry), a **second capstone pod appears**. You changed a file in a PR and a pod materialized in the cluster — no `kubectl apply`, no `helm upgrade`, no cluster credentials anywhere in your hands. `argocd app get capstone` shows the new synced revision matching your merge commit sha.

This is worth pausing on. The deploy *was* the merge. If you `git log capstone/chart/values.yaml` you're reading the deploy history. If this rollout were bad, `git revert <merge-sha>` + push would scale it straight back to 1 — **rollback is a revert**, no special tooling.

#### Speeding up the poll (and how prod does it)

Argo polls git every ~3 minutes by default. That's fine for a lab but feels slow. In production you'd configure a **git webhook** so GitHub pings Argo the instant `main` changes — instant deploys, no polling. On kind (no public URL for GitHub to reach) you can't easily receive a webhook, so use the UI **Refresh** button or `argocd app get capstone --refresh` to force an immediate compare. Know the webhook exists; it's why real GitOps feels instant.

### 3. Prove rollback-by-revert

Don't just talk about it — do it once so it's muscle memory:

```bash
git revert HEAD --no-edit      # revert the merge's file change (the replicaCount bump)
git push
argocd app get capstone --refresh
kubectl -n capstone get pods   # back to 1 pod
```

The revert is a normal commit that happens to undo the previous one. Argo treats it like any other change to `main` and reconciles the cluster back. This is the entire rollback story — no Helm revision numbers, no snapshots.

### 4. The machine half — CI opens the image-bump PR

Now automate the annoying part. Section 2's CI already builds and pushes `ghcr.io/itsmahadi007/capstone:sha-<commit>` on every push to `main`. Add a job that, after the push succeeds, opens a PR bumping the chart's `image.tag` to that new tag.

First, make sure the chart *has* an `image.tag` to bump. In `capstone/chart/values.yaml` it should look like (from S5 — adjust names to your chart):

```yaml
image:
  repository: ghcr.io/itsmahadi007/capstone
  tag: "latest"        # ← the line CI will rewrite to sha-<commit>
  pullPolicy: IfNotPresent
```

Pinning `tag` to a specific `sha-…` (never `latest`) is the whole game: it's the Section 1 "`:latest` bit me overnight" lesson made into policy — the running version is always an immutable, git-recorded tag.

Create `.github/workflows/bump-image-tag.yml`:

```yaml
name: bump-image-tag

# Runs AFTER the CI workflow finishes successfully on main.
on:
  workflow_run:
    workflows: ["ci"]          # ← the name: of your Section 2 workflow (.github/workflows/ci.yml)
    types: [completed]
    branches: [main]

permissions:
  contents: write              # push the bump branch
  pull-requests: write         # open the PR

jobs:
  bump:
    # only if CI actually succeeded
    if: ${{ github.event.workflow_run.conclusion == 'success' }}
    runs-on: ubuntu-latest      # a plain hosted runner is fine — this job never touches the cluster
    steps:
      - uses: actions/checkout@v4
        with:
          ref: main

      - name: Compute the image tag CI just pushed
        id: tag
        run: echo "value=sha-${GITHUB_SHA::7}" >> "$GITHUB_OUTPUT"
        # matches S2's docker/metadata-action sha tag. If your CI tags differently, mirror it here.

      - name: Install yq
        run: sudo snap install yq

      - name: Bump image.tag in values.yaml
        run: |
          yq -i '.image.tag = "${{ steps.tag.outputs.value }}"' capstone/chart/values.yaml

      - name: Open a PR with the bump
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          BRANCH="bump/image-${{ steps.tag.outputs.value }}"
          git config user.name  "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git checkout -b "$BRANCH"
          git add capstone/chart/values.yaml
          git commit -m "chore(capstone): bump image to ${{ steps.tag.outputs.value }}"
          git push -u origin "$BRANCH"
          gh pr create --fill \
            --title "Deploy capstone ${{ steps.tag.outputs.value }}" \
            --body "Automated image bump. Merge to deploy via Argo CD."
```

Line-by-line, the parts that matter:

- **`on: workflow_run`** — this workflow chains *after* your `ci` workflow completes, so the image is already in GHCR before we propose deploying it. The `if:` guard skips the bump if CI failed — you never propose deploying a broken build.
- **`permissions:`** — the Section 2/Lab 6 lesson (authz is per-action): the built-in `GITHUB_TOKEN` gets *exactly* `contents:write` + `pull-requests:write`, nothing more. Least privilege, no personal token, no secret you manage.
- **`yq -i '.image.tag = …'`** — the one-line edit that is the entire "deploy" from CI's side. CI's whole cluster-facing power is "rewrite one string in a YAML file and ask a human to merge it."
- **`gh pr create`** — same tool you used by hand in step 1, now in CI. GitHub deliberately does **not** trigger further workflows from a `GITHUB_TOKEN`-created PR, so this can't cause an infinite CI loop. (A nice safety accident worth knowing.)

Commit this workflow on a branch and PR it in (dogfooding the flow):

```bash
git checkout -b add-bump-workflow
git add .github/workflows/bump-image-tag.yml capstone/chart/values.yaml
git commit -m "ci(gitops): open image-bump PR after each successful build"
git push -u origin add-bump-workflow
gh pr create --fill
gh pr merge --squash --delete-branch
```

### 5. Trigger the full loop end to end

Make any trivial code change to the capstone (a comment in `capstone/app/main.py`), push it through, and watch the whole chain:

```bash
git checkout main && git pull
# ...edit a comment in capstone/app/main.py...
git add -A && git commit -m "chore(capstone): trivial change to trigger the pipeline" && git push
```

Now watch the Actions tab (or `gh run watch`): the `ci` workflow runs → builds+pushes `sha-<newcommit>` → the `bump-image-tag` workflow fires → a **new PR appears** titled `Deploy capstone sha-<newcommit>`. Review the one-line diff, merge it:

```bash
gh pr list                        # the bot's bump PR is here
gh pr merge <number> --squash --delete-branch
```

…and within the poll interval, `kubectl -n capstone get pods` shows the pod recreated with the new image tag. `kubectl -n capstone get deployment capstone -o jsonpath='{..image}'` confirms it's the `sha-<newcommit>` tag. **That is the whole pipeline:** one code push → automated build → automated deploy-proposal → one human merge → Argo reconciles. You never ran a deploy command or held a cluster credential.

#### If the bump PR never appears

Check the Actions tab for the `bump-image-tag` run. Common causes: (a) the `workflows: ["ci"]` name doesn't exactly match your Section 2 workflow's `name:` field — fix the string; (b) CI failed, so the `if:` guard correctly skipped the bump — fix CI first; (c) the tag format in "Compute the image tag" doesn't match what S2's `metadata-action` actually produced — check GHCR for the real tag string and mirror it. This is the same "the automation only does what you told it exactly" discipline as a Dockerfile.

## Verify

```bash
gh run list --limit 3            # ci then bump-image-tag, both green
kubectl -n capstone get deployment capstone -o jsonpath='{.spec.template.spec.containers[0].image}' ; echo
```

The image ends in `sha-<the-commit-you-just-pushed>` — an immutable tag, recorded in a merged PR, deployed by Argo, with your hands never on the cluster.

Then answer aloud:

**1. In this design, what is CI allowed to do, and what is it deliberately *not* allowed to do? Why does that split matter?**

<details><summary>Answer (read after attempting aloud)</summary>

CI may build/push the image and open a PR that rewrites one line of `values.yaml`. It may **not** push to main and **not** touch the cluster — it holds no cluster credentials. The split matters because CI is the most-attacked surface (runs arbitrary PR code, pulls third-party actions); keeping cluster creds out of it means a compromised CI can at most propose a change a human still has to merge. Blast radius stays tiny.

</details>

**2. You merged a PR and a new pod appeared with no deploy command. What actually triggered the deploy, and where's the deploy history?**

<details><summary>Answer (read after attempting aloud)</summary>

The merge changed `main`; Argo CD, watching that branch, re-rendered the chart and reconciled the cluster to the new commit. The "deploy" *was* the merge. The deploy history is the git history of the repo — `git log` on `values.yaml` is the log of every version deployed, with the PR as the who/why.

</details>

**3. How do you roll back, and why is there no special rollback tool?**

<details><summary>Answer (read after attempting aloud)</summary>

`git revert` the offending commit and push; Argo reconciles the cluster back to the reverted state. No special tool because the desired state lives in git and Argo always converges to it — undoing a deploy is just another commit. (Helm revisions still exist underneath, but you drive everything from git.)

</details>

**4. Why open a PR from CI instead of using Argo Image Updater to auto-bump tags?**

<details><summary>Answer (read after attempting aloud)</summary>

The PR variant keeps a *reviewable diff* and an *explicit human merge gate* — you see exactly what will deploy and approve it, and the trigger is visible in git. Image Updater auto-bumps by watching the registry: less visible, no review step, more magic. The PR variant is the safer default; Image Updater is the option you mention as consciously not chosen (or reserved for low-risk environments).

</details>

## Clean up

Leave everything running — the pipeline is now the point. Revert the `replicaCount` back to `1` via one more small PR if you want the cluster light for Lab 5 (which adds a second environment). Stop the port-forwards when idle; re-run next session.
