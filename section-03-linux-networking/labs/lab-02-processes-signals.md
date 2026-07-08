# Lab 2 — Processes & signals, from the ops side

**Goal:** learn to *read a running system* — `ps`/`top`, the `STAT` column, the `/proc` live dashboard — and to *talk to* processes with the full signal vocabulary (not just Section 1's "knock on the door"). Then meet the thing vps-lab doesn't have — **systemd** — by reading a real unit file on paper, because on a real VPS that's how every service you'll ever run gets started.

## The mental map (read this first)

In Section 1 you learned three process facts from the *container* side: everything is a process tree, **PID 1 is special** (it dies → the container dies), and the only way to talk to a process from outside is a **signal** (`docker stop` = SIGTERM, wait 10s, SIGKILL → exit 137). This lab is the same truths from the *server admin* side, where you have `ps`, `/proc`, and `kill` instead of `docker` verbs.

```
        THE PROCESS TREE (inside vps-lab)                 HOW YOU INSPECT / CONTROL IT
   ┌──────────────────────────────────────┐
   │  PID 1  sshd -D   ◀── the init slot  │        ps aux        ─ snapshot: who's running, what STAT
   │    │     (systemd on a real box)      │        top / htop    ─ live: CPU, mem, refreshing
   │    ├─ sshd: mahadi [priv]             │        /proc/<pid>/  ─ the kernel's live file for a PID
   │    │    └─ bash  (your login shell)   │        pstree        ─ the tree, drawn
   │    │         └─ sleep 1000            │
   │    └─ (docker-proxy, capstone, …)     │        kill -SIGNAL <pid>  ─ send a signal
   └──────────────────────────────────────┘        jobs / fg / bg / nohup ─ shell job control
```

Two ideas to carry:

- **A signal is a numbered doorbell the kernel rings for you.** You don't call the process; you ask the *kernel* to deliver a signal, and the process either has a handler for it or takes the kernel's default action. `kill` is a badly-named command — it sends *any* signal, not just the fatal one.
- **`/proc` is not a real disk.** It's the kernel exposing its own live state *as if* it were files, so every tool you know (`cat`, `ls`, `grep`) becomes a system inspector. `top`, `ps`, `free` — they're all just pretty-printers over `/proc`.

## Steps

> All inside vps-lab: `ssh -i vps-lab/keys/vps_key -p 9022 mahadi@localhost`

### 1. Read the process list — and decode STAT

```bash
# inside vps-lab
ps aux | head
```

`ps aux` = every process, all users, with detail (`a` all users, `u` user-oriented columns, `x` including those with no terminal). The column that repays study is **STAT**:

```
USER  PID %CPU %MEM   VSZ  RSS TTY  STAT START  TIME COMMAND
root    1  0.0  0.1  ...        ?    Ss   10:00  0:00 sshd: /usr/sbin/sshd -D ...
```

The first letter is the **process state**, the rest are modifiers:

| STAT | meaning |
|---|---|
| `R` | **R**unning or runnable (on-CPU or waiting its turn) |
| `S` | **S**leeping — waiting for an event (most processes, most of the time) |
| `D` | **D**isk sleep — *uninterruptible*, stuck in a kernel I/O call. **Can't be killed, not even by -9.** Lots of `D` = an I/O problem (dying disk, hung NFS) |
| `Z` | **Z**ombie — finished, but its parent hasn't read the exit code yet (Section 1's zombie-reaping doorman, `tini`, exists to prevent a pile of these) |
| `T` | s**T**opped — suspended by SIGSTOP/Ctrl-Z |
| modifiers | `s` session leader · `<` high priority · `N` low priority (niced) · `l` multi-threaded · `+` in the foreground process group |

