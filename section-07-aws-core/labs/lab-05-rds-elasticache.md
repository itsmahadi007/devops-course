# Lab 5 — RDS & ElastiCache vs self-managed

**Goal:** understand exactly what you *buy* when you stop running Postgres and Redis yourself (S1's compose stack) and let AWS run them as **RDS** and **ElastiCache** — and, just as important, what you *give up*. This is a pure-reasoning lab (neither service is in LocalStack's free tier) built directly on top of the databases you already tune for a living. The SAA tests these as design tradeoffs — Multi-AZ vs read replica, when managed is worth it, backup/recovery objectives — and your self-managed experience is the perfect ground to reason from.

> **LocalStack reality:** RDS and ElastiCache are **not** in the free tier — this lab is paper + diagrams, with an OPTIONAL real-AWS RDS build at the end (same-day teardown). That's genuinely how the exam approaches them: you're scored on *choosing and sizing*, never on typing `create-db-instance`.

## The mental map (read this first)

You already run Postgres and Redis in `docker-compose.yml`. You own everything: the version, the config, backups, failover, patching, the volume. RDS and ElastiCache are that same Postgres/Redis with a **managed-service line drawn across the stack** — AWS takes everything below the line:

```
   SELF-MANAGED (your S1 compose)          MANAGED (RDS / ElastiCache)
   ──────────────────────────────          ────────────────────────────
   your queries / schema        ← YOU  →   your queries / schema        ← YOU
   ──────────────────────────────          ────────────────────────────
   engine config / tuning       ← YOU  →   parameter group (you set knobs)  ← YOU-ish
   backups                      ← YOU  →   automated snapshots + PITR    ← AWS
   failover / replication       ← YOU  →   Multi-AZ standby, auto-failover← AWS
   patching / minor upgrades    ← YOU  →   maintenance window            ← AWS
   OS / host / disk             ← YOU  →   (you never see it)            ← AWS
   ──────────────────────────────          ────────────────────────────
```

**What you buy:** you stop being paged at 3am for a failed disk, a corrupt WAL, or a failover that didn't happen. **What you give up:** the SSH key. No superuser, no OS access, no arbitrary extensions, version choices constrained to what AWS supports, and a price premium over raw EC2. For most teams that's a great trade — the exam's default lean is "use the managed service unless there's a specific reason not to."

The four RDS concepts the SAA drills, mapped to what you know:

- **Multi-AZ = high availability, NOT scaling.** RDS keeps a **synchronous standby replica in another AZ**. If the primary's AZ dies, RDS flips the DNS endpoint to the standby automatically (~60–120s), no data loss. You do **not** read from the standby — it's a hot spare. This is the "≥2 AZs" availability principle from Lab 3/4, applied to your database. *(Your compose Postgres has no equivalent — if that container's AZ died, you'd restore from backup by hand.)*
- **Read Replica = scaling reads, NOT availability.** An **asynchronous** copy you *can* read from — offload reporting/analytics queries off the primary. Async means slight lag and possible tiny data loss on promotion, so it's not a failover mechanism by default (though you can promote one manually). "Read-heavy, primary is CPU-bound on SELECTs" → read replicas.
- **Automated backups + PITR.** RDS snapshots daily and streams transaction logs, so you can restore to **any second** in the retention window (point-in-time recovery). The exam speaks in **RPO** (how much data can you lose — recovery *point*) and **RTO** (how long to recover — recovery *time*). Multi-AZ gives tiny RTO/RPO for AZ failure; backups give you recovery from *logical* disasters (someone dropped a table) that a standby would have faithfully replicated.
- **Parameter groups & the endpoint.** You tune the engine via a **parameter group** (the managed stand-in for editing `postgresql.conf` — the tuning you do at CosmosID), and your app connects to a **DNS endpoint** that AWS repoints on failover — so the app config never changes, exactly like S1's `redis://redis:6379` service-DNS habit: name, never IP.

