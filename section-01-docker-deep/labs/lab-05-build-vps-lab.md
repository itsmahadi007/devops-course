# Lab 5 — Build your fake VPS

**Goal:** build `vps-lab/` — a Debian container with sshd and key-only auth that you SSH into like a rented server. Sections 2 and 3 depend on it. Writing it yourself is the point: users, sshd config, and key auth are everyday server work.

## The mental map (read this first)

What *is* a VPS, stripped of marketing? **Linux + an SSH daemon + a user + your key.** That's the whole product. And every one of those four things fits in a container — SSH is just a TCP service like any other, so a container running sshd is indistinguishable, from your terminal's point of view, from a $5/month rented box. (Two honest differences: no systemd inside — Lab 1's foreground rule still reigns — and it shares your Mac's kernel. Neither matters for practicing server work.)

The key-auth mental model — get this straight once and SSH stops being mysterious:

- **Public key = a lock.** You install it on the server (`authorized_keys`). Not secret — it's a *lock*; anyone may see a lock.
- **Private key = the only key that opens it.** Stays on your Mac, never travels anywhere — during login the server issues a mathematical challenge only the private-key holder can answer, so the secret itself is never sent.

And there are **two directions of trust** in every SSH connection, which people constantly mix up:

```
 YOUR MAC                                    THE "VPS" (container)
┌─────────────────────┐                     ┌──────────────────────────┐
│ ssh client          │  1. server proves   │ sshd (PID 1, foreground) │
│                     │     ITSELF first    │                          │
│ ~/.ssh/known_hosts ◀├─── host key ────────┤ /etc/ssh/ssh_host_*      │
│  (locks I've seen)  │                     │  (the server's identity) │
│                     │  2. then YOU prove  │                          │
│ keys/vps_key ───────┼──── challenge ─────▶│ ~/.ssh/authorized_keys   │
│  (private — SECRET) │      response       │  (locks that admit you)  │
└─────────────────────┘                     └──────────────────────────┘
        │                                              ▲
        └── ssh -p 9022 mahadi@localhost ── host:9022 → container:22
```

