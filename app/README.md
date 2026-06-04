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

For changes to visible frontend pages, run the app locally and capture
screenshots when practical. Include the changed page or section and a relevant
validation, empty, blocked, or error state when applicable. Save screenshots
only under ignored local paths such as `artifacts/screenshots/`; do not commit
them unless the project explicitly expects committed UI snapshots. If
screenshots are skipped, note why and describe the manual UI checks performed.

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
Redfish, Cisco console, Cisco Ansible SSH, ESXi read-only checks, and NetApp
setup planning. Default
`PROVIDER_MODE=mock` never runs real probes on page load. Cisco console
discovery is read-only filesystem inspection of `/dev/serial/by-id/*`,
`/dev/ttyUSB*`, and `/dev/ttyACM*`; it does not open serial ports or send
commands during discovery.
iLO, ESXi, and Cisco management configuration is reported only as
configured/missing flags. The API does not return configured host, username, or
password values.

`netapp-ontap` setup remains plan/preview only. The provider page displays the
planned Controller SP, cluster management, node management, SVM management, and
iSCSI LIF addresses separately from current/discovered targets. When
`NETAPP_CONFIGURED=false`, current/discovered targets stay empty and cluster
management is not treated as reachable just because a planned address exists.
The page also shows separate setup and upgrade readiness, bootstrap/API/upgrade
readiness, cluster/SVM/LIF intent, storage/iSCSI intent, and artifact/report
placeholders. The structured
`GET /api/v1/providers/netapp-ontap/plan-preview` endpoint returns the same
plan-only contract for Run Center and future report generation. Run Center
renders it as a preview-only section with refresh only; it has no NetApp apply,
confirm, start, execution, upgrade, reboot, wipe, create, or configuration
control. `GET /api/v1/providers/netapp-ontap/artifacts` returns mock-only,
non-downloadable artifact metadata for the plan preview without writing files or
generating archives. `GET /api/v1/providers/artifacts` aggregates provider
artifact metadata, and the Reports / Artifacts page exposes the NetApp
placeholder outside Run Center with provider/kind/status filters.
`GET /api/v1/providers/netapp-ontap/upgrade-readiness` is offline-only: it uses
an unknown or locally configured placeholder current ONTAP version and sanitized
media inventory metadata to preview candidate media and upgrade path shape.
`GET /api/v1/providers/netapp-ontap/console-readiness` is manual/offline only:
it lists prerequisites, manual operator steps, expected prompts/states, and
disabled bootstrap actions without opening serial ports or sending commands.
`GET /api/v1/providers/netapp-ontap/observations` and `PUT
/api/v1/providers/netapp-ontap/observations` capture bounded operator
readiness observations in a process-local mock store only and reject
secret-shaped note text. Run Center shows the same local notes in the
console/bootstrap section and warns operators not to paste passwords, tokens,
or raw configs.
`GET /api/v1/providers/netapp-ontap/readiness-comparison` compares planned
targets with those operator observations only and reports matched, unknown,
warning, and blocked manual readiness rows without live discovery. Optional Controller B
console observation is surfaced as a warning when it has not been recorded, and
the console readiness summary separates required and optional observation
counts. Cluster management not configured, node management not configured, SVM
management planned but not live, iSCSI LIF range planned but not live, missing
credentials, and missing `LAB_READONLY_ACK=YES` are reported as setup/upgrade
readiness blockers where applicable.
Keep `NETAPP_CONFIGURED=false`; ONTAP API readiness is disabled and no NetApp
Service Processor, console, SSH, ONTAP API, storage provisioning, LIF creation,
upgrade, reboot, wipe, or apply call is made.

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

`GET /api/v1/providers/cisco/setup-wizard-plan` is preview-only. It reports the
latest cached prompt-readiness state when available, explains why initial setup
wizard handling is blocked, shows future guarded bootstrap planning steps, and
keeps answer-wizard, configuration, save, reload, erase/copy, SSH/SCP,
running-config backup, and real apply actions disabled.

`GET /api/v1/providers/cisco/bootstrap-requirements` validates the preview-only
inputs needed before any future guarded bootstrap design: management IP,
subnet/prefix, gateway, management VLAN/interface strategy, hostname,
domain/DNS, local admin username presence, SSH/SCP policy, save behavior, and
explicit confirmation requirements. `PUT` to the same endpoint stores
non-secret local planning values under
`.local/cisco/bootstrap-requirements.json`, which is ignored by Git. The
workflow returns blockers/warnings only and does not generate commands, answer
setup prompts, enable SSH/SCP, save configuration, or apply anything.

`GET /api/v1/providers/cisco/console-bootstrap/plan` builds the guarded
Cisco-only console bootstrap preview for this lab target:
`192.168.1.220/24` (`255.255.255.0`). It distinguishes setup-wizard,
direct exec/config-mode, and unsupported prompt flows, shows redacted preview
commands, and keeps destructive reset/wipe actions separate and disabled.
`POST /api/v1/providers/cisco/console-bootstrap/apply` is blocked by default
and records a redacted blocked result unless all backend gates pass, including
the exact confirmation phrase
`APPLY CISCO CONSOLE BOOTSTRAP 192.168.1.220`. The current implementation is a
guarded scaffold and does not perform serial writes.

See `app/docs/cisco-real-lab-bootstrap-runbook.md` for the safe local-lab
operator flow, required gates, blocked-result meanings, and evidence handling.

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

NetApp-only real-run readiness, with no ONTAP probes or apply actions:

```bash
PROVIDER_MODE=local-readonly make netapp-real-readiness
```

The backend loads local provider values from `.env.local.real-lab`, but ignores
`PROVIDER_MODE` from that file so default app and test startup remains mock.
Plain `make provider-smoke` runs in mock mode and skips probes. With explicit
`PROVIDER_MODE=local-readonly`, the smoke command skips missing
hardware/configuration and planned but not configured ESXi/Cisco management
targets gracefully, must not print passwords, and writes sanitized reports under
ignored `artifacts/real-lab/`. The NetApp-only readiness command writes
`netapp-readiness-*` artifacts under the same ignored directory and never
contacts ONTAP, SP, console, SSH, storage, upgrade, reboot, wipe, or apply
endpoints.

## Safety Defaults

- `PROVIDER_MODE=mock`
- No plaintext secrets are stored
- Provider credential records are references only
- Real provider adapters must require explicit configuration
- Planning and approval are separate from execution
- Production-like workflows keep the approval gate

See [docs/security.md](docs/security.md) and
[docs/provider-adapters.md](docs/provider-adapters.md).
