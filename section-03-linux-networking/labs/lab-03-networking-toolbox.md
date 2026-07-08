# Lab 3 — The networking toolbox

**Goal:** build fluency (not artifacts) with the five commands you'll reach for on every box for the rest of your career — `ip`, `ss`, `dig`, `nc`, `curl` — and lock in the single most useful debugging heuristic in networking: **connection refused vs. connection timeout**. By the end you'll speak raw HTTP to the capstone container by hand.

## The mental map (read this first)

A network service, stripped down, is just **a process holding a numbered mailbox (a socket) open, waiting for mail.** Everything in this lab answers one of four questions about that:

```
   ip    ──▶  "what's my address, and how do packets leave here?"   (interfaces + routes)
   ss    ──▶  "which mailboxes are open, and WHO holds each one?"    (listening sockets → PID)
   dig   ──▶  "what number does this NAME resolve to?"               (DNS)
   nc    ──▶  "can I even reach that mailbox? let me knock."         (raw TCP)
   curl  ──▶  "let me have the full HTTP conversation, verbosely."   (application layer)
```

And the heuristic that turns a vague "the site is down" into a diagnosis in one command:

```
   you send a packet to host:port ─┐
                                    ├─▶  something answers "nobody's home on that port"  → REFUSED (fast, an RST)
                                    ├─▶  packet vanishes, no reply at all                 → TIMEOUT (slow, silence)
                                    └─▶  it answers                                        → OPEN
```

**Refused = a live host said no** (nothing is listening on that port, *or* a firewall actively rejected you). **Timeout = nobody said anything** (wrong host / no route, *or* a firewall silently dropped the packet). That difference — a fast "no" vs. a slow silence — is the first fork in every network debug, and Lab 6's firewall will let you *manufacture* both on purpose.

## Steps

> All inside vps-lab: `ssh -i vps-lab/keys/vps_key -p 9022 mahadi@localhost`
>
> This lab inspects the deployed capstone. Confirm it's up first: `sudo docker ps` should list one capstone container publishing `8080->8000`. If not, run the **reimage ritual** in Lab 4 step 2 to restore the Section 2 state.

### 0. Install the two tools the base image lacks

vps-lab's Dockerfile already ships `iproute2` (that's `ip` and `ss`). `dig` and `nc` aren't in a minimal Debian, so install them:

```bash
# inside vps-lab
sudo apt-get update && sudo apt-get install -y bind9-dnsutils netcat-openbsd
```

`bind9-dnsutils` is Debian 12's package name for `dig`/`nslookup` (older guides say `dnsutils` — it's an alias). `netcat-openbsd` is the `nc` variant with the flags this lab uses. (Reminder from Section 1: apt-installed packages here survive `stop`/`start` but die on `down`/recreate — the reimage ritual re-installs them.)

### 1. `ip` — your address and your exits

```bash
ip -brief addr        # -brief = the human summary
```

```
lo    UNKNOWN  127.0.0.1/8 ::1/128
eth0  UP       172.20.0.2/16 ...
```

Two interfaces, same as Section 1 Lab 5 saw — but now you'll read routes too. `lo` is **loopback**: the machine talking to itself, `127.0.0.1`, never touches a wire. `eth0` holds the container's private address on the compose network (`172.x`). Now: how does a packet to the outside world *leave*?

```bash
ip route
```

```
default via 172.20.0.1 dev eth0
172.20.0.0/16 dev eth0 proto kernel scope link src 172.20.0.2
```

Read it top-down, most-specific-wins: a packet for `172.20.x.x` (same network) goes **directly** out `eth0`. Anything else matches `default` and is handed to the **gateway** `172.20.0.1` (the Docker network's router — this is where Docker Desktop's NAT takes over to reach the internet). "What's my default gateway?" is the first question when a box can reach its neighbours but not the internet. `ip link` shows the interfaces at layer 2 (MAC addresses, up/down state) if you need it.

### 2. `ss` — who owns which port