Step 1 is the **host key** (server → you: "I'm the same machine as last time" — that's what `known_hosts` records). Step 2 is the **user key** (you → server: "I hold the private key for a lock in `authorized_keys`"). Same math, opposite directions. Interviewers love this distinction.

Ports: host side is **9022** (our 9000-series rule; reads as "9000-series, port 22"), container side the conventional 22. Out in the wild you'll constantly see 2222 used for this — same trick, different number.

## Steps

### 1. Generate a dedicated keypair (never committed — `vps-lab/keys/` is gitignored)

```bash
cd vps-lab
mkdir -p keys
ssh-keygen -t ed25519 -f keys/vps_key -N "" -C "vps-lab"
```

Flag by flag: `-t ed25519` = the modern signature algorithm (tiny keys, fast, no known weaknesses — the default choice in 2026); `-f keys/vps_key` = where to write; `-N ""` = empty passphrase (fine for a lab key; real ops keys get a passphrase + ssh-agent); `-C "vps-lab"` = a label so you can tell keys apart later.

You get **two files**: `vps_key` (the private key — the SECRET) and `vps_key.pub` (the lock — this one goes in the image). The "randomart" box in the output is just a visual fingerprint for humans; ignore it. Before moving on: `git status` must NOT show `keys/` — the `.gitignore` is what makes this a public-repo-safe lab.

### 2. Write `vps-lab/Dockerfile`

```dockerfile
FROM debian:12-slim
# a bare Debian — the closest thing to what a hosting provider hands you

RUN apt-get update && apt-get install -y --no-install-recommends \
        openssh-server sudo curl vim iproute2 \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir /run/sshd
# one RUN = one layer: the apt catalog downloaded by `update` is deleted in the
# SAME layer, so it never ships (layers are append-only — a later rm hides, not shrinks)
# mkdir /run/sshd: sshd's privilege-separation dir — normally systemd creates it
# at boot; no systemd here, so we do its one job ourselves

# The user you'll log in as — passwordless sudo, like a fresh VPS after cloud-init
RUN useradd --create-home --shell /bin/bash mahadi \
    && echo 'mahadi ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/mahadi
# a drop-in file under sudoers.d, never editing /etc/sudoers itself —
# standard practice: drop-ins are additive, reviewable, and can't corrupt the main file

# Key-only auth — the two lines every real server gets hardened with
RUN sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config \
    && sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
# the ^#\? regex catches the line whether Debian shipped it commented out or not

COPY keys/vps_key.pub /home/mahadi/.ssh/authorized_keys
# installing the LOCK (public half) — the private key never enters the image

RUN chown -R mahadi:mahadi /home/mahadi/.ssh \
    && chmod 700 /home/mahadi/.ssh && chmod 600 /home/mahadi/.ssh/authorized_keys
# not decoration: sshd's StrictModes REFUSES keys whose file permissions are loose —
# if others could edit your authorized_keys, they could add their own lock

EXPOSE 22
CMD ["/usr/sbin/sshd", "-D"]
# -D = "don't daemonize" — Lab 1's foreground rule: sshd must BE PID 1,
# because the daemonizing parent would exit and kill the container
```

Every line here is a real server-hardening task you'd bill for: non-root user, sudoers drop-in, `PasswordAuthentication no`, `PermitRootLogin no`, `authorized_keys` permissions. Notice how much of Labs 1–3 shows up uninvited: single-layer apt hygiene, exec-form CMD, the foreground rule, chown/chmod ownership story.

### 3. Write `vps-lab/docker-compose.yml`

```yaml
services:
  vps:
    build: .
    container_name: vps-lab   # fixed name — infrastructure gets a stable name, no project prefix
    hostname: vps-lab         # what you'll see in the shell prompt after login
    ports:
      - "9022:22"             # host 9022 (our 9000-series rule) → container's conventional 22
    restart: unless-stopped   # NEW concept — see below
```

#### `restart:` — the first time Docker babysits FOR you

Until now, a dead container stayed dead. `restart: unless-stopped` tells the *daemon*: if this container exits — crash, or Docker Desktop itself restarts — bring it back automatically. Exactly what a real VPS does after a power cycle: it boots back. The three values worth knowing: `no` (default), `on-failure` (only on non-zero exit), `unless-stopped` (always revive, *except* when a human explicitly ran `stop` — the human's decision is respected). This is why vps-lab will simply *be there* tomorrow morning without you thinking about it.

### 4. Launch and connect

```bash
docker compose up -d --build
ssh -i keys/vps_key -p 9022 mahadi@localhost
```

First connect prints something like:

```
The authenticity of host '[localhost]:9022' can't be established.
ED25519 key fingerprint is SHA256:....
Are you sure you want to continue connecting (yes/no/[fingerprint])?
```

That's mental-map **step 1** — the server showing its host key, and your client admitting it has never seen this machine before. Answering `yes` is the **TOFU model** (trust-on-first-use): "I can't verify you this first time, but I'm recording your fingerprint in `~/.ssh/known_hosts` — if it ever changes, I'll scream." Say yes. Then step 2 happens silently (challenge → your private key answers) and you're "on a server" — prompt says `mahadi@vps-lab`.

#### The scary warning you WILL meet later

The host key is generated when `openssh-server` installs — i.e. **baked into the image at build time**. So `down`/`up` from the same image = same identity, silent connect. But the day a *rebuild* re-runs that apt layer (cache bust — you know several ways that happens), the image gets a NEW host key, and ssh greets you with:

```
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
@    WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!     @
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
IT IS POSSIBLE THAT SOMEONE IS DOING SOMETHING NASTY!
```

On a real server this warning is serious (possible man-in-the-middle). Here, you *are* the "someone" — you rebuilt the machine. The fix is to forget the old fingerprint:

```bash
ssh-keygen -R "[localhost]:9022"
```

then connect again and TOFU anew. Knowing this warning's two readings — attack vs. legitimately rebuilt box — is day-one ops literacy.

### 5. Act like it's day one on a rented box

```bash
# inside vps-lab
whoami && hostname     # mahadi, vps-lab — you, on "your server"
sudo apt update        # no password prompt — the sudoers drop-in at work
ip addr                # what does the network look like from inside?
exit
```

`ip addr` shows two interfaces: `lo` (loopback) and an `eth0` holding a private `172.x.x.x` — the compose network you now know well, seen from the *server's* side this time. That address is what Lab 4's phonebook would hand out for this container.

### 6. Understand its lifecycle

```bash
docker stop vps-lab && docker start vps-lab   # files you created inside survive
ssh -i keys/vps_key -p 9022 mahadi@localhost 'hostname'
```

(That trailing `'hostname'` form runs one command and disconnects — the workhorse of every deploy script you'll write in Sections 2–3.)

Stop/start keeps the writable layer (your "server state" — Lab 1). `docker compose down` would destroy it and hand you a factory-fresh VPS — which is a *feature*: break it fearlessly, rebuild in 30 seconds. Real rented servers offer the same two moves under the names "reboot" vs "reimage". (No systemd in here — services run in the foreground or via `service ...`; Section 3 works with that deliberately.)

## Verify

- `ssh -i keys/vps_key -p 9022 mahadi@localhost 'whoami'` prints `mahadi` with no password prompt.
- `ssh -p 9022 root@localhost` is **refused** — expect `Permission denied (publickey)`: with password auth off, sshd won't even offer a password prompt; and root wouldn't get in regardless (`PermitRootLogin no`).
- `git status` shows `keys/` untracked/ignored — no private key can reach the public repo.

## Clean up

Nothing — leave `vps-lab` running; it's infrastructure for the next sections (and `restart: unless-stopped` will keep it that way). Commit `Dockerfile` and `docker-compose.yml` (NOT keys).
