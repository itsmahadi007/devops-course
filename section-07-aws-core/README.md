# Section 07 — AWS Core

**Status:** in progress · **Time:** ~1.5 weeks at 2–4h/day · **Labs:** 6

Section 6 taught you to *declare* infrastructure with Terraform and read a state file. That was the grammar. This section is the vocabulary: the ~8 primitives AWS is actually built from, the ones every `terraform apply` against AWS is secretly creating. You already ship on EC2 and S3 by hand — this section replaces "I clicked until it worked" with a mental model you can reason from, and doubles as the groundwork for the AWS Solutions Architect Associate (SAA) exam in Section 11.

You will run most of this locally against **LocalStack** (a fake AWS that answers real AWS API calls on your Mac) — $0, no real account touched. Where LocalStack's free tier can't emulate a service, you'll learn it on paper with diagrams, the way the exam tests it anyway.

## The mental model (read first)

**AWS is a datacenter you drive entirely through one HTTP API.** There is no magic. Every button in the console, every Terraform resource, every `aws` command is a signed HTTPS request to an endpoint like `ec2.us-east-1.amazonaws.com`. You already believe this — it's exactly how your Django app talks to Stripe. AWS is just the biggest REST API on earth with a very strict bouncer at the door.

That bouncer is the first primitive. Here are all of them:

```
                         ┌──────────────────────────────────────────┐
                         │  IAM  — the bouncer on EVERY api call      │
                         │  "is THIS principal allowed to do THIS     │
                         │   action on THIS resource, right now?"     │
                         └───────────────────┬────────────────────────┘
                                             │ (every arrow below is gated by IAM)
   ┌──────────┬──────────┬───────────────────┼───────────┬───────────┬──────────┐
   ▼          ▼          ▼                    ▼           ▼           ▼          ▼
COMPUTE    STORAGE    NETWORK             DATABASE     BALANCING   MESSAGING  OBSERVE
EC2 /      S3 (obj)   VPC + subnets       RDS (SQL)    ELB/ALB     SQS/SNS    CloudWatch
Lambda /   EBS(disk)  routes, gateways    DynamoDB     Route 53    EventBr.   CloudTrail
ECS/EKS    EFS(files) SG / NACL           ElastiCache  CloudFront             (audit)
```

Eight boxes. Everything AWS sells is one of these, a managed flavour of one of these, or glue between them. When a scenario question throws "Amazon Kinesis Data Firehose" at you, you don't need to have used it — you slot it under MESSAGING and reason from there.

Two cross-cutting truths sit under the whole diagram:

- **Region → Availability Zone.** AWS is partitioned into ~30 **regions** (`us-east-1`, `ap-south-1` = Mumbai, closest to you). Each region is 3+ **Availability Zones** (AZs) — separate buildings, separate power, a few km apart. "Highly available" almost always means "spread across ≥2 AZs." A whole region going down is rare; a single AZ blipping is the thing you design against. This is the single most-tested idea on the SAA.
- **Everything is an API call, and every call is authorized by IAM.** This is why IAM is Lab 1 and why it's the primitive that composes with all the others. It maps exactly to Section 1 Lab 6's `Login Succeeded` lesson: *authentication* ("is this token real?") is step one, *authorization* ("may this identity do this?") is a separate check at the moment of the action. AWS just does both on literally every request.

**Map it to what you already own:**

| You know (earlier sections) | AWS primitive | The relationship |
|---|---|---|
| Docker daemon API on one host | AWS API across a planet | Same idea, bigger blast radius; IAM is the daemon's missing auth layer |
| Docker user-defined network, service-DNS (S1 L4) | VPC + subnets + route tables | A private LAN you define; routing is explicit, not automatic |
| `iptables` / conntrack inside vps-lab (S3 L6) | Security Groups (stateful) vs NACLs (stateless) | SG = conntrack-backed allow rules; NACL = raw stateless firewall |
| GHCR token scopes / `GITHUB_TOKEN` (S1 L6, S2 L3) | IAM policies (least privilege) | "What may this credential do?" — same reflex, richer grammar |
| Self-managed Postgres/Redis in compose (S1 L4) | RDS / ElastiCache | You trade control for someone else running backups/failover |
| Docker healthcheck → K8s probe (S1 L3 → S4) | ALB target-group health check | Same "is it actually answering?" stamp, load-balancer edition |

If you can fill that table from memory by the end of the section, the SAA's networking and IAM domains are half-won.

## How SAA questions actually test (read this before Lab 6)

The exam is **not** a trivia quiz about API parameters. It is a *decision* test. Almost every question is a short scenario ending in "what is the MOST cost-effective / MOST highly-available / MOST secure solution?" — and three of the four answers are technically possible. The skill is **elimination by constraint**, then **tie-break by cost**.

The recurring constraints and their trigger words:

- **Durability / "must not lose data"** → S3 (11 nines), multi-AZ RDS, EBS snapshots. Eliminates instance-store, single-AZ.
- **Availability / "survive an AZ failure"** → ≥2 AZs, Multi-AZ RDS, ASG across subnets, ELB. Eliminates single-instance answers.
- **Latency / "global users" / "fast reads"** → CloudFront, read replicas, ElastiCache, edge. Eliminates single-region-only.
- **Decoupling / "handle spikes" / "don't lose requests"** → SQS between tiers. Eliminates synchronous-only.
- **Cost / "cheapest" / "infrequent access"** → S3 storage classes, Spot, Reserved/Savings Plans, right-sizing. This is usually the *tie-breaker* once two options both work.
- **Security / "least privilege" / "no long-lived keys"** → IAM roles (not users), VPC endpoints, encryption at rest. Eliminates "embed access keys."

