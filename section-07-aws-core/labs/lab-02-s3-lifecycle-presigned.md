# Lab 2 — S3: lifecycle + presigned URLs

**Goal:** build the storage primitive you'll use more than any other — an S3 bucket — and drive the two features that separate "I know S3 exists" from "I design with S3": **lifecycle rules** (automatic cost control) and **presigned URLs** (time-boxed access without handing out credentials). You already `put` and `get` objects casually; this lab makes the durability/cost/access model explicit, exactly as the SAA tests it. Everything here runs fully on LocalStack's free tier.

## The mental map (read this first)

S3 is not a filesystem. It's a **flat key-value store for blobs**, globally namespaced by bucket:

```
   BUCKET  (globally-unique name, lives in ONE region)
   capstone-artifacts
   │
   ├── "reports/2026/q1.pdf"   ── an OBJECT: key (a string) → bytes + metadata
   ├── "reports/2026/q2.pdf"        the "/" is just part of the key string —
   └── "uploads/user-42.png"        there are NO real folders, only key prefixes
```

Three facts that answer most S3 exam questions:

- **Durability is 11 nines (99.999999999%).** S3 replicates every object across ≥3 AZs automatically. "Where do I store data I must never lose?" → S3. You do nothing to get this.
- **Storage classes are a cost menu, not a quality menu.** Same durability, different access price/latency: **Standard** (hot, default) → **Standard-IA** (infrequent, cheaper storage, pay-per-retrieval) → **Glacier / Deep Archive** (cold, cents/TB, retrieval takes minutes-to-hours). The design skill is matching access pattern to class — and automating the transition with a **lifecycle rule** so you don't pay Standard prices for logs nobody reads after 30 days.
- **Access is deny-by-default and controlled three ways:** IAM policies (Lab 1), bucket policies (resource-based), and — for temporary, credential-free sharing — **presigned URLs**.

A **presigned URL** is the elegant one, and a frequent interview question:

```
   Your backend (has the credentials)                 Browser / client (has NONE)
   ────────────────────────────────                   ────────────────────────────
   sign a GET/PUT request for                          just does an HTTP GET/PUT to
   "uploads/x.png", expires in 300s   ── URL ─────▶     that long URL. No AWS keys.
   using YOUR role's permission                        Works until it expires, then 403.
```

The signature *is* your permission, baked into the URL and stamped with an expiry. This is how "upload directly to S3 from the browser" works without your secret key ever leaving the server — the same instinct as Lab 1's roles-over-keys: hand out the narrowest, shortest-lived grant that does the job. It maps to your backend life too: it's exactly a signed, expiring download link, like the ones you'd issue for a paid file.

## Steps

### 1. Confirm LocalStack is up (from Lab 1) and the alias is set

```bash
cd section-07-aws-core/localstack && docker compose up -d
alias awslocal='AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=us-east-1 aws --endpoint-url=http://localhost:9080'
awslocal s3 ls    # empty output = no buckets yet, connection works
```

Empty output (no error) means you're connected and there are no buckets. An error here is the same triage as Lab 1 step 3 — container down, or alias not set.

### 2. Create a bucket and turn on versioning

```bash
awslocal s3 mb s3://capstone-artifacts
awslocal s3api put-bucket-versioning --bucket capstone-artifacts \
  --versioning-configuration Status=Enabled
awslocal s3api get-bucket-versioning --bucket capstone-artifacts
```

`mb` = "make bucket". The last call should echo `"Status": "Enabled"`. **Versioning** keeps every version of an object instead of overwriting — a `put` to an existing key creates a new version and keeps the old one; a `delete` just adds a "delete marker" you can remove to undo. This is the S3 answer to "protect against accidental overwrite/delete." Note the tradeoff the exam probes: **old versions still cost storage** until a lifecycle rule expires them (step 4). Versioning without lifecycle = a quietly growing bill.

#### Why bucket names feel so fussy

S3 bucket names are **globally unique across all AWS accounts on earth** and DNS-compatible (lowercase, no underscores). On real AWS `capstone-artifacts` is almost certainly taken — you'd suffix it (`capstone-artifacts-mahadi-7f3a`). On LocalStack the namespace is just your fake account, so the plain name works. Remember the real-world rule for the exam.

### 3. Put an object and watch a version stack up

```bash
echo "build 1" > artifact.txt
awslocal s3 cp artifact.txt s3://capstone-artifacts/reports/artifact.txt
echo "build 2" > artifact.txt
awslocal s3 cp artifact.txt s3://capstone-artifacts/reports/artifact.txt
awslocal s3api list-object-versions --bucket capstone-artifacts --prefix reports/
```

The last call shows **two versions** of the same key, each with a distinct `VersionId`, one marked `"IsLatest": true`. That's versioning working — "build 1" isn't gone, it's a previous version you could restore. Notice `reports/` is just a key prefix in the output, not a directory object.

### 4. Add a lifecycle rule — automatic cost control

Save this as `lifecycle.json`. It says: move objects to cheaper Standard-IA after 30 days, archive to Glacier after 90, delete outright after 365, and clean up noncurrent (old) versions after 30 days.

```json
{
  "Rules": [
    {
      "ID": "tier-down-and-expire",
      "Status": "Enabled",
      "Filter": { "Prefix": "reports/" },
      "Transitions": [
        { "Days": 30, "StorageClass": "STANDARD_IA" },
        { "Days": 90, "StorageClass": "GLACIER" }
      ],
      "Expiration": { "Days": 365 },
      "NoncurrentVersionExpiration": { "NoncurrentDays": 30 }
    }
  ]
}
```

