# Lab 3 — Containerize the model server

**Goal:** move the model server off your bare terminal and into the compose stack, beside the api/redis/db from Section 1. Along the way, confront the one genuinely new problem LLM serving adds to containerization — **the model file is huge and doesn't belong in your source tree** — and learn the three ways to get weights into a container and when to pick each. You'll also measure the honest cost of losing Metal inside the container.

## The mental map (read this first)

Containerizing a normal service is Section 1 muscle memory: `FROM`, copy code, run. A model server breaks that habit because of one fact: **the weights are a 640 MB (to many-GB) binary blob that changes rarely, isn't source code, and must not live in your git repo or your image layers by default.** So the real question of this lab isn't "how do I containerize llama.cpp" (the official image already exists) — it's **"where does the model file come from at run time?"** Three answers:

```
 ┌─ BAKE ──────────────────────┐  ┌─ MOUNT ─────────────────────┐  ┌─ INIT-DOWNLOAD ─────────────┐
 │ COPY the .gguf into a        │  │ keep the .gguf on the host,  │  │ small stock image; server    │
 │ custom image at build time   │  │ bind/volume-mount it in      │  │ pulls the .gguf at startup   │
 │                              │  │                              │  │ via -hf into a cache VOLUME  │
 │ image size: HUGE (+640MB…GB) │  │ image size: tiny (stock)     │  │ image size: tiny (stock)     │
 │ start: instant, offline      │  │ start: instant, offline      │  │ start: slow 1st time, needs  │
 │ immutable: model IS the tag  │  │ model lives outside image    │  │   network; cached after      │
 │ ship: one artifact, portable │  │ good for local dev / swaps   │  │ good for k8s (initContainer) │
 └──────────────────────────────┘  └──────────────────────────────┘  └──────────────────────────────┘
        prod / air-gapped                   local iteration               cluster w/ shared cache
```

There's no universally right answer — it's a trade-off interviewers love:

- **Bake** = fully self-contained and immutable (the image tag *is* an exact model version), but every image is enormous and you rebuild to change models. Right for air-gapped or strictly-reproducible prod.
- **Mount** = image stays tiny, model swaps are instant, but the container isn't self-contained — it depends on a file being present on whatever host runs it. Great for local dev.
- **Init-download** = tiny image + a cache volume the server fills on first boot. Slow first start and needs network, but it's the pattern that scales cleanly to Kubernetes (an `initContainer` fetches weights into a shared volume — Lab 6). **This is what we'll wire into compose**, because it's the one that carries forward.

And the truth you must not gloss over: **inside Docker Desktop's Linux VM there is no Metal.** The container's `llama-server` runs **CPU-only**. Your bare Lab 1 server used the GPU; this one won't. Expect noticeably fewer tokens/sec. That's not a bug — it's the reason real GPU LLM serving needs GPU passthrough (`--gpus` / NVIDIA device plugin on real clusters), and the reason "just containerize it" isn't the whole story for AI infra. You'll measure the gap in step 3.

The stack you're extending (Section 1's, now with a fourth service):

```
 localhost:9000 ──▶ api ──┬──▶ redis   (service DNS, no host port)
                          ├──▶ db      (service DNS, no host port)
 localhost:9110 ──▶ model ┘  LLM_BASE_URL=http://model:8080/v1   ← api calls it by NAME
                            (CPU-only in the VM; weights in a cache volume)
```

## Steps

### 1. See all three approaches (only one gets built)

