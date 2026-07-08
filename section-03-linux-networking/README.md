# Section 03 — Linux & Networking (inside vps-lab)

**Status:** written — start after Section 02 · **Time:** ~1.5 weeks at 2–4h/day · **Labs:** 6

Section 2 ended with a robot: every push builds the capstone, and a deploy job SSHes into vps-lab and runs it there. The working chain is **Mac:9030 → vps-lab:8080 → inner container:8000**. But so far vps-lab has only been a place where deploys *land*. This section makes you its **administrator** — because between "the container is running" and "users can reach it safely" sits an entire layer of Linux that every ops tool quietly assumes you know.

## The mental model (read first)

**Linux is the substrate; everything else in this course is a UI over it.** Four kernel ideas carry the whole trade:

1. **Files with rulebooks** — every file carries an owner name-tag and a permissions rulebook (you met owner-vs-rulebook in Section 1 Lab 3; now we go all the way: octal, special bits, umask).
2. **Processes with signals** — everything running is a process in a tree; the only way to talk to one from outside is a signal (Section 1's "knock on the door", now the full vocabulary).
3. **Sockets** — every network service is just a process holding a numbered mailbox open. One command (`ss`) lists every mailbox and who holds it.
4. **Packet checkpoints** — the kernel runs fixed checkpoints on every packet's path (netfilter). Firewalls, and Docker's `-p` flag itself, are rules at those checkpoints.

Docker didn't replace any of this — it *automates* it (namespaces around processes, iptables rules around sockets). Kubernetes automates it again at scale. When an abstraction leaks — and at 3am it always leaks — the debugging happens at THIS layer. This section is learning the substrate on purpose, instead of at 3am.

**The arc:** permissions → processes → network toolbox, then the payoff: **nginx as a reverse proxy** in front of the deployed capstone (host port **9040**), then **TLS from first principles** with a self-signed cert (**9041**), then a **firewall** around all of it. End state:

```
 YOUR MAC                          vps-lab (the "VPS")
┌─────────────┐  :9040 (http) ┌────────────────────────────────────────┐
│ curl /      ├──────────────▶│ :80 ─┐                                 │
│ browser     │  :9041 (https)│      ├─ nginx ──▶ 127.0.0.1:8080 ─┐    │
│             ├──────────────▶│ :443─┘                            ▼    │
│             │  :9030 (raw)  │                      inner Docker:     │
│             ├──────────────▶│ :8080 ─────────────▶ capstone :8000    │
│             │  :9022 (ssh)  │                                        │
│             ├──────────────▶│ :22  sshd (PID 1)                      │
└─────────────┘               └────────────────────────────────────────┘
```

### Where the illusion is honest (read this once, believe it forever)

vps-lab behaves like a rented server from your terminal's point of view — but it's a container, and this section is exactly where the differences show. Naming them beats pretending:

| A real VPS | vps-lab | What you'll notice |
|---|---|---|
| Its own kernel | borrows Docker Desktop's VM kernel | `uname -r` says `linuxkit`; `/proc/loadavg`, `meminfo`, `nproc` report the **whole VM**, not the container — a real production gotcha we'll exploit as a lesson |
| systemd is PID 1 | sshd is PID 1 (Section 1's foreground rule) | no `systemctl`; services start via `service …` or by hand. We read **real systemd unit files on paper** — apt installs them even though nothing runs them |
| installed packages survive reboots | survive `stop`/`start`, die on **recreate** (`down`, compose config change) | "reimage ritual" documented in Lab 4 — writing that runbook is itself real ops practice |
| provider gives you a rescue console for lockouts | `docker exec` from your Mac | which is why we can do firewall experiments a real box would punish |
| public IP + domain name | localhost + published ports | Let's Encrypt can't reach us → Lab 5 does self-signed for real, Let's Encrypt on paper |

## Why this matters for jobs

- "**Walk me through what happens when a user hits your API**" is the single most common infra screening question. After Lab 5 your answer runs: TLS handshake → nginx → proxy headers → upstream socket → app — with a live system you built behind every sentence.
- **Debugging on a box you've never seen** is the actual job. `ss -tlnp`, "refused vs timeout", reading nginx error logs — these are the difference between "can use a server" and "can run a server".
- Reverse proxy + TLS on a VPS is the **bread-and-butter freelance infra gig** (the contract-market entry lane from `docs/why-this-course.md`).
- CKA's Linux-y bits (permissions, processes, services, iptables-shaped networking) are all here. Kubernetes Services literally ARE iptables rules written by kube-proxy — Lab 6 is you reading that mechanism a section early.

## Labs

| Lab | What you build | Proves |
|---|---|---|
| [1 — Permissions deep dive](labs/lab-01-permissions-deep-dive.md) | nothing new — you master the rulebook | octal, x-on-directories, setuid, sticky bit, umask, perm audits |
| [2 — Processes & signals, ops side](labs/lab-02-processes-signals.md) | a supervision mental model | ps/STAT, /proc, signal vocabulary, nohup, systemd on paper |
| [3 — Networking toolbox](labs/lab-03-networking-toolbox.md) | fluency, not artifacts | ip/ss/dig/nc, HTTP spoken by hand, refused-vs-timeout |
| [4 — nginx reverse proxy](labs/lab-04-nginx-reverse-proxy.md) | nginx fronting the capstone on **9040** | proxy_pass, forwarding headers, access logs, 502s |
| [5 — TLS + HTTPS](labs/lab-05-tls-https.md) | self-signed HTTPS on **9041** | chain of trust, SANs, cert ops, Let's Encrypt theory |
| [6 — Firewall (iptables/nftables)](labs/lab-06-firewall-iptables.md) | rules inside vps-lab only | chains, Docker's DNAT, DROP vs REJECT, lockout + recovery |

Do them in order. Each ends with **Verify** (proof it worked) and **Clean up**.

### Progress

- [ ] Lab 1 — Permissions deep dive
- [ ] Lab 2 — Processes & signals
- [ ] Lab 3 — Networking toolbox
- [ ] Lab 4 — nginx reverse proxy
- [ ] Lab 5 — TLS + HTTPS
- [ ] Lab 6 — Firewall

## Before you start — confirm what Section 2 left behind

```bash
# on your Mac
curl -s localhost:9030/health
ssh -i vps-lab/keys/vps_key -p 9022 mahadi@localhost 'sudo docker ps'
```

Expect the health JSON and one running capstone container publishing `8080->8000`. If either fails, use the **reimage ritual** in Lab 4 (step 2) to restore the Section 2 state — it works standalone.

## Reading (curated, ~2h total)

- [nginx: Beginner's Guide](https://nginx.org/en/docs/beginners_guide.html) — master/workers, config reload, the 15-minute official tour
- [nginx admin guide: reverse proxy](https://docs.nginx.com/nginx/admin-guide/web-server/reverse-proxy/) — the exact pattern Lab 4 builds
- [The Illustrated TLS 1.3 Connection](https://tls13.xargs.org/) — every byte of a handshake, annotated; skim before Lab 5, return after
- [Let's Encrypt: How It Works](https://letsencrypt.org/how-it-works/) — the missing piece Lab 5 teaches on paper
- [man 5 proc](https://man7.org/linux/man-pages/man5/proc.5.html) — skim the per-PID entries after Lab 2; it's the kernel's own docs for its dashboard
- [Arch Wiki: iptables](https://wiki.archlinux.org/title/Iptables) — the clearest chains/tables walkthrough in existence; read after Lab 6 to consolidate

## Done when

Every task in [checkpoint.md](checkpoint.md) passes from memory, and [notes.md](notes.md) is filled in your own words. Then Section 4 gets written — where the kind cluster arrives, compose habits become manifests, healthchecks become probes, and the iptables rules you can now read turn out to be how Kubernetes Services work.