```bash
awslocal s3api put-bucket-lifecycle-configuration \
  --bucket capstone-artifacts --lifecycle-configuration file://lifecycle.json
awslocal s3api get-bucket-lifecycle-configuration --bucket capstone-artifacts
```

The `get` echoes your rule back — that's your proof it's stored. Read the rule as a lifecycle: a build artifact is hot for a month (Standard), rarely touched for two more (IA is cheaper to store), cold-archived for the rest of the year (Glacier — pennies), then deleted. **You wrote a cost-optimization policy once and it runs forever.** This is the SAA's favourite cost lever, and the answer to "how do you reduce S3 spend on aging data?"

#### The catch LocalStack hides

On real AWS these transitions happen on a background schedule (you won't see `artifact.txt` in Glacier tomorrow — the 30-day clock is real time). LocalStack stores the *rule* faithfully but doesn't fast-forward physics. So your proof here is "the rule is accepted and readable," not "watch it move" — which is exactly what the exam asks you to reason about anyway. Don't wait around expecting a transition.

### 5. Generate a presigned URL and use it with no credentials

```bash
awslocal s3 presign s3://capstone-artifacts/reports/artifact.txt --expires-in 300
```

This prints a long URL containing `X-Amz-Signature=…` and `X-Amz-Expires=300`. That signature encodes *your* permission to GET this one object, valid for 300 seconds. Now fetch it as a client with zero AWS setup — plain `curl`, no keys, no alias:

```bash
curl -s "<paste the presigned URL here>"
```

You get back `build 2` — the object's bytes, delivered to a caller who never authenticated to AWS. That's the whole trick: the URL *is* the credential, scoped to one object and one short window.

#### Prove the expiry actually bites (the security point)

Generate one with a 1-second expiry, wait, then use it:

```bash
URL=$(awslocal s3 presign s3://capstone-artifacts/reports/artifact.txt --expires-in 1)
sleep 3
curl -s "$URL"
```

Now you get an `AccessDenied` / `Request has expired` error instead of the file. That expiry is the safety valve — a leaked presigned URL is useless after its window, unlike a leaked access key. This is why presigned URLs are the SAA-correct answer to "let users upload/download without giving them credentials."

### 6. (Reasoning drill — no commands) Match the scenario to the S3 feature

Decide before peeking at Verify:

- **(a)** "Users upload profile photos directly from the browser; the app server must never hold AWS keys client-side."
- **(b)** "Compliance requires we can recover any document to its state 6 months ago."
- **(c)** "We keep 50 TB of logs; they're queried heavily for a week, then almost never."

## Verify

Proof command — the bucket has versioning, a lifecycle rule, and objects:

```bash
awslocal s3api get-bucket-versioning --bucket capstone-artifacts
awslocal s3api get-bucket-lifecycle-configuration --bucket capstone-artifacts
awslocal s3 ls s3://capstone-artifacts/reports/
```

Then answer aloud:

**1. Scenario (a), (b), (c) — which S3 feature answers each?**

<details><summary>Answer (read after attempting aloud)</summary>

- **(a) Presigned URLs** — the server signs a short-lived PUT URL; the browser uploads straight to S3 with no credentials. (Bonus: a bucket CORS config lets the browser call it.)
- **(b) Versioning** — every version is retained, so you restore the version from 6 months ago (pair with a lifecycle noncurrent-version expiry so it doesn't cost forever, and MFA-delete if it's truly critical).
- **(c) Lifecycle transition to Standard-IA (or Glacier)** — hot for the first week on Standard, then a rule tiers the aging logs down to a cheaper class automatically. Intelligent-Tiering is the hands-off variant if access is unpredictable.

</details>

**2. A presigned URL leaks into a public Slack channel. How bad, versus an access key leaking?**

<details><summary>Answer (read after attempting aloud)</summary>

Far less bad. The presigned URL grants exactly one action on one object and stops working at its expiry (seconds-to-hours), and it's already scoped by whatever permission the signer had. A leaked *access key* is a persistent identity — it works on everything that key's policies allow, indefinitely, until a human notices and revokes it. Same lesson as Lab 1: narrow scope + short life beats broad + permanent.

</details>

**3. You enabled versioning to be safe. Two months later the bill climbed. Why, and what's the fix?**

<details><summary>Answer (read after attempting aloud)</summary>

Every overwrite kept the old version, and every "delete" just added a delete marker — none of that data actually left, so you're paying to store the full history of every object. The fix is a lifecycle rule with `NoncurrentVersionExpiration` (expire old versions after N days) and optionally `ExpiredObjectDeleteMarker` cleanup. Versioning and lifecycle are a pair; using one without the other is the trap.

</details>

## Clean up

```bash
# empty the bucket including all versions, then remove it
awslocal s3 rm s3://capstone-artifacts --recursive
awslocal s3api delete-bucket --bucket capstone-artifacts
awslocal s3 ls    # back to empty
rm -f artifact.txt lifecycle.json
```

Leave LocalStack running for Lab 3 (VPC). If a `delete-bucket` complains the bucket isn't empty, it's the versions — `list-object-versions` then delete each `VersionId`, or just `docker compose down` to wipe LocalStack's state entirely.
