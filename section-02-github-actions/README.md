# Section 02 — CI/CD with GitHub Actions (stub)

**Status:** stub — written in full when Section 01's checkpoint passes, adapted to its notes.

**Goal:** every push to the capstone runs test → build → push-to-GHCR automatically; a deploy job ships it to vps-lab over SSH — a complete, real pipeline.

**You'll be able to:** read/write workflow YAML fluently, use the cache and matrix features, wire secrets properly, build+push Docker images in CI, do an SSH deploy job, and debug failed runs fast.

**Planned labs:** first workflow anatomy → lint+test on push → docker build/push with GHCR token → cache the build → SSH deploy to vps-lab → branch-protection with required checks.

**Builds on:** Lab 3's image, Lab 5's vps-lab, Lab 6's registry flow.
