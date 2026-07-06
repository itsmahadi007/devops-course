# Section 04 — Kubernetes Core (stub)

**Status:** stub — written when Section 03 completes.

**Goal:** the center of gravity of the whole course. Run the capstone stack on a local kind cluster and operate it: deploy, expose, scale, configure, break, debug. CKA-aligned from day one.

**You'll be able to:** explain the control plane honestly, write Deployment/Service/Ingress/ConfigMap/Secret manifests by hand, use probes (your Lab 3 healthcheck concept, K8s-style), scale with HPA, debug with `kubectl describe/logs/events`, and survive the standard "pod is CrashLooping — go" interview scenario.

**Planned labs:** install kind + kubectl, cluster anatomy tour → first Deployment + Service for capstone → ConfigMaps/Secrets + probes → Ingress with local ingress-nginx → Redis as a StatefulSet mini-intro + HPA → kill-things-and-debug drills.

**Builds on:** capstone image on GHCR (Sections 1–2).
