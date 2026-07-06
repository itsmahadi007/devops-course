# Lab 5 — Build your fake VPS

**Goal:** build `vps-lab/` — a Debian container with sshd and key-only auth that you SSH into like a rented server. Sections 2 and 3 depend on it. Writing it yourself is the point: users, sshd config, and key auth are everyday server work.

## Steps

**1. Generate a dedicated keypair (never committed — `vps-lab/keys/` is gitignored):**

```bash
cd vps-lab
mkdir -p keys
ssh-keygen -t ed25519 -f keys/vps_key -N "" -C "vps-lab"
```

**2. Write `vps-lab/Dockerfile`:**

```dockerfile
FROM debian:12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        openssh-server sudo curl vim iproute2 \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir /run/sshd

# The user you'll log in as — sudo without password, like a fresh VPS setup
RUN useradd --create-home --shell /bin/bash mahadi \
    && echo 'mahadi ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/mahadi

# Key-only auth — password login off, root login off
RUN sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config \
    && sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config

COPY keys/vps_key.pub /home/mahadi/.ssh/authorized_keys
RUN chown -R mahadi:mahadi /home/mahadi/.ssh \
    && chmod 700 /home/mahadi/.ssh && chmod 600 /home/mahadi/.ssh/authorized_keys

EXPOSE 22
CMD ["/usr/sbin/sshd", "-D"]
```

Every line here is a real server-hardening task you'd bill for: non-root user, sudoers drop-in, `PasswordAuthentication no`, `PermitRootLogin no`, `authorized_keys` permissions (sshd *refuses* keys with wrong modes — that 700/600 is not decoration).

**3. Write `vps-lab/docker-compose.yml`:**

```yaml
services:
  vps:
    build: .
    container_name: vps-lab
    hostname: vps-lab
    ports:
      - "2222:22"
    restart: unless-stopped
```

**4. Launch and connect:**

```bash
docker compose up -d --build
ssh -i keys/vps_key -p 2222 mahadi@localhost
```

First connect prompts for host-key trust — that's the TOFU (trust-on-first-use) model; say yes. You're now "on a server."

**5. Act like it's day one on a rented box:**

```bash
# inside vps-lab
whoami && hostname
sudo apt update
ip addr        # what does the network look like from inside?
exit
```

**6. Understand its lifecycle:**

```bash
docker stop vps-lab && docker start vps-lab   # files you created inside survive
ssh -i keys/vps_key -p 2222 mahadi@localhost 'hostname'
```

Stop/start keeps the writable layer (your "server state"). `docker compose down` would destroy it and give you a factory-fresh VPS — which is a *feature*: break it fearlessly, rebuild in 30 seconds. (No systemd in here — services run in the foreground or via `service ...`; Section 3 works with that deliberately.)

## Verify

- `ssh -i keys/vps_key -p 2222 mahadi@localhost 'whoami'` prints `mahadi` with no password prompt.
- `ssh -p 2222 root@localhost` is **refused** (root login off, no password auth).
- `git status` shows `keys/` untracked/ignored — no private key can reach the public repo.

## Clean up

Nothing — leave `vps-lab` running; it's infrastructure for the next sections. Commit `Dockerfile` and `docker-compose.yml` (NOT keys).
