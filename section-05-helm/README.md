# Section 05 — Helm (stub)

**Status:** stub — written when Section 04 completes.

**Goal:** stop copy-pasting YAML. Package the capstone stack as a Helm chart with values for dev/prod, and consume third-party charts the way every real cluster does.

**You'll be able to:** write a chart from scratch (templates, values, helpers), install/upgrade/rollback releases, override values per environment, and vet a third-party chart before trusting it.

**Planned labs:** helm-ify the Section 4 manifests → values files + template functions → upgrade/rollback lifecycle → install a real third-party chart (redis) and read what it actually deployed.

**Builds on:** all Section 04 manifests.
