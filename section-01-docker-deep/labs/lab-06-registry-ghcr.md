# Lab 6 — Ship the image to a registry (GHCR)

**Goal:** push the capstone image to GitHub Container Registry and pull it back like a stranger would. Registries are how images travel — CI (Section 2) will do this exact dance automatically.

## Steps

**1. Log in to GHCR using your existing gh auth:**

```bash
gh auth token | docker login ghcr.io -u itsmahadi007 --password-stdin
```

**2. Tag with the registry-qualified name** (a tag is just a pointer — nothing is copied):

```bash
cd capstone
docker tag capstone:0.1.0 ghcr.io/itsmahadi007/capstone:0.1.0
docker tag capstone:0.1.0 ghcr.io/itsmahadi007/capstone:latest
docker images | grep capstone   # same IMAGE ID, three names
```

Anatomy of the full name: `registry/owner/repo:tag`. Without a registry prefix, `docker push` would try Docker Hub.

**3. Push:**

```bash
docker push ghcr.io/itsmahadi007/capstone:0.1.0
docker push ghcr.io/itsmahadi007/capstone:latest
```

Watch the layer-by-layer upload — and note the second push says "Layer already exists" for everything (content-addressing again; only the tag moved).

**4. Make the package public:** GitHub → your profile → Packages → `capstone` → Package settings → Change visibility → Public. (New GHCR packages default to private.)

**5. Prove it round-trips — delete local, pull like a stranger:**

```bash
docker rmi ghcr.io/itsmahadi007/capstone:0.1.0 ghcr.io/itsmahadi007/capstone:latest capstone:0.1.0
docker logout ghcr.io
docker pull ghcr.io/itsmahadi007/capstone:0.1.0
docker run -d --name from-registry -p 8000:8000 ghcr.io/itsmahadi007/capstone:0.1.0
curl -s localhost:8000/health
```

Anyone on earth can now run your service with one command. That URL is portfolio evidence.

## Verify

- `curl localhost:8000/health` works from the pulled-from-registry container, after a logout.
- Explain out loud: what does a tag actually point to? Why was the second push instant?

## Clean up

```bash
docker rm -f from-registry
```

Log back in when needed: the CI in Section 2 will use its own token, not yours.
