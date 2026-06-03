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

No real vCenter, ESXi, NetApp, switch API, AWX, Ansible, Terraform, OpenTofu,
NetBox, or Nautobot calls are made in this version. HPE iLO/Redfish and Cisco
console, Cisco Ansible SSH, and ESXi checks are preview-only and run only
through explicit local-readonly probe actions.

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

Safe start/stop/restart from the app directory:

```bash
cd /home/administrator/infra-config-portal-netapp/app
make start
make status
make restart
make stop
```

These targets call the repository-root `./runit` supervisor. It writes PID files
under `.local/run/`, logs under `.local/log/`, and only stops app-owned FastAPI
and Vite dev server processes after validating their command lines and working
directories. It does not kill Firefox, Chrome, Chromium, browser processes, or
arbitrary clients connected to `5173`.

Foreground backend-only development:

```bash
cd /home/administrator/infra-config-portal-netapp/app
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
cd /home/administrator/infra-config-portal-netapp/app/backend
PROVIDER_MODE=mock .venv/bin/pytest -q tests/test_smoke_vm_lifecycle.py
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

Foreground frontend-only development, in a second terminal:

```bash
cd /home/administrator/infra-config-portal-netapp/app
make frontend-install
make frontend-run
```

The Vite dev server runs at `http://127.0.0.1:5173` and proxies API requests
to `http://127.0.0.1:8001`.

The VM request list shows filterable request status, ownership, readiness, and
blocked indicators. The request detail view shows readiness, blockers,
lifecycle actions, approval, mock execution, cancellation, request-scoped audit
events, draft editing, notes updates for editable pre-execution requests, and
mock artifact/report cards. Run Center shows pending requests, local workflow
runs, mock stage status, report handoff links, and review-before-execute state.
Audit Events can be filtered by request ID, workflow run ID, event type,
status, link scope, and text payload. Media Inventory shows sample metadata by
default, or placeholder-only metadata from explicitly configured
`MEDIA_INVENTORY_DIRS`.

## Docker Compose

```bash
cd /home/administrator/infra-config-portal-netapp/app
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
9. `GET /api/v1/media-inventory`
10. `GET /api/v1/audit-events`

The readiness endpoint is read-only. It returns readiness flags, structured
`blockers` and `warnings` with `code`, `message`, `severity`, and `action`, a
machine-friendly `next_action`, and a short operator summary. It does not create
plans, execute workflows, write audit events, or call provider adapters.

The media inventory endpoint is metadata-only. It does not copy, mount, parse,
deploy, or execute local media files, and it redacts actual local filenames.

## Provider Status Preview

Provider Status shows mock provider health plus preview surfaces for HPE iLO /
Redfish, Cisco console, Cisco Ansible SSH, and ESXi read-only checks. Default
`PROVIDER_MODE=mock` never runs real probes on page load. Cisco console
discovery is read-only filesystem inspection of `/dev/serial/by-id/*`,
`/dev/ttyUSB*`, and `/dev/ttyACM*`; it does not open serial ports or send
commands during discovery.
iLO, ESXi, and Cisco management configuration is reported only as
configured/missing flags. The API does not return configured host, username, or
password values.

ESXi and Cisco management IPs can be planned without being treated as reachable
targets. Keep `ESXI_CONFIGURED=false` until ESXi management networking is
installed and keep `CISCO_MGMT_CONFIGURED=false` until console bootstrap has
configured Cisco management IP/SSH. Provider status and provider-smoke skip
those network probes while the flags are false; Cisco console discovery still
runs.

The Cisco Setup Readiness panel and
`GET /api/v1/providers/cisco/setup-readiness` compose Cisco console discovery
and Cisco Ansible status into a bootstrap preview. It shows the planned
management IP, console candidate counts, prompt-readiness next action,
SSH/SCP and Ansible readiness as plan-only, backup/report placeholders, and
disabled dangerous actions. It does not expose an apply button, open config
mode, enable SSH/SCP, back up running-config, save config, reload, erase, copy,
or change VLANs, interfaces, users, or passwords.

`POST /api/v1/providers/cisco-console/prompt-readiness` is a separate
newline-only console check for the setup workflow. It opens the selected
console path only in explicit `PROVIDER_MODE=local-readonly` mode with lab
read-only acknowledgements, sends newline, reads and redacts the prompt state,
and does not run show commands or configuration commands.

For an isolated local lab, optional settings live in `.env.local.real-lab` at
the repository root. Do not commit that file. Create it with:

```bash
./scripts/setup-real-lab-env.sh
```

Set `PROVIDER_MODE=local-readonly` only when manually running explicit
read-only probes and require `LAB_CLOSED_LOOP_ACK=YES` and
`LAB_READONLY_ACK=YES`. iLO probes use GET-only Redfish calls with short
timeouts and redacted responses. Cisco prompt readiness opens the selected
console only after a button click and sends newline only. Cisco console probes
open the selected console only after a button click or manual smoke command,
then send newline and safe `show` commands when already at an exec prompt.
Cisco Ansible probes check SSH, parse a generated temporary inventory, and run
only fixed safe `show` commands. ESXi probes use HTTPS GET and TCP reachability
checks only.

Optional manual smoke:

```bash
PROVIDER_MODE=local-readonly make provider-smoke
```

The backend loads local provider values from `.env.local.real-lab`, but ignores
`PROVIDER_MODE` from that file so default app and test startup remains mock.
Plain `make provider-smoke` runs in mock mode and skips probes. With explicit
`PROVIDER_MODE=local-readonly`, the smoke command skips missing
hardware/configuration and planned but not configured ESXi/Cisco management
targets gracefully, must not print passwords, and writes sanitized reports under
ignored `artifacts/real-lab/`.

## Safety Defaults

- `PROVIDER_MODE=mock`
- No plaintext secrets are stored
- Provider credential records are references only
- Real provider adapters must require explicit configuration
- Planning and approval are separate from execution
- Production-like workflows keep the approval gate

See [docs/security.md](docs/security.md) and
[docs/provider-adapters.md](docs/provider-adapters.md).
