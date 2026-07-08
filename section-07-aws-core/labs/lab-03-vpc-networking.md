# Lab 3 — VPC networking

**Goal:** build a real-world VPC layout — public and private subnets across two AZs, an internet gateway, a NAT gateway, security groups and NACLs — first as a diagram you can draw from memory, then as actual AWS objects in LocalStack. VPC is the SAA's densest domain and the thing most engineers fake. You already understand it more than you think: it's the Docker user-defined network from S1 Lab 4 and the iptables rules from S3 Lab 6, drawn at datacenter scale with the routing made *explicit*.

> **LocalStack reality (read once):** the free tier creates and describes VPC/subnet/route-table/gateway/SG/NACL **objects** faithfully — you'll build the whole topology and read it back, which proves you know the object model and their relationships. What LocalStack does **not** do is route real packets between fake instances or enforce SG/NACL rules on live traffic (that needs no emulator to *understand* — and the exam tests the routing *logic*, not packet delivery). So: build it for real, reason about the traffic on paper. Every command below works on the free tier.

## The mental map (read this first)

A **VPC** is your own private, walled-off network inside a region — you pick its IP range and nothing gets in or out except through doors you place. Picture the target layout for a typical web app:

```
        VPC  10.0.0.0/16   (65k private addresses, region-wide)
   ┌─────────────────────────────────────────────────────────────────────┐
   │                                                                       │
   │   AZ-a (us-east-1a)                    AZ-b (us-east-1b)               │
   │  ┌──────────────────────┐            ┌──────────────────────┐         │
   │  │ PUBLIC  10.0.1.0/24   │            │ PUBLIC  10.0.2.0/24   │         │
   │  │  route: 0.0.0.0/0 →IGW│            │  route: 0.0.0.0/0 →IGW│         │
   │  │  [ ALB / NAT GW ]     │            │  [ ALB ]              │         │
   │  └──────────┬───────────┘            └───────────┬──────────┘         │
   │             │  (private subnets route out via NAT, not IGW)           │
   │  ┌──────────▼───────────┐            ┌───────────▼──────────┐         │
   │  │ PRIVATE 10.0.11.0/24  │            │ PRIVATE 10.0.12.0/24  │        │
   │  │  route:0.0.0.0/0 →NAT │            │  route:0.0.0.0/0 →NAT │        │
   │  │  [ app servers ]      │            │  [ app servers, RDS ] │        │
   │  └──────────────────────┘            └──────────────────────┘         │
   │                                                                       │
   │        IGW ── the ONE door to the internet (attached to the VPC)      │
   └───────────────────────────────────┬───────────────────────────────────┘
                                        │
                                   the internet
```

The rules that make this work, and that the exam drills relentlessly:

- **A subnet is "public" for exactly one reason: its route table sends `0.0.0.0/0` to an Internet Gateway (IGW).** There is no "public" checkbox with meaning beyond that route + a public IP. "Private" = no route to the IGW. This is the single fact that unlocks half of VPC questions.
- **The Internet Gateway (IGW)** is the VPC's one door to/from the internet. One per VPC, attached to the VPC. No IGW route = no internet, full stop.
- **The NAT Gateway** lets *private* subnets reach *out* (download packages, call APIs) without being reachable *in*. It lives in a **public** subnet and private subnets route their `0.0.0.0/0` to it. One-way: outbound-initiated only. (This is literally `MASQUERADE`/SNAT — the exact thing Docker does so your containers reach the internet while staying unreachable from it. You saw the concept in S3 Lab 6.)
- **Security Group (SG) = stateful firewall on the instance (ENI).** Allow-rules only, no deny. *Stateful* means: allow inbound on 443, and the response goes out automatically — you don't write a return rule. This is **conntrack** from S3's iptables lab, managed for you.
- **Network ACL (NACL) = stateless firewall on the subnet edge.** Allow *and* deny rules, evaluated by number. *Stateless* means you must allow the return traffic explicitly (the ephemeral port range 1024–65535 outbound), because it doesn't remember the request. Raw iptables with no conntrack.

