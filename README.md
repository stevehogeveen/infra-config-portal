# infra-config-portal

Self-service infrastructure configuration portal for requesting, validating,
approving, executing, and auditing datacenter automation workflows.

The current MVP scaffold lives in `app/`. It is mock-first by design: local
development must not call real vSphere, ESXi, iLO, NetApp, switch, OVF, storage,
AWX, Terraform, NetBox, Nautobot, or other infrastructure provider APIs.

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

## Run Locally

Backend:

```bash
cd /home/administrator/infra-config-portal/app
make backend-venv
make backend-run
```

Frontend, in a second terminal:

```bash
cd /home/administrator/infra-config-portal/app
make frontend-install
make frontend-run
```

The backend runs at `http://127.0.0.1:8001`. The Vite frontend runs at
`http://127.0.0.1:5173` and proxies API requests to the backend.

Docker Compose:

```bash
cd /home/administrator/infra-config-portal/app
docker compose up --build
```

Compose starts local PostgreSQL, the FastAPI backend, and the Vite frontend.
Provider adapters still run in mock mode only.

## Tests And Checks

From the repository root:

```bash
make test
make lint
```

`make test` runs backend pytest and the frontend TypeScript/build check.
`make lint` runs backend Ruff only when it is installed in `app/backend/.venv`,
then runs the frontend build/type check.

## Codex Exec Mode

This repository includes repeatable non-interactive Codex workflows under
`.codex/`.

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
does not accept `--ask-for-approval`.

If local bwrap sandboxing fails before shell execution, the explicitly
acknowledged fallback command is:

```bash
CODEX_SANDBOX_MODE=danger-full-access CODEX_DANGER_ACK=I_UNDERSTAND make codex-next
```

`danger-full-access` is never the default. Use it only on an isolated
development machine with no real infrastructure credentials, no secrets, no
production SSH keys, and no access to real vSphere, ESXi, iLO, NetApp,
switches, DNS, IPAM, storage, or production networks.

## Safety Rules

- Keep `PROVIDER_MODE=mock` for local development and Codex exec tasks.
- Do not add real credentials, IPs, hostnames, tokens, passwords, or customer
  data.
- Do not make real vSphere, ESXi, iLO, NetApp, switch, OVF, storage, AWX,
  Terraform, NetBox, Nautobot, or source-of-truth API calls.
- Do not use `--yolo` or sandbox bypass flags.
- Do not use `danger-full-access` by default; it is allowed only through the
  explicit Codex wrapper environment variables and acknowledgement above.
- Future real provider adapters must require explicit configuration, dry-run or
  planning, approval, and audit logging.