**Bake (for contrast — read, don't build unless curious).** A `capstone/model.Dockerfile` would look like:

```dockerfile
FROM ghcr.io/ggml-org/llama.cpp:server
# Download the weights AT BUILD TIME so they live in a layer (the "bake").
RUN llama-server -hf Qwen/Qwen3-0.6B-GGUF:Q8_0 --dry-run || true
# → the resulting image is ~640MB bigger than stock. `docker images` will show it.
```

The point to *feel*: `docker images` on this would be stock-size **plus 640 MB**, and swapping to Q4 means a rebuild + re-push of the whole thing. Multiply by a 5 GB model and you see why baking is a deliberate prod choice, not a default.

**Mount (for local dev).** If you'd already downloaded a `.gguf` to `~/models/`, you'd mount it and point `-m` at it — no download, no bake:

```yaml
    volumes:
      - ~/models:/models:ro          # read-only bind mount of your host model folder
    command: -m /models/Qwen3-0.6B-Q8_0.gguf --host 0.0.0.0 --port 8080 -c 4096 --jinja
```

Tiny image, instant start, but the container now *requires* that file to exist on the host.

**Init-download (what we build).** Stock image, `-hf` pulls at startup into a **cache volume** so it only downloads once — the Section 1 named-volume lesson applied to model weights.

### 2. Add the `model` service to `capstone/docker-compose.yml`

Full updated file — the `model` service and its `llmcache` volume are new, and `api` gains one env var. Everything else is your Section 1 stack unchanged:

```yaml
services:            # each entry = one container Docker will run and babysit

  api:               # ── your capstone, built from the Section 1 Dockerfile ──
    build: .
    ports:
      - "9000:8000"  # host:container — the api's door to your Mac
    environment:
      REDIS_URL: redis://redis:6379/0        # compose DNS
      LLM_BASE_URL: http://model:8080/v1     # ← NEW: the model service, by name (compose DNS)
    depends_on:
      redis:
        condition: service_healthy
      db:
        condition: service_healthy
      model:
        condition: service_healthy           # ← NEW: don't start api until the model ANSWERS
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

  model:             # ── NEW: the self-hosted LLM server ──
    image: ghcr.io/ggml-org/llama.cpp:server   # official multi-arch image (CPU-only in the VM)
    command: >                                  # init-download: pulls the GGUF at startup
      -hf Qwen/Qwen3-0.6B-GGUF:Q8_0
      --host 0.0.0.0 --port 8080
      -c 4096 --jinja
      --metrics
    ports:
      - "9110:8080"  # published so you can curl it directly (Lab 5 scrapes /metrics too)
    volumes:
      - llmcache:/root/.cache/llama.cpp   # weights cached here → downloaded once, survives restarts
    healthcheck:
      # /health answers only once the model is fully loaded → real readiness, not "process up"
      test: ["CMD-SHELL", "curl -sf http://localhost:8080/health || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 120s   # first boot must DOWNLOAD the model — give it a long grace window

  redis:
    image: redis:8-alpine
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  db:
    image: postgres:18-alpine
    environment:
      POSTGRES_PASSWORD: localdev
    volumes:
      - pgdata:/var/lib/postgresql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 3s
      retries: 5

volumes:
  pgdata:
  llmcache:            # ← NEW: the model-weights cache — download once, reuse forever
```

#### The lines that carry the lesson

- **`command: >` with `-hf …`** — the init-download approach, live. First `up` downloads the GGUF into the container; the `llmcache` volume catches it so it's *never* downloaded again. This is Section 1's "persistence is a per-service decision" — model weights are exactly the kind of expensive-to-fetch data that earns a volume.
- **`--host 0.0.0.0`** — the container flip you predicted in Lab 1. Bare on your Mac you bound loopback; inside the container the api reaches `model` across the network wall, so the server must listen on all interfaces (Section 1's `0.0.0.0` rule, verbatim).
- **`LLM_BASE_URL: http://model:8080/v1`** — the api finds the model by **service name**, container-side port `8080` (conventional, unmoved — only the *host* side went to 9110). No IPs. The exact compose-DNS pattern as `redis://redis:6379`, now for the LLM. Your Lab 2 code needs **zero changes** — only this env flips.
- **`condition: service_healthy` on `model`** — the api won't even start until the model's `/health` answers. Without it you'd recreate Lab 2's "model unreachable" race at stack scale; the retry loop would paper over it, but gating is cleaner.
- **`start_period: 120s`** — the healthcheck grace window is *long* because the first boot downloads ~640 MB before `/health` goes green. On a big model this would be minutes; the grace period must cover the *download*, not just the load. (Failures during the grace period don't count — Section 1's healthcheck flags.)
- **`--metrics`** — turns on the Prometheus `/metrics` endpoint now, so Lab 5 can scrape it without a restart.
- **container-side `8080`, host-side `9110`** — the model server's conventional port is 8080; we publish it on 9110 to stay in this section's block and let you curl it directly. Same split-brain addressing as every service since Section 1.

### 3. Bring it up and measure the Metal gap

```bash
cd capstone
docker compose up -d
docker compose logs -f model      # watch the download, then "server is listening"
```

#### What the first boot shows

The `model` logs will show a Hugging Face download progress, then the familiar load lines — but **notice what's missing**: no `ggml_metal_init: found device`. Instead you'll see it fall back to CPU. That single absent line is the whole Metal-in-container story. `docker compose ps` will show `model` as `(health: starting)` for up to two minutes while it downloads, then `(healthy)`; the api waits for that flip before starting.

Now compare tokens/sec against Lab 1's bare (Metal) run:

```bash
curl -s localhost:9110/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen","messages":[{"role":"user","content":"Explain DNS in one sentence."}],"max_tokens":80}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('tok/s:', d['timings']['predicted_per_second'])"
```

#### Reading the number

Expect the containerized (CPU) number to be **a large fraction lower** than Lab 1's Metal number — often 2–5× slower depending on your chip and how many CPU threads the VM gets. For a 0.6B model it's still perfectly usable (tens of tok/s), but the gap is real and it *widens* with model size. The takeaway to carry into interviews: **containerization is free for CPU-bound and IO-bound services, but GPU acceleration does not cross the container boundary for free** — you need explicit device passthrough, which Docker Desktop's Mac VM doesn't offer for Metal. This is why serious LLM serving happens on Linux hosts with NVIDIA GPUs and the container toolkit, and why "runs on my Mac in a container" is a dev convenience, not a perf statement.

### 4. Prove the full chain works

```bash
curl -s "localhost:9000/ask?q=what+is+a+container+image%3F" | python3 -m json.tool
```

This goes `host:9000 → api → model:8080 (service DNS) → back`. A real answer means the entire stack — your Lab 2 code, unchanged, now talking to a *containerized* model by service name — is wired. The placeholder is dead across the whole stack, not just your laptop.

## Verify

- `docker compose ps` shows all four services healthy; `/ask` on `:9000` returns a model answer routed through the `model` service; the model's tokens/sec is measurably lower than Lab 1's Metal run.
- You can answer, out loud, without looking:

- Bake vs mount vs init-download — one sentence each on when you'd pick it.

  <details><summary>Answer (read after attempting aloud)</summary>

  **Bake**: weights baked into the image — pick for air-gapped/strict-reproducibility prod, accepting a huge image and rebuild-to-swap. **Mount**: weights on the host, mounted in — pick for local dev where you swap models often and want a tiny image. **Init-download**: stock image pulls weights into a cache volume at startup — pick for clusters (initContainer + shared volume), accepting a slow, network-dependent first boot.

  </details>

- Why does the model server bind `0.0.0.0` in the container but you used `127.0.0.1` bare in Lab 1?

  <details><summary>Answer (read after attempting aloud)</summary>

  Same network-namespace wall as Section 1's CMD. Bare on the Mac, loopback was safest — only local processes needed it. In the container, the api reaches `model` *across* the container network, so the server must listen on all interfaces (`0.0.0.0`) for that cross-container traffic to arrive; loopback would refuse it.

  </details>

- Your image is the stock `llama.cpp:server` yet the model persists across `docker compose down`/`up` without re-downloading. How?

  <details><summary>Answer (read after attempting aloud)</summary>

  The `llmcache` **named volume** mounted at `~/.cache/llama.cpp`. The `-hf` download lands there on first boot; the volume outlives containers (Section 1's stateful-vs-stateless lesson), so subsequent boots find the weights already present and skip the download. The image stays tiny because the weights live in the volume, not a layer.

  </details>

- Why is the containerized model slower than the bare one, and what would fix it on a real server?

  <details><summary>Answer (read after attempting aloud)</summary>

  Docker Desktop's Linux VM has no access to the Mac's Metal GPU, so the container runs CPU-only inference while the bare brew binary used the GPU. GPU acceleration doesn't cross the container boundary automatically. On a real Linux host you'd pass the GPU through (`--gpus all` with the NVIDIA container toolkit; the device plugin in Kubernetes) so the container can use CUDA — that's the standard production LLM-serving setup.

  </details>

## Clean up

```bash
docker compose down          # keeps volumes (pgdata AND llmcache) — model won't re-download next time
# docker compose down -v     # ONLY if you want to reclaim the ~640MB model cache too
```

Commit the updated `docker-compose.yml`. Update the capstone evolution log: "Section 10: model server containerized as a compose service (init-download into a cache volume, wired to the api by service DNS)."
