# AGENTS.md

## Project

This repository is an infrastructure configuration and automation portal for
requesting, validating, approving, executing, and auditing datacenter
automation workflows.

The current implementation lives under `app/` and uses:

- Backend: Python, FastAPI, Pydantic, SQLAlchemy, Alembic, pytest.
- Frontend: React, TypeScript, Vite.
- Local dev: Docker Compose and safe mock defaults.

## Exec Mode Workflow

- Prefer small task files in `.codex/tasks/` over long chat sessions.
- Run tasks with `make codex-task TASK=.codex/tasks/<task>.md`,
  `make codex-next`, or the scripts in `scripts/`.
- Avoid asking the user questions unless blocked by missing information that
  cannot be discovered locally and where a reasonable assumption would be risky.
- Inspect relevant files before editing.
- Keep changes narrow and aligned with the existing app structure.
- Every Codex exec task should end with a concise summary; the wrapper saves
  that final response in `.codex/runs/`.
- Update `.codex/task-queue.md`, README files, docs, or tests when the task
  changes commands, workflows, behavior, or safety assumptions.

## Safety Rules

Never add real credentials, secrets, IPs, tokens, passwords, hostnames, or
customer data.

All provider integrations must default to mock mode.

Do not make real calls to:

- VMware vSphere or ESXi
- HPE iLO or Redfish
- NetApp ONTAP
- network switches or VLAN controllers
- OVF or OVA deployment endpoints
- storage provisioning APIs
- AWX, Ansible Automation Platform, Terraform, or OpenTofu backends
- NetBox, Nautobot, or other source-of-truth systems

Any real infrastructure integration must require explicit configuration outside
automated Codex tasks and must support dry-run or plan, approval, audit logging,
and rollback notes where practical.

Never use `--yolo`, `danger-full-access`, destructive Git resets, or sandbox
bypass flags.

Never allow arbitrary user-provided code execution or arbitrary Ansible
variables from the UI without validation.

Never bypass request validation or approval gates for production-like
workflows.

## Architecture Expectations

The portal is a control plane, not the automation engine itself.

Use clean separation between:

- API routes
- request schemas
- domain models
- workflow state machine
- provider adapters
- source-of-truth adapters
- audit/event logging
- frontend UI components

Provider adapters should use interfaces or abstract base classes so real
implementations can replace mock implementations later without changing request
lifecycle code.

## MVP Scope

The first MVP is `Deploy VM from Template`.

The first implementation must use mock providers only.

Required request states:

- draft
- submitted
- validating
- needs_approval
- approved
- planned
- executing
- completed
- failed
- cancelled

## Testing

Use the root commands when possible:

```bash
make test
make lint
```

Backend-only tests can be run from `app/` with:

```bash
make backend-test
```

Frontend build/type checks can be run from `app/frontend/` with:

```bash
npm run build
```

Add or update tests for request validation, lifecycle transitions, audit event
creation, mock VM deployment execution, API endpoint behavior, provider adapter
contracts, and changed frontend behavior where tooling exists.

## Done Means

A task is not done until:

- relevant code is formatted
- relevant tests pass, or limitations are documented with exact commands
- README or docs are updated when commands, workflows, or behavior changes
- safety assumptions are explicit
- no real infrastructure calls are made
- providers remain mocked by default
- the final response includes files changed, tests run, failures or skipped
  checks, and recommended next steps