So `Ss` on sshd = sleeping + session leader. Seeing a `Z` or a wall of `D` is a diagnosis, not trivia. Confirm PID 1 is still sshd (Section 1's rule, from the admin side):

```bash
ps -p 1 -o pid,comm,stat    # PID 1 = sshd — no systemd here (a real VPS would show 'systemd')
```

### 2. `/proc` — the kernel's dashboard as files

Every process has a directory `/proc/<pid>/`. Open PID 1's:

```bash
sudo cat /proc/1/cmdline | tr '\0' ' '; echo   # exact argv, NUL-separated → we swap NULs for spaces
sudo ls -l /proc/1/exe                          # symlink to the actual binary on disk
sudo ls /proc/1/fd                              # every open file descriptor (sockets, logs, pipes)
```

`cmdline` is the *real* command line (more honest than `ps`, which can be faked). `exe` proves which binary is running even if the file was deleted. `fd/` — the open file descriptors — is how you answer "what files/sockets does this process hold open?" without any special tool. This is the raw material `lsof` prints.

#### The container honesty check — `/proc` lies about the machine size

This is a **real production gotcha**, not a lab curiosity:

```bash
nproc                 # CPU count
cat /proc/loadavg     # load average
free -h               # memory
```

These report the **whole Docker Desktop VM**, not vps-lab's slice — because the container shares the host kernel, and these particular `/proc` files aren't namespaced. On a real cloud VPS they'd be honest. The consequence bites in production: an app that sizes its worker/thread pool from `nproc` (Gunicorn, Nginx `worker_processes auto;`, the JVM) will spin up threads for **the host's** core count while the container is cgroup-limited to two — massive over-subscription. The truth lives in the cgroup, not `/proc`:

```bash
cat /sys/fs/cgroup/cpu.max 2>/dev/null || echo "(cgroup v2 path may differ)"
```

The lesson to carry to Kubernetes: **`requests`/`limits` are the real numbers; `/proc` is the machine's, not your slice's.** (This is the same family of surprise as the OOMKilled=137 callback coming in Section 4.)

### 3. Make a process, watch it, signal it

Start a long sleeper in the background and inspect it:

```bash
sleep 1000 &          # '&' = run in background, shell keeps the prompt
jobs                  # [1]+ Running   sleep 1000 &   — the shell's job table
SLEEP_PID=$!          # $! = PID of the last backgrounded process
ps -o pid,ppid,stat,comm -p $SLEEP_PID   # STAT 'S' (sleeping), PPID = your bash
```

Now the signal vocabulary. List them all, then use the ones that matter:

```bash
kill -l | head        # the full numbered menu
kill -SIGTERM $SLEEP_PID      # 15: "please shut down cleanly" — the polite ask (docker stop's first move)
```

`sleep` has no SIGTERM handler, so it takes the kernel's **default** action for SIGTERM (terminate) and dies. Check the job table again — it's gone. The signals worth memorising:

| Signal | # | What it means | Catchable? |
|---|---|---|---|
| SIGHUP | 1 | terminal hung up (also: "reload config" by convention — nginx uses it) | yes |
| SIGINT | 2 | Ctrl-C — interrupt | yes |
| SIGKILL | 9 | **die now** — the kernel yanks the process; no handler runs | **no** |
| SIGTERM | 15 | "please shut down" — the default `kill`, the graceful one | yes |
| SIGSTOP / SIGCONT | 19 / 18 | freeze / resume (Ctrl-Z sends SIGTSTP, a catchable cousin) | STOP: no |

The critical pair, from Section 1's exit-code lesson: **SIGTERM (15) is a request the process can catch and handle** (flush buffers, close connections, exit clean → exit code 143 = 128+15). **SIGKILL (9) cannot be caught** — the kernel removes the process mid-instruction, no cleanup, exit 137 = 128+9. `kill -9` is the sledgehammer you reach for *only* when a process ignores SIGTERM. Prove the exit-code arithmetic:

```bash
sleep 1000 & 
kill -9 $!                     # SIGKILL
wait $! ; echo "exit: $?"      # 137 = 128 + 9  (the 137 you saw in Section 1, from the sender's side)
```

### 4. `nohup` and the SIGHUP problem — why background jobs die on logout

Here's a trap that catches everyone once: you start a server with `&`, close your SSH session, and the server dies. Why? When your terminal disconnects, the kernel sends **SIGHUP** (hang-up) to the whole session — and a bare `&` job is still in that session.

```bash
# the fragile way — dies when you log out
python3 -m http.server 8888 &

# the durable way — immune to SIGHUP, output redirected to a file
nohup python3 -m http.server 8888 > /tmp/http.log 2>&1 &
```

`nohup` = "**no** **h**ang**up**": it ignores SIGHUP and detaches from the terminal, so the process survives logout. `> /tmp/http.log 2>&1` captures both stdout and stderr (a detached process has no terminal to print to). This is the crude ancestor of what a service manager does properly — which is the whole point of the next step.

Kill that server before moving on:

```bash
kill $(pgrep -f http.server)   # pgrep finds PIDs by command pattern
```

### 5. systemd on paper — the thing vps-lab doesn't have

On a real VPS you would **never** run a service with `nohup ... &`. You'd write a **systemd unit** and let the init system supervise it — restart on crash, start on boot, capture logs, run as a specific user. vps-lab has no systemd (PID 1 is sshd — Section 1's foreground rule), so `systemctl` fails here. But apt *installs* unit files anyway (nginx will, in Lab 4). Read one as documentation. Write the unit the capstone deploy *would* use on a real box:

```bash
# inside vps-lab — we write this to READ it, not to run it
sudo tee /etc/systemd/system/capstone.service >/dev/null <<'EOF'
[Unit]
Description=Capstone API (the S1 FastAPI service)
After=network.target docker.service
Requires=docker.service

[Service]
# ExecStart runs in the FOREGROUND — same rule as a container's PID 1.
# systemd IS the supervisor here, so the process must not daemonize.
ExecStart=/usr/bin/docker run --rm -p 8080:8000 ghcr.io/itsmahadi007/capstone:latest
Restart=always            # crash? systemd relaunches it — like compose's 'restart: unless-stopped'
RestartSec=3
User=mahadi               # drop privileges — never run a service as root without reason
UMask=0027                # Lab 1's umask, set per-service

[Install]
WantedBy=multi-user.target   # 'enable' hooks it here so it starts at boot
EOF

# On a REAL server you'd now run (these FAIL here — no systemd — and that's the lesson):
# sudo systemctl daemon-reload
# sudo systemctl enable --now capstone
systemctl status capstone 2>&1 | head -3    # here: "System has not been booted with systemd"
```

