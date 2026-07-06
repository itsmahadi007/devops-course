# vps-lab — the fake VPS

A Docker container that behaves like a rented server: Debian 12, `sshd`, a sudo user, key-only auth. You SSH into it exactly like a Hetzner/DigitalOcean box — no cloud bill.

**This folder starts empty on purpose.** You build it yourself in **Section 1, Lab 5** — writing the Dockerfile IS the exercise. The finished `Dockerfile` and `docker-compose.yml` get committed here when the lab is done.

Used by: Section 1 (built here), Section 3 (all Linux/networking labs run inside it over SSH), Section 2 (CI deploy target).

Keys live in `vps-lab/keys/` — **gitignored, never committed**.
