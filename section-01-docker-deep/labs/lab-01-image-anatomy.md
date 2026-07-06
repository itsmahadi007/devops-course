# Lab 1 — Image anatomy

**Goal:** see layers, cache, and container lifecycle with your own eyes instead of taking them on faith.

## Steps

**1. Pull and dissect an image:**

```bash
docker pull nginx:alpine
docker history nginx:alpine
```

`docker history` shows one row per layer — read it bottom-up: base OS → packages → config → metadata. Note which rows are `0B` (metadata-only instructions like `ENV`, `EXPOSE`, `CMD` create no filesystem layer).

```bash
docker image inspect nginx:alpine --format '{{json .RootFS.Layers}}' | tr ',' '\n'
```

Those `sha256:` digests are the content-addressed layers. Pull another alpine-based image and compare — shared digests are stored once on disk.

**2. Run it, poke it:**

```bash
docker run -d --name anatomy -p 8080:80 nginx:alpine
curl -s localhost:8080 | head -4
docker exec -it anatomy sh
```

Inside the container: `ps aux` (PID 1 is nginx — a container lives exactly as long as PID 1), `cat /etc/os-release`, then `exit`.

**3. Prove the writable layer is ephemeral:**

```bash
docker exec anatomy sh -c 'echo scratch > /tmp/i-will-die'
docker exec anatomy cat /tmp/i-will-die        # it's there
docker rm -f anatomy
docker run -d --name anatomy -p 8080:80 nginx:alpine
docker exec anatomy cat /tmp/i-will-die        # gone — new container, fresh writable layer
```

**4. Logs and lifecycle:**

```bash
docker logs anatomy --tail 5
docker stop anatomy && docker ps -a --filter name=anatomy   # Exited, not deleted
docker start anatomy && docker ps --filter name=anatomy
```

`stop` vs `rm`: a stopped container keeps its writable layer; `rm` destroys it. (Note: on macOS the Docker engine runs inside a lightweight VM — `/var/lib/docker` lives there, not on your Mac's filesystem.)

## Verify

You can answer, out loud, without looking:
- Why do `ENV`/`CMD` lines show `0B` in `docker history`?
- What exactly is destroyed by `docker rm` that survives `docker stop`?
- Two images share a base — is it stored twice? How do you check?

## Clean up

```bash
docker rm -f anatomy
```
