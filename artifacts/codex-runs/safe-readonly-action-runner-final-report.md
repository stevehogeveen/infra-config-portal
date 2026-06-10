# Safe Read-Only Action Runner Final Report

Date: 2026-06-09

Scope: `/home/administrator/infra-config-portal`

## Outcome

The workflow registry now supports guarded UI/API execution for allowlisted
`read_only` and `report_only` actions. The runner refuses write,
destructive, reset, install, bootstrap, and upgrade actions before any command
or API action starts.

No destructive workflow was run. No live provider check was run during
validation or screenshot capture; tests monkeypatch subprocess calls and the
screenshots use mocked API responses.

## Backend Changes

- Added `app/backend/app/services/workflow_action_allowlist.py` with exact
  command/API allowlist entries for safe read-only/report-only actions.
- Added `app/backend/app/services/workflow_action_runner.py` to run only
  allowlisted actions, redact output, normalize run results, and block unsafe
  actions.
- Added `app/backend/app/services/workflow_action_run_store.py` to save traces
  under `artifacts/codex-runs/workflow-action-runs/` and expose latest/listed
  traces.
- Added `POST /api/v1/workflows/actions/{action_id}/run`.
- Added `GET /api/v1/workflows/actions/{action_id}/runs`.
- Extended workflow action schemas with UI run support fields and normalized
  run result fields.
- Updated the registry so latest workflow action run traces override older
  historical artifact status for that action.

## Frontend Changes

- Added safe action run buttons in Lab Setup, Run Center, and Control Center.
- Added calm labels such as `Run Verification`, `Read Console State`,
  `Check Firmware`, `Check Toolchain`, `Refresh Status`, and `Run Check`.
- Kept write/destructive/upgrade actions guarded with `Requires guarded
  workflow` instead of run buttons.
- Added spinner/disabled state while an action is running.
- Added current run result display with source, freshness, mock clarity,
  return code, redacted summaries, blockers, warnings, and evidence links.
- Added Playwright coverage for a safe run button and a destructive blocked
  action.
- Ignored generated Playwright `app/frontend/test-results/` output.

## Audit Artifact

- `artifacts/codex-runs/safe-action-runner-audit.md`

The audit lists UI-runnable actions, blocked actions, read-only actions that
remain copy-only, and runner guardrails.

## Screenshots

- `artifacts/screenshots/safe-action-runner-lab-setup.png`
- `artifacts/screenshots/safe-action-runner-control-center.png`
- `artifacts/screenshots/safe-action-runner-action-result.png`
- `artifacts/screenshots/safe-action-runner-destructive-blocked.png`

Screenshot capture used a mocked API harness against a temporary local Vite
server. The mocked result exercises the `live_probe/current/not_mock` UI state
without calling hardware.

## Validation

- `make lint`: passed.
  - Shell syntax checks passed.
  - `.codex/config.toml` parsed.
  - Backend Ruff passed.
  - Frontend production build passed.
- `make test`: passed.
  - Backend pytest: `326 passed in 215.88s`.
  - Frontend production build passed.
- `npm run test:e2e -- --reporter=line`: passed.
  - Playwright: `2 passed`.

## Safety Notes

- Unknown workflow action IDs return a 404 with a clear blocker.
- Known but unsafe actions return a normalized blocked result and save a trace.
- Output summaries are redacted before display or trace persistence.
- Historical artifacts remain evidence only and do not override newer current
  run traces.
- Mock/test state is not promoted to current real-lab state.

## Recommended Next Steps

1. Add a background job model if long-running safe checks should outlive a
   single HTTP request.
2. Extend the allowlist only after each additional read-only command has a
   command-shape and side-effect review.
3. Add live operator validation for one safe check in an explicitly configured
   local lab session, starting with iLO reachability or Toolchain Check.

## Skill Review

The existing Lab Builder skills covered this pass. No new reusable skill is
needed from this run.
