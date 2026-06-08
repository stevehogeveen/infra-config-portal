# Control Center Final Report

Generated: 2026-06-08

Scope: `/home/administrator/infra-config-portal`

## Outcome

Added a power-user Control Center at `/control-center` while preserving the
existing simplified Run Center / Lab Builder guided flow.

The new Control Center provides:

- Guided View link back to `/run-center`.
- Full action catalog with 46 actions across 9 sections.
- Lab Profile panel with current values, known lab values, configured flags,
  stale/invalid value warnings, edit-profile handoff, and a copyable non-secret
  env update command.
- Current state, desired state, and plan/diff blocks for each major stage.
- Cisco, HPE/iLO, RAID, ESXi, NetApp, firmware/upgrade, verification, commander
  mode, and report controls.
- Visible Firmware / Upgrade Center with iLO firmware, BIOS, Smart Array,
  Cisco IOS XE, Cisco ROMMON, ESXi media/version, ONTAP, NetApp disk, shelf,
  and SP/BMC firmware rows.
- Visible commander controls: reclaim serial port, force live discovery, ignore
  cached artifact, and run live check.
- Action History / Reports and a filterable Action Catalog table.

## Backend

Added typed action-catalog support:

- `GET /api/v1/control/actions`
- `POST /api/v1/control/actions/{action_id}/plan`
- `POST /api/v1/control/actions/{action_id}/run`

The `run` endpoint is intentionally a safe placeholder in this pass. It returns
the action, blockers, and suggested command/API endpoint, but does not execute
commands, call providers, write serial commands, apply configuration, reset
devices, install ESXi, provision storage, or run firmware updates.

The catalog exposes:

- action id and label
- device/stage
- description
- read-only/write/destructive/upgrade classification
- required inputs
- required flags
- required confirmations
- availability
- blocker
- last run/report status
- suggested command/API endpoint

## Frontend

Added route/navigation:

- `/control-center`
- Sidebar item: `Control Center`

Added reusable Control Center components:

- `CurrentStateBlock`
- `DesiredStateBlock`
- `PlanDiffBlock`
- `ActionButtonRow`
- `ControlSection`
- `ActionCatalogTable`

The UI shows controls directly rather than requiring Advanced diagnostics, while
still keeping raw diagnostics collapsed inside each section.

## Reports And Screenshots

Created design/audit reports:

- `artifacts/codex-runs/control-center-control-audit.md`
- `artifacts/codex-runs/control-center-design.md`
- `artifacts/codex-runs/control-center-final-report.md`

Captured screenshots:

- `artifacts/screenshots/control-center-overview.png`
- `artifacts/screenshots/control-center-cisco.png`
- `artifacts/screenshots/control-center-firmware.png`
- `artifacts/screenshots/control-center-esxi-netapp.png`

## Validation

Commands run:

- `cd app/backend && PROVIDER_MODE=mock .venv/bin/python -m py_compile app/services/control_actions.py app/schemas.py app/api/routes.py`
- `cd app/backend && PROVIDER_MODE=mock .venv/bin/pytest -q tests/test_api.py::test_control_action_catalog_exposes_device_actions_without_direct_runs tests/test_api.py::test_control_action_plan_and_run_are_safe_placeholders tests/test_api.py::test_control_action_unknown_returns_404`
- `cd app/backend && PROVIDER_MODE=mock .venv/bin/ruff check app tests`
- `cd app/frontend && PROVIDER_MODE=mock npm run build`
- `make lint`
- `make test`

Final results:

- Backend tests: `274 passed`
- Frontend build: passed
- Root lint: passed
- Root test: passed

## Safety

- Provider mode remained mock for validation.
- No real infrastructure calls were added to page load.
- No firmware updates were implemented or run.
- No direct write/destructive/provider run is enabled from Control Center.
- Direct run endpoint is a no-op/manual-command placeholder.
- Secrets are not displayed; credential values remain represented only as
  configured/missing through existing provider surfaces.

## Remaining Work

- Add guarded direct execution lanes per action once confirmation, audit, and
  rollback/report contracts are explicitly designed.
- Add persisted action history records instead of inferring latest status from
  report files.
- Add richer profile editing directly in Control Center if desired; current
  edit path links to Lab Profiles and exposes a non-secret env command.
- Add frontend unit/component tests if a frontend test harness is introduced.
