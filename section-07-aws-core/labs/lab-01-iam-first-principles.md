# Lab 1 — IAM from first principles

**Goal:** stand up LocalStack, then build the identity primitive by hand — a user, a role, and policies — and *read policy JSON like a compiler reads code*. By the end you can look at any policy and say exactly who can do what, and why a request is allowed or denied. This is the single highest-leverage AWS skill: it gates every other service, and it's the SAA's most-tested domain. It's also the direct sequel to Section 1 Lab 6's authn-vs-authz lesson and Section 2's `GITHUB_TOKEN` scoping.

## The mental map (read this first)

Every AWS API call carries a **principal** (who is asking), names an **action** (`s3:GetObject`), and targets a **resource** (`arn:aws:s3:::my-bucket/*`). Before AWS does anything, it runs the request through a decision engine:

```
   A request arrives:  principal=Alice  action=s3:DeleteObject  resource=arn:…:my-bucket/report.pdf
                                     │
                                     ▼
        ┌───────────────────────────────────────────────────────────┐
        │  IAM POLICY EVALUATION  (runs on EVERY call)                │
        │                                                             │
        │  1. Is there an EXPLICIT DENY that matches?  ── yes ──▶ DENY │  ← deny always wins
        │              │ no                                           │
        │  2. Is there an ALLOW that matches?          ── yes ──▶ ALLOW│
        │              │ no                                           │
        │  3. (no matching allow)                      ─────────▶ DENY │  ← implicit deny
        └───────────────────────────────────────────────────────────┘

   Everything is DENIED by default. You are always *adding* allows.
   A single explicit Deny anywhere beats every Allow.
```

That box is the whole game. Memorise the three rules in order — **explicit deny > allow > implicit deny (default deny)** — and 30% of the SAA's security questions answer themselves.

Now the two identity types people confuse forever:

```
  USER                                   ROLE
  ────                                   ────
  a permanent identity                   a temporary identity you ASSUME
  has long-lived credentials             has NO permanent credentials
  (access key + secret) — a liability    you get short-lived keys on assume, they expire
  "a person or a service account"        "a hat any allowed principal can put on"

  human at a keyboard, an old script  →  USER
  EC2 instance / CI job / Lambda      →  ROLE   (no keys to leak, keys rotate automatically)
```

The SAA's single most repeated security recommendation: **for anything that isn't a human, use a role, not a user with access keys.** Why? Access keys are the GHCR-token-in-a-file problem from S1 L6 at cloud scale — they leak, they don't rotate, they end up in git. A role hands out credentials that self-destruct in an hour. Your Section 2 CI using `GITHUB_TOKEN` (short-lived, scoped, minted per-run) is the exact same pattern — AWS calls it a role.

A **policy** is a JSON document attached to a user, a role, or a resource. Its skeleton — the six elements you'll read all lab:

```json
{
  "Version": "2012-10-17",              // always this date; it's a schema version, not "today"
  "Statement": [
    {
      "Sid": "AllowReadUploads",        // optional human label
      "Effect": "Allow",                // Allow | Deny
      "Action": ["s3:GetObject"],       // what verbs
      "Resource": ["arn:aws:s3:::uploads/*"],  // on what
      "Condition": { "StringEquals": { "aws:username": "alice" } }  // optional guards
    }
  ]
}
```

Read a policy in this order: **Effect → Action → Resource → Condition.** "This statement *allows* the actions *X* on resources *Y*, but only when *Z*."

## Steps

### 1. Create the LocalStack compose file

Make a folder `section-07-aws-core/localstack/` and put this in `docker-compose.yml`:

```yaml
services:
  localstack:
    image: localstack/localstack:latest   # 2026 unified image; pin a date tag (e.g. :2026.06) for reproducibility
    container_name: localstack
    ports:
      - "9080:4566"          # single edge port; your S7 host-port block is 9080–9089
    environment:
      - LOCALSTACK_AUTH_TOKEN=${LOCALSTACK_AUTH_TOKEN}   # from your .env; free Hobby token
      - SERVICES=iam,sts,s3,ec2      # only boot what these labs use → faster start
      - DEBUG=1                       # verbose logs; you'll read them when a call misbehaves
    volumes:
      - "./volume:/var/lib/localstack"          # LocalStack's own state (gitignore it)
      - "/var/run/docker.sock:/var/run/docker.sock"  # lets LocalStack run helper containers (EC2 etc.)
```

And create `section-07-aws-core/localstack/.env` (this file is **gitignored** — never commit it):

```
LOCALSTACK_AUTH_TOKEN=ls-your-free-hobby-token-here
```

Add a `.gitignore` inside `section-07-aws-core/localstack/` so state and token never leak:

```
.env
volume/
```

#### Why the docker.sock mount, and why it's safe here

LocalStack emulates some services (like EC2 instances) by spinning up *real helper containers* on your Docker Desktop. To do that it needs to talk to the Docker daemon — the same socket you've mounted before. On a shared server this mount is a privilege-escalation risk (a container that can drive Docker can own the host); on your laptop, for a throwaway lab, it's fine. Note the instinct — an interviewer may ask why mounting `docker.sock` is dangerous.

