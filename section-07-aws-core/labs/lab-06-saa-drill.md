# Lab 6 — SAA scenario drill

**Goal:** practise the actual exam skill — reading a scenario, eliminating impossible answers by constraint, and tie-breaking on cost. No infrastructure. This lab is a bank of SAA-style questions across everything Labs 1–5 covered, each with a full worked answer. Do it *out loud*, from memory, committing to an answer before you open the collapsible. If you can narrate the reasoning (not just pick the letter), you're exam-ready on this section's material.

## The mental map (read this first)

Every SAA question is the same shape. Train the reflex:

```
   1. READ the scenario → circle the CONSTRAINT words:
        "must not lose data"  "survive an AZ failure"  "global users"
        "cheapest"  "least operational overhead"  "no long-lived credentials"
                                   │
   2. ELIMINATE answers that violate the hard constraint (usually 2 of 4 die here)
                                   │
   3. Of the survivors, TIE-BREAK on the qualifier:
        "MOST cost-effective" → cheapest survivor
        "LEAST operational overhead" → most-managed survivor
        "MOST secure" → least-privilege / no-keys survivor
                                   │
   4. Sanity check against the constraint again. Commit.
```

The trap answers are always *technically possible but wrong on the qualifier* — they work, but they're more expensive, more manual, or less secure than the intended answer. Never pick "it would work"; pick "it best satisfies the exact word they emphasised."

## The drill

Answer each aloud, then check.

**Q1 — credentials.** An application running on an EC2 instance needs to read objects from an S3 bucket. What is the MOST secure way to grant access?

<details><summary>Answer</summary>

**An IAM role attached to the EC2 instance (instance profile)**, with a least-privilege policy allowing `s3:GetObject` on that bucket. Wrong answers: embedding an access key in the app config (long-lived, leakable — the exact Lab 1 anti-pattern), or a user with keys in an env var. Machines get roles, not keys — credentials are short-lived and auto-rotated, nothing to leak. This is the single most-repeated SAA security answer.

</details>

**Q2 — storage cost.** A company stores application logs in S3. Logs are queried heavily for 30 days, occasionally for the next 60, and must be retained 7 years for compliance but are almost never read after 90 days. MOST cost-effective approach?

<details><summary>Answer</summary>

**A lifecycle rule**: Standard for 30 days → Standard-IA at 30 → Glacier (or Glacier Deep Archive) at 90 → keep until the 7-year expiration. One policy, runs forever, matches storage class to access pattern (Lab 2). Wrong answers: keeping everything in Standard (pays hot prices for cold data), or deleting at 90 days (violates the 7-year compliance constraint — a hard-constraint elimination).

</details>

**Q3 — availability.** A web app must remain available even if an entire Availability Zone fails. Which architecture?

<details><summary>Answer</summary>

**An ALB spanning ≥2 AZs, in front of an Auto Scaling Group with instances across those same AZs (min ≥2), plus a Multi-AZ RDS.** Every tier is spread across AZs. Wrong answers: a single large instance (one AZ = single point of failure), or an ASG in one AZ (self-healing but not AZ-fault-tolerant). Remember Lab 4's distinction: Auto Scaling alone ≠ HA; HA comes from spreading across AZs.

</details>

**Q4 — decoupling / spikes.** An order-processing system drops requests during traffic spikes because the backend can't keep up. MOST reliable fix with LEAST data loss?

<details><summary>Answer</summary>

