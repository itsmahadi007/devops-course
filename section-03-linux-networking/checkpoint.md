# Checkpoint — Section 03: Linux & Networking

Pass every task **from memory** — no peeking at the labs. If you have to peek, the section isn't done yet; redo that lab tomorrow and try again.

## Practical tasks

- [ ] **1.** On a fresh file, set `rwxr-x---` two ways (octal and symbolic) and confirm they're identical. Then create a directory with a file inside, remove the directory's `x` bit, and demonstrate that you can `ls` it but not `cat` the file — explain why in one sentence.
- [ ] **2.** Find every setuid-root binary on the box in one command, and make a copy of `/bin/id` setuid-root to prove `euid` changes when a normal user runs it. (Then delete it — it's a footgun.)
- [ ] **3.** Start a background process, find its PID two different ways (`jobs`/`$!` and `pgrep`), read its `/proc/<pid>/cmdline` and open FDs, then stop it with SIGTERM. Separately, `kill -9` a process and show the exit code is 137.
- [ ] **4.** Write a systemd unit file for the capstone from memory (the three sections, `ExecStart` foreground, `Restart=always`, `User=`, `WantedBy=`) and explain aloud what each maps to in compose and Kubernetes.
- [ ] **5.** With `ss -tlnp`, list every listening socket on vps-lab and name the owner of each. Then speak raw HTTP to the capstone by hand with `nc` and get a 200.
- [ ] **6.** Cause a "connection refused" and a "connection timeout" *on purpose* with `nc`/curl, and state which firewall target (Lab 6) produces each.
- [ ] **7.** From nothing, put nginx in front of the capstone: install it, write the reverse-proxy config with the four forwarding headers, `nginx -t`, reload, and prove the request went *through* nginx (the `Server:` header). Then stop the upstream and diagnose the 502 from the error log.
- [ ] **8.** Generate a self-signed cert with a correct SAN, serve the capstone over HTTPS, show curl rejecting it (self-signed) and then accepting it with `--cacert`. Read the cert and point out the line that proves it's self-signed.
- [ ] **9.** Find the DNAT rule that `docker run -p 8080:8000` created, in the right table and chain. Then firewall yourself out of SSH and recover via the rescue console — without recreating the container.

## Explain aloud (interview drill — answer in 60–90 seconds each)

- [ ] Read `-rwsr-xr-x root root /usr/bin/passwd` aloud: what is every field, what does the `s` do, and why is that bit a security-audit target?
- [ ] `x` on a file vs `x` on a directory — the two completely different meanings, and the bug that appears when a parent directory loses its `x`.
- [ ] `umask 022`: what permissions do a new file and a new directory get, with the arithmetic, and why do directories start from 777 not 666?
- [ ] setuid vs setgid vs sticky bit — one real-world use of each (`passwd`, a shared team folder, `/tmp`), and the leading octal digit for each.
- [ ] The STAT column: what do `R`, `S`, `D`, `Z`, `T` mean, and which state can't be killed even with `-9` (and what is it telling you about the box)?
- [ ] SIGTERM vs SIGKILL: which is catchable, what exit codes each produces, and how `docker stop` uses both.
- [ ] Why does `nproc` inside a container lie, what breaks because of it, and where does the true CPU limit live?
- [ ] Why write a systemd unit instead of `nohup cmd &`? Map `Restart=always` and the foreground `ExecStart` to things you already know from Sections 1–2.
- [ ] "Connection refused" vs "connection timeout" — what each tells you about the host and where you look next, tied to DROP vs REJECT.
- [ ] `ss -tlnp` shows port 8080 owned by `docker-proxy`, not the app. Explain the full picture of what `-p 8080:8000` set up (proxy + NAT rule).
- [ ] Walk through what happens when a user hits `https://your-api/health` — every hop, TLS handshake to app response and back. (The single most common infra screening question.)
- [ ] A reverse proxy returns 502 vs 504 — what does each specifically mean, and where do you look for each?
- [ ] Why do `X-Real-IP` / `X-Forwarded-For` / `X-Forwarded-Proto` headers exist, and what concrete bug appears when `X-Forwarded-Proto` is missing behind a TLS-terminating proxy?
- [ ] The TLS handshake: what problem does each half (encryption vs identity) solve, what is a chain of trust, and why *specifically* does a browser warn on a self-signed cert (is the traffic encrypted)?
- [ ] What is a SAN, and why can a cert signed by a trusted CA still be rejected?
- [ ] Where would Let's Encrypt slot in on a real box — what are the HTTP-01 and DNS-01 challenges, and why can't it issue a cert for vps-lab?
- [ ] Netfilter: name the five hooks/chains and what routing decision forks INPUT vs FORWARD. What are the `filter` and `nat` tables for?
- [ ] What did `docker run -p` create at the netfilter layer, which table/chain holds it, and how is that the same mechanism as a Kubernetes Service (Section 4 spoiler)?

## Where the container illusion differs from a real VPS (say these honestly)

- [ ] Three things vps-lab does *not* behave like a real VPS on, and how each showed up in a lab: the shared kernel (`/proc`/`nproc` reporting the whole VM), no systemd (unit files installed but not run), and packages/firewall-rules dying on recreate (the reimage ritual).
- [ ] Why the firewall lab is *safe* here in a way it wouldn't be on a real box (network-namespace isolation + `docker exec` rescue console).

## Gate

- [ ] `notes.md` filled in my own words (the five sections — not just the session digests)
- [ ] Everything committed: the six lab files, README, and the `vps-lab/docker-compose.yml` port additions (9040, 9041) + `cap_add` — **no keys, no `.key`, no certs**

When all boxes are checked, say so — the next section (Kubernetes Core with kind) gets written against your notes, and the iptables rules you can now read become how kube-proxy routes a Service.
