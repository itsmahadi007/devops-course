# Lab 4 — EC2, ALB, and Auto Scaling

**Goal:** understand the classic three-piece web-tier pattern — **EC2** (the compute), an **Application Load Balancer** (the front door), and an **Auto Scaling Group** (the self-healing, self-sizing fleet) — well enough to draw it and defend every choice in a scenario. You launch an EC2 instance in LocalStack to make the object model concrete; ALB and ASG you learn on paper with diagrams (LocalStack's free tier doesn't emulate them), which is exactly how the SAA tests them. This lab stands on Lab 3's VPC — the LB lives in public subnets, the instances in private ones.

> **LocalStack reality:** the free tier runs **EC2** (it can even back instances with real helper containers via the docker.sock mount from Lab 1) — so steps 1–3 are hands-on. **ALB/ELB and Auto Scaling are not in the free tier** — steps 4–6 are paper + decision drills, with an OPTIONAL real-AWS free-account build at the end (same-day teardown). This split is fine: the exam never asks you to *click* an ASG together, it asks *when* and *why*.

## The mental map (read this first)

The pattern that has launched a million web apps:

```
                     the internet
                          │
                   ┌──────▼───────┐
                   │     ALB      │   lives in PUBLIC subnets, ≥2 AZs
                   │ (layer 7,    │   health-checks each target, routes by path/host
                   │  HTTP/HTTPS) │   terminates TLS here
                   └──┬────────┬──┘
          ┌───────────┘        └───────────┐
          ▼                                ▼
   ┌─────────────┐                  ┌─────────────┐
   │ TARGET GROUP│  ◀── the ASG registers/deregisters instances here
   │  ┌────────┐ │                  │  ┌────────┐ │
   │  │ EC2 #1 │ │  PRIVATE subnet  │  │ EC2 #2 │ │  PRIVATE subnet
   │  │ AZ-a   │ │                  │  │ AZ-b   │ │  AZ-b
   │  └────────┘ │                  │  └────────┘ │
   └─────────────┘                  └─────────────┘
          ▲                                ▲
          └──────── AUTO SCALING GROUP ─────┘
             desired=2, min=2, max=6
             replaces unhealthy instances (self-healing)
             adds/removes instances on a metric (self-sizing)
```

The three pieces and the one job each does:

- **EC2** = a virtual server. You pick an **instance type** (`t3.micro` = 2 vCPU burstable, cheap; `m5.large` = balanced; `c5` = compute; `r5` = memory) and an **AMI** (the disk image it boots from — the cloud cousin of a Docker base image). It's the least-managed compute AWS sells: you own the OS, patching, everything above the hypervisor. Your existing "I deploy on EC2" experience *is* this box.
- **ALB (Application Load Balancer)** = a **layer-7** (HTTP/HTTPS) front door. It health-checks its targets and only sends traffic to healthy ones, spreads load across AZs, terminates TLS, and routes by path (`/api → group A`, `/ → group B`) or host header. Its health check is the S1 Docker healthcheck / K8s readiness probe you already know — "is this instance actually answering?" — deciding who receives traffic.
- **ASG (Auto Scaling Group)** = the fleet manager. It keeps `desired` instances running across your chosen subnets/AZs, **replaces any that fail a health check** (self-healing — the reconcile loop from S1 compose and K8s, applied to whole servers), and **scales the count** up/down on a policy (CPU > 70% → add instances). It registers new instances into the ALB's target group automatically.

**The load-balancer family — one exam slide's worth:**

| | ALB | NLB | (CLB) |
|---|---|---|---|
| Layer | 7 (HTTP/HTTPS) | 4 (TCP/UDP) | legacy, avoid |
| Routes by | path, host, headers | IP/port only | basic |
| Use when | web apps, microservices, path routing | extreme throughput, low latency, static IP, non-HTTP | never (new work) |
| Speed | fast | fastest | — |

Default answer to "load-balance a web app" = **ALB**. Switch to **NLB** only when you hear "millions of requests/sec," "ultra-low latency," "static IP / PrivateLink," or "not HTTP."

## Steps

Keep LocalStack up and the alias set.

### 1. Find an AMI and launch an EC2 instance into the private subnet

LocalStack seeds fake AMIs. Reuse Lab 3's VPC if it's still up; otherwise recreate a subnet quickly. Launch into a private subnet:

```bash
# a subnet to launch into (reuse $PRIV_A from Lab 3, or make one)
SUBNET_ID=${PRIV_A:-$(awslocal ec2 create-subnet --vpc-id "$(awslocal ec2 create-vpc --cidr-block 10.0.0.0/16 --query 'Vpc.VpcId' --output text)" --cidr-block 10.0.11.0/24 --query 'Subnet.SubnetId' --output text)}

INSTANCE_ID=$(awslocal ec2 run-instances \
  --image-id ami-df5de72bdb3b \
  --instance-type t3.micro \
  --subnet-id "$SUBNET_ID" \
  --count 1 \
  --query 'Instances[0].InstanceId' --output text)
echo "INSTANCE_ID=$INSTANCE_ID"
```

`run-instances` returns an `i-…` ID. On real AWS `ami-df5de72bdb3b` wouldn't be valid — you'd look up the current Amazon Linux 2023 AMI ID for your region (it changes with every patch, which is why Terraform/Packer resolve it dynamically). LocalStack accepts placeholder AMI IDs. You chose `t3.micro`: the smallest general-purpose burstable type, and the one that used to be free-tier — a sensible dev default.

#### The instance-type mental shortcut

The letter is the family, the number is the generation, the suffix is the size: `t3.micro` = **t**(burstable)**3**(gen 3)**.micro**(size). Families worth knowing for the exam: **t** = burstable/cheap (dev, low-traffic), **m** = balanced (general web), **c** = compute-optimized (CPU-bound), **r** = RAM-optimized (in-memory caches, big DBs), **g/p** = GPU (ML — you'll care in Section 10). "Memory-intensive workload" → `r`; "CPU-bound batch" → `c`; "small steady web app" → `t` or `m`.

### 2. Read the instance's state and placement

```bash
awslocal ec2 describe-instances --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].{State:State.Name,Type:InstanceType,AZ:Placement.AvailabilityZone,PrivateIp:PrivateIpAddress,SubnetId:SubnetId}'
```

You'll see `State: running`, its type, the AZ, and a private IP from the subnet's range (`10.0.11.x`). It has **no public IP** because it's in a private subnet — correct for an app server that should only be reachable through the load balancer. That "only the LB is exposed; instances hide in private subnets" layout is the SAA-preferred web-tier security posture.

### 3. Attach user-data (the boot script) — the pattern behind every ASG

Real instances configure themselves at first boot via a **user-data** script (install the app, start it). This is how an ASG can launch identical, ready-to-serve instances with no manual step — the cloud version of a Dockerfile's `CMD`, sort of. Inspect the attribute:

```bash
awslocal ec2 describe-instance-attribute --instance-id "$INSTANCE_ID" --attribute userData
```

Empty here (we launched without one), but note the mechanism: in an ASG you don't launch instances by hand — you define a **Launch Template** (AMI + instance type + user-data + SG + IAM role) once, and the ASG stamps out identical instances from it. Launch Template : ASG :: Docker image : Kubernetes Deployment. Same "define the unit once, let the controller replicate it" idea you've now seen three times (compose, K8s, here).

### 4. (PAPER) Design the ALB + target group + listener

No LocalStack for this — reason it through. The pieces and how they connect:

- **Target group** — a set of backends (your EC2 instances, or IPs, or Lambdas) plus a **health check** (`GET /health` every 30s; 2 passes = healthy, 3 fails = drained). Only healthy targets get traffic. Your capstone already exposes `/health` (S1 Lab 3) — that's the endpoint the target group would hit.
- **Listener** — "on port 443 (HTTPS), do X." X is a rule: default → forward to target group A; `path is /api/*` → target group B. This is where TLS terminates (you attach an ACM certificate).
- **The ALB itself** — spans ≥2 public subnets (AZs), gets a DNS name, and you point your domain's Route 53 record at it.

Draw the request path from memory: `client → Route 53 (DNS) → ALB (TLS terminate, pick healthy target by path) → target group → EC2 in a private subnet → response back out`. If you can narrate that, you can answer most ALB questions.

#### Why "terminate TLS at the ALB" matters

The ALB decrypts HTTPS, so your instances can speak plain HTTP internally (simpler, and you manage one certificate at the LB via ACM, free auto-renewing). The exam contrasts this with **end-to-end encryption** (re-encrypt to the instances) for compliance-heavy cases, and with the **NLB** (layer 4, passes TCP through without seeing HTTP — used when you need TLS to terminate on the instance itself or need raw TCP).

### 5. (PAPER) Design the Auto Scaling Group

The ASG config is four numbers and a trigger:

- **min / desired / max** (e.g. 2 / 2 / 6): never fewer than min, aim for desired, never more than max. `min: 2` across two AZs = survives an AZ loss with capacity to spare.
- **health check type**: EC2 (is the VM alive?) or, better, **ELB** (does it pass the ALB's `/health`?). ELB health checks catch a hung app that the OS thinks is fine — the same "process running ≠ app answering" lesson from your Docker healthcheck.
- **scaling policy**: *target tracking* ("keep average CPU at 50%") is the modern default — you name the target, AWS figures out when to add/remove. Older styles: *step* (CPU > 70 → +2) and *scheduled* (scale up at 9am).
- **self-healing**: if an instance fails its health check, the ASG terminates and replaces it — no page, no human. This is the reconcile loop (S1 compose "recreate only the drift", K8s "kill a pod, watch it come back") at the server-fleet level.

**The distinction the exam always tests: scaling vs availability.** An ASG with `min: 1` gives you *self-healing* (a dead instance is replaced) but **not** high availability during the replacement gap. `min: 2` across 2 AZs gives you both. Auto Scaling ≠ automatically highly-available — you get HA from spreading across AZs, not from the ASG existing.

### 6. (PAPER) Decision drills — say the answer before reading Verify

- **(a)** "Traffic is spiky — quiet at night, 10× at noon. Minimize cost without manual intervention."
- **(b)** "A single EC2 instance keeps dying at 3am and taking the site down until someone restarts it."
- **(c)** "We need to route `/api` to one fleet and `/` to another, under one domain and one certificate."
- **(d)** "A trading system needs the absolute lowest latency and a static IP; traffic is raw TCP, not HTTP."

### 7. (OPTIONAL — real AWS free account, same-day teardown)

Only if you want to see a real ALB+ASG once. AWS's 2026 free plan gives new accounts up to $200 in credits over 6 months with **no charges until you choose to upgrade** — so a few hours costs nothing *(verify latest — Free Tier terms changed in 2025)*. Minimal build, then **tear down the same day**:

1. VPC with 2 public + 2 private subnets (or use the default VPC).
2. Launch Template: Amazon Linux 2023, `t3.micro`, user-data that installs and starts a hello server on port 80.
3. Target group (`/` health check) + ALB across the two public subnets.
4. ASG: min 2 / desired 2 / max 4, ELB health check, target-tracking on 50% CPU.
5. Hit the ALB DNS name, then terminate an instance and watch the ASG replace it.

**Teardown checklist (do it today):** delete the ASG (this terminates the instances) → delete the ALB and target group → delete the Launch Template → release any Elastic IPs → delete the NAT Gateway if you made one (the one thing that bills by the hour) → set a **$1 billing alarm** before you start, as a tripwire. Confirm zero running instances and no NAT before you close the tab.

## Verify

Proof command — your LocalStack instance is running in a private subnet:

```bash
awslocal ec2 describe-instances --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].{State:State.Name,AZ:Placement.AvailabilityZone,PrivateIp:PrivateIpAddress,PublicIp:PublicIpAddress}'
```

`State: running`, a private IP, and `PublicIp: null`. Then answer the drills aloud:

**Drills (a)–(d):**

<details><summary>Answer (read after attempting aloud)</summary>

- **(a) Auto Scaling Group with target tracking** (e.g. keep CPU ~50%), min low, max high. It scales out at noon and back in at night automatically — you pay for what the load needs, no human. (Bonus cost lever: Spot instances in the ASG for the burst capacity.)
- **(b) Put the instance in an ASG with min ≥ 1 and an ELB health check** — self-healing replaces the dead instance automatically. For true availability during the gap, min 2 across 2 AZs behind an ALB.
- **(c) An ALB with path-based listener rules** — one listener on 443, one ACM certificate, rules forwarding `/api/*` to target group A and `/` to target group B. This is ALB's signature capability (layer-7 routing) that an NLB can't do.
- **(d) A Network Load Balancer (NLB)** — layer 4, lowest latency, supports a static/Elastic IP, handles raw TCP. ALB is wrong here because it's HTTP-only and adds latency; the triggers "lowest latency / static IP / raw TCP" all point to NLB.

</details>

**Bonus — why launch app servers into private subnets behind the LB, not public ones?**

<details><summary>Answer (read after attempting aloud)</summary>

Only the load balancer needs to be internet-facing. Keeping instances in private subnets means the internet cannot reach them directly at all — the only ingress is through the ALB, on the ports and paths you allow, to healthy targets. Smaller attack surface (the same "fewer doors" principle as giving only the api a `ports:` line in S1's compose). Instances still reach out for updates via the NAT Gateway. Exposed LB, hidden fleet is the default secure web-tier layout.

</details>

## Clean up

```bash
awslocal ec2 terminate-instances --instance-ids "$INSTANCE_ID"
# or wipe everything:
docker compose down && docker compose up -d
```

If you did the OPTIONAL real-AWS build, re-run its teardown checklist now and confirm the AWS console shows zero running instances and no NAT Gateway. Leave LocalStack running for Lab 5.
