# infra-config-portal

Self-service infrastructure configuration portal for requesting, validating,
approving, executing, and auditing datacenter automation workflows.

The first MVP implements one safe workflow:

- Deploy VM from vSphere template
- Store requests locally
- Validate user input and mock source-of-truth data
- Require approval before planning and execution
- Report readiness, blockers, and the next safe action
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

## Tests And Smoke Coverage

From the repository root:

```bash
make test
make lint
```

`make test` runs backend pytest and the frontend TypeScript/build check.
`make lint` runs shell syntax checks, backend Ruff when installed in
`backend/.venv`, and the frontend build/type check.

The backend pytest suite includes a local mock VM lifecycle smoke test. Run only
that smoke test with:

```bash
cd /home/administrator/infra-config-portal/app/backend
.venv/bin/pytest -q tests/test_smoke_vm_lifecycle.py
```

The smoke test uses FastAPI `TestClient`, an in-memory SQLite database, and mock
provider adapters only. It covers health, VM request creation, draft patching,
submit, approval, dry-run planning, mock execution to completed, audit events,
readiness checks, execution-before-plan rejection, stale-plan invalidation after an
execution-affecting edit, and completed-request cancellation rejection.

Keep `PROVIDER_MODE=mock`. The smoke test must not call vCenter, ESXi, iLO,
Redfish, NetApp, switches, DNS, IPAM, storage, AWX, Terraform, OpenTofu,
NetBox, Nautobot, PowerCLI, govc, OVF Tool, or any lab/production
infrastructure.

## Frontend Quick Start

In a second terminal:

```bash
cd /home/administrator/infra-config-portal/app
make frontend-install
make frontend-run
```

The Vite dev server runs at `http://127.0.0.1:5173` and proxies API requests
to `http://127.0.0.1:8001`.

The request detail view shows readiness, blockers, lifecycle actions, approval,
mock execution, cancellation, request-scoped audit events, draft editing, and
notes updates for editable pre-execution requests. Run Center shows pending
requests, local workflow runs, mock stage status, and review-before-execute
state.

## Docker Compose

```bash
cd /home/administrator/infra-config-portal/app
docker compose up --build
```

Compose starts PostgreSQL, the FastAPI backend, and the Vite frontend. Provider
adapters still run in mock mode only.

## MVP API Flow

1. `POST /api/v1/requests/vm-deploy`
2. `GET /api/v1/requests/{id}/readiness`
3. `POST /api/v1/requests/{id}/submit`
4. `POST /api/v1/requests/{id}/approve`
5. `POST /api/v1/requests/{id}/plan`
6. `GET /api/v1/requests/{id}/readiness`
7. `POST /api/v1/requests/{id}/execute`
8. `GET /api/v1/workflow-runs`
9. `GET /api/v1/audit-events`

The readiness endpoint is read-only. It returns readiness flags, structured
`blockers` and `warnings` with `code`, `message`, `severity`, and `action`, a
machine-friendly `next_action`, and a short operator summary. It does not create
plans, execute workflows, write audit events, or call provider adapters.

## Safety Defaults

- `PROVIDER_MODE=mock`
- No plaintext secrets are stored
- Provider credential records are references only
- Real provider adapters must require explicit configuration
- Planning and approval are separate from execution
- Production-like workflows keep the approval gate

See [docs/security.md](docs/security.md) and
[docs/provider-adapters.md](docs/provider-adapters.md).