### 2. Boot LocalStack and confirm it's healthy

```bash
cd section-07-aws-core/localstack
docker compose up -d
docker compose logs -f localstack | grep -m1 Ready
```

Expect a line like `Ready.` (the older phrasing was `Ready.` / a banner). If instead you see the container exit or a log line about **auth token invalid / license**, your token in `.env` is wrong or missing — LocalStack 2026 refuses to start without a valid free token. Fix `.env`, then `docker compose up -d --force-recreate`.

#### If the container starts but every `awslocal` call hangs or refuses

LocalStack takes a few seconds to bind port 4566 internally. `docker compose ps` should show it `healthy`; a bare `Up` without healthy means give it 10s. If `curl localhost:9080/_localstack/health` returns JSON listing your services as `"available"`/`"running"`, the edge is up and the problem is your alias/endpoint, not LocalStack.

### 3. Set up the `awslocal` alias

In the same terminal (define it every new shell, or add to `~/.zshrc`):

```bash
alias awslocal='AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=us-east-1 aws --endpoint-url=http://localhost:9080'
awslocal sts get-caller-identity
```

Expect JSON with `"Account": "000000000000"` and an ARN like `arn:aws:iam::000000000000:root`. That account number — twelve zeros — is LocalStack's tell: you are safely in the fake, not real AWS. `sts get-caller-identity` is the "who am I right now?" call; you'll use it constantly.

#### If you see `Could not connect to the endpoint URL`

The alias is pointing at 9080 but nothing's listening — LocalStack isn't up, or you skipped `docker compose up`. If instead you get a *credentials* error, your alias didn't export the fake keys — re-paste it exactly (the env vars sit *before* `aws` on purpose, so they apply only to that command).

### 4. Create a user and read what "no policy" means

```bash
awslocal iam create-user --user-name alice
awslocal iam create-access-key --user-name alice
```

The second call returns an `AccessKeyId` + `SecretAccessKey`. Note what just happened: those are **long-lived credentials** — they work until someone deletes them. This is the liability the mental map warned about. In real AWS you'd now be responsible for rotating and guarding these forever. A role (step 7) never hands you this problem.

Right now Alice can *authenticate* but can do *nothing* — she has zero policies, and the default is deny. Authenticated but unauthorized: the exact S1 L6 split (`Login Succeeded` ≠ permitted), now on the AWS side.

### 5. Write and attach a least-privilege policy — the CI-push drill

Section 2's CI pushes images to a registry. Suppose that CI ran on AWS and pushed to S3 instead of GHCR. The junior move is to give it `AdministratorAccess`. The SAA-correct move is a policy that can do *exactly* that one job and nothing else. Save this as `ci-push-policy.json`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowPushToArtifactsBucketOnly",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject"
      ],
      "Resource": "arn:aws:s3:::capstone-artifacts/*"
    },
    {
      "Sid": "AllowListThatBucketOnly",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::capstone-artifacts"
    }
  ]
}
```

Read it aloud before running anything: statement 1 allows *put and get objects* but only under the `capstone-artifacts/*` key prefix; statement 2 allows *listing* the bucket itself. Note the ARN difference — **objects** are `bucket/*`, the **bucket** is `bucket` with no slash. Mixing these up is the #1 real-world IAM bug and a favourite SAA trap. There is no `s3:DeleteBucket`, no `*` action, no second bucket. That is least privilege: the credential can do its job and cause no other damage if stolen.

```bash
awslocal iam create-policy --policy-name ci-push --policy-document file://ci-push-policy.json
awslocal iam attach-user-policy --user-name alice \
  --policy-arn arn:aws:iam::000000000000:policy/ci-push
awslocal iam list-attached-user-policies --user-name alice
```

The last call should list `ci-push`. Alice can now push artifacts — and only that.

### 6. Reading drill — no commands, just judgement

For each policy below, decide the outcome *before* reasoning it out. These are exactly the shape of SAA questions.

**Policy A** — attached to Bob:
```json
{ "Version": "2012-10-17", "Statement": [
  { "Effect": "Allow", "Action": "s3:*", "Resource": "*" },
  { "Effect": "Deny",  "Action": "s3:DeleteObject", "Resource": "arn:aws:s3:::prod-*/*" }
]}
```
> Question: Bob calls `s3:DeleteObject` on `prod-billing/invoice.pdf`. Allowed?

**Policy B** — Carol has *no* policy granting `ec2:*`, but her team policy says:
```json
{ "Effect": "Allow", "Action": "ec2:DescribeInstances", "Resource": "*" }
```
> Question: Carol calls `ec2:TerminateInstances`. Allowed?

**Policy C** — a bucket policy (resource-based, attached to the bucket) says `Deny` to everyone except a specific role; Dave's *user* policy grants him `s3:GetObject *`.
> Question: Dave (a plain user, not that role) reads an object. Allowed?

Answers are in **Verify** — attempt all three aloud first.

### 7. Create a role — the credential that expires

A role needs two policies: a **trust policy** (who may assume it — the door) and **permission policies** (what they can do once inside — the rooms). Save the trust policy as `trust-ec2.json`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "ec2.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

Read it: "the EC2 *service* is allowed to call `sts:AssumeRole` on this role." That's how an EC2 instance gets credentials without you ever putting an access key on it — the instance wears the role, AWS hands its code short-lived keys through the instance metadata service, and they rotate automatically. This is the answer to a dozen SAA questions: *"An app on EC2 needs to read S3 — how do you give it access without hardcoding keys?"* → **an instance role.**

```bash
awslocal iam create-role --role-name capstone-ec2-role \
  --assume-role-policy-document file://trust-ec2.json