**Put an SQS queue between the front-end and the processing tier** — the front-end enqueues instantly, workers (often an ASG scaled on queue depth) drain at their own pace, nothing is dropped during a spike. This is the "decoupling" trigger. Wrong answers: bigger instances (delays the ceiling, doesn't remove it), or synchronous retries (still lossy under sustained spike). Buffering async between tiers is the AWS reflex — it's Celery/broker thinking you already have.

</details>

**Q5 — global latency.** Users worldwide complain that a static-content website (images, JS) is slow far from `us-east-1`. Cheapest way to speed it up globally?

<details><summary>Answer</summary>

**CloudFront (CDN) in front of the S3 bucket** — content is cached at edge locations near users; origin stays a single S3 bucket. Wrong answers: replicating the site into buckets in every region (operational overhead + cost), or a bigger instance (it's static content, not compute-bound). "Global users + static/ cacheable + latency" → CloudFront.

</details>

**Q6 — private access to S3.** Instances in a private subnet must read from S3, but you want to avoid the hourly cost of a NAT Gateway and keep the traffic off the public internet entirely. What do you use?

<details><summary>Answer</summary>

**A VPC Gateway Endpoint for S3** — it adds a route so S3 traffic goes through AWS's private network, no NAT Gateway needed, and the Gateway Endpoint is **free**. Wrong answers: NAT Gateway (works but costs per-hour + data — the thing we're avoiding), or making the subnet public (exposes the instances). This is the Lab 3 NAT-cost-trap's clean answer. (Gateway Endpoints exist for S3 and DynamoDB; other services use Interface Endpoints / PrivateLink, which do cost.)

</details>

**Q7 — accidental deletion.** A team wants to recover their production database to the exact state it was in 20 minutes before a bad migration dropped a table. Which capability, and which common answer is a trap?

<details><summary>Answer</summary>

**Point-in-time restore (PITR) from RDS automated backups** — restore to any second in the retention window, i.e. just before the migration. The **trap is Multi-AZ**: it's for infrastructure failover, and its synchronous standby faithfully replicated the `DROP TABLE`, so it's no help against a logical mistake. HA protects against hardware/AZ failure; backups protect against humans. (Lab 5.)

</details>

**Q8 — least privilege policy.** You must grant a CI job permission to upload build artifacts to one specific S3 bucket and nothing else. Which policy is correct?

<details><summary>Answer</summary>

A policy with `Effect: Allow`, `Action: [s3:PutObject, s3:GetObject]` on `arn:aws:s3:::that-bucket/*` **and** `s3:ListBucket` on `arn:aws:s3:::that-bucket` (no slash) — objects vs bucket ARN distinction from Lab 1. Wrong answers: `s3:*` on `*` (wildly over-privileged), or `AdministratorAccess` (the junior move). Attach it to a **role** the CI assumes, not a user with static keys. Least privilege = exactly the actions and resources the job needs, nothing more.

</details>

**Q9 — the deny trap.** A user is in a group with `AdministratorAccess`, but an explicit `Deny` on `s3:DeleteBucket` is attached directly to the user. Can the user delete a bucket?

<details><summary>Answer</summary>

**No.** Explicit Deny always wins over any Allow, regardless of where each is attached — group, user, or resource. The evaluation engine checks for a matching explicit Deny first (Lab 1's rule 1). This is exactly how "admin, but fenced off from a few dangerous actions" guardrails are built (also how AWS Organizations SCPs work). Admin ≠ unstoppable when a Deny is in play.

</details>

**Q10 — cost tie-break on compute.** A batch job runs nightly for ~2 hours, is fault-tolerant (can restart if interrupted), and has no deadline pressure. Cheapest EC2 purchasing option?

<details><summary>Answer</summary>

**Spot Instances** — up to ~90% cheaper than On-Demand, and the "can be interrupted / fault-tolerant / no deadline" description is the textbook Spot use case. Wrong answers: Reserved Instances / Savings Plans (for steady 24/7 baseline load, not 2 hours/night), or On-Demand (works but most expensive of the survivors). Match purchasing model to workload shape: steady → Reserved/Savings; spiky-baseline → On-Demand; interruptible → Spot.

</details>

**Q11 — SG vs NACL debugging.** After tightening network rules, a web server receives requests but clients never get responses. Which layer is the likely culprit and why?

<details><summary>Answer</summary>

The **NACL** — it's stateless, so someone likely allowed inbound but forgot to allow the outbound ephemeral-port return range (1024–65535); the reply is dropped on the way out. A Security Group can't cause this because it's stateful (return traffic auto-allowed). "Requests arrive, responses vanish" = stateless-firewall return-traffic bug (Lab 3). No conntrack, no free return path.

</details>

**Q12 — region vs AZ.** A financial app must keep serving even if an entire AWS *region* goes down. Is Multi-AZ enough?

<details><summary>Answer</summary>

**No** — Multi-AZ protects against a single-AZ failure *within* a region. Surviving a whole-region outage needs a **multi-region** design: cross-region read replicas or a standby region, S3 cross-region replication, Route 53 failover/latency routing, and data replicated across regions. This is the highest availability tier and the highest cost — the exam reserves it for the strongest "must survive a region failure" wording. Don't over-engineer to multi-region when the scenario only says "AZ."

</details>

## Verify

You're done when you can answer **all twelve aloud from memory**, narrating the elimination + tie-break, not just the letter. If any two still feel like guesses, note which primitive they belong to and re-read that lab's mental map.

Final synthesis question — answer aloud, no collapsible:

> Draw, from memory, a highly-available, secure, cost-conscious architecture for the capstone app on real AWS: VPC layout, where the ALB/instances/database live, how the CI gets permission to deploy, and one cost optimization. If you can narrate that end-to-end, this section did its job.

<details><summary>A reference answer (compare after you've drawn yours)</summary>

VPC across 2 AZs; **public subnets** hold the ALB (and a NAT Gateway); **private subnets** hold the EC2/ASG app fleet and a **Multi-AZ RDS**. Clients hit Route 53 → ALB (TLS terminated via ACM) → target group → app instances → RDS via its endpoint; ElastiCache in front of the DB for hot reads. Instances have **no public IP** and reach out via NAT (or a **VPC Gateway Endpoint** for S3 to skip NAT cost). The app assumes an **IAM instance role** (no keys). CI assumes a **least-privilege role** to deploy. Cost optimizations: S3 lifecycle rules for logs/artifacts, Spot in the ASG for burst capacity, a Gateway Endpoint instead of NAT for S3 traffic, right-sized instance types, and a billing alarm as the tripwire. Every tier spread across ≥2 AZs = survives an AZ failure.

</details>

## Clean up

Nothing to tear down. If LocalStack is still running from earlier labs and you're finished, `cd section-07-aws-core/localstack && docker compose down`. Then fill in `notes.md` in your own words and work the `checkpoint.md` from memory — that's the section gate.
