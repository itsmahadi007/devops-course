# Lab 2 — A real test gate for the capstone

**Goal:** give the capstone an actual quality gate — ruff (lint) and pytest (tests) running on every push that touches it — and start `ci.yml`, the workflow the rest of this section keeps growing. Along the way: uv in CI, path filters, and a matrix that runs the same job on two operating systems at once.

## The mental map (read this first)

CI's first job is to be a **bouncer**: code that doesn't pass doesn't ship. Everything else this section builds (image build, deploy) will stand *behind* this gate — a failed test must stop the whole pipeline.

```
 git push (touches capstone/**)
      │
      ▼
 ┌─────────────────────────  test job  ──────────────────────────┐
 │                    strategy.matrix fans out:                  │
 │  ┌──────────────────────────┐  ┌───────────────────────────┐  │
 │  │ ubuntu-latest (amd64 VM) │  │ macos-latest (arm64, M-*) │  │
 │  │  checkout                │  │  checkout                 │  │
 │  │  install uv              │  │  install uv               │  │
 │  │  uv sync --frozen        │  │  uv sync --frozen         │  │
 │  │  ruff check              │  │  ruff check               │  │
 │  │  pytest                  │  │  pytest                   │  │
 │  └──────────────────────────┘  └───────────────────────────┘  │
 │        both green → job green → (Lab 3: build may proceed)    │
 └────────────────────────────────────────────────────────────────┘
```

Three new ideas ride along:

