# Lab 4 — Compose stack: capstone + Redis + Postgres

**Goal:** run a multi-service stack with one command — service DNS, healthcheck-gated startup, persistent volumes. This is the shape of every real backend you'll operate.

## Steps

**1. Write `capstone/docker-compose.yml`:**

```yaml
services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      REDIS_URL: redis://redis:6379/0
    depends_on:
      redis:
        condition: service_healthy
      db:
        condition: service_healthy

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
      POSTGRES_PASSWORD: localdev   # local lab only — never a real secret
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 3s
      retries: 5

volumes:
  pgdata:
```

Things to notice while writing: `REDIS_URL` uses hostname `redis` — the **service name is a DNS name** on the default compose network. `depends_on.condition: service_healthy` means the API won't start until Redis/Postgres *answer*, not merely exist — that's your Lab 3 healthcheck concept applied to ordering.

**2. Bring it up and test the wiring:**

```bash
cd capstone
docker compose up -d --build
docker compose ps                    # all healthy
curl -s localhost:8000/visits        # {"visits": 1}
curl -s localhost:8000/visits        # {"visits": 2} — Redis wiring works
```

**3. Prove service DNS from inside:**

```bash
docker compose exec api python -c "import socket; print(socket.gethostbyname('redis'), socket.gethostbyname('db'))"
docker compose exec db psql -U postgres -c 'SELECT version();'
```

**4. Prove volume persistence:**

```bash
docker compose exec db psql -U postgres -c 'CREATE TABLE survivors(id int);'
docker compose down                  # containers destroyed — but no -v
docker compose up -d
docker compose exec db psql -U postgres -c '\dt'   # survivors is still there
curl -s localhost:8000/visits        # counter reset? Redis had no volume — that's the lesson
```

Redis lost its counter (ephemeral), Postgres kept its table (named volume). Sit with that difference for a second — it's the whole "stateful vs stateless" conversation.

**5. Read the logs like an operator:**

```bash
docker compose logs -f --tail 20 api
```

(Ctrl-C to stop following.)

## Verify

- One command (`docker compose up -d --build`) brings up all three services healthy.
- `/visits` increments; the Postgres table survives `down`+`up`; you can explain why Redis's counter didn't.

## Clean up

```bash
docker compose down -v   # -v also removes the named volume — full reset
```

Commit `docker-compose.yml`. Update the capstone evolution log.
