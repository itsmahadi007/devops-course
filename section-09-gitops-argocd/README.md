# Section 09 — GitOps with Argo CD (stub)

**Status:** stub — written when Section 08 completes.

**Goal:** the repo becomes the source of truth: Argo CD reconciles the cluster to what git says. Change YAML → merge → cluster converges. Manual `kubectl apply` retires.

**You'll be able to:** explain GitOps vs push-CI deployment honestly, install and operate Argo CD, structure an environments repo (dev/prod overlays), handle drift (someone kubectl-edited prod — what happens?), and roll back by revert.

**Planned labs:** install Argo CD on kind → app-of-apps for the capstone chart → sync policies + drift experiment → rollback-by-git-revert → wire the Section 2 CI to bump image tags via PR (full loop: push → build → PR → merge → cluster updates itself).

**Builds on:** Sections 2, 5, 8 — this ties the whole pipeline together.
