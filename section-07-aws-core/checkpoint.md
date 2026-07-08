# Checkpoint — Section 07: AWS Core

Pass every task **from memory** — no peeking at the labs. If you have to peek, the section isn't done yet; redo that lab tomorrow and try again. The explain-aloud and scenario blocks are the real point of this section — the SAA is a reasoning exam, so drill the reasoning until it's reflex.

## Practical tasks

- [ ] **1.** From a cold start, bring up LocalStack (compose file from memory, minus the exact env keys), set the `awslocal` alias, and prove you're connected with `sts get-caller-identity` (account = twelve zeros).
- [ ] **2.** Create a user, write a least-privilege policy (put/get/list on one bucket only, objects-vs-bucket ARN correct), attach it, and confirm with `list-attached-user-policies`. Then create a role with an EC2 trust policy.
- [ ] **3.** Create an S3 bucket with versioning, put two versions of an object, add a lifecycle rule (transition + expiry), and generate a working presigned URL that a plain `curl` (no creds) can use — then show it 403s after expiry.
- [ ] **4.** Build a VPC by hand: two public + two private subnets across two AZs, IGW + public route table, NAT + private route table, an SG. Prove the public route table has `0.0.0.0/0 → igw` and the private one has `0.0.0.0/0 → nat`.
- [ ] **5.** Launch an EC2 instance into a private subnet and show it has a private IP and **no** public IP.
- [ ] **6.** Answer all twelve Lab 6 scenarios aloud, narrating elimination + cost tie-break, and draw the full capstone-on-AWS architecture from memory.

## Explain aloud (interview drill — answer in 60–90 seconds each)

- [ ] "AWS is a datacenter you drive through one API." Name the ~8 primitives and the two cross-cutting truths (region/AZ, everything-is-IAM-gated).
- [ ] The IAM evaluation engine: state the three rules in order. Why is everything denied by default, and what beats an Allow?
- [ ] User vs role: what does each have, what expires, and why is "machines get roles, not keys" the default answer? Tie it to Section 2's `GITHUB_TOKEN`.
- [ ] Read a policy's six elements in order (Effect → Action → Resource → Condition …). Why is the objects ARN (`bucket/*`) different from the bucket ARN (`bucket`), and what breaks if you swap them?
- [ ] What single thing makes an S3 object durable to 11 nines, and what does a storage class change (and not change)?
- [ ] Versioning without a lifecycle rule: what goes wrong, and what's the fix?
- [ ] A presigned URL leaks publicly — how bad, versus an access key leaking, and why?
- [ ] What makes a subnet "public"? (Answer must be about the route table, not a checkbox.) What makes it private?
- [ ] IGW vs NAT Gateway: what each is for, which direction each allows, and which one Docker's default bridge already taught you.
- [ ] SG vs NACL: stateful vs stateless, allow-vs-deny, attached-where. Map each to iptables with/without conntrack. Which one causes "requests arrive but responses vanish"?
- [ ] EC2 instance-type shorthand: read `r5.large` and `c5.xlarge`; which family for a memory cache, which for CPU-bound batch?
- [ ] ALB vs NLB: layer, what each routes by, and the trigger words that push you to NLB.
- [ ] Auto Scaling Group: min/desired/max, self-healing vs self-sizing, and why "an ASG exists" is NOT the same as "highly available."
- [ ] Managed (RDS) vs self-managed Postgres: what you buy, what you give up (the SSH key), and when the tradeoff is a dealbreaker.
- [ ] Multi-AZ vs Read Replica: what each is FOR, and the two classic traps (reading the standby; using Multi-AZ as delete-protection).
- [ ] RPO vs RTO in one sentence each; which recovery tool covers an accidental `DROP TABLE` and which does not.

## SAA-style scenario drill (say the answer, then the elimination reasoning)

- [ ] **App on EC2 needs to read an S3 bucket, most securely.** What, and why not access keys?

<details><summary>Answer</summary>

**IAM role (instance profile)** with least-privilege `s3:GetObject` on that bucket. Access keys are long-lived, leakable, and don't rotate — the Lab 1 anti-pattern. Roles hand out short-lived auto-rotating credentials via instance metadata. "Machines get roles, not keys."