The SG-vs-NACL table is worth memorising cold:

| | Security Group | Network ACL |
|---|---|---|
| Attached to | instance / ENI | subnet |
| Rules | allow only | allow **and** deny |
| State | **stateful** (return auto-allowed) | **stateless** (allow return yourself) |
| Evaluation | all rules, permissive union | numbered, first match wins |
| Default | deny all inbound, allow all outbound | (default NACL) allow all both ways |
| Your mental hook | iptables **with** conntrack | iptables **without** conntrack |

## Steps

Keep LocalStack up (`docker compose up -d`) and the alias set. You'll capture IDs into shell variables so later commands can reference them — read each command's expected output before running.

### 1. Create the VPC

```bash
VPC_ID=$(awslocal ec2 create-vpc --cidr-block 10.0.0.0/16 --query 'Vpc.VpcId' --output text)
echo "VPC_ID=$VPC_ID"
awslocal ec2 describe-vpcs --vpc-ids "$VPC_ID" --query 'Vpcs[0].CidrBlock'
```

`create-vpc` returns a `vpc-…` ID captured into `$VPC_ID`; the describe echoes `10.0.0.0/16`. You now own a private /16 — 65,536 addresses to carve into subnets. AWS reserves 5 addresses per subnet (first four + last), a detail the exam occasionally checks.

### 2. Carve two public and two private subnets across two AZs

```bash
PUB_A=$(awslocal ec2 create-subnet --vpc-id "$VPC_ID" --cidr-block 10.0.1.0/24 \
  --availability-zone us-east-1a --query 'Subnet.SubnetId' --output text)
PUB_B=$(awslocal ec2 create-subnet --vpc-id "$VPC_ID" --cidr-block 10.0.2.0/24 \
  --availability-zone us-east-1b --query 'Subnet.SubnetId' --output text)
PRIV_A=$(awslocal ec2 create-subnet --vpc-id "$VPC_ID" --cidr-block 10.0.11.0/24 \
  --availability-zone us-east-1a --query 'Subnet.SubnetId' --output text)
PRIV_B=$(awslocal ec2 create-subnet --vpc-id "$VPC_ID" --cidr-block 10.0.12.0/24 \
  --availability-zone us-east-1b --query 'Subnet.SubnetId' --output text)
echo "PUB_A=$PUB_A PUB_B=$PUB_B PRIV_A=$PRIV_A PRIV_B=$PRIV_B"
```

Four subnet IDs. Note the deliberate design: two AZs so an AZ failure never takes out your whole tier (the availability principle). A subnet lives in **exactly one AZ** — it never spans AZs. That's why "highly available" always means "≥2 subnets in ≥2 AZs."

### 3. Attach an Internet Gateway and make the public subnets public

```bash
IGW_ID=$(awslocal ec2 create-internet-gateway --query 'InternetGateway.InternetGatewayId' --output text)
awslocal ec2 attach-internet-gateway --internet-gateway-id "$IGW_ID" --vpc-id "$VPC_ID"

# a route table whose default route points at the IGW = "the public route table"
PUB_RT=$(awslocal ec2 create-route-table --vpc-id "$VPC_ID" --query 'RouteTable.RouteTableId' --output text)
awslocal ec2 create-route --route-table-id "$PUB_RT" \
  --destination-cidr-block 0.0.0.0/0 --gateway-id "$IGW_ID"
awslocal ec2 associate-route-table --route-table-id "$PUB_RT" --subnet-id "$PUB_A"
awslocal ec2 associate-route-table --route-table-id "$PUB_RT" --subnet-id "$PUB_B"
awslocal ec2 describe-route-tables --route-table-ids "$PUB_RT" \
  --query 'RouteTables[0].Routes'
```

The final describe shows two routes: `10.0.0.0/16 → local` (added automatically — every subnet can reach every other subnet in the VPC, always) and `0.0.0.0/0 → igw-…` (yours). **That second route is literally the thing that makes `PUB_A` and `PUB_B` "public subnets."** Nothing else changed about the subnets — the route table did it. Say that sentence out loud; it's the crux of the whole domain.