You already do this reasoning as a backend engineer — you just do it with Postgres-vs-Redis and Celery-vs-cron. This section gives you the AWS names to hang it on. Lab 6 is nothing but this drill.

## Labs

| Lab | What you build | Proves | LocalStack? |
|---|---|---|---|
| [1 — IAM from first principles](labs/lab-01-iam-first-principles.md) | users, a role, policies; a least-privilege CI-push policy | policy evaluation logic, JSON reading, roles-vs-users | ✅ full (IAM) |
| [2 — S3: lifecycle + presigned URLs](labs/lab-02-s3-lifecycle-presigned.md) | a bucket with versioning, a lifecycle rule, a working presigned upload/download | object storage model, storage classes, time-boxed access | ✅ full (S3) |
| [3 — VPC networking](labs/lab-03-vpc-networking.md) | a VPC with public/private subnets, IGW, NAT, SGs, NACLs | routing on paper + as objects; SG-vs-NACL mapped to iptables | ✅ objects only (see lab) |
| [4 — EC2 / ALB / ASG](labs/lab-04-ec2-alb-asg.md) | an EC2 instance in LocalStack; ALB+ASG on paper + decision drills | when to use what; target groups, health checks, scaling | ⚠️ EC2 only; ALB/ASG on paper |
| [5 — RDS / ElastiCache vs self-managed](labs/lab-05-rds-elasticache.md) | the managed-service tradeoff, Multi-AZ / read-replica / backup design | what you buy by giving up the SSH key | ✖️ paper + OPTIONAL real free-tier |
| [6 — SAA scenario drill](labs/lab-06-saa-drill.md) | nothing — you answer scenarios and cost-reason | the exam's actual skill: elimination + cost tie-break | ✖️ paper |

Do them in order — Lab 1's IAM is assumed by every lab after it, and Lab 3's VPC is the stage Lab 4 stands on. Each ends with **Verify** and **Clean up**.

## Tooling — read before Lab 1 ($0, but one 2026 change)

> **The LocalStack situation changed in 2026.** The old free "Community Edition" was retired (image `localstack/localstack` and pro merged into one; the last community image was ~`3.x`). Today's free tier is the **Hobby plan**: still **$0, no credit card**, but it requires a free account and a `LOCALSTACK_AUTH_TOKEN`. The Hobby plan covers exactly the services these labs lean on hands-on — **IAM, S3, EC2, VPC** — and does *not* cover RDS, ElastiCache, ELB/ALB, or Auto Scaling, which is precisely why Labs 4–5 teach those on paper. This is normal for the SAA anyway: those services are tested as *design decisions*, not button-clicks. *(verify latest — LocalStack's tiers move fast; the free tier's exact service list is at the licensing link below.)*

**One-time setup (do this once, before Lab 1):**

1. **AWS CLI v2** (the client — LocalStack speaks the same protocol):
   ```bash
   brew install awscli
   aws --version    # aws-cli/2.x …
   ```
2. **A free LocalStack account + token.** Sign up at `app.localstack.cloud` (Hobby / non-commercial, no card), copy your **Auth Token** from the workspace settings. You'll store it as an environment variable — **never** commit it (it's a credential; the repo's `.gitignore` covers `.env`).
3. **A gitignored `.env` for the token.** Create `section-07-aws-core/localstack/.env` (Lab 1 gives the exact content). Confirm `.env` is ignored: `git check-ignore section-07-aws-core/localstack/.env` should echo the path.

**The `awslocal` shortcut.** Every lab drives LocalStack with a command called `awslocal`. Rather than install the `awscli-local` pip package (which defaults to port 4566 and would miss our host port 9080), define this shell alias — it points the real `aws` CLI at LocalStack on **9080** and injects harmless fake credentials so you never touch real AWS:

```bash
alias awslocal='AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=us-east-1 aws --endpoint-url=http://localhost:9080'
```

`test`/`test` are the well-known LocalStack fake credentials — **not secrets**, safe to type anywhere. LocalStack ignores their value; it just needs *some* credentials present so the CLI signs the request. (If you prefer a truly no-account path, LocalStack-compatible clones exist that listen on the same `4566` protocol — a `Floci`/`moto`-style server — and the same alias works against them by changing the port. The labs are written for LocalStack, but every command is vanilla AWS API and portable.)

Full LocalStack compose file contents live inside Lab 1 (you create them there). Host port for LocalStack in this section: **9080 → 4566** (your S7 block is 9080–9089; don't stray).

## Reading (curated, ~2h total)

- [IAM policy evaluation logic](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html) — read until "explicit deny always wins" is reflex. This *is* Lab 1.
- [IAM policy JSON structure](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements.html) — the six elements every policy is made of.
- [VPC — how it works](https://docs.aws.amazon.com/vpc/latest/userguide/how-it-works.html) — subnets, route tables, gateways in the source's own words.
- [Security Groups vs Network ACLs](https://docs.aws.amazon.com/vpc/latest/userguide/infrastructure-security.html) — the stateful/stateless table; the SAA loves this distinction.
- [S3 storage classes](https://aws.amazon.com/s3/storage-classes/) — the cost menu Lab 2's lifecycle rule navigates.
- [The Well-Architected Framework pillars](https://docs.aws.amazon.com/wellarchitected/latest/framework/the-pillars-of-the-framework.html) — the mindset the exam scores you against (skim the six pillar names + one line each).
- [LocalStack plans / free tier](https://docs.localstack.cloud/aws/licensing/) — confirm the current free-tier service list before you assume a lab will run.

## Done when

Every task in [checkpoint.md](checkpoint.md) passes from memory, and [notes.md](notes.md) is filled in your own words. Then Section 8 (Observability) gets written against your notes — it pays back the Section 1 "logs die with the container" debt, and its CloudWatch mental model leans directly on this section's "everything is an API + IAM" frame.
