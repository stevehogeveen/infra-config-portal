# Workflow Action Registry Final Report

Generated: 2026-06-09

## Scope

This pass created a shared workflow/action registry and artifact-backed run
trace model for Run Center, Control Center, Reports, and future workflow UI
surfaces.

Work stayed inside `/home/administrator/infra-config-portal`.
`/home/administrator/lab-builder` was not modified.

No destructive hardware workflows were run. No live provider calls were made by
this implementation pass. Historical artifacts are linked as evidence only and
are not treated as fresh real-lab state.

## Delivered Reports

- `artifacts/codex-runs/workflow-action-registry-audit.md`
- `artifacts/codex-runs/workflow-action-registry-design.md`
- `artifacts/codex-runs/run-trace-contract-report.md`
- `artifacts/codex-runs/workflow-action-registry-final-report.md`

## Backend Implementation

Added:

- `app/backend/app/services/workflow_registry.py`
- `app/backend/tests/test_workflow_registry.py`

Updated:

- `app/backend/app/api/routes.py`
- `app/backend/app/schemas.py`
- `app/backend/app/services/report_center.py`
- `app/docs/workflows.md`

The registry exposes:

- `GET /api/v1/workflows/stages`
- `GET /api/v1/workflows/stages/{stage_id}`
- `GET /api/v1/workflows/actions`
- `GET /api/v1/workflows/actions/{action_id}`

The backend service provides:

- stage listing
- action listing
- stage-specific action lookup
- action detail lookup
- stage summary construction
- artifact/report evidence attachment
- local policy based availability classification
- artifact-backed run trace summaries

The registry intentionally does not probe live providers during list/detail
reads. It uses local policy and existing artifacts so registry views stay safe
and fast.

## Seeded Registry

Seeded 9 stages:

- `lab-profile`
- `firmware`
- `cisco`
- `ilo`
- `raid`
- `esxi`
- `netapp`
- `build-verification`
- `reports`

Seeded 59 workflow actions across:

- Lab profile active profile and IP profile validation
- Firmware inventory, compliance, waiver, and guarded upgrade placeholders
- Cisco serial discovery, console recovery, privilege checks, VLAN10 bootstrap,
  readiness, and firmware inventory
- HPE/iLO reachability, auth, inventory, virtual media, one-time boot, reset,
  and boot status
- RAID discovery, planning, debug, apply, pending, reset, and validation
- ESXi install readiness, media URL, virtual media, one-time boot, installer
  boot detection, management readiness, rebuild/install, SSH/API checks
- NetApp console discovery/autodiscovery, read-state, NFS/vCenter readiness,
  setup preview, validation, and certification reporting
- Build verification, live status/current state, toolchain checks, and run
  checks
- Report Center issue and summary actions

Destructive and write-capable actions are explicitly marked with non-read-only
`mode` values and gate/confirmation requirements.

## Run Trace Model

Added a lightweight run trace shape with:

- `run_id`
- `action_id`
- `stage_id`
- `started_at`
- `finished_at`
- `status`
- `source_type`
- `freshness`
- `command`
- `report_artifacts`
- `summary`
- `blockers`
- `warnings`
- `next_action`

Current traces are artifact-backed. Existing report files produce
`historical_artifact` traces. Missing checks produce `not_checked` traces. The
registry does not promote mock/test/historical evidence into current real-lab
state.

## Frontend Integration

Updated:

- `app/frontend/src/App.tsx`
- `app/frontend/src/api.ts`
- `app/frontend/src/types.ts`
- `app/frontend/src/styles.css`

Run Center now consumes workflow stages and stage details from the registry for
the first shared workflow view.

Control Center now shows the action catalog from the workflow registry, with
copyable commands, mode badges, availability, report links, safety gates, and
run trace summaries.

Reports now group issue cards by linked source action/stage when the report
issue can be mapped to registry metadata. Report links remain evidence, not
primary UI clutter.

## Screenshots

Captured:

- `artifacts/screenshots/workflow-registry-run-center.png`
- `artifacts/screenshots/workflow-registry-control-center.png`
- `artifacts/screenshots/workflow-registry-action-detail.png`

Visual checks confirmed:

- Run Center renders the registry stage table with 9 stages.
- Control Center renders the registry action catalog.
- Action detail renders RAID apply metadata, gates, command guidance, reports,
  and run trace summary.

## Validation

Passed:

- `make lint`
- `make test`

Final `make test` result:

- Backend: `317 passed in 230.21s`
- Frontend production build passed after backend tests.

Additional focused checks passed during implementation:

- `app/backend/.venv/bin/pytest -q app/backend/tests/test_workflow_registry.py`
- `PROVIDER_MODE=mock app/backend/.venv/bin/pytest -q app/backend/tests/test_workflow_registry.py`
- `PROVIDER_MODE=mock app/backend/.venv/bin/ruff check app/backend/app/services/workflow_registry.py app/backend/app/api/routes.py app/backend/app/schemas.py app/backend/app/services/report_center.py app/backend/tests/test_workflow_registry.py`
- `npm run build` from `app/frontend`

## Known Limits

- No generic `POST run action` endpoint was added in this pass. Registry actions
  expose copyable commands and endpoint metadata where available.
- Run trace persistence is not database-backed yet. Current state is built from
  policy plus artifacts.
- Some legacy hard-coded Run Center and Control Center sections remain. The new
  registry is now the shared contract for staged replacement.
- Report-to-action linking is deterministic but artifact-name based until every
  report producer writes explicit `action_id` and `stage_id` metadata.

## Skill Improvement Review

Used project skills:

- `lab-builder-skill-steward`
- `lab-builder-real-runtime`
- `lab-builder-ux`
- `lab-builder-product-craft`
- `lab-builder-hardware-run`
- `lab-builder-report-remediation`
- `lab-builder-toolchain`
- `lab-builder-dual-app-architecture`

No skill files were created or updated. The main reusable learning from this
pass is that registry list/detail reads must avoid provider status probes and
must classify historical artifacts as evidence only. That can be folded into a
future skill update if requested.