### 4. Add a NAT Gateway so private subnets can reach out (but not be reached)

```bash
# NAT needs a public IP (Elastic IP) and lives in a PUBLIC subnet
EIP_ALLOC=$(awslocal ec2 allocate-address --domain vpc --query 'AllocationId' --output text)
NAT_ID=$(awslocal ec2 create-nat-gateway --subnet-id "$PUB_A" \
  --allocation-id "$EIP_ALLOC" --query 'NatGateway.NatGatewayId' --output text)

# a private route table: default route → NAT (not IGW)
PRIV_RT=$(awslocal ec2 create-route-table --vpc-id "$VPC_ID" --query 'RouteTable.RouteTableId' --output text)
awslocal ec2 create-route --route-table-id "$PRIV_RT" \
  --destination-cidr-block 0.0.0.0/0 --nat-gateway-id "$NAT_ID"
awslocal ec2 associate-route-table --route-table-id "$PRIV_RT" --subnet-id "$PRIV_A"
awslocal ec2 associate-route-table --route-table-id "$PRIV_RT" --subnet-id "$PRIV_B"
```

The private route table sends internet-bound traffic to the NAT, which sits in a public subnet and relays it out through the IGW — with source-address translation, so return packets come back to the NAT and never expose the private instance's address. **Outbound works, inbound-initiated does not.** That asymmetry is the entire point of a private subnet: your database can `apt update` but the internet cannot open a connection to it. It's the same one-way street Docker gives every container by default.

#### The cost trap the SAA loves

A NAT Gateway is **not free** on real AWS — it's ~$0.045/hour plus data-processing charges, running 24/7. "We have a tiny private subnet that rarely phones home, how do we cut the NAT bill?" has real answers: a NAT *instance* (cheaper, you manage it), **VPC endpoints** (reach S3/DynamoDB privately with no NAT at all — a Gateway Endpoint is free), or just not needing outbound. On LocalStack it costs nothing, but bank the fact — it's a favourite cost question.

### 5. Create a Security Group (stateful) and read its default posture

```bash
SG_ID=$(awslocal ec2 create-security-group --group-name web-sg \
  --description "web tier" --vpc-id "$VPC_ID" --query 'GroupId' --output text)
awslocal ec2 authorize-security-group-ingress --group-id "$SG_ID" \
  --protocol tcp --port 443 --cidr 0.0.0.0/0
awslocal ec2 authorize-security-group-ingress --group-id "$SG_ID" \
  --protocol tcp --port 80 --cidr 0.0.0.0/0
awslocal ec2 describe-security-groups --group-ids "$SG_ID" \
  --query 'SecurityGroups[0].{In:IpPermissions,Out:IpPermissionsEgress}'
```

You added inbound 80 and 443 from anywhere. Notice you never wrote an outbound rule for the *responses* — because an SG is **stateful**, the reply to an allowed inbound request is automatically permitted. The default egress (allow-all-out) is what you see in `Out`. Compare to Docker: publishing `-p 443:443` is the "allow inbound 443" equivalent; the response path is handled for you by conntrack. Same idea.

#### The SG rule that has no networking equivalent you've met

An SG rule's source can be **another security group** instead of a CIDR: "allow inbound 5432 *from* the `web-sg`" on your database SG. That means "any instance wearing the web SG may reach the DB, whatever its IP" — identity-based network rules, not address-based. This is the clean, exam-correct way to wire a web tier to a DB tier, and it has no direct Docker/iptables analogue (it's closer to K8s NetworkPolicy podSelectors, which you'll meet again).

### 6. Look at the default NACL (stateless) — mostly to contrast

```bash
awslocal ec2 describe-network-acls --filters "Name=vpc-id,Values=$VPC_ID" \
  --query 'NetworkAcls[0].Entries'
```

