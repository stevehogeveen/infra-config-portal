# AGENTS.md

## Project

This repository is an infrastructure configuration and automation portal for
requesting, validating, approving, executing, and auditing datacenter
automation workflows.

`reference/lab-builder-reference.md` summarizes the existing
`/home/administrator/lab-builder` app. Read it before product, workflow,
provider-module, Run Center, artifact/reporting, or operator UX work. Treat it
as the target behavior reference for what this app should grow toward, while
keeping this repo mock-first and safe by default.

The current implementation lives under `app/` and uses:

- Backend: Python, FastAPI, Pydantic, SQLAlchemy, Alembic, pytest.
- Frontend: React, TypeScript, Vite.
- Local dev: Docker Compose and safe mock defaults.

## Project Skills

Project-specific Codex skills live under `.codex/skills/`. Before starting any
task, inspect `.codex/skills/` and automatically use the relevant Lab Builder
skills. Read the matching `SKILL.md` before editing or reporting. Use the
smallest matching set of skills for the task.

Automatic loading rules:

- For frontend, navigation, layout, operator wording, or UX work, use
  `lab-builder-ux` and `lab-builder-product-craft`.
- For real runtime, status, source type, freshness, live-vs-mock boundaries,
  blocker classification, or `local-lab-readwrite` gates, use
  `lab-builder-real-runtime`.
- For hardware workflows, discover-plan-apply-verify-report sequencing, lab
  profiles, console autodiscovery, NetApp/Cisco/iLO/ESXi sequencing, or run
  artifacts, use `lab-builder-hardware-run`.
- For blocker/report work, Report Center, issue cards, stale config warnings,
  evidence links, copyable fix commands, or recheck commands, use
  `lab-builder-report-remediation`.
- For external tools, Toolchain Readiness, provider tool availability, Cisco
  serial/SSH tooling, iLO Redfish/iLOrest, ESXi install/vSphere tooling,
  NetApp ONTAP tooling, or firmware workflows, use `lab-builder-toolchain`.
- For cross-app synthesis between this repo and `/home/administrator/lab-builder`,
  use `lab-builder-dual-app-architecture`.
- For skill upkeep, skill inventory, or deciding whether a reusable skill
  should be created or updated, use `lab-builder-skill-steward`.

Skill list:

- `lab-builder-real-runtime`: runtime status, source type, freshness,
  live-vs-mock boundaries, stale evidence, blocker classification, or
  `local-lab-readwrite` gates.
- `lab-builder-ux`: sidebar navigation, setup page layout, operator next
  actions, status color semantics, Reports, or evidence/raw JSON placement.
- `lab-builder-hardware-run`: discover-plan-apply-verify-report workflows,
  lab profile handling, console autodiscovery, NetApp/Cisco/iLO/ESXi run
  sequencing, or hardware artifacts.
- `lab-builder-report-remediation`: Report Center, issue cards, stale config
  warnings, blocker fields, evidence links, copyable fix commands, or recheck
  commands.
- `lab-builder-toolchain`: Toolchain Readiness, provider tool availability,
  Cisco serial/SSH tooling, iLO Redfish/iLOrest, ESXi install/vSphere tooling,
  NetApp ONTAP tooling, or firmware baseline workflows.
- `lab-builder-skill-steward`: automatic skill selection, skill inventory,
  skill creation criteria, and major-run skill improvement reviews.
- `lab-builder-dual-app-architecture`: architecture comparisons and migration
  planning between `infra-config-portal` and `lab-builder`.
- `lab-builder-product-craft`: product polish, visual coherence, page
  simplification, action-first controls, and mock-state clarity.

Mock/test state must never be treated as real lab state. Historical artifacts
are evidence, not current blockers unless a fresh check proves the blocker
still exists.

## Exec Mode Workflow

- Start root automation from `/home/administrator/infra-config-portal`, not
  `/home/administrator/infra-config-portal/app`. Root `.codex/` paths are
  resolved from the Git repository root.
- Prefer small task files in `.codex/tasks/` over long chat sessions.
- Run tasks with `make codex-task TASK=.codex/tasks/<task>.md`,
  `make codex-next`, or the scripts in `scripts/`.
- The wrappers honor `CODEX_SANDBOX_MODE` (default: `workspace-write`) and
  `CODEX_APPROVAL_POLICY` (default: `never`). Pass approval policy through
  `-c "approval_policy=\"${CODEX_APPROVAL_POLICY}\""`; do not use
  `--ask-for-approval`. The root `Makefile` exports these safe defaults for
  `make codex-*` commands and still allows explicit per-command environment
  overrides.
- If local bwrap sandboxing fails before shell execution, the only permitted
  fallback is:

  ```bash
  CODEX_SANDBOX_MODE=danger-full-access CODEX_DANGER_ACK=I_UNDERSTAND make codex-next
  ```

- Use that fallback only on an isolated development machine with no real
  infrastructure credentials, no secrets, no production SSH keys, and no access
  to real vSphere, ESXi, iLO, NetApp, switches, DNS, IPAM, storage, or
  production networks. Do not export `CODEX_SANDBOX_MODE=danger-full-access`
  globally; set it only on the single fallback command.
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

Never use `--yolo`, destructive Git resets, or sandbox bypass flags.

Do not use `danger-full-access` by default. It is permitted only for the
Codex wrapper fallback when the user explicitly sets
`CODEX_SANDBOX_MODE=danger-full-access` and
`CODEX_DANGER_ACK=I_UNDERSTAND`.

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

## UI Screenshot Validation

When a Codex task changes visible frontend UI, launch the app locally and
capture screenshots when practical. Cover the changed page or section and at
least one relevant validation, empty, blocked, or error state when applicable.
Save screenshots only under ignored local artifact/debug paths such as
`artifacts/screenshots/`; do not commit screenshots unless the project
explicitly expects committed UI snapshots. If screenshots cannot be captured,
the final response must say why and describe the manual UI checks performed.

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
