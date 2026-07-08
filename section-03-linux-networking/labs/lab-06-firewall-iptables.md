# Lab 6 — Firewall: iptables / nftables (inside vps-lab only)

**Goal:** read a real firewall ruleset, understand the netfilter checkpoints every packet passes through, add a block rule and *feel* the difference between **DROP** and **REJECT** (Lab 3's timeout vs. refused, now made by you), find the DNAT rule that Docker's `-p` flag secretly wrote, and — the finale — firewall yourself out of SSH and recover through the "rescue console". Then see, a section early, that a Kubernetes Service is *literally this*.

> ## ⚠️ Read this box twice — the one hard safety rule
> **Every command in this lab runs INSIDE vps-lab, never on your Mac or Docker host.** iptables on the Mac would edit Docker Desktop's own NAT rules and break container networking for everything. The reason this lab is *safe* is exactly the illusion-difference from the section README: vps-lab's firewall rules live in the container's **own network namespace** — they cannot touch your Mac — and if you lock yourself out, `docker exec` is a rescue console a real VPS can only dream of. So: SSH in first, and stay in.

## The mental map (read this first)

The Linux kernel runs a packet through a fixed set of **checkpoints** (netfilter *hooks*) on its journey. A firewall is just rules parked at those checkpoints. There are five, and where a packet is *going* decides which it hits:

```
                    ┌──────────── is this packet FOR me? ────────────┐
   packet in ──▶ PREROUTING ──▶ (routing decision)                    │
                                   │                                   │
                          yes, local│              no, passing through │
                                   ▼                                   ▼
                                 INPUT                             FORWARD
                            (to a local process)            (routed to elsewhere —
                                   │                          Docker's containers,
                                   ▼                          a router's traffic)
                            local process                          │
                                   │                               │
                                OUTPUT ◀── local process sends ──   │
                                   │                               │
                                   ▼                               ▼
                              POSTROUTING ──────────────────▶ packet out
```

Two more layers on top of the hooks:

- **Tables** group rules by *purpose*. The two that matter: **`filter`** (allow/deny — the actual firewall) and **`nat`** (rewrite addresses — this is where `docker -p` lives). A third, `mangle`, tweaks packets; ignore it for now.
- **Chains** are the ordered rule-lists attached to a hook (the built-ins are named after the hooks: `INPUT`, `FORWARD`, etc.; you can add custom ones — Docker does).

How a chain decides: rules are checked **top-to-bottom, first match wins**, and each chain has a **default policy** (`ACCEPT` or `DROP`) applied if nothing matched. A rule's *target* is the verdict: `ACCEPT`, `DROP` (silently bin it), `REJECT` (bin it *and* send back "no"), or "jump to another chain".

The one distinction that carries the whole lab:

- **DROP** = the packet vanishes. The sender gets *no reply* and waits → **timeout** (Lab 3's slow silence). Stealthy — the port looks dead.
- **REJECT** = the kernel sends back an ICMP/RST "closed" → the sender fails **instantly** → **connection refused** (Lab 3's fast no). Polite — the port announces it's blocked.

You made these two feelings in Lab 3 with `nc`; now you'll *cause* them with firewall rules.

## Steps

> **All inside vps-lab.** Get in and stay in: `ssh -i vps-lab/keys/vps_key -p 9022 mahadi@localhost`

### 0. (Optional) make the NET_ADMIN capability explicit in compose

vps-lab already carries `privileged: true` (S2, for Docker-in-Docker), which *includes* the `NET_ADMIN` and `NET_RAW` capabilities that iptables needs — so **iptables already works here without any change.** But `privileged` is a sledgehammer (all capabilities). The principled, least-privilege way to grant *just* firewall powers — what you'd use on a non-DinD box — is `cap_add`. It's worth stating explicitly so the requirement is documented:

```yaml
services:
  vps:
    build: .
    container_name: vps-lab
    hostname: vps-lab
    privileged: true          # S2: DinD (already implies NET_ADMIN + NET_RAW)
    cap_add:
      - NET_ADMIN             # S3 Lab 6: the explicit, documented capability for iptables/nftables
    ports:
      - "9022:22"
      - "9030:8080"
      - "9040:80"
      - "9041:443"
    restart: unless-stopped
```

This is a no-op on top of `privileged`, so **you don't have to recreate** (avoid another reimage). If you were dropping `privileged` on a real box, `cap_add: [NET_ADMIN]` is the line that keeps iptables working. Leave `privileged` for now since DinD needs it.

### 1. Read the existing ruleset — including Docker's handiwork

```bash
# inside vps-lab
sudo iptables -L -n -v            # list the FILTER table: -n numeric, -v counts (packets/bytes per rule)
```

You'll see the built-in chains (`INPUT`, `FORWARD`, `OUTPUT`) plus **`DOCKER`** and **`DOCKER-USER`** chains — Docker wrote those when you ran the capstone with `-p`. Now the payoff — look at the **nat** table, where port publishing actually lives:

```bash
sudo iptables -t nat -L DOCKER -n
```

```
Chain DOCKER (2 references)
target     prot opt source     destination
DNAT       tcp  --  0.0.0.0/0  0.0.0.0/0   tcp dpt:8080 to:172.17.0.2:8000
```

**There it is.** That `DNAT` (Destination NAT) rule *is* your `docker run -p 8080:8000` from Section 2, in its true form: "any packet arriving for port **8080**, rewrite its destination to the inner container **172.17.0.2:8000**." The `-p` flag you've typed for six years is **a NAT rule + the docker-proxy helper you saw in Lab 3** — together they're the whole mechanism. Docker even gives you **`DOCKER-USER`**, a chain guaranteed to run *before* Docker's own rules, specifically so you can add firewall rules that survive Docker rewriting everything else:

```bash
sudo iptables -L DOCKER-USER -n     # empty by default — your safe place to add container-traffic rules
```

### 2. DROP vs REJECT — make Lab 3's two feelings on purpose

Use nginx's port 80 (published to your Mac as 9040). Baseline — it works:

```bash
# from your Mac, in a second terminal:
curl -sI --max-time 5 localhost:9040/health | head -1     # HTTP/1.1 301 (or 200) — reachable
```

Now, **inside vps-lab**, REJECT new connections to port 80:

```bash
# inside vps-lab
sudo iptables -I INPUT -p tcp --dport 80 -j REJECT     # -I = INSERT at top so it's hit first
```

```bash
# from your Mac:
curl -sI --max-time 5 localhost:9040/health
# → curl: (7) Failed to connect ... Connection refused      ← INSTANT. This is REJECT.
```

Fast "no" — the kernel actively refused. Swap REJECT for DROP and feel the difference:

```bash
# inside vps-lab
sudo iptables -D INPUT -p tcp --dport 80 -j REJECT     # -D = DELETE that exact rule
sudo iptables -I INPUT -p tcp --dport 80 -j DROP
```

```bash
# from your Mac:
curl -sI --max-time 5 localhost:9040/health
# → (hangs ~5s) curl: (28) Connection timed out            ← SLOW SILENCE. This is DROP.
```

Same block, opposite experience: **REJECT = fast refused, DROP = slow timeout.** That's Lab 3's diagnostic heuristic, now something you can *cause* — and it's why "refused vs timeout" points at different problems (a refused might be a REJECT rule or a dead service; a timeout might be a DROP rule or a black-holed route). Firewalls usually DROP (stealth — don't reveal the port exists to a scanner). Remove the rule and confirm recovery:

```bash
# inside vps-lab
sudo iptables -D INPUT -p tcp --dport 80 -j DROP
# from your Mac: curl -sI --max-time 5 localhost:9040/health | head -1   → back to normal
```

### 3. nftables — the same rules, the modern syntax

Debian 12's `iptables` command is really `iptables-nft`: a compatibility shim that writes rules into the **nftables** kernel subsystem (the successor that replaced the old iptables backend). See the *same* rules in native nft form:

```bash
# inside vps-lab
sudo nft list ruleset | head -40
```

You'll recognise your Docker DNAT and chains, expressed in nftables' cleaner syntax (`table ip nat { chain ... }`). The takeaway for interviews and CKA: **on any Debian/RHEL box since ~2021, "iptables" is a front-end; nftables is the engine.** You can write rules in either dialect; they land in the same place. Don't mix the two front-ends managing the same rules — pick one. (Docker still speaks the iptables dialect, so on a Docker host, use `iptables`.)

### 4. The finale — firewall yourself out of SSH, then rescue

This is the experiment a real VPS would *punish* (you'd need the provider's web console to recover); here `docker exec` is your rescue hatch. Block SSH:

```bash
# inside vps-lab — this will freeze NEW ssh connections
sudo iptables -I INPUT -p tcp --dport 22 -j DROP
```

Your *current* SSH session may keep working (established connection), but a **new** one is dead:

```bash
# from your Mac — open a NEW terminal and try:
ssh -i vps-lab/keys/vps_key -p 9022 mahadi@localhost 'echo hi'
# → hangs, then times out.  You are locked out. (DROP → timeout, per step 2.)
```

**This is the classic "I firewalled myself out of my own server" — the #1 way ops engineers ruin an afternoon.** On a real cloud box, recovery means the provider's out-of-band console (the KVM/serial console every provider offers precisely for this). Here, the rescue console is `docker exec`, which enters vps-lab's namespaces **directly, bypassing the network entirely** (it's not SSH — Section 1's lesson):

```bash
# from your Mac — the rescue console:
docker exec -it vps-lab bash
# now inside vps-lab as root, via the hatch — undo the block:
iptables -D INPUT -p tcp --dport 22 -j DROP
exit
```

```bash
# from your Mac — ssh works again:
ssh -i vps-lab/keys/vps_key -p 9022 mahadi@localhost 'echo recovered'   # prints: recovered
```

The lesson that sticks: **always have out-of-band access before you touch the firewall, and prefer adding an ACCEPT rule for your own IP *before* a default-DROP.** The pro move on a real box is `iptables ... -j DROP` guarded by a scheduled `iptables -F` (flush) a few minutes out, so a lockout self-heals — or configuring via a tool that reverts on lost connection.

### 5. Persistence reality (read, don't run)

Your rules live in kernel memory. They **vanish on reboot** — and here, on any vps-lab **recreate** (the reimage ritual wipes them too). On a real box you'd persist them:

```bash
# real-box persistence (informational):
#   sudo apt install iptables-persistent   # saves rules, restores on boot
#   sudo netfilter-persistent save         # or: iptables-save > /etc/iptables/rules.v4
```

The point for now: **firewall rules are runtime state, not baked into the image** — same category as the apt packages and the nginx config that die on recreate. Section 6 (Terraform) is where all this stops being hand-typed and becomes code.

## Verify

Proof command — cause both failure modes and recover, from memory:

```bash
# inside vps-lab
sudo iptables -I INPUT -p tcp --dport 80 -j REJECT
# from Mac: curl --max-time 5 -sI localhost:9040/  → "Connection refused" FAST
sudo iptables -D INPUT -p tcp --dport 80 -j REJECT
sudo iptables -I INPUT -p tcp --dport 80 -j DROP
# from Mac: curl --max-time 5 -sI localhost:9040/  → "timed out" SLOW
sudo iptables -D INPUT -p tcp --dport 80 -j DROP
sudo iptables -t nat -L DOCKER -n | grep DNAT      # the -p rule is still there, untouched
```

Then answer aloud:

**1. A packet arrives at the box. Name the netfilter checkpoints it might traverse, and what decides whether it hits INPUT vs FORWARD.**

<details><summary>Answer (read after attempting aloud)</summary>

A packet hits `PREROUTING` first, then the kernel makes a **routing decision**: is this packet destined for a *local* process on this box, or is it just *passing through* to somewhere else? If local → `INPUT` → the process → (if it replies) `OUTPUT` → `POSTROUTING` → out. If passing through (e.g. traffic being routed to a container, or a machine acting as a router) → `FORWARD` → `POSTROUTING` → out. Locally-originated traffic starts at `OUTPUT`. So the destination + routing decision is what forks INPUT vs FORWARD — and it's why container/proxy traffic (destined *elsewhere*) is filtered in FORWARD/`DOCKER-USER`, while traffic to sshd/nginx on the box itself is filtered in INPUT.

</details>

**2. DROP vs REJECT — what does the client experience with each, and which does a stealth firewall prefer and why?**

<details><summary>Answer (read after attempting aloud)</summary>

**DROP** silently bins the packet — the sender gets no reply at all and eventually **times out** (slow silence). **REJECT** bins it *and* sends back an ICMP/TCP-RST "port closed", so the sender fails **instantly** with "connection refused" (fast no). These are exactly Lab 3's timeout vs. refused, now caused by a rule. A stealth firewall prefers **DROP**: a refused reply confirms to a port-scanner that the host is alive and the port is filtered; a timeout reveals nothing, so the host looks dead/unreachable — less information leaked to an attacker.

</details>

**3. `docker run -p 8080:8000` — what did it actually create at the netfilter layer, and where do you look to see it?**

<details><summary>Answer (read after attempting aloud)</summary>

It created a **DNAT (Destination NAT) rule** in the `nat` table's `DOCKER` chain: "packets for port 8080 → rewrite destination to the inner container's `172.x:8000`" — visible via `sudo iptables -t nat -L DOCKER -n`. Combined with the userland `docker-proxy` process (Lab 3's `ss` output on 8080), that pair *is* port publishing. So `-p` isn't magic — it's a firewall/NAT rule plus a helper process. This is the same mechanism kube-proxy uses in Kubernetes: a Service's ClusterIP is a bunch of DNAT rules load-balancing to pod IPs — which is why reading this now pays off in Section 4.

</details>

**4. You added `iptables -I INPUT -p tcp --dport 22 -j DROP` and got locked out of SSH. Why did DROP (not REJECT) cause a *hang*, how did you recover, and what's the pro habit that prevents this?**

<details><summary>Answer (read after attempting aloud)</summary>

DROP silently discards the SYN packets of new SSH connections, so the client waits with no reply → hang/timeout (REJECT would have failed fast with "refused"). Recovery was `docker exec -it vps-lab bash` — a **rescue console** that enters the container's namespaces directly, bypassing the network and sshd entirely (it's not SSH — Section 1's lesson), where you `iptables -D` the rule. On a real VPS the equivalent is the provider's out-of-band/serial console. The pro habits: (a) always have out-of-band access before touching the firewall; (b) insert an ACCEPT rule for your own IP/SSH *before* any default-DROP; (c) on a remote box, guard risky rules with a scheduled `iptables -F` a few minutes out so a lockout self-heals.

</details>

## Clean up

```bash
# inside vps-lab — make sure no block rules survive (they'd break later labs/sections)
sudo iptables -D INPUT -p tcp --dport 80 -j REJECT 2>/dev/null
sudo iptables -D INPUT -p tcp --dport 80 -j DROP   2>/dev/null
sudo iptables -D INPUT -p tcp --dport 22 -j DROP   2>/dev/null
sudo iptables -L INPUT -n --line-numbers           # confirm INPUT has no leftover REJECT/DROP you added
exit
```

Leave vps-lab, nginx+TLS, and the capstone running — that stack (HTTPS-fronted app on a box you now administer end to end) is the section's deliverable. The firewall rules were runtime-only and are now flushed; the Docker DNAT rules stay (they're Docker's, not yours).

**Section 3 done when** every task in [../checkpoint.md](../checkpoint.md) passes from memory and [../notes.md](../notes.md) is filled in your own words. Next: Section 4 builds a kind cluster, and the DNAT rule you just read turns out to be exactly how a Kubernetes Service routes traffic.
