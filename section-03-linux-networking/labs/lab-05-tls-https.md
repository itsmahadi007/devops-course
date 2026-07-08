# Lab 5 — TLS from first principles + self-signed HTTPS

**Goal:** understand what actually happens in an HTTPS handshake (not the hand-wave), then make nginx serve the capstone over **HTTPS on host port 9041** with a self-signed certificate — read the cert, watch the handshake with `openssl s_client`, understand *exactly why the browser warns*, and learn on paper where Let's Encrypt would slot in on a real box.

## The mental map (read this first)

TLS solves two problems at once, and people conflate them:

1. **Encryption** — nobody between you and the server can read the traffic.
2. **Identity** — you're actually talking to the real server, not an impostor in the middle.

The handshake solves both using the **same asymmetric-key math you already met in Section 1's SSH lab** (public key = a lock anyone can use, private key = the only thing that opens it), plus one new idea: a **chain of trust**.

```
      THE HANDSHAKE (simplified TLS 1.3)                    THE CHAIN OF TRUST
 client                         server              ┌────────────────────────────────────┐
   │  1. hello, here's what I support │              │  Root CA  (in your OS/browser store) │
   │─────────────────────────────────▶              │     │ signs                          │
   │  2. my certificate (has my       │              │     ▼                                │
   │◀────  PUBLIC key + who I claim   │              │  Intermediate CA                     │
   │        to be, SIGNED by a CA)    │              │     │ signs                          │
   │  3. [verify the signature chain] │              │     ▼                                │
   │  4. key exchange → shared secret │              │  your server's LEAF cert  ◀─ served  │
   │◀────────────────────────────────▶              └────────────────────────────────────┘
   │  5. encrypted HTTP flows          │       "I trust the leaf BECAUSE I trust who signed
   │◀════════════════════════════════▶│        who signed it, up to a root I already trust."
```

The key insight — **why a certificate means anything at all:** a cert is just "here's my public key and my identity (`example.com`), and here's a **signature** from a Certificate Authority vouching for it." Your browser ships with ~150 **root CA** public keys baked in (the *trust store*). If the cert's chain leads up to one of those roots, the browser trusts it. **A self-signed cert has no such chain** — it vouches for *itself* ("trust me because I say so") — which is precisely why the browser warns. The encryption is identical; the *identity* is unverified.

One more must-know: modern browsers verify identity against the certificate's **SAN** (Subject Alternative Name) field — the list of hostnames/IPs the cert is valid for. The old `CN` (Common Name) field is ignored. A cert without a matching SAN fails validation *even if* the chain is trusted. This trips up everyone making their first cert.

## Steps

> Cert generation and nginx config are **inside vps-lab**; the compose port edit is **on your Mac**.

### 1. Generate a self-signed cert (inside vps-lab)

`openssl` ships with Debian. One command makes both a private key and a self-signed cert:

```bash
# inside vps-lab
ssh -i vps-lab/keys/vps_key -p 9022 mahadi@localhost   # from your Mac, if not already in
sudo mkdir -p /etc/nginx/tls
sudo openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout /etc/nginx/tls/capstone.key \
  -out    /etc/nginx/tls/capstone.crt \
  -days 365 \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
```

Flag by flag — every one is a real concept:

