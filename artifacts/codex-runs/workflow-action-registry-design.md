# Workflow Action Registry Design

Date: 2026-06-09

Scope: backend registry contract for Run Center, Control Center, Reports, and future Lab Setup pages. No hardware workflow execution is added in this design.

## Design Goal

Create one typed action/stage definition system that can be consumed by:

- Run Center: stage order, stage status, next action, and action detail.
- Control Center: expert action catalog, copyable commands, safety gates.
- Reports: source action/stage links and evidence grouping.
- Future pages: provider setup/detail pages without hard-coded action metadata.

## Action Fields

Each action exposes:

- `action_id`: stable unique action key such as `raid.apply`.
- `label`: operator-facing label.
- `stage`: registry stage id.
- `stage_label`: display label for the stage.
- `provider`: provider or workflow family, such as `cisco`, `hpe-ilo`, `netapp`, `toolchain`, or `reports`.
- `category`: one of `discover`, `inventory`, `plan`, `apply`, `verify`, `report`, `reset`, `upgrade`, `waive`, `reclaim`.
- `mode`: one of `read_only`, `write`, `destructive`, `upgrade`, `report_only`.
- `description`: short operator-facing action summary.
- `source_type`: one of `make_target`, `backend_script`, `api_endpoint`, `manual_guidance`.
- `command`: copyable local command when available.
- `api_endpoint`: matching API endpoint when available.
- `api_method`: endpoint method when available.
- `required_mode`: required provider/runtime mode.
- `required_gates`: environment flags or mode gates.
- `required_confirmations`: confirmation phrases or explicit operator acknowledgements.
- `required_credentials`: presence-only credential references; no values.
- `safety_notes`: non-secret safety constraints.
- `inputs`: typed action inputs with secret markers where applicable.
- `outputs`: expected output classes.
- `reports`: report artifacts this action can produce.
- `last_run_report`: latest existing report artifact path, if any.
- `last_run_status`: `report_available` or `not_checked`.
- `current_availability`: `available`, `manual_command_required`, `blocked`, or `not_available`.
- `blockers`: current gate/policy blockers from local policy evaluation only.
- `next_action`: operator next action or blocker.
- `evidence_artifacts`: existing linked report artifacts.
- `stale_after_seconds`: recommended freshness TTL.
- `last_run_trace`: lightweight run trace summary.

## Stage Fields

Each stage exposes:

- `stage_id`: stable stage key.
- `label`: display label.
- `order`: numeric workflow order.
- `current_state`: summarized as `blocked`, `historical`, `not_checked`, or `not_available`.
- `desired_state`: operator goal for the stage.
- `primary_action`: first recommended read/report action.
- `secondary_actions`: remaining action ids.
- `dependencies`: prior stage ids.
- `reports`: report artifact paths tied to the stage.
- `action_count`: action count.
- `blocked_count`: blocked action count.
- `report_count`: count of currently existing reports.
- `actions`: expanded action definitions for stage detail pages.

## Seeded Stage Order

1. `lab-profile`
2. `firmware`
3. `cisco`
4. `ilo`
5. `raid`
6. `esxi`
7. `netapp`
8. `build-verification`
9. `reports`

## Run Trace Contract

The initial run trace model is artifact-backed, not database-backed.

Fields:

- `run_id`
- `action_id`
- `stage_id`
- `started_at`
- `finished_at`
- `status`
- `source_type`: `live_probe`, `live_cached`, `historical_artifact`, `test_fixture`, or `not_checked`
- `freshness`
- `command`
- `report_artifacts`
- `summary`
- `blockers`
- `warnings`
- `next_action`

Current behavior:

- Existing report artifacts produce a trace with `source_type=historical_artifact` and `freshness=historical`.
- Missing reports produce `source_type=not_checked`.
- No mock/test payload is promoted to live state.
- No registry endpoint runs an action.

## Availability Rules

- Read-only and report-only actions can expose commands or GET endpoints as copyable guidance.
- Write/destructive/upgrade actions evaluate local action policy gates.
- `PROVIDER_MODE=mock` blocks real write/destructive/upgrade policy actions.
- Provider health is not probed by simple registry reads; current provider blockers remain in provider status/report APIs.
- Direct execution remains disabled until a future guarded run lane exists.

## Report Linkage

Reports are linked by exact artifact paths first, then by source/stage fallback.

Issue cards can now expose:

- `source_stage_id`
- `source_stage_label`
- `source_action_id`
- `source_action_label`
- `source_action_link`

This lets Reports point back to the source action without turning report links into blocker headlines.

## Backend API

Added GET-only endpoints:

- `GET /api/v1/workflows/stages`
- `GET /api/v1/workflows/actions`
- `GET /api/v1/workflows/actions/{action_id}`
- `GET /api/v1/workflows/stages/{stage_id}`

No POST run endpoint is added in this pass.

## Future Database Model

The eventual database table should store durable run traces and stage events:

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

The artifact-backed API in this pass is intentionally shaped so it can be backed by that table later without changing the frontend contract.

## Safety Notes

- No secrets are part of registry definitions.
- Credentials are represented only as presence/reference requirements.
- Historical evidence is labeled historical.
- Mock/test state is not used as current real lab state.
- Destructive actions are visible but blocked unless explicit local gates are satisfied.
