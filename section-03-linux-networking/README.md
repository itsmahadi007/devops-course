# Section 03 — Linux & Networking gaps (stub)

**Status:** stub — written when Section 02 completes.

**Goal:** close the specific gaps between "can use a server" and "can run a server": TLS from first principles, reverse proxying, firewalls, process supervision, debugging with the standard toolbox. All labs run INSIDE vps-lab over SSH.

**You'll be able to:** put nginx in front of the capstone as a reverse proxy, issue and install a TLS cert (local CA with mkcert; Let's Encrypt theory), reason about DNS records you already configure but now understand end-to-end, use `ss`/`curl -v`/`dig`/`tcpdump` to debug, and harden a fresh box (fail2ban concepts, least-privilege users).

**Planned labs:** day-one server hardening ritual → nginx reverse proxy for capstone → TLS with a local CA + HTTPS end-to-end → DNS deep-read (A/AAAA/CNAME/MX/TXT + propagation) → network debugging drills → break-and-fix scenarios.

**Builds on:** vps-lab (Lab 5), capstone image (via the Section 2 deploy).