Read the three sections aloud — they map exactly onto things you already know:

- **`[Unit]`** — metadata + ordering. `After=` / `Requires=` is `depends_on` from compose (Section 1 Lab 4), at the OS level.
- **`[Service]`** — how to run it. `ExecStart` runs in the **foreground** (systemd is the supervisor, so daemonizing would confuse it — the exact same foreground rule as a container's PID 1). `Restart=always` is `restart: unless-stopped`. `User=` drops privileges. `UMask=` is Lab 1.
- **`[Install]`** — `WantedBy=multi-user.target` is what `systemctl enable` wires up so the service starts at boot.

The chain you now understand end-to-end: **systemd unit** (real VPS) → **compose `restart:`** (Section 1) → **Kubernetes `restartPolicy` + Deployment** (Section 4). Same supervision idea, three altitudes. On a real box: `systemctl start/stop/status/restart`, `journalctl -u capstone` for its logs, `systemctl enable` for boot-start. Memorise that verb set — it's half of CKA's "node isn't ready" debugging.

Clean the paper unit away:

```bash
sudo rm /etc/systemd/system/capstone.service
```

## Verify

Proof command — start a supervised-style background process, find it two ways, signal it, confirm it's gone:

```bash
# inside vps-lab
nohup sleep 500 > /tmp/s.log 2>&1 &
pgrep -f "sleep 500"                       # prints a PID → it's running, detached
kill $(pgrep -f "sleep 500")               # polite SIGTERM
pgrep -f "sleep 500" || echo "gone"        # prints 'gone' → it accepted the signal and exited
```

Then answer aloud:

**1. STAT shows a process in `D`. You `kill -9` it and nothing happens. Why — and what is `D` telling you about the box?**

<details><summary>Answer (read after attempting aloud)</summary>

`D` is **uninterruptible sleep** — the process is blocked inside a kernel call, almost always waiting on I/O (disk, network filesystem). In that state it can't be delivered *any* signal, not even SIGKILL, because the kernel won't return to userspace to act on it until the I/O completes. So `kill -9` is queued but does nothing until the I/O unblocks. A cluster of `D`-state processes is a red flag for a storage problem — a dying disk, a hung NFS mount — not a runaway process. You fix the I/O, not the process.

</details>

**2. Difference between SIGTERM and SIGKILL, and which exit codes each produces?**

<details><summary>Answer (read after attempting aloud)</summary>

SIGTERM (15) is a *polite request* the process can **catch** and handle — flush buffers, close connections, exit cleanly → exit code **143** (128+15). SIGKILL (9) **cannot be caught or ignored**; the kernel removes the process immediately with no cleanup → exit code **137** (128+9). The 128+n rule encodes "killed by signal n". `docker stop` does exactly this dance: SIGTERM, wait (10s default), then SIGKILL — which is why a well-behaved app catches SIGTERM (137 in your logs means it didn't, or it ran out of time / got OOM-killed).

</details>

**3. `nproc` inside vps-lab reports 8, but the container is limited to 2 CPUs. Why, and what breaks because of it?**

<details><summary>Answer (read after attempting aloud)</summary>

The container shares the host kernel, and `/proc`/`nproc` read *unnamespaced* host values — so `nproc` reports the whole Docker Desktop VM's core count, not the container's cgroup limit. Apps that auto-size worker/thread pools from `nproc` (Gunicorn workers, `nginx worker_processes auto`, JVM GC threads) will create threads for 8 cores while cgroup-throttled to 2 → context-switch thrash and CPU throttling. The authoritative number lives in the cgroup (`/sys/fs/cgroup/cpu.max`), not `/proc`. In Kubernetes this is exactly why you set `resources.requests/limits` and why some runtimes need explicit worker counts.

</details>

**4. Why would you write a systemd unit instead of `nohup mycmd &`, and what does `Restart=always` correspond to in the tools you already know?**

<details><summary>Answer (read after attempting aloud)</summary>

`nohup ... &` just detaches a process; nothing supervises it. A systemd unit gives you restart-on-crash, start-on-boot (`enable` → `WantedBy=multi-user.target`), log capture (`journalctl -u`), a defined user/umask, and dependency ordering (`After=`/`Requires=`). `Restart=always` is the same idea as compose's `restart: unless-stopped` (Section 1) and Kubernetes' Deployment + `restartPolicy` (Section 4) — a supervisor that keeps the service alive. The `ExecStart` process must run in the **foreground** for the same reason a container's PID 1 does: systemd is the supervisor and needs to watch the actual process, not a daemonized orphan.

</details>

## Clean up

```bash
# inside vps-lab
pkill -f "sleep " 2>/dev/null; pkill -f http.server 2>/dev/null
rm -f /tmp/s.log /tmp/http.log
sudo rm -f /etc/systemd/system/capstone.service
exit
```

Leave vps-lab running. Lab 3 opens the network toolbox on the same box.
