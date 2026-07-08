# Lab 4 — nginx as a reverse proxy

**Goal:** put nginx in front of the deployed capstone container so the outside world hits **nginx**, not the app. You'll write the proxy config, add the forwarding headers that let the app know who really called, read the access/error logs, and deliberately cause (then diagnose) a **502 Bad Gateway**. Published on host port **9040**. This is the single most common thing a reverse proxy is used for, and the answer to "walk me through what happens when a user hits your API".

## The mental map (read this first)

Right now the chain from Section 2 is: **Mac:9030 → vps-lab:8080 → inner container:8000**, and the app is exposed *raw*. A **reverse proxy** inserts a receptionist in front of it:

```
                              vps-lab (the "VPS")
 YOUR MAC                    ┌───────────────────────────────────────────────┐
┌──────────┐  :9040 (http)  │  nginx  ────proxy_pass───▶ 127.0.0.1:8080       │
│  curl /  ├───────────────▶│  :80    (adds headers,       │  (docker-proxy)  │
│ browser  │                │  logs,  terminates conn,     ▼                  │
│          │                │  will do TLS in Lab 5)   inner Docker:          │
│          │                │                          capstone :8000         │
└──────────┘                └───────────────────────────────────────────────┘
   nginx is the ONLY thing the world talks to; the app only ever hears from nginx.
```

Why every real service on earth is behind one — nginx is the single door that does the jobs the app shouldn't:

- **one public port for many services** — route `/api` here, `/` there, all on :80/:443.
- **TLS termination** (Lab 5) — nginx does the crypto once; the app speaks plain HTTP behind it.
- **buffering, timeouts, rate-limits, gzip, static files** — infrastructure concerns, kept out of app code (12-factor's spirit).
- **the app's real address stays private** — clients only ever reach nginx.

"Reverse" proxy because it sits in front of the *servers* (fronts many backends for many clients); a *forward* proxy sits in front of the *clients*. **nginx runs as a master + worker processes** (Section 1's PID/process tree, applied): the master reads config and owns the port; workers handle connections. A config reload = tell the master via a signal (SIGHUP — Lab 2's "reload by convention") — zero downtime.

The critical honesty: to the app, *every* request now appears to come from nginx (`127.0.0.1`). If the app logs client IPs or does per-client anything, it needs nginx to **forward** the original details in headers. That's what half this config is.

## Steps

> Config edits happen **inside vps-lab**; the compose edit happens **on your Mac**.

### 1. Confirm the starting state (or reimage)

```bash
# on your Mac
curl -s localhost:9030/health                                      # {"status":"ok"}
ssh -i vps-lab/keys/vps_key -p 9022 mahadi@localhost 'sudo docker ps'  # one capstone, 8080->8000
```

Both should succeed. If either fails, run the reimage ritual (next).

### 2. The reimage ritual — restore the Section 2 state from scratch

A container recreate (`down`, or any compose change) hands you a **factory-fresh** vps-lab: the user, sshd, and key survive (they're baked in the Dockerfile), but **anything installed at runtime is gone** — Docker itself, the capstone image, apt packages from Lab 3. This is the "reimage" half of "reboot vs reimage" (Section 1 Lab 5). On a real VPS you'd keep this runbook in the repo; writing it *is* the ops skill. Run it whenever vps-lab is empty:

```bash
# on your Mac — recreate the box
cd vps-lab
docker compose up -d --build
ssh-keygen -R "[localhost]:9022" 2>/dev/null   # forget the old host key if it was rebuilt (Lab 5, S1)

# install Docker INSIDE vps-lab (Section 2 did this; recreate wiped it)
ssh -i keys/vps_key -p 9022 mahadi@localhost \
  'sudo apt-get update && sudo apt-get install -y docker.io'

# pull + run the capstone (multi-arch image from S2's CI — the deploy chain's payload)
ssh -i keys/vps_key -p 9022 mahadi@localhost \
  'sudo docker run -d --restart unless-stopped --name capstone -p 8080:8000 ghcr.io/itsmahadi007/capstone:latest'

curl -s localhost:9030/health   # {"status":"ok"} — back to the Section 2 end state
```

(Docker-inside-a-container works because vps-lab runs `privileged: true` — S2 added that for DinD; the honesty about DinD was covered there. `--restart unless-stopped` on the inner container means it survives a vps-lab reboot the same way vps-lab survives Docker Desktop restarting.)

### 3. Install nginx and understand its shape

```bash
# inside vps-lab
ssh -i vps-lab/keys/vps_key -p 9022 mahadi@localhost   # (from your Mac)
sudo apt-get update && sudo apt-get install -y nginx
nginx -v                       # nginx/1.22.x — Debian 12's stable (verify latest with this command)
```

nginx installs a systemd unit — but there's no systemd here (Lab 2), so start it the fallback way and confirm the process tree:

```bash
sudo nginx                     # start the master (foreground rule doesn't apply — nginx daemonizes ITSELF by design here)
ps -o pid,ppid,user,comm -C nginx
```

```
  PID  PPID USER     COMMAND
  842     1 root     nginx        ← master (owns :80, reads config)
  843   842 www-data nginx        ← worker (handles connections, dropped to unprivileged user)
```

There's the **master/worker** model live: the master runs as root (only root may bind port 80 — ports <1024 are privileged) and immediately spawns workers as the unprivileged `www-data`. Same privilege-drop principle as running the app as `appuser` in Section 1. Confirm nginx is listening (Lab 3's tool):

```bash
sudo ss -tlnp | grep :80       # nginx on 0.0.0.0:80
curl -s -o /dev/null -w '%{http_code}\n' localhost:80   # 200 — the default welcome page
```

### 4. Publish port 9040 — the compose edit (on your Mac)

nginx listens on :80 *inside* vps-lab, but no host port maps to it yet. Edit `vps-lab/docker-compose.yml` on your Mac to add the S3 door. Here is the full file — the `9040:80` line is the S3 addition (`9030:8080` and `privileged` came from S2):

```yaml
services:
  vps:
    build: .
    container_name: vps-lab
    hostname: vps-lab
    privileged: true          # S2: lets Docker run INSIDE vps-lab (DinD)
    ports:
      - "9022:22"             # SSH (permanent, S1)
      - "9030:8080"           # S2: raw capstone deploy chain (Mac:9030 → 8080 → inner :8000)
      - "9040:80"             # S3 Lab 4: nginx HTTP  ◀── ADD THIS LINE
    restart: unless-stopped
```

Applying a *ports* change requires a **recreate** (ports are fixed at container creation — Section 1's "env stamped at creation" lesson, same class):

```bash
# on your Mac
cd vps-lab
docker compose up -d          # recreates vps-lab to pick up the new port mapping
```

**This wipes the box** (recreate = reimage). So immediately re-run the **reimage ritual (step 2)** — Docker, capstone, and nginx are all gone again. (Annoying, yes — that friction is exactly why real infra is codified: Terraform in Section 6 makes "recreate + reprovision" one command. For now, do it by hand once; it cements the runbook.) After reimaging, `sudo apt-get install -y nginx && sudo nginx` again inside, then continue.

> **Tip to avoid the double-reimage:** add the `9040:80` line *before* you first provision, so the recreate and the provisioning happen once. If you already provisioned, just accept the one extra reimage — it's good practice.

### 5. Write the reverse-proxy config

Debian's nginx uses the `sites-available` / `sites-enabled` pattern (a config drawer + symlinks to the ones you've switched on). Turn off the default welcome site and add ours:

```bash
# inside vps-lab
sudo rm -f /etc/nginx/sites-enabled/default        # unlink the welcome page

sudo tee /etc/nginx/sites-available/capstone >/dev/null <<'EOF'
server {
    listen 80;
    server_name _;                       # '_' = match any hostname (we have no domain)

    access_log /var/log/nginx/capstone.access.log;
    error_log  /var/log/nginx/capstone.error.log;

    location / {
        proxy_pass http://127.0.0.1:8080;    # hand the request to the capstone (docker-proxy on 8080)

        # --- the forwarding headers: tell the app who REALLY called ---
        proxy_set_header Host              $host;              # original Host: header
        proxy_set_header X-Real-IP         $remote_addr;       # the client's real IP
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;  # the client-chain
        proxy_set_header X-Forwarded-Proto $scheme;            # http vs https (matters in Lab 5)
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/capstone /etc/nginx/sites-enabled/capstone
```

Why the headers matter: without them, the app sees every request as coming from `127.0.0.1` (nginx) over `http`, always. `X-Real-IP`/`X-Forwarded-For` restore the true client IP (for logs, rate-limiting, geo); `X-Forwarded-Proto` tells the app the *user* used HTTPS even though nginx→app is plain HTTP (so the app builds `https://` redirect URLs correctly — a real bug when it's missing). `$host`, `$remote_addr`, `$scheme` are nginx **variables** — nginx fills them per-request.

### 6. Test the config, reload, and prove it works

**Never reload a config you haven't tested** — a syntax error can take the whole server down. `nginx -t` is the pre-flight check, a reflex before every reload:

```bash
# inside vps-lab
sudo nginx -t
```

```
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful
```

Now reload — the master re-reads config and gracefully swaps workers, **zero dropped connections** (in-flight requests finish on old workers):

```bash
sudo nginx -s reload           # -s reload = send the master the reload signal (SIGHUP under the hood)
```

From your Mac, hit the app *through* nginx:

```bash
# on your Mac
curl -s localhost:9040/health          # {"status":"ok"} — but served THROUGH nginx now
curl -sI localhost:9040/health         # note: Server: nginx/1.22.x  ← nginx answered, not uvicorn
```

The `Server: nginx` header is the proof the receptionist is in the path. Compare with `curl -sI localhost:9030/health` (raw, `Server: uvicorn`) to see both doors into the same app.

### 7. Read the logs — and manufacture a 502

Watch nginx's access log while you hit it:

```bash
# inside vps-lab
sudo tail -f /var/log/nginx/capstone.access.log &
# from your Mac in another terminal: curl -s localhost:9040/health
```

```
192.168.65.1 - - [09/Jul/2026:10:00:00 +0000] "GET /health HTTP/1.1" 200 15 "-" "curl/8.x"
```

Read the combined log format: client IP, timestamp, request line, **status (200)**, bytes sent, referer, user-agent. This is the raw material every access-log analysis tool parses. Kill the tail (`fg` then Ctrl-C, or `kill %1`).

Now the classic failure — **502 Bad Gateway** — on purpose. Stop the upstream and knock:

```bash
# inside vps-lab
sudo docker stop capstone
# from your Mac:  curl -sI localhost:9040/health   →  HTTP/1.1 502 Bad Gateway
sudo tail -2 /var/log/nginx/capstone.error.log
```

```
connect() failed (111: Connection refused) while connecting to upstream,
  client: 192.168.65.1, ... upstream: "http://127.0.0.1:8080/health"
```

**This is Lab 3's "refused" wearing a proxy costume.** nginx tried to `connect()` to `127.0.0.1:8080`, the kernel said "nobody's listening" (error 111 = ECONNREFUSED — because you stopped the container), and nginx reports that upward as a **502 Bad Gateway**: "*I'm* fine, but the thing I proxy to isn't answering". Memorise the distinction: **502 = upstream is down/refusing** (start the app), vs **504 Gateway Timeout = upstream too slow** (Lab 3's timeout, wearing the same costume). Bring it back:

```bash
sudo docker start capstone
# from your Mac:  curl -sI localhost:9040/health  →  200 again
```

## Verify

Proof command — the full chain, and the 502 diagnosis, from memory:

```bash
# on your Mac
curl -sI localhost:9040/health | head -1        # HTTP/1.1 200 OK  (through nginx)
curl -sI localhost:9040/health | grep -i server # Server: nginx/1.22.x
# then, inside vps-lab: sudo docker stop capstone
curl -sI localhost:9040/health | head -1        # HTTP/1.1 502 Bad Gateway
# inside vps-lab: sudo docker start capstone     (restore)
```

Then answer aloud:

**1. A user hits `https://your-api/health`. Walk the request through every hop to the app and back (the interview question).**

<details><summary>Answer (read after attempting aloud)</summary>

DNS resolves the name → the packet reaches the box on :443 (Lab 5) → **nginx** accepts it, terminates TLS (does the crypto), and matches a `server`/`location` block → nginx opens a plain-HTTP connection to the **upstream** (`proxy_pass http://127.0.0.1:8080`), adding `Host`, `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto` headers → docker-proxy on 8080 forwards into the inner container's :8000 → **uvicorn/the app** handles it and returns JSON → back up the same chain, nginx relays it to the client, logs a line in the access log. nginx is the only thing the client ever talks to; the app only ever hears from nginx (`127.0.0.1`), which is why the forwarding headers exist.

</details>

**2. `curl` through nginx returns 502 Bad Gateway. What does 502 specifically mean, how is it different from 504, and where do you look?**

<details><summary>Answer (read after attempting aloud)</summary>

**502 Bad Gateway** = nginx reached its upstream's port but the connection **failed/was refused** — the backend is down, crashed, or not listening (the `error_log` shows `connect() failed (111: Connection refused)`). It's Lab 3's "connection refused", reported by the proxy. **504 Gateway Timeout** = nginx *connected* but the upstream didn't respond in time — the backend is up but too slow/hung (Lab 3's "timeout"). For 502: check the upstream is running (`docker ps`, `ss -tlnp` for the port) and that `proxy_pass` points at the right host:port. For 504: check the backend's own latency/health.

</details>

**3. Why do we set `X-Forwarded-For` / `X-Real-IP` headers at all, and what breaks without `X-Forwarded-Proto`?**

<details><summary>Answer (read after attempting aloud)</summary>

Because once traffic goes through the proxy, the app sees the *proxy's* address (`127.0.0.1`) as the client on every request — the real client IP is lost. `X-Real-IP` / `X-Forwarded-For` carry the true client IP (and the proxy chain) so the app's logging, rate-limiting, and geo-logic work. Without `X-Forwarded-Proto`, the app can't tell the user arrived over HTTPS (nginx→app is plain HTTP), so any URL it builds — redirects, absolute links, secure-cookie decisions — comes out as `http://`, causing redirect loops and insecure-cookie bugs behind a TLS-terminating proxy. This becomes concrete in Lab 5.

</details>

## Clean up

```bash
# inside vps-lab
# leave nginx running and the proxy config in place — Lab 5 adds TLS to this SAME server block.
sudo nginx -t                  # sanity: config still valid
exit
```

Leave everything up. Lab 5 turns this HTTP proxy into HTTPS on 9041. (Commit only your section-03 files and the `vps-lab/docker-compose.yml` port line — the nginx config lives *inside* the container, not in the repo; on a real box it would be codified, which Section 6 addresses.)