awslocal iam attach-role-policy --role-name capstone-ec2-role \
  --policy-arn arn:aws:iam::000000000000:policy/ci-push
awslocal iam get-role --role-name capstone-ec2-role
```

`get-role` echoes the trust policy back. The role now exists, trusts EC2, and can push artifacts — with zero long-lived keys anywhere. Compare to Alice in step 4, whose secret key is a permanent liability.

### 8. (OPTIONAL) Watch enforcement actually block a call

By default LocalStack, like a permissive dev sandbox, *lets everything through* — it doesn't run the evaluation engine unless you ask. Turn it on to see a denial happen for real. Edit the compose `environment:` to add `ENFORCE_IAM=1`, then `docker compose up -d --force-recreate`. Now a call the policy doesn't allow returns `AccessDenied` instead of succeeding.

> This is a genuine feature of the free tier, but LocalStack's IAM enforcement is a moving target and doesn't cover every action — *(verify latest)*. If it doesn't behave, don't lose sleep: the exam tests the *evaluation logic* (step 6), not LocalStack's fidelity. Turn `ENFORCE_IAM` back off after, so later labs aren't fighting denials while you learn other services.

## Verify

Proof command — Alice's attached policy is exactly one, least-privilege:

```bash
awslocal iam list-attached-user-policies --user-name alice
awslocal iam get-role --role-name capstone-ec2-role --query 'Role.AssumeRolePolicyDocument'
```

First shows only `ci-push`; second shows EC2 as the trusted principal. Then answer aloud:

**1. Policy A: Bob deletes `prod-billing/invoice.pdf`. Allowed?**

<details><summary>Answer (read after attempting aloud)</summary>

**Denied.** The first statement allows `s3:*` on everything, but the second is an explicit `Deny` on `s3:DeleteObject` for `prod-*/*`, and `prod-billing/invoice.pdf` matches `prod-*/*`. Explicit deny always wins over any allow — rule 1 of the evaluation engine. This is the classic "allow broadly, deny the dangerous exceptions" guardrail pattern.

</details>

**2. Policy B: Carol calls `ec2:TerminateInstances`. Allowed?**

<details><summary>Answer (read after attempting aloud)</summary>

**Denied — by implicit (default) deny.** No statement anywhere grants `ec2:TerminateInstances`; her only allow is for `DescribeInstances`. With no matching Allow and no matching Deny, the default kicks in: everything is denied unless explicitly allowed. This is why granting a broad `Describe*` doesn't accidentally grant destructive actions.

</details>

**3. Policy C: Dave (a user, not the trusted role) reads the object. Allowed?**

<details><summary>Answer (read after attempting aloud)</summary>

**Denied.** The bucket policy is a *resource-based* explicit Deny for everyone except one role; Dave isn't that role, so the Deny matches him. Even though his identity policy grants `s3:GetObject`, an explicit Deny on the resource side beats it. Both identity-based and resource-based policies feed the *same* evaluation engine, and any explicit Deny in either wins. (Contrast: if the bucket policy had been silent instead of Deny, his identity Allow would have carried the day.)

</details>

**4. Why is a role the right call for the CI job, and how is that the same idea as Section 2's `GITHUB_TOKEN`?**

<details><summary>Answer (read after attempting aloud)</summary>

A role hands out short-lived credentials that expire (typically ~1 hour) and rotate automatically — nothing long-lived to leak, commit, or forget to rotate. A user with an access key is a permanent liability: one leak and the key works until a human notices and revokes it. Section 2's `GITHUB_TOKEN` is identical thinking — GitHub mints a scoped, single-run token per workflow that dies when the job ends, instead of you storing a personal token forever. "Machines get roles, not keys" is the SAA's default answer to any 'give this compute access' question.

</details>

## Clean up

```bash
awslocal iam detach-user-policy --user-name alice --policy-arn arn:aws:iam::000000000000:policy/ci-push
awslocal iam delete-user --user-name alice          # will error if the access key still exists
awslocal iam delete-access-key --user-name alice --access-key-id <the id from step 4>  # if needed, before delete-user
awslocal iam detach-role-policy --role-name capstone-ec2-role --policy-arn arn:aws:iam::000000000000:policy/ci-push
awslocal iam delete-role --role-name capstone-ec2-role
awslocal iam delete-policy --policy-arn arn:aws:iam::000000000000:policy/ci-push
```

Leave LocalStack **running** — Lab 2 uses the same container. If you're stopping for the day, `docker compose stop` keeps state; `docker compose down` wipes it (fine — the labs rebuild fast). The `volume/` folder is your persistence if you ever want state across `down`.
