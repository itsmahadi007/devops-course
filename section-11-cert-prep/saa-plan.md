# AWS SAA plan — 4 weeks to a pass

**Goal:** pass AWS Certified Solutions Architect – Associate within 4 weeks of starting this plan (i.e. after CKA — this is the weeks-5–8 lane). Section 7 built the mental models; this plan fills the service-coverage gaps and grinds the exam's one real skill: **scenario elimination**.

## Exam facts (verified 2026-07 — re-check the [official page](https://aws.amazon.com/certification/certified-solutions-architect-associate/) when you book)

| Fact | Value |
|---|---|
| Exam code | **SAA-C03** — still the current version. (Blogs claiming an "SAA-C04 launched in 2024" are content-farm noise; the official AWS pages say SAA-C03. If AWS *does* announce a C04 before you book, they always give months of overlap — check once, then stop worrying.) |
| Price | **$150** |
| Format | **65 questions / 130 minutes** — exactly 2 min/question. Multiple choice (1 of 4) and multiple response (2+ of 5+). **15 of the 65 are unscored** experimental questions you can't identify — so never let one bizarre question shake you; it may literally not count |
| Passing | **720 / 1000** scaled (roughly ~72%, shifts with question difficulty) |
| Retake | **No free retake** — 14-day wait, pay again. This is why the readiness gate in `checkpoint.md` is strict |
| Delivery | Pearson VUE — online proctored from home (strict room rules) or a test center (there are Pearson VUE centers in Dhaka; for a recall exam, the center's boring reliability beats home-proctor stress — your call) |

## The mental map (read this first)

```
SAA-C03 domain                      weight   your coverage
──────────────────────────────────  ──────   ─────────────────────────────
1. Design Secure Architectures       30%     █████░░░░░  S7 IAM deep; KMS,
                                             Organizations, edge = gaps
2. Design Resilient Architectures    26%     █████░░░░░  S7 VPC/EC2/RDS;
                                             Route 53, SQS, DR = gaps
3. Design High-Performing Archs      24%     ████░░░░░░  caching instincts;
                                             serverless, analytics = gaps
4. Design Cost-Optimized Archs       20%     ████░░░░░░  S7 drill lab started
                                             it; pricing models = gaps
```

**What this exam actually is:** 65 short business scenarios, each ending in "which solution…?" plus a superlative — *MOST cost-effective, LEAST operational overhead, HIGHLY available*. Two of the four options are always wrong on requirements; the last two differ only on the superlative. So the skill is: **spot the superlative → eliminate two → decide between two.** That's why the grind here is question banks, not videos — you have 6 years of AWS usage and S7's mental models; you need reps in *their* question grammar, not more concepts.

**The CKA contrast, so you switch gears properly:** CKA rewarded typing; SAA rewards *reading*. No terminal, no partial credit, 2 minutes per question. Different sport, same jersey.

## Domain map: covered vs gaps

"Covered" means S7 (plus 6 years of real usage) built it. Gap = you'd currently guess.

### Domain 1 — Design Secure Architectures (30%)

| Topic cluster | Covered by | Gap? |
|---|---|---|
| IAM users/roles/policies, policy JSON, least privilege | S7 Lab 1 (deep — the policy-reading drills) | Covered |
| Cross-account access, resource policies vs identity policies | S7 Lab 1 partial | **Partial** — the "which policy wins" evaluation logic |
| AWS Organizations, SCPs, Control Tower | — | **GAP** |
| KMS (CMK types, key rotation, envelope encryption), Secrets Manager vs Parameter Store | — | **GAP** — KMS shows up constantly |
| S3 security: bucket policies, Block Public Access, presigned URLs, encryption modes (SSE-S3/KMS/C) | S7 Lab 2 (presigned URLs done) | **Partial** — encryption-mode picker questions |
| VPC security: SG vs NACL, VPC endpoints (gateway vs interface) | S7 Lab 3 (SG vs NACL mapped to iptables) | **Partial** — endpoints |
| Edge protection: WAF, Shield, GuardDuty/Inspector/Macie ("which detects what") | — | **GAP** — memorize the one-liner for each |
| Cognito (user pools vs identity pools) | — | **GAP** (light — a couple of questions) |

### Domain 2 — Design Resilient Architectures (26%)

| Topic cluster | Covered by | Gap? |
|---|---|---|
| Multi-AZ vs multi-region; ELB + ASG patterns | S7 Lab 4 | Covered — refresh |
| RDS Multi-AZ vs read replicas; Aurora (replicas, global database, serverless) | S7 Lab 5 (Multi-AZ vs replica concepts) | **Partial** — Aurora specifics |
| Route 53 routing policies (simple/weighted/latency/failover/geolocation) + health checks | — (S1 gave you DNS fundamentals) | **GAP** — guaranteed questions |
| Decoupling: SQS (standard vs FIFO, DLQ, visibility timeout), SNS, EventBridge, fan-out | Your backend instincts (you've run queues for years) | **GAP in AWS terms** — learn their vocabulary for what you already know |
| Storage resilience: EFS vs EBS vs S3 vs instance store; EFS availability | S7 Lab 2 (S3) | **Partial** — EFS/instance-store |
| DynamoDB (on-demand vs provisioned, global tables) | — | **GAP** |
| DR patterns: backup-restore / pilot light / warm standby / multi-site + RTO/RPO maths | — | **GAP** — classic scenario set |
| Hybrid connect: Site-to-Site VPN, Direct Connect, Transit Gateway | — | **GAP** (conceptual — "which and when") |

### Domain 3 — Design High-Performing Architectures (24%)

| Topic cluster | Covered by | Gap? |
|---|---|---|
| Caching: ElastiCache Redis vs Memcached, DAX, CloudFront | S7 Lab 5 (Redis tradeoffs — your home turf) | **Partial** — CloudFront behaviors, DAX |
| CloudFront vs Global Accelerator ("global users" questions) | — | **GAP** |
| Serverless: Lambda (limits, concurrency), API Gateway, Step Functions | You've *used* Lambda; exam wants limits/patterns | **Partial** |
| Containers on AWS: ECS vs Fargate vs EKS vs App Runner | S4–S5 K8s depth makes EKS trivial; the *ECS family taxonomy* is the gap | **Partial** |
| EBS volume types (gp3/io2/st1/sc1), placement groups, enhanced networking | S7 Lab 4 touched EC2 families | **GAP** — the gp3-vs-io2 picker |
| FSx family (Windows/Lustre/NetApp/OpenZFS) | — | **GAP** — pure memorization, one table |
| Analytics/streaming: Kinesis (Streams vs Firehose vs Analytics), Athena, Glue, EMR, MSK | — | **GAP** — "which ingestion tool" questions |
| Database picker: RDS vs Aurora vs DynamoDB vs Redshift vs OpenSearch | S7 Lab 5 built the frame | **Partial** — Redshift/OpenSearch corners |

### Domain 4 — Design Cost-Optimized Architectures (20%)

| Topic cluster | Covered by | Gap? |
|---|---|---|
| S3 storage classes + lifecycle + Intelligent-Tiering | S7 Lab 2 (lifecycle done) | **Partial** — class-picker edge cases (retrieval fees, minimum durations) |
| EC2 pricing: on-demand vs Reserved vs Savings Plans vs Spot (and *which Savings Plan*) | — | **GAP** — guaranteed questions |
| NAT gateway costs, VPC endpoint cost avoidance, data-transfer rules (cross-AZ, cross-region, egress) | S7 Lab 3 built the VPC map | **GAP** — the cost layer on top |
| Cost tools: Cost Explorer, Budgets, Cost & Usage Report, Compute Optimizer | — | **GAP** (light) |
| Right-sizing databases/storage for cost scenarios | S7 Lab 6 started exactly this | **Partial** |

## Resources ($0-bias, in priority order)

1. **[Official SAA-C03 exam guide (PDF)](https://d1.awsstatic.com/training-and-certification/docs-sa-assoc/AWS-Certified-Solutions-Architect-Associate_Exam-Guide.pdf)** — free. The domain/task statements above come from here; it also lists in-scope services. Read once, fully.
2. **AWS Skill Builder free tier** — the free **Official Practice Question Set (20 questions with explanations)** and the free *Exam Prep: SAA-C03* course. The official question set is your calibration standard: it's exactly the real exam's voice.
3. **Service FAQs** (free, and criminally underrated): the S3, EC2, VPC, RDS, Route 53, SQS FAQs are where exam questions are literally mined from. Read the FAQ of every **GAP** row above.
4. **Tutorials Dojo cheat sheets** (free at tutorialsdojo.com) — the best service-comparison tables anywhere ("S3 vs EBS vs EFS", "SQS vs SNS vs Kinesis"). Your gap tables above map one-to-one onto their sheets.
5. **Tutorials Dojo practice exams** (~$15 on Udemy, frequent sales) — **the one paid item, and worth it.** 6 full 65-question sets, explanations better than the real exam's. This is the grind engine for weeks 2–4. (Stephane Maarek's practice sets, also ~$15, are the alternate; you don't need both.)
6. **Well-Architected Framework pillar pages** (free) — skim the five pillars once; the exam's superlatives are these pillars in disguise.

Skip: full video courses. They're 27 hours re-teaching what S7 + six years already gave you. FAQs + cheat sheets + question grind is the senior-engineer path.

## Question-bank strategy (the grind method)

- **Always full 65-question timed sets.** Stamina is part of the exam — 130 minutes of scenario-reading fatigue is real.
- **Review EVERY question, including ones you got right.** A right answer for the wrong reason is a future wrong answer. The explanations are the actual course.
- **Keep an error log** (one file, three columns): *service/topic · why I missed it (knowledge gap vs misread superlative vs fell for distractor) · the one-line rule to remember.* The log's "rule" column becomes your final-week review sheet.
- **Never memorize answers** — TD question order/wording shifts, and the real exam paraphrases. If your score jumps on a *repeated* set but not on a fresh one, you're memorizing, not learning. The readiness gate uses **fresh sets only**.
- **Distractor patterns to learn by name:** the option that's real-but-wrong-scale (Redshift for a 1GB dataset), the deprecated-ish option (NAT instance vs NAT gateway), the works-but-most-ops option when "least operational overhead" was asked, the multi-region answer when multi-AZ satisfies the requirement (cost!).

## The superlative → reflex table (drill until instant)

| The question says | Your brain says |
|---|---|
| "MOST cost-effective" | Spot → S3-IA/Glacier tiers → single-AZ where HA isn't demanded → Savings Plans; check retrieval-fee traps |
| "LEAST operational overhead" | Managed/serverless wins: Lambda, Fargate, Aurora Serverless, DynamoDB, EventBridge |
| "Highly available" | Multi-**AZ** (not region), ALB + ASG across AZs, RDS Multi-AZ |
| "Fault tolerant" | Stronger than HA → active-active, multi-region, Route 53 failover |
| "Real-time" / "streaming" | Kinesis Data Streams (or MSK); "near-real-time, load into S3/Redshift" → Firehose |
| "Decouple" | SQS between tiers; fan-out → SNS→SQS; schedule/event routing → EventBridge |
| "Global users, low latency" | Static/content → CloudFront; TCP/UDP or non-HTTP → Global Accelerator |
| "Millisecond, key-value, any scale" | DynamoDB (+ DAX if "microsecond reads") |
| "Petabyte migration, limited bandwidth" | Snow family; ongoing sync → DataSync |
| "On-prem keeps working with cloud storage" | Storage Gateway (File/Volume/Tape — know the three) |
| "Ad-hoc SQL on S3 data" | Athena (+ Glue for catalog) |
| "Lift and shift database / servers" | DMS (+SCT if engine changes) / MGN |
| "RPO 5 minutes, RTO 1 hour" | Read the numbers → warm standby vs pilot light vs backup-restore — smaller RTO/RPO = more standing infra = more cost |

## Cost/scenario reasoning drills (S7 Lab 6, continued)

Do these on paper, aloud, 10 minutes each — they train the *deciding between the final two options* muscle:

1. **The S3 class picker:** 100GB of logs, written daily, read hot for 7 days, audit-read maybe once a year, keep 7 years. Design the lifecycle. Now change "maybe once a year" to "must retrieve in under 5 minutes when auditors call" — what changed and why? (Retrieval SLAs and fees are the trap.)
2. **NAT arithmetic:** 20 private-subnet instances pull 500GB/month from S3 through a NAT gateway. Price the NAT (hourly + per-GB processing), then delete the cost with a gateway VPC endpoint. This exact scenario is on every practice set.
3. **The RTO/RPO ladder:** one workload, four DR budgets — write which pattern (backup-restore / pilot light / warm standby / multi-site) each budget buys and roughly what each costs relative to prod.
4. **Reserved vs Savings Plan vs Spot:** a steady API tier, a nightly batch job, a dev environment used 9–5. Assign a pricing model to each and defend it in one sentence.
5. **Cross-AZ tax:** why does an ALB→instances-in-3-AZs design cost data-transfer money that a single-AZ design doesn't, and when is eating that cost non-negotiable? (Ties the HA superlative to the cost superlative — the exam loves making them fight.)

## 4-week schedule

Relative: **week 1 = the week you start this plan** (course week 5, after CKA). Daily ~2.5–3h. Every day ends with 10 flashcard-style reps from your error log.

### Week 1 — gap study, domains 1–2

| Day | Block A (~90 min) | Block B (~60 min) |
|---|---|---|
| 1 | Exam guide PDF, fully · Skill Builder free practice set (20 Qs) as cold diagnostic | Start the error log with the diagnostic's misses |
| 2 | KMS + Secrets Manager vs Parameter Store (FAQ + TD sheet) | S3 encryption modes + bucket-policy questions |
| 3 | Organizations/SCP + the security-services one-liners (WAF/Shield/GuardDuty/Inspector/Macie) | VPC endpoints (gateway vs interface) + SG/NACL refresh from S7 notes |
| 4 | Route 53 routing policies + health checks | DR patterns + RTO/RPO ladder (drill 3) |
| 5 | SQS/SNS/EventBridge in AWS vocabulary | DynamoDB + Aurora gap study |
| 6–7 | EFS/EBS/instance-store + hybrid connect (VPN/DX/TGW) | Light: re-read week's error-log rules |

### Week 2 — gap study domains 3–4, first full mock

| Day | Block A | Block B |
|---|---|---|
| 1 | CloudFront vs Global Accelerator · Lambda limits + API GW | ECS/Fargate/EKS/App Runner taxonomy |
| 2 | EBS volume types + placement groups · FSx table | Kinesis family + Athena/Glue |
| 3 | EC2 pricing models · NAT/data-transfer cost rules | Cost tools + drills 2 & 4 |
| 4 | S3 class picker (drill 1) + drill 5 | Superlative table: cover-and-recall until instant |
| 5 | **TD practice exam #1, timed, full 65** | Begin review (right answers included) |
| 6–7 | Finish #1 review into the error log | Re-study the two weakest domains it exposed |

### Week 3 — the grind

- Alternate days: **full timed set** (TD #2, #3, #4) / **full review day** for yesterday's set — review takes as long as the exam did; that's correct and non-negotiable.
- Between sets: FAQ-read the services your error log names more than twice.
- End of week: TD #5 as a fresh-set checkpoint. **≥75% on this fresh set** = on track; below → extend this week before booking, remember there's no free retake.

### Week 4 — exam week

| Day | Work |
|---|---|
| 1 | TD #6 (final fresh set), timed. **Readiness bar: ≥80% on a fresh set** (checkpoint.md gate) → book the exam for day 5 |
| 2 | Full error-log review — read every "rule" line aloud; redo the 5 reasoning drills cold |
| 3 | Skill Builder official 20-set again (it's the real exam's voice — recalibrate) · superlative table one last time |
| 4 | Rest + logistics: Pearson VUE system test if online (or route to the test center), ID ready |
| 5 | **Exam.** Pace = 2 min/question; flag and move on at 2.5; first pass through all 65, second pass for flags. Remember: 15 questions are unscored — a weird one may be free |

**After the pass:** cert line on both CVs same day, the "finished the course — both certs" flagship LinkedIn post (see `market-entry.md` and repo `TODO.md`), and the SAA + 6-years-hands-on combination goes into the backend-led CV's cloud story too — it's not just for the DevOps lane.
