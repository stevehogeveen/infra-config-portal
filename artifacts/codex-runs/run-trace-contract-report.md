# Run Trace Contract Report

Date: 2026-06-09

No hardware workflow was run. This pass implements an artifact-backed run trace shape so the UI and API can converge before a database-backed hardware run table exists.

## Current Implementation

`app/backend/app/services/workflow_registry.py` exposes `last_run_trace` on every workflow action.

Trace fields:

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

## Source Type Rules

- Existing report artifact: `source_type=historical_artifact`, `freshness=historical`.
- No report artifact: `source_type=not_checked`, `freshness=not_checked`.
- No registry path currently emits `live_probe`, `live_cached`, or `test_fixture`.
- Mock/test payloads are not used as current real-lab state.

## Status Rules

- `report_available`: a linked artifact exists.
- `not_checked`: no linked trace or artifact exists.
- `blocked`: local policy gates block the action.

These statuses are action evidence states, not proof that the real lab is currently ready.

## API Placement

The trace is embedded in:

- `GET /api/v1/workflows/actions`
- `GET /api/v1/workflows/actions/{action_id}`
- `GET /api/v1/workflows/stages`
- `GET /api/v1/workflows/stages/{stage_id}`

## Frontend Placement

Run Center and Control Center render run trace summaries through `RunTraceSummary`. The component displays:

- status
- source type
- freshness
- finished timestamp when a report artifact exists
- warning that historical artifacts are evidence only

## Future Database Table

A later database-backed implementation should persist:

- one action run row per invocation
- one stage event row per stage transition or action event
- stdout/stderr/log artifact references, not raw secrets
- report bundle references
- blocker/warning snapshots
- next action at finish time
- operator, runtime mode, and gate metadata

The registry action contract should remain stable when this table is added.

## Safety

- No live probe was run for this report.
- No destructive action was run.
- No secret, credential value, token, or local env content is printed.