- `req -x509` = make a self-signed certificate directly (skip the "certificate signing request → CA signs it" step, because *we are* the CA here).
- `-newkey rsa:2048` = generate a fresh 2048-bit RSA private key at the same time. (RSA-2048 is the safe default; ed25519/ECDSA certs exist and are smaller, RSA is maximally compatible.)
- `-nodes` = "**no** **DES**" — don't encrypt the private key with a passphrase. A passphrase-protected key would make nginx prompt for it on every start (impossible for an unattended service) — real servers use `-nodes` + tight file permissions instead. **Chmod it like an SSH key** (Lab 1): the private key must be unreadable to others.
- `-days 365` = validity window. Real public CAs now cap at ~90 days (Let's Encrypt) precisely to force automated renewal.
- `-subj "/CN=localhost"` = the subject identity (mostly cosmetic now that SAN rules).
- `-addext "subjectAltName=..."` = **the field that actually matters** — the hostnames/IPs this cert is valid for. Without it, every client rejects the cert.

You now have a `.key` (the SECRET — never leaves the box, never committed) and a `.crt` (the public certificate — safe to hand out). Lock the key down:

```bash
sudo chmod 600 /etc/nginx/tls/capstone.key
sudo ls -l /etc/nginx/tls/            # key 600, crt 644 — same discipline as .ssh
```

### 2. Read the cert you just made

```bash
sudo openssl x509 -in /etc/nginx/tls/capstone.crt -noout -text | head -25
```

Look for these lines — they *are* the mental map, made concrete:

```
Issuer:  CN = localhost           ◀─ who vouches for this cert
Validity: Not Before / Not After  ◀─ the 365-day window
Subject: CN = localhost           ◀─ who this cert is FOR
...
X509v3 Subject Alternative Name:
    DNS:localhost, IP Address:127.0.0.1   ◀─ the SAN — what browsers check
```

**Issuer == Subject.** That's the definition of self-signed: the cert's issuer *is* the cert's subject — it vouches for itself. On a real Let's Encrypt cert the Issuer would read `R3 / Let's Encrypt`, a name that chains to a root in every trust store. This one chains to nothing.

### 3. Add HTTPS to the nginx server block (inside vps-lab)

Extend the Lab 4 config: keep :80, add a TLS `server` block on :443, and redirect HTTP→HTTPS (standard practice — never serve the app on plain HTTP once TLS exists):

```bash
# inside vps-lab
sudo tee /etc/nginx/sites-available/capstone >/dev/null <<'EOF'
# HTTP :80 — redirect everything to HTTPS
server {
    listen 80;
    server_name _;
    return 301 https://$host$request_uri;    # 301 permanent redirect to the https URL
}

# HTTPS :443 — the real server
server {
    listen 443 ssl;
    server_name _;

    ssl_certificate     /etc/nginx/tls/capstone.crt;   # the public cert nginx presents
    ssl_certificate_key /etc/nginx/tls/capstone.key;   # the private key (proves nginx owns the cert)
    ssl_protocols       TLSv1.2 TLSv1.3;               # disable ancient, broken versions

    access_log /var/log/nginx/capstone.access.log;
    error_log  /var/log/nginx/capstone.error.log;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;      # now correctly says 'https' to the app
    }
}
EOF

sudo nginx -t          # ALWAYS test before reload (Lab 4 reflex)
sudo nginx -s reload
```

Note `$scheme` now resolves to `https` for the TLS server block — so the app finally learns the user is on HTTPS (the Lab 4 header that "does nothing until now" starts earning its keep). **TLS terminates at nginx**: the crypto happens here, and nginx→app stays plain HTTP on loopback (`127.0.0.1:8080`) — fine, because that hop never leaves the box.

### 4. Publish 9041 — compose edit (on your Mac)

Add the HTTPS door. Full file, `9041:443` is the new S3 line:

```yaml
services:
  vps:
    build: .
    container_name: vps-lab
    hostname: vps-lab
    privileged: true
    ports:
      - "9022:22"             # SSH
      - "9030:8080"           # S2 raw deploy chain
      - "9040:80"             # S3 Lab 4 nginx HTTP
      - "9041:443"            # S3 Lab 5 nginx HTTPS  ◀── ADD THIS LINE
    restart: unless-stopped
```

```bash
# on your Mac
cd vps-lab && docker compose up -d      # recreate to add the port
```

**Recreate = reimage.** Re-run the Lab 4 step 2 reimage ritual, then re-do steps 1 and 3 of this lab (cert + config). (Same friction as Lab 4 — one command in Section 6 will end it. To do all recreations at once, you could add `9040:80` and `9041:443` together back in Lab 4.)

### 5. Connect over HTTPS — and meet the warning, then satisfy it

First, prove the warning is real. A plain `curl` refuses the self-signed cert:

```bash
# on your Mac
curl -sI https://localhost:9041/health
```

```
curl: (60) SSL certificate problem: self-signed certificate
```

**This is the browser warning, in text.** curl did the handshake, got the cert, tried to chain it to a trusted root, found none → refused. This is TLS's *identity* guarantee working exactly as designed: unverified identity = stop. Two ways forward:

```bash
# (a) -k = "I accept the risk, skip verification" — encryption still happens, identity is NOT checked
curl -k -sI https://localhost:9041/health          # HTTP/1.1 200 OK

# (b) the honest way: explicitly trust OUR cert as the CA for this request
#     first copy the cert out of vps-lab to your Mac:
scp -i vps-lab/keys/vps_key -P 9022 mahadi@localhost:/tmp/capstone.crt ./capstone.crt 2>/dev/null || \
  ssh -i vps-lab/keys/vps_key -p 9022 mahadi@localhost 'sudo cat /etc/nginx/tls/capstone.crt' > capstone.crt
curl --cacert capstone.crt -sI https://localhost:9041/health   # HTTP/1.1 200 OK, identity VERIFIED
```

`-k` (insecure) is fine for a lab and a disaster in production — it's "encrypt but don't check who I'm talking to", which throws away half of TLS and is how MITM attacks succeed. `--cacert` is the honest version: "here's the one CA I choose to trust for this call". Watch the redirect too — hitting HTTP now bounces to HTTPS:

```bash
curl -k -sI http://localhost:9040/health | head -1     # HTTP/1.1 301 Moved Permanently
```

### 6. Watch the handshake with `openssl s_client`

`curl` hides the handshake; `openssl s_client` shows it — this is *the* tool for debugging "why won't this TLS connect":

```bash
# on your Mac
echo | openssl s_client -connect localhost:9041 -servername localhost 2>/dev/null | head -20
```

Read the output — it's the mental map, live:

```
CONNECTED(...)
depth=0 CN = localhost
verify error:num=18:self-signed certificate     ◀─ the chain led nowhere (depth 0 = the leaf itself)
---
Certificate chain
 0 s:CN = localhost
   i:CN = localhost                              ◀─ subject == issuer: self-signed, one link, no chain
---
SSL-Session:
    Protocol  : TLSv1.3                          ◀─ negotiated the modern protocol
    Cipher    : TLS_AES_256_GCM_SHA384
```

`verify error:num=18:self-signed certificate` names the exact reason clients balk. `-servername localhost` sends the **SNI** (Server Name Indication) — the "which site do you want?" field sent *in the clear* at the start of the handshake, so one IP can host many TLS sites (the TLS-era analogue of the `Host:` header). Omit it and multi-site servers hand you the wrong cert — a classic real-world gotcha.

### 7. Let's Encrypt — where the real cert would come from (on paper)

You can't get a real cert here, and understanding *why* is the lesson. Let's Encrypt (via the **ACME** protocol) issues free, trusted, 90-day certs — but it must first **prove you control the domain**:

- **HTTP-01 challenge:** the CA gives you a token; you serve it at `http://yourdomain/.well-known/acme-challenge/<token>`; the CA fetches it over the *public internet*. If it appears, you clearly control that domain → cert issued.
- **DNS-01 challenge:** you place a TXT record in the domain's DNS; the CA queries it. (This one works for wildcard certs and private servers.)

**Why it can't work on vps-lab:** no public IP, no domain name — Let's Encrypt's servers cannot reach `localhost:9041` to complete HTTP-01. That's not a limitation of the tech; it's the whole point (only real domain owners get certs). On a real VPS the entire flow is one command with **certbot**:

```bash
# would run on a real box with a real domain + public IP (do NOT run here):
#   sudo apt install certbot python3-certbot-nginx
#   sudo certbot --nginx -d api.yourdomain.com
# → certbot solves the challenge, drops the cert on disk, rewrites your nginx TLS block,
#   and installs a systemd timer to auto-renew before the 90 days expire.
```

That's the difference between this lab and production: swap the self-signed cert for a certbot-issued one and **nothing else in the nginx config changes** — same `ssl_certificate` lines, real trust. (Optional real-domain extra below.)

<details><summary>OPTIONAL: do it for real on a domain you own (same-day teardown)</summary>

If you own a domain and a real public box (a $5 VPS, or a temporary cloud instance): point an A record at its IP, `apt install certbot python3-certbot-nginx`, run `certbot --nginx -d your.domain`, and watch a *green padlock* appear with zero `-k`. **Teardown same day:** `certbot delete`, remove the A record, destroy the instance. This is the single most common paid freelance infra task — worth doing once end-to-end.

</details>

## Verify

Proof command — encryption works, identity is (correctly) untrusted until you supply the CA:

```bash
# on your Mac
curl -sI https://localhost:9041/health 2>&1 | grep -qi "self-signed" && echo "identity: correctly UNTRUSTED"
curl -k -sI https://localhost:9041/health | head -1                    # HTTP/1.1 200 OK (encrypted)
curl -k -sI http://localhost:9040/health | head -1                     # HTTP/1.1 301 (redirect to https)
echo | openssl s_client -connect localhost:9041 2>/dev/null | grep -i "Protocol"   # TLSv1.3
```

Then answer aloud:

**1. Your browser shows "Not Secure / certificate not trusted" on the self-signed site. Is the traffic encrypted? Explain what's wrong and what isn't.**

<details><summary>Answer (read after attempting aloud)</summary>

Yes — the traffic **is** fully encrypted; the handshake completed and a session key was negotiated. What failed is the *identity* half of TLS: the certificate is self-signed (Issuer == Subject), so its chain doesn't lead to any root CA in the browser's trust store. The browser can't verify you're talking to the *real* server rather than an impostor, so it warns. Encryption ✅, verified identity ❌. A Let's Encrypt cert fixes the identity half by chaining to a trusted root — the encryption is identical either way.

</details>

**2. What is a SAN, and what happens if the cert's SAN doesn't include the hostname you're connecting to — even if the cert is signed by a trusted CA?**

<details><summary>Answer (read after attempting aloud)</summary>

SAN = **Subject Alternative Name**, the list of hostnames/IPs a cert is valid for. Modern clients verify the connection hostname against the SAN (the old CN field is ignored). If the SAN doesn't include the host you dialled, validation **fails** — you get a name-mismatch error — *regardless* of a perfect trust chain. A cert trusted by a CA but issued for `example.com` won't work for `api.example.com`. It's the #1 first-cert mistake: forgetting `-addext subjectAltName=...`.

</details>

**3. TLS terminates at nginx. What does that mean for the nginx→app hop, and why is `X-Forwarded-Proto` suddenly load-bearing?**

<details><summary>Answer (read after attempting aloud)</summary>

"TLS terminates at nginx" = nginx does all the encryption/decryption; the connection from nginx to the app is **plain HTTP** on loopback (`127.0.0.1:8080`), which is safe because it never leaves the box. But that means the app can't tell the *user* arrived over HTTPS — from the app's view it's an http request. `X-Forwarded-Proto: https` (set by nginx, from `$scheme`) tells the app the original scheme, so redirects, absolute URLs, and secure-cookie decisions come out `https://` instead of `http://`. Without it you get redirect loops and insecure cookies behind a TLS-terminating proxy.

</details>

**4. Why can't Let's Encrypt issue a cert for vps-lab, and what exactly would change in your nginx config if you swapped in a real certbot cert?**

<details><summary>Answer (read after attempting aloud)</summary>

Let's Encrypt must prove you control the domain via an ACME challenge — HTTP-01 (it fetches a token from `http://yourdomain/.well-known/...` over the public internet) or DNS-01 (it reads a TXT record). vps-lab has no public IP and no domain, so the CA's servers can't reach it to validate → no cert. That's by design: only real domain owners get certs. Swapping in a certbot cert changes **almost nothing** in nginx — the `ssl_certificate` / `ssl_certificate_key` lines point at certbot's files instead of the self-signed ones; the server block is otherwise identical. certbot also adds a renewal timer because real certs are ~90 days.

</details>

## Clean up

```bash
# on your Mac
rm -f capstone.crt              # the exported cert copy
# inside vps-lab: leave the TLS config + cert in place — this is the section's end state
#   (nginx+TLS fronting the capstone). Lab 6 puts a firewall around it.
```

Leave everything running. Commit your section-03 files + the two new `docker-compose.yml` port lines. **Never commit the `.key`** — it lives only inside the container (and it's gitignored regardless).
