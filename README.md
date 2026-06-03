# infra-config-portal

Self-service infrastructure configuration portal for requesting, validating,
approving, executing, and auditing datacenter automation workflows.

The current MVP scaffold lives in `app/`. It is mock-first by design: local
development must not call real vSphere, ESXi, NetApp, switch APIs, OVF, storage,
AWX, Terraform, NetBox, Nautobot, or other infrastructure provider APIs. HPE
iLO/Redfish, Cisco console, Cisco Ansible SSH, and ESXi preview probes are
allowed only when explicitly run in `PROVIDER_MODE=local-readonly` on an
isolated local lab machine.

## Project Layout

```text
infra-config-portal/
  .codex/                  Project-scoped Codex exec automation
  scripts/                 Codex exec wrapper scripts
  Makefile                 Root local and Codex commands
  AGENTS.md                Repo instructions for Codex
  app/                     Current portal MVP scaffold
  reference/               Older notes, experiments, or adjacent ideas
```

## Always Run From Repo Root

Root automation paths such as `.codex/tasks`, `.codex/runs`, and
`.codex/task-queue.md` live at `/home/administrator/infra-config-portal-netapp`, not
under `app/`.

Before running root `make` or Codex automation commands:

```bash
cd /home/administrator/infra-config-portal-netapp
```

If you are in `/home/administrator/infra-config-portal-netapp/app`, move up one level
first. Running root-only targets from `app/` prints:

```text
Run this from /home/administrator/infra-config-portal-netapp, not /home/administrator/infra-config-portal-netapp/app.
```

## Run Locally

Safe app workflow from the repository root:

```bash
cd /home/administrator/infra-config-portal-netapp
make app-start
make app-status
make app-restart
make app-stop
```

The safe workflow is implemented by `./runit`. It records backend and frontend
PID files under `.local/run/`, logs to `.local/log/`, and only stops processes
whose command line and working directory match this app's FastAPI backend or
Vite frontend. It does not kill Firefox, Chrome, Chromium, browser processes,
or arbitrary clients connected to the frontend port.

`make dev` is an alias for `make app-restart`.

Foreground backend-only development:

```bash
cd /home/administrator/infra-config-portal-netapp/app
make backend-venv
make backend-run
```

Foreground frontend-only development, in a second terminal:

```bash
cd /home/administrator/infra-config-portal-netapp/app
make frontend-install
make frontend-run
```

The backend runs at `http://127.0.0.1:8001`. The Vite frontend runs at
`http://127.0.0.1:5173` and proxies API requests to the backend.

Docker Compose:

```bash
cd /home/administrator/infra-config-portal-netapp/app
docker compose up --build
```

Compose starts local PostgreSQL, the FastAPI backend, and the Vite frontend.
Provider adapters still run in mock mode only.

## Provider Status Preview

The Provider Status page shows mock provider cards plus HPE iLO/Redfish, Cisco
console, Cisco Ansible SSH, and ESXi read-only previews. Default
`PROVIDER_MODE=mock` performs no real probes on page load. Cisco discovery
dynamically inspects `/dev/serial/by-id/*`, `/dev/ttyUSB*`, and `/dev/ttyACM*`
without opening the serial port. Local iLO, ESXi, and Cisco settings are shown
only as configured/missing flags; configured hostnames, usernames, and passwords
are not returned in provider status payloads.

ESXi and Cisco management IPs can be recorded as planned targets without being
treated as reachable devices. Keep `ESXI_CONFIGURED=false` until ESXi
management networking is installed and keep `CISCO_MGMT_CONFIGURED=false` until
console bootstrap has configured Cisco management IP/SSH. Provider status and
provider-smoke skip those network probes while the flags are false; Cisco
console discovery still runs.

The Cisco Setup Readiness panel and
`GET /api/v1/providers/cisco/setup-readiness` compose Cisco console discovery
and Cisco Ansible status into a bootstrap preview. It shows the planned
management IP, console candidate counts, prompt-readiness next action,
SSH/SCP and Ansible readiness as plan-only, backup/report placeholders, and
disabled dangerous actions. It does not expose an apply button, open config
mode, enable SSH/SCP, back up running-config, save config, reload, erase, copy,
or change VLANs, interfaces, users, or passwords.