</details>

- [ ] **Logs: hot 30 days, cold after 90, keep 7 years, rarely read late.** Cheapest?

<details><summary>Answer</summary>

**S3 lifecycle rule**: Standard → Standard-IA at 30d → Glacier/Deep Archive at 90d → expire at 7y. Matches class to access pattern automatically. Keeping all in Standard overpays; deleting at 90d violates the 7-year compliance constraint.

</details>

- [ ] **Must survive a full AZ failure.** Architecture?

<details><summary>Answer</summary>

**ALB across ≥2 AZs → ASG (min ≥2) across those AZs → Multi-AZ RDS.** Every tier spread across AZs. A single instance or single-AZ ASG fails the constraint. HA comes from AZ-spread, not from Auto Scaling existing.

</details>

- [ ] **Order system drops requests during spikes.** Least-loss fix?

<details><summary>Answer</summary>

**SQS between front-end and workers** — enqueue instantly, drain at the workers' pace, scale workers on queue depth. Nothing dropped. Bigger instances only delay the ceiling; sync retries stay lossy. Decouple async between tiers.

</details>

- [ ] **Private instances need S3, avoid NAT hourly cost, keep off the public internet.** What?

<details><summary>Answer</summary>

**VPC Gateway Endpoint for S3** — private route to S3 through AWS's network, free, no NAT. NAT works but bills hourly + data; a public subnet exposes the instances. (Gateway Endpoints: S3 + DynamoDB only.)

</details>

- [ ] **Recover the DB to 20 min before a bad migration dropped a table.** What, and the trap?

<details><summary>Answer</summary>

**PITR from RDS automated backups.** The trap is **Multi-AZ** — its synchronous standby replicated the `DROP TABLE`, so it doesn't help against a logical mistake. HA guards hardware/AZ failure; backups guard against humans.

</details>

- [ ] **Global users, slow static site far from the origin region.** Cheapest speed-up?

<details><summary>Answer</summary>

**CloudFront in front of S3** — edge caching near users, single origin. Multi-region buckets add cost/overhead; a bigger instance is irrelevant for static content. "Global + cacheable + latency" → CDN.

</details>

- [ ] **Admin user, but an explicit Deny on `s3:DeleteBucket` attached directly. Can they delete?**

<details><summary>Answer</summary>

**No.** Explicit Deny beats any Allow, wherever each is attached. The engine checks explicit Deny first. This is exactly how "admin with guardrails" (and Organizations SCPs) work — admin isn't unstoppable when a Deny matches.

</details>

- [ ] **Nightly 2-hour fault-tolerant batch, no deadline.** Cheapest EC2 purchase model?

<details><summary>Answer</summary>

**Spot Instances** — up to ~90% off, and "interruptible / fault-tolerant / no deadline" is the textbook Spot case. Reserved/Savings are for steady 24/7 baseline; On-Demand works but is the priciest survivor. Match purchase model to workload shape.

</details>

- [ ] **Requests arrive but responses never return after a firewall change.** Which layer, why?

<details><summary>Answer</summary>

**NACL** — stateless, so inbound was allowed but the outbound ephemeral-port return range (1024–65535) wasn't; the reply is dropped outbound. An SG can't cause this (stateful, return auto-allowed). "Responses vanish" = stateless-firewall / no-conntrack bug.

</details>

- [ ] **Must keep serving even if a whole region fails. Is Multi-AZ enough?**

<details><summary>Answer</summary>

**No** — Multi-AZ only survives a single-AZ failure within one region. Region survival needs **multi-region**: cross-region replicas/standby, S3 CRR, Route 53 failover. Highest tier, highest cost — reserved for explicit "survive a region" wording. Don't over-build to multi-region for an "AZ" scenario.

</details>

## Gate

- [ ] `notes.md` filled in my own words
- [ ] LocalStack compose file + any policy JSON I want to keep are committed (no `.env`, no `LOCALSTACK_AUTH_TOKEN`, no `volume/` state — verify with `git status` before committing)
- [ ] I can draw the full capstone-on-AWS architecture from memory and defend every choice

When all boxes are checked, say so — the next section (Observability) gets written against your notes, and it finally pays back the Section 1 "logs die with the container" debt.