**Path filters** — this repo holds course notes *and* the app. A push that only edits `section-02/.../notes.md` should not burn a CI run. `paths:` tells the doorbell to only ring for changes under `capstone/**` (plus the workflow file itself — a self-reference whose reason you'll see below).

**Matrix** — one job definition, N clones, each with different variables. The classic use is Python versions; the capstone pins `>=3.14` so today's more useful axis is **OS**. Bonus with a hidden agenda: `macos-latest` runners are Apple Silicon — so your tests will pass on arm64 *and* amd64 machines, quietly foreshadowing Lab 4's multi-arch build of the very same code.

**Lockfile discipline, now in its natural habitat.** Lab 3 of Section 1 taught `--frozen` ("lockfile is law, fail loudly on drift") for image builds. CI is where that law gets *enforced for the team*: every run installs byte-identical deps or dies trying.

## Steps

### 1. Add the dev tools to the capstone

```bash
cd /Users/mahadihassan/Documents/plan/projects/devops-course/capstone
uv add --dev pytest httpx ruff
```

`uv add --dev` does three things in one move: writes a `dev` dependency group into `pyproject.toml`, re-resolves, and updates `uv.lock`. Expect output ending in something like `+ pytest==9.x.x`, `+ httpx==0.x`, `+ ruff==0.15.x` (plus a few transitive friends). `httpx` is there because FastAPI's `TestClient` drives the app through it.

Check what it wrote — `pyproject.toml` should now carry:

```toml
[dependency-groups]
dev = [
    "httpx>=0.28",
    "pytest>=9",
    "ruff>=0.15",
]
```

(Exact minimums may differ — uv pins to what it resolved today. That's fine; the lockfile holds the real versions.)

Why a *group* and not `dependencies`? Because the production image must never carry test tools — and your Dockerfile already enforces that: `uv sync --frozen --no-dev` in the builder stage skips groups. One file, two audiences: CI installs everything, the image installs runtime-only. The `--no-dev` flag you wrote in Section 1 just became load-bearing.

### 2. Configure ruff and pytest in `pyproject.toml`

Append to `capstone/pyproject.toml`:

```toml
[tool.ruff]
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "B"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

- **`select`** — rule families: `E`/`F` = pycodestyle errors + pyflakes (the "this is broken or sloppy" core), `I` = import sorting, `B` = bugbear (real-bug patterns like mutable default args). A deliberately small, defensible set — lint rules you can't justify in review are noise.
- **`pythonpath = ["."]`** — the line that prevents tonight's most likely failure. The capstone is `package = false` (never installed as a package), so nothing puts its folder on `sys.path`. pytest by default only adds the *tests* directory — from there, `from app.main import app` finds no `app`. This setting adds the project root. Cheap line, classic trap; the failure it prevents is pre-explained in step 4.

### 3. Write the first tests

Create `capstone/tests/test_api.py`:

```python
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_ask_echoes_question():
    r = client.get("/ask", params={"q": "what is devops?"})
    assert r.status_code == 200
    body = r.json()
    assert body["question"] == "what is devops?"
    assert "placeholder" in body["answer"]  # S10 replaces the canned answer — this pins today's contract


def test_visits_degrades_without_redis():
    r = client.get("/visits")
    assert r.status_code == 200
    assert r.json()["visits"] is None
```

Notes on intent (the tests are boring on purpose):

- No Redis container, no mocks — `/visits` already has a no-REDIS_URL degradation path, so the test asserts *that*, documenting the behavior instead of fighting it. CI stays dependency-free until the app genuinely needs more.
- The `/ask` test pins the placeholder contract. When Section 10 wires a real LLM, this test failing is the *correct* signal that the contract changed.

### 4. Run the gate locally — expect one failure

Always run the gate on your own machine before making CI run it; the feedback loop is seconds vs minutes:

```bash
uv run ruff check .
```

Expect a **finding, not a clean pass**: `app/main.py` imports `redis` before `fastapi`, and rule `I` wants third-party imports alphabetized —

```
app/main.py:5:1: I001 [*] Import block is un-sorted or un-formatted
```

The `[*]` means auto-fixable:

```bash
uv run ruff check --fix .
uv run ruff check .        # now: All checks passed!
```

Look at the diff (`git diff app/main.py`) — it swapped two import lines. Trivial here; the habit matters: **lint locally, push clean.** A CI run that fails on formatting wastes a round trip a 2-second local command would have caught. (Teams automate the reflex with pre-commit hooks — same idea, mechanized.)

```bash
uv run pytest
```

Expect `3 passed` in well under a second.

#### If you see `ModuleNotFoundError: No module named 'app'`

The `pythonpath` line from step 2 is missing or you're not in `capstone/`. Mechanics worth owning: pytest found `tests/test_api.py`, added `tests/` to `sys.path` (its default "prepend the test file's dir" import mode), and then `from app.main import ...` looked for `app/` — which lives one level up, invisible. `pythonpath = ["."]` adds the project root relative to `pyproject.toml`. Installed-package projects don't hit this; `package = false` ones do.

### 5. Write `ci.yml`

Create `.github/workflows/ci.yml` (repo root, next to hello.yml):

```yaml
name: ci

on:
  push:
    branches: ["main"]
    paths:
      - "capstone/**"
      - ".github/workflows/ci.yml"
  pull_request:
    paths:
      - "capstone/**"
      - ".github/workflows/ci.yml"

permissions:
  contents: read

jobs:

  test:
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest]
    runs-on: ${{ matrix.os }}
    defaults:
      run:
        working-directory: capstone
    steps:
      - uses: actions/checkout@v7

      - name: Install uv
        uses: astral-sh/setup-uv@v8.3.2   # NOTE: astral-sh publishes no floating `v8` major tag —
                                          # only exact tags (v8.3.2) + a floating v7. `@v8` fails to resolve.
        with:
          enable-cache: true
          cache-dependency-glob: "capstone/uv.lock"

      - name: Install deps (exactly what uv.lock says)
        run: uv sync --frozen

      - name: Lint
        run: uv run ruff check .

      - name: Test
        run: uv run pytest -v
```

Pre-read, top to bottom:

- **`paths:` includes the workflow file itself.** Without that self-reference, editing `ci.yml` alone wouldn't trigger `ci` — you'd push a workflow change and get silence, the most confusing non-error in Actions. With it, pipeline edits test themselves.
- **`permissions: contents: read`** — the job's keycard (Lab 1) gets the minimum: read the repo, nothing else. Baseline habit now; Lab 3 *widens* it deliberately for one job and you'll feel why the default should stay narrow.
- **`strategy.matrix`** — `os: [ubuntu-latest, macos-latest]` clones the job per value; `runs-on: ${{ matrix.os }}` consumes it. In the UI you'll see `test (ubuntu-latest)` and `test (macos-latest)` as separate parallel jobs. Default `fail-fast: true` means one red variant cancels its siblings — saves minutes, and the "cancelled" (not "failed") status on the second job can confuse first-timers; now it won't.
- **`defaults.run.working-directory: capstone`** — every `run:` step cds there first (the app is a subfolder of the course repo). It applies to `run:` steps only — `uses:` steps like checkout ignore it, which is why the cache glob on the next line still needs the `capstone/` prefix.
- **`setup-uv` with `enable-cache`** — remember the empty hotel room: every run would re-download every wheel. This caches uv's download cache in GitHub's cache service between runs, keyed by a hash of `uv.lock` — lockfile unchanged → warm cache → `uv sync` takes ~1–2s. Same warehouse Lab 4 will push Docker *layers* into.
- **`uv sync --frozen`** — installs the locked versions and **fails if `pyproject.toml` and `uv.lock` disagree**. uv also auto-installs Python 3.14 itself here (the runner's system Python is irrelevant — uv manages its own interpreters; one less thing to matrix over).

### 6. Push and watch the fan-out

```bash
cd /Users/mahadihassan/Documents/plan/projects/devops-course
git add capstone/pyproject.toml capstone/uv.lock capstone/tests/ capstone/app/main.py .github/workflows/ci.yml
git commit -m "ci: lint+test gate for capstone"
git push
gh run watch
```

Expect **two** test jobs running simultaneously, both green in ~30–60s (first run is cache-cold; watch the setup-uv step report a cache miss, then hit on the next run).

#### If `uv sync --frozen` fails with a lockfile error

`error: The lockfile at uv.lock needs to be updated` means pyproject and lock drifted — typically a hand-edit to `pyproject.toml` without `uv lock`, or forgetting to commit the updated `uv.lock`. This failure is the *feature*: CI just refused to guess. Fix: `uv lock` locally, commit both files. (Exact Section-1 `--frozen` lesson, now enforced by a robot.)

#### If the run doesn't trigger at all

Read your own `paths:` filter before suspecting GitHub — did the commit actually touch `capstone/**` or `ci.yml`? `git show --stat HEAD` lists the changed paths. Filter-didn't-match produces no run and no error; it's the intended behavior of step 5's design, working against you until the mental model settles.

## Verify

- `gh run list --workflow=ci --limit 1` shows ✓, and opening the run shows `test (ubuntu-latest)` and `test (macos-latest)` both green.
- Negative test — prove the bouncer bounces: break an assertion (`"status": "not ok"`), push, watch red; revert, push, watch green. A gate you've never seen fail is a gate you shouldn't trust.

Then answer aloud:

**1. Why does `paths:` list the workflow file itself, and what happens when it doesn't?**

<details><summary>Answer (read after attempting aloud)</summary>

Path filters ring the doorbell only when a changed file matches. A push that edits *only* `ci.yml` matches nothing without the self-reference, so the workflow silently doesn't run — no error, no red X, just absence. Adding `.github/workflows/ci.yml` to its own filter means pipeline changes exercise the pipeline. Silent non-triggering is the classic path-filter footgun.

</details>

**2. What exactly does `uv sync --frozen` protect in CI that it can't fully protect on your laptop?**

<details><summary>Answer (read after attempting aloud)</summary>

The *team-wide* guarantee. Locally, `--frozen` keeps one machine honest; in CI it's an unskippable checkpoint on every push — nobody can merge a pyproject edit with a stale lockfile, because the run dies loudly. Reproducibility becomes enforced policy instead of personal discipline. Same law as the Dockerfile's `--frozen`; different courtroom.

</details>

**3. The matrix ran your tests on an arm64 Mac and an amd64 Ubuntu VM. Why is that pair more valuable to this course than a Python-version matrix?**

<details><summary>Answer (read after attempting aloud)</summary>

The capstone pins one Python (`>=3.14`), so a version matrix would test one cell. The OS pair proves the code is architecture-clean on exactly the two CPU families the Lab 4 multi-arch image will target (and that Section 1 left as a debt: arm64-only image, x86 VPS = `exec format error`). Version matrices earn their keep for libraries that must support many Pythons — know both answers.

</details>

**4. Why do test tools live in a dependency *group*, and where was that decision already enforced before this lab?**

<details><summary>Answer (read after attempting aloud)</summary>

Groups split audiences: CI needs pytest/ruff/httpx; the production image must not carry them (size, attack surface — every extra package is CVEs to patch, Section 1's slim-image lesson). The enforcement predates the tools: the Dockerfile's builder stage has run `uv sync --frozen --no-dev` since Section 1 Lab 3 — dev groups were excluded from the image before the dev group existed.

</details>

## Clean up

Nothing to tear down — the gate should stay armed forever. Just make sure the negative-test breakage is reverted and pushed green, and that `git status` is clean (tests, configs, and the lockfile all committed).
