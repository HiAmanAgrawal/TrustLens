# infra/

Deployment artefacts. Empty for now — we deploy nothing until the local
end-to-end happy path works.

## Planned contents

| File                  | Purpose                                                    |
| --------------------- | ---------------------------------------------------------- |
| `docker-compose.yml`  | Local stack: FastAPI + Postgres + Redis + ngrok            |
| `Dockerfile.backend`  | Slim Python image, installs `libzbar0` + Playwright deps   |
| `Dockerfile.frontend` | Next.js standalone build                                   |
| `k8s/` or `fly.toml`  | Production deploy target (decide once a host is picked)    |

## Decisions still to make

- **Where do we host?** Fly.io, Render, AWS Lightsail, Hetzner. India-region
  latency matters for the 3 s SLA.
- **DB managed or self-hosted?** Managed Postgres saves us pager pain; pick
  whichever the host supports natively.
- **Browser pool location.** Playwright with CapSolver is heavy; may need a
  separate worker service.