Optional local real-lab values live in `.env.local.real-lab`, which is ignored
by Git and must not be committed. Create it with:

```bash
./scripts/setup-real-lab-env.sh
```

Manual local-readonly smoke:

```bash
PROVIDER_MODE=local-readonly make provider-smoke
```

The backend loads local provider values from `.env.local.real-lab`, but ignores
`PROVIDER_MODE` from that file so default app and test startup remains mock.
Plain `make provider-smoke` runs in mock mode and skips probes. With explicit
`PROVIDER_MODE=local-readonly`, the smoke command writes sanitized JSON and
Markdown summaries under ignored `artifacts/real-lab/`, skips planned but not
configured ESXi/Cisco management targets gracefully, and must not print
passwords.

## Tests And Checks

From the repository root:

```bash
make test
make lint
```

`make test` runs backend pytest and the frontend TypeScript/build check.
`make lint` runs backend Ruff only when it is installed in `app/backend/.venv`,
then runs the frontend build/type check.

The backend pytest suite includes a mock-only VM lifecycle smoke test. To run
that smoke coverage directly:

```bash
cd /home/administrator/infra-config-portal-netapp/app/backend
PROVIDER_MODE=mock .venv/bin/pytest -q tests/test_smoke_vm_lifecycle.py
```

The smoke test uses FastAPI `TestClient`, an in-memory SQLite database, and the
mock provider adapters. It verifies health, draft creation and patching,
submission, approval, readiness summaries, dry-run planning, mock execution to
completion, audit events for major transitions, execution-before-plan
rejection, stale-plan invalidation after an execution-affecting edit, and
completed-request cancellation rejection. It does not start a backend server
and must remain `PROVIDER_MODE=mock`.

## Codex Exec Mode

This repository includes repeatable non-interactive Codex workflows under
`.codex/`.

Run these commands from `/home/administrator/infra-config-portal-netapp`.

Run the audit task:

```bash
make codex-audit
```

Run a specific task:

```bash
make codex-task TASK=.codex/tasks/001-backend-vm-request-lifecycle.md
```

Run the next unchecked task from `.codex/task-queue.md`:

```bash
make codex-next
```

Resume the most recent exec session:

```bash
make codex-resume
```

The wrapper scripts run `codex exec` from the repository root with safe
defaults: `CODEX_SANDBOX_MODE=workspace-write`,
`CODEX_APPROVAL_POLICY=never`, and workspace-write network access disabled.
They pass approval policy with
`-c "approval_policy=\"${CODEX_APPROVAL_POLICY}\""` because this installed CLI
does not accept `--ask-for-approval`. The root `Makefile` exports those safe
defaults for `make codex-*` commands; callers may override them explicitly in
the command environment.

If local bwrap sandboxing fails before shell execution, the explicitly
acknowledged fallback command is:

```bash
CODEX_SANDBOX_MODE=danger-full-access CODEX_DANGER_ACK=I_UNDERSTAND make codex-next
```

`danger-full-access` is never the default. Use it only on an isolated
development machine with no real infrastructure credentials, no secrets, no
production SSH keys, and no access to real vSphere, ESXi, iLO, NetApp,
switches, DNS, IPAM, storage, or production networks. Do not export
`CODEX_SANDBOX_MODE=danger-full-access` globally; set it only on the single
fallback command that requires it.

## Safety Rules

- Keep `PROVIDER_MODE=mock` for local development and Codex exec tasks.
- Use `PROVIDER_MODE=local-readonly` only for explicit local iLO, Cisco, and
  ESXi preview probes on an isolated lab machine with
  `LAB_CLOSED_LOOP_ACK=YES` and `LAB_READONLY_ACK=YES`.
- Do not add real credentials, IPs, hostnames, tokens, passwords, or customer
  data.
- Do not make real vSphere, ESXi, iLO, NetApp, switch, OVF, storage, AWX,
  Terraform, NetBox, Nautobot, or source-of-truth API calls.
- Do not use `--yolo` or sandbox bypass flags.
- Do not use `danger-full-access` by default; it is allowed only through the
  explicit Codex wrapper environment variables and acknowledgement above.
- Future real provider adapters must require explicit configuration, dry-run or
  planning, approval, and audit logging.