**ElastiCache** is the same story for Redis/Memcached: managed, in-VPC, with Multi-AZ + automatic failover (Redis) and cluster-mode sharding for scale. The design questions are "cache-aside vs write-through," "is losing the cache on failover acceptable?" (usually yes — it's a cache, the S1 "Redis reset to visits:1 is correct, Postgres doing that is an incident" lesson), and Redis-vs-Memcached (Redis for persistence/replication/data structures; Memcached for pure multi-threaded ephemeral caching).

## Steps (reasoning — no LocalStack)

### 1. Map your compose stack to its managed equivalent

Write out, from memory, what each line of your S1 `docker-compose.yml` becomes on AWS:

- `postgres:18-alpine` with a `pgdata` volume → **RDS for PostgreSQL 18**, storage auto-scaling on, `pgdata` becomes managed EBS you never touch.
- healthcheck-gated `depends_on` → the app connects to the RDS **endpoint**; RDS's own health/failover replaces your healthcheck's role for the DB.
- `redis:7` → **ElastiCache for Redis**, `REDIS_URL` points at the ElastiCache endpoint.
- Both live in **private subnets** (Lab 3) — a database with a public IP is an exam-instant-wrong answer and a real-world breach waiting to happen. Access is controlled by an SG that allows 5432/6379 *only from the app tier's SG* (the SG-referencing-SG trick from Lab 3).

### 2. Decide Multi-AZ vs Read Replica for three needs

For each, say which (or both) and why:

- **(a)** "The database must survive an AZ outage with no data loss and near-zero manual work."
- **(b)** "The primary is fine on writes but pegged at 100% CPU serving a reporting dashboard's heavy reads."
- **(c)** "A dev ran `DELETE FROM orders` without a WHERE clause an hour ago."

### 3. Size the RPO/RTO conversation

An interviewer/scenario asks: "How much data can you afford to lose, and how fast must you be back?" Practise answering:

- Multi-AZ failover: RTO ~1–2 min, RPO ~0 (synchronous) — but only for *infrastructure* failure, not logical mistakes.
- Automated backup + PITR: RTO minutes-to-an-hour (restore builds a new instance), RPO ~5 min or better — and it *does* cover logical mistakes.
- Cross-region read replica / snapshot copy: covers a whole-region outage — the highest tier, highest cost.

The exam trap: someone proposes Multi-AZ as protection against accidental deletes. **It isn't** — the standby replicates the delete instantly. Only backups/PITR save you from yourself.

### 4. (OPTIONAL — real AWS free account, same-day teardown)

If you want to touch a real RDS once. The 2026 free plan gives new accounts credits with no charges until you upgrade *(verify latest)*, and a `db.t4g.micro` single-AZ instance is tiny. Minimal build:

1. In the default VPC (or Lab 4's), create a **DB subnet group** spanning two private subnets.
2. `create-db-instance`: PostgreSQL, `db.t4g.micro`, 20 GB, **not publicly accessible**, an SG allowing 5432 from your app SG only.
3. Connect with `psql` from an instance in the same VPC using the RDS **endpoint**.
4. Take a manual snapshot; toggle Multi-AZ on and watch a standby get built (this *does* cost while on — turn it back off).

**Teardown checklist (today):** delete the DB instance (**uncheck "create final snapshot"** for a lab, or you'll pay for the snapshot) → delete the DB subnet group → delete any manual snapshots → confirm no RDS instances and no orphaned snapshots in the console → keep the $1 billing alarm from Lab 4 armed. RDS is one of the easiest ways to get a surprise bill — the instance bills per-hour even idle.

## Verify

No infra to prove — this lab's proof is the reasoning. Answer aloud:

**1. Multi-AZ vs Read Replica — one sentence each on what they're *for*, and the mistake people make.**

<details><summary>Answer (read after attempting aloud)</summary>

**Multi-AZ** = high availability: a synchronous standby in another AZ that RDS fails over to automatically on infrastructure failure — you can't read from it, it's a hot spare. **Read Replica** = read scaling: an asynchronous readable copy to offload SELECT-heavy traffic. The mistake: treating Multi-AZ as read scaling (you can't read the standby) or treating a read replica as HA (it's async, so it can lag and isn't an automatic failover target). Different problems, different tools.

</details>

**2. Scenarios (a), (b), (c) from step 2.**

<details><summary>Answer (read after attempting aloud)</summary>

- **(a) Multi-AZ** — synchronous standby, automatic failover, ~0 data loss for AZ failure.
- **(b) Read Replica(s)** — point the reporting dashboard at the replica endpoint, taking read load off the primary. (Or ElastiCache in front if the reads are cacheable.)
- **(c) Point-in-time restore from automated backups** to just before the `DELETE`. Multi-AZ would *not* help — the standby already replicated the delete. This is the classic "HA ≠ backup" trap.

</details>

**3. What exactly do you give up by moving self-managed Postgres to RDS, and when is that a dealbreaker?**

<details><summary>Answer (read after attempting aloud)</summary>

You give up OS/superuser access — no SSH, no arbitrary extensions or custom builds, engine versions limited to what RDS supports, less control over exact patch timing (maintenance windows), and you pay a premium over raw EC2. Dealbreakers: you need an unsupported extension or a bleeding-edge/custom Postgres build, an OS-level agent on the DB host, or truly extreme per-dollar performance tuning. For ~everyone else, offloading backups/failover/patching is worth the premium — which is why "use RDS" is the exam's default. (Aurora is the next step up: RDS-compatible, cloud-native storage, higher performance/cost.)

</details>

**4. Why does the app connect to an RDS *endpoint* (DNS name) and never a hardcoded IP — and where have you enforced this habit before?**

<details><summary>Answer (read after attempting aloud)</summary>

Because on failover AWS repoints that endpoint's DNS from the primary to the standby — if the app had an IP hardcoded, failover would break it. Same reason S1's compose used `redis://redis:6379` (service DNS) instead of `172.30.0.2`: names survive the thing behind them being replaced, IPs don't. 12-factor config-from-env means the endpoint is the only thing that changes between environments.

</details>

## Clean up

Nothing on LocalStack to remove. If you did the OPTIONAL real-AWS build, run its teardown checklist now and confirm the console shows no RDS instances and no lingering snapshots. This is the last lab that touches infrastructure — Lab 6 is a pure written drill. You can `docker compose down` on LocalStack now if you're done with the hands-on labs; keep it if you want to re-drill Labs 1–4.
