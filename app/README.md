# infra-config-portal

Self-service infrastructure configuration portal for requesting, validating,
approving, executing, and auditing datacenter automation workflows.

The first MVP implements one safe workflow:

- Deploy VM from vSphere template
- Store requests locally
- Validate user input and mock source-of-truth data
- Require approval before planning and execution
- Simulate execution through mock provider adapters
- Record audit events for each important transition

No real vCenter, ESXi, iLO, NetApp, switch, AWX, Ansible, Terraform, OpenTofu,
NetBox, or Nautobot calls are made in this version.

## Project Layout

```text
infra-config-portal/
  README.md                 Workspace note
  reference/                Prior notes or related ideas
  app/
    backend/                FastAPI API, SQLAlchemy models, tests
    frontend/               React + Vite + TypeScript UI
    docs/                   Architecture, workflow, security, providers
    docker-compose.yml      Local dev services
    .env.example            Safe mock defaults
    Makefile                Common local tasks
```

## Backend Quick Start

```bash
cd /home/administrator/infra-config-portal/app
make backend-venv
make backend-test
make backend-run
```

The backend defaults to SQLite at `backend/.local/infra_config_portal.db`.

API health check:

```bash
curl http://127.0.0.1:8001/health
```

## Frontend Quick Start

In a second terminal:

```bash
cd /home/administrator/infra-config-portal/app
make frontend-install
make frontend-run
```

The Vite dev server runs at `http://127.0.0.1:5173` and proxies API requests
to `http://127.0.0.1:8001`.

## Docker Compose

```bash
cd /home/administrator/infra-config-portal/app
docker compose up --build
```

Compose starts PostgreSQL, the FastAPI backend, and the Vite frontend. Provider
adapters still run in mock mode only.

## MVP API Flow

1. `POST /api/v1/requests/vm-deploy`
2. `POST /api/v1/requests/{id}/submit`
3. `POST /api/v1/requests/{id}/approve`
4. `POST /api/v1/requests/{id}/plan`
5. `POST /api/v1/requests/{id}/execute`
6. `GET /api/v1/audit-events`

## Safety Defaults

- `PROVIDER_MODE=mock`
- No plaintext secrets are stored
- Provider credential records are references only
- Real provider adapters must require explicit configuration
- Planning and approval are separate from execution
- Production-like workflows keep the approval gate

See [docs/security.md](docs/security.md) and
[docs/provider-adapters.md](docs/provider-adapters.md).