This is the command you'll type a thousand times. It replaced the old `netstat`:

```bash
sudo ss -tlnp
```

Flags: **`t`** TCP, **`l`** listening only, **`n`** numeric (don't waste time resolving names/ports), **`p`** show the owning process (needs sudo to see other users' processes).

```
State   Local Address:Port   Peer Address:Port  Process
LISTEN  0.0.0.0:22           0.0.0.0:*          users:(("sshd",pid=1,...))
LISTEN  0.0.0.0:8080         0.0.0.0:*          users:(("docker-proxy",pid=...))
```

Read each line as "**who** is holding **which** mailbox, open to **whom**":

- `0.0.0.0:22` owned by **sshd, pid=1** — Section 1's PID 1, seen from the socket side. `0.0.0.0` = "listening on *all* interfaces" (the `--host 0.0.0.0` lesson from Section 1 Lab 2, now visible in `ss`).
- `0.0.0.0:8080` owned by **docker-proxy** — *this is the payoff.* When your S2 deploy ran `docker run -p 8080:8000` inside vps-lab, Docker put a `docker-proxy` process on `8080` that forwards into the inner container's `8000`. So "who owns port 8080?" is answered concretely: a docker-proxy helper, not the app itself. (Lab 6 shows the *other* half of `-p` — the NAT rule — and the two together are how published ports work.)

If a port bind ever fails with "address already in use", `sudo ss -tlnp | grep :PORT` is how you find the current owner in one line. This is the exact tool for Section 1's "port is already allocated", from inside the box.

### 3. `dig` — names to numbers

DNS is a phone book: names in, addresses out. `dig` shows the whole lookup; `+short` gives just the answer:

```bash
dig +short example.com          # one or more A records (IPv4 addresses)
dig example.com | sed -n '/ANSWER SECTION/,/^$/p'   # the annotated answer block
cat /etc/resolv.conf            # which resolver this box asks
```

`/etc/resolv.conf` names the DNS server the box trusts. On a normal machine it's the LAN/ISP resolver; here it points at Docker's embedded resolver (`127.0.0.11` — the same one Section 1 Lab 4 used so `redis://redis:6379` worked by *name*). That closes a loop: compose's service-name DNS and public-internet DNS are the **same mechanism**, one just has private entries Docker injects. Note the difference in kind: `ss` finds *ports*; `dig` resolves *names* — the two halves of "where do I connect?".

### 4. `nc` — knock on a port, and speak HTTP by hand

`nc` (netcat) is a bare TCP wire. First, use it purely to *test reachability*:

```bash
nc -vz 127.0.0.1 8080          # -v verbose, -z "just check, send no data"
```

```
Connection to 127.0.0.1 8080 port [tcp/*] succeeded!
```

That's a clean **OPEN**. Now the heuristic, live — knock on a port nothing listens on:

```bash
nc -vz 127.0.0.1 9999          # nothing is on 9999
```

```
nc: connect to 127.0.0.1 port 9999 (tcp) failed: Connection refused
```

**REFUSED, and it came back instantly** — the kernel sent an RST because no socket owns 9999. Hold that feeling; in Lab 6 you'll make the *same* port instead **time out** (silence) with a DROP rule, and the contrast is the whole lesson.

Now the party trick that makes HTTP stop being magic — **be the browser, by hand:**

```bash
printf 'GET /health HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n' | nc 127.0.0.1 8080
```

You typed the raw request bytes; `nc` put them on the socket; the capstone app answered on the same socket:

```
HTTP/1.1 200 OK
date: ...
server: uvicorn
content-type: application/json
...

{"status":"ok"}
```

Everything above the blank line is **headers**; the blank line (`\r\n\r\n`) is the separator; below it is the **body**. That's the entire HTTP/1.1 protocol — a text conversation over TCP. `curl`, your browser, and nginx all just automate typing this. The `\r\n` (carriage-return + newline) line endings are not optional — HTTP is picky, and hand-typing it once teaches you why a malformed proxy header breaks things (Lab 4).