The default NACL allows all traffic both directions (rule 100 allow, plus the catch-all `*` deny at the end). The exam point isn't to configure it — most designs leave NACLs at default and do their filtering with SGs — it's to know *when* you'd touch it: NACLs are your tool for a **blanket subnet-wide deny** (block a malicious IP range across every instance at once) precisely because SGs can't deny. And because NACLs are stateless, if you ever add rules you must remember the ephemeral-port return range (1024–65535) or replies silently vanish — the classic NACL debugging nightmare.

## Verify

Proof command — the whole topology exists and is wired:

```bash
echo "VPC:      $VPC_ID"
awslocal ec2 describe-route-tables --route-table-ids "$PUB_RT" \
  --query 'RouteTables[0].Routes[?GatewayId!=`local`]'    # should show 0.0.0.0/0 → igw
awslocal ec2 describe-route-tables --route-table-ids "$PRIV_RT" \
  --query 'RouteTables[0].Routes[?NatGatewayId!=null]'    # should show 0.0.0.0/0 → nat
awslocal ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" \
  --query 'Subnets[].{Id:SubnetId,Cidr:CidrBlock,AZ:AvailabilityZone}' --output table
```

You should see the IGW route on the public table, the NAT route on the private table, and four subnets across two AZs. Then answer aloud:

**1. What single thing makes a subnet "public"? What makes it "private"?**

<details><summary>Answer (read after attempting aloud)</summary>

A subnet is **public** iff its associated route table has a route for `0.0.0.0/0` pointing at an **Internet Gateway** (and instances have public IPs). It's **private** if it has no route to the IGW — typically its default route goes to a NAT Gateway (outbound-only) or nowhere. "Public/private" is a property of the *route table*, not a flag on the subnet. The `local` route (the VPC's own CIDR) is always present and never makes a subnet public.

</details>

**2. A private-subnet server must download OS updates but must never be reachable from the internet. What do you place, and where?**

<details><summary>Answer (read after attempting aloud)</summary>

A **NAT Gateway in a public subnet**, and point the private subnet's route table `0.0.0.0/0` at it. NAT does source-translation so outbound-initiated connections work and their replies return, but no one on the internet can initiate a connection inward. It's SNAT/MASQUERADE — the same one-way street Docker gives containers. (Cheaper alternatives worth naming: NAT instance, or VPC endpoints if it only needs AWS services like S3.)

</details>

**3. SG vs NACL: your web server accepts HTTPS but its responses are being dropped. Which firewall is more likely misconfigured, and why?**

<details><summary>Answer (read after attempting aloud)</summary>

The **NACL**, because it's *stateless* — if someone added inbound allow rules but forgot to allow the outbound ephemeral-port range (1024–65535), the request arrives but the reply is denied on the way out. A Security Group can't cause this: it's *stateful*, so an allowed inbound request's response is automatically permitted. "Responses mysteriously dropped" is almost always a stateless-NACL return-traffic bug — the direct consequence of no conntrack.

</details>

**4. How is the NAT Gateway the same idea as something Docker did for your containers in Section 1?**

<details><summary>Answer (read after attempting aloud)</summary>

Docker gives containers on a bridge network outbound internet access via source NAT (MASQUERADE) while keeping them unreachable from outside unless you publish a port. A NAT Gateway does exactly that for a private subnet: outbound-initiated traffic is translated and allowed, inbound-initiated is impossible. Same mechanism (SNAT), same security property (one-way), different scale. Publishing a container port (`-p`) is the rough equivalent of putting something in a public subnet with an inbound SG rule.

</details>

## Clean up

Delete in reverse dependency order (NAT and routes before the VPC), or just wipe LocalStack:

```bash
# fastest: nuke all LocalStack state
docker compose down
docker compose up -d
```

If you want to practise ordered teardown (good CKA/interview muscle): delete routes → disassociate/delete route tables → delete NAT gateway → release EIP → delete subnets → detach/delete IGW → delete SG → delete VPC. On real AWS the order matters (you can't delete a VPC with dependencies attached) — the same "dependencies block destroy" reality you saw in Terraform (Section 6). Leave LocalStack running for Lab 4.
