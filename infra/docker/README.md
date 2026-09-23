# Phase 0.5 Docker Boundary

`docker-compose.phase05.yml` defines the intended local validation topology:

- Postgres 17
- Temporal
- Temporal UI
- MinIO
- imgproxy
- Sanocea API process
- Sanocea Temporal worker process

Startup:

```bash
docker compose -f sanocea/infra/docker/docker-compose.phase05.yml up --build
```

This workspace currently does not have Docker installed, so this topology could
not be started locally during implementation.