### 5. `curl -v` — the full conversation, annotated

`curl` does step 4 for you and *narrates* it:

```bash
curl -v http://127.0.0.1:8080/health
```

The `>` lines are what curl **sent**, the `<` lines are what came **back**:

```
*   Trying 127.0.0.1:8080...
* Connected to 127.0.0.1 (127.0.0.1) port 8080
> GET /health HTTP/1.1
> Host: 127.0.0.1:8080
> User-Agent: curl/...
>
< HTTP/1.1 200 OK
< server: uvicorn
< content-type: application/json
<
{"status":"ok"}
```

`curl -v` is your everyday tool; `curl -I` sends a `HEAD` (headers only, no body) when you just want the status line. Keep `curl -v` in your fingers — in Lab 4 you'll use it to *see* the headers nginx adds, and in Lab 5 to watch the TLS handshake curl narrates before the HTTP even starts.

## Verify

Proof command — resolve, knock, and speak, in one pass:

```bash
# inside vps-lab
sudo ss -tlnp | grep -E ':(22|8080)'                        # both mailboxes, with owners
nc -vz 127.0.0.1 8080 && echo "REACHABLE"                   # OPEN
nc -vz 127.0.0.1 9999 || echo "REFUSED (as expected)"       # REFUSED, instantly
printf 'GET /health HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n' | nc 127.0.0.1 8080 | tail -1
```

The last line prints the health JSON — proof you spoke HTTP by hand to the deployed capstone. Then answer aloud:

**1. `curl` to your service hangs for 30 seconds then fails, vs. fails instantly with "connection refused". What does each tell you, and where do you look next?**

<details><summary>Answer (read after attempting aloud)</summary>

**Refused (instant)** = a live host answered with a TCP RST — the host is up and reachable, but *nothing is listening* on that port (the service crashed / never started / bound to the wrong interface), or a firewall actively **REJECT**ed you. Look at `ss -tlnp` (is the process even listening? on which address — `127.0.0.1` only vs `0.0.0.0`?). **Timeout (slow silence)** = no reply at all — wrong host/IP, no route, or a firewall **DROP**ping packets into a black hole. Look at `ip route`, the address you dialled, and firewall rules. Fast "no" = reached the host; slow silence = didn't (or was dropped).

</details>

**2. `ss -tlnp` shows port 8080 owned by `docker-proxy`, not by the capstone app. Why?**

<details><summary>Answer (read after attempting aloud)</summary>

The S2 deploy ran `docker run -p 8080:8000` *inside* vps-lab. Docker's port-publishing puts a `docker-proxy` userland helper listening on the host-side port (8080 here, on vps-lab's network) that forwards connections into the inner container's `8000` (the container publishes on all interfaces, `0.0.0.0`). So the process holding the 8080 socket is Docker's proxy, and the app sits behind it on 8000. (The other half of `-p` is a NAT/DNAT rule in iptables — Lab 6. Together, proxy + DNAT are how `-p` works.)

</details>

**3. `/etc/resolv.conf` inside vps-lab points at `127.0.0.11`. What is that, and how does it connect to Section 1's `redis://redis:6379`?**

<details><summary>Answer (read after attempting aloud)</summary>

`127.0.0.11` is Docker's **embedded DNS resolver**, present in every container on a user-defined network. It resolves *service names* to the current container IPs (that's how `redis://redis:6379` worked in Section 1 Lab 4 without hardcoding an IP) and forwards everything else (like `example.com`) to the host's real resolver. Punchline: compose service-DNS and public-internet DNS are the same mechanism — Docker's resolver just injects private records for your service names and proxies the rest.

</details>

## Clean up

```bash
# inside vps-lab
# nothing to tear down — this lab was pure inspection.
# (bind9-dnsutils / netcat-openbsd stay installed for later labs; they'll re-install on reimage.)
exit
```

Leave the capstone container and vps-lab running — Lab 4 puts nginx in front of that exact `8080`.
