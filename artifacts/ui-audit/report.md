# UI Screenshot Audit

Date: 2026-06-02

Target app:

- Frontend: http://localhost:5173
- Backend: http://127.0.0.1:8001
- API docs: http://127.0.0.1:8001/docs
- Port 8000: not listening during audit
- Provider mode: mock

Method:

- Read `reference/lab-builder-reference.md` before the audit.
- Inspected frontend routes in `app/frontend/src/App.tsx`.
- Inspected backend API routes in `app/backend/app/api/routes.py` and OpenAPI.
- Seeded local mock-only sample requests through the API to capture draft, planned, and completed lifecycle states.
- Captured screenshots with Firefox/geckodriver.
- No real provider calls were made.

## Screenshots

- `dashboard.png`
- `run-center.png`
- `new-vm-request.png`
- `request-detail-draft.png`
- `request-detail-draft-edit.png`
- `request-detail-planned.png`
- `request-detail-planned-lifecycle.png`
- `request-detail-completed.png`
- `workflow-run-planned.png`
- `workflow-run-completed.png`
- `workflow-run-completed-result.png`
- `audit-events.png`
- `media-inventory.png`
- `provider-status.png`

Support files:

- `runtime-sample-ids.json`
- `screenshot-manifest.json`
- `geckodriver.log`
- `geckodriver-scroll.log`

## Surface Inspected

Frontend routes:

- `/` dashboard and VM request list table
- `/run-center`
- `/requests/new`
- `/requests/:id`
- `/workflow-runs/:id`
- `/audit-events`
- `/media`
- `/providers`

Backend endpoints:

- `GET /health`
- `GET /api/v1/catalog`
- `GET /api/v1/requests`
- `POST /api/v1/requests/vm-deploy`
- `GET/PATCH /api/v1/requests/{request_id}`
- `GET /api/v1/requests/{request_id}/readiness`
- `POST /api/v1/requests/{request_id}/submit`
- `POST /api/v1/requests/{request_id}/approve`
- `POST /api/v1/requests/{request_id}/plan`
- `POST /api/v1/requests/{request_id}/execute`
- `POST /api/v1/requests/{request_id}/cancel`
- `GET /api/v1/workflow-runs`
- `GET /api/v1/workflow-runs/{workflow_run_id}`
- `GET /api/v1/audit-events`
- `GET /api/v1/media-inventory`
- `GET /api/v1/providers/status`

## What Works Well

- The app already has an operator-console shell with persistent navigation for Dashboard, Run Center, requests, audit, media, and provider status.
- The request detail page exposes readiness, blockers, warnings, next action, status progression, lifecycle buttons, approval controls, edit/notes controls, and request-scoped audit events.
- Mock-only provider safety is explicit in provider status and Run Center. Provider messages state that vCenter, ESXi, AWX, Terraform/OpenTofu, Redfish, ONTAP, and switch calls are not made.
- The backend lifecycle is well represented in API shape: create, submit, approve, plan, execute, cancel, readiness, workflow runs, audit events, media inventory, and provider status.
- Media inventory correctly uses sample/redacted placeholder metadata when local media directories are not configured.
- Audit events show clear transition messages and status changes.

## What Is Missing

- There is no dedicated VM request list route. The dashboard contains recent requests, but there is no full list with filters, search, status grouping, ownership, or aging.
- Dashboard does not show readiness, blockers, failed/blocked work, next recommended action, provider safety mode, or Run Center priority.
- Run Center is not yet the central operating surface. It shows runs and a review panel, but it does not provide a focused queue of executable planned work, blocked work, or next operator actions.
- Plan/review is mostly raw JSON on workflow run pages. Operators need a structured dry-run review with summary, target placement, intended changes, stage list, risks, blockers, and confirmation requirements.
- Workflow run detail does not show stage/event logs as first-class UI. Stage events exist in JSON and Run Center cards, but there is no timeline/log viewer, progress indicator, or artifact section.
- Artifact/report/history placeholders are not first-class. Completed runs do not show report links, generated artifact placeholders, export/debug bundle placeholders, or history summaries.
- The new VM request form has no inline readiness preview, field-level validation summary, source-of-truth validation preview, or mock-only safety banner.
- Global audit events do not show request IDs, workflow run IDs, links, or event payload details, making correlation difficult.
- Blocked-state explanations exist in readiness data, but the UI does not consistently explain why disabled lifecycle buttons are disabled.

## What Is Confusing

- Run Center defaults to the latest completed run, but its Execution Review banner still reads `pending` because it uses `plan_json.review_before_execute` even after completion. That makes completed work look like it still needs review.
- Run Center counts one planned run, but `Pending Requests` is empty because planned requests are excluded from the pending request filter. From an operator view, a planned request ready for execute is still actionable work.
- On request detail, disabled buttons do not explain the missing prerequisite. The readiness panel explains the next action, but the button row itself is not self-explanatory.
- The planned request edit section is labeled `Notes`, but it renders the full request form with most fields disabled. This makes it look like the full intent may be editable after planning.
- Workflow run detail uses raw JSON panels for plan/result. It is technically complete, but hard to scan under operational pressure.
- The approval control remains visible in non-approval states. It is disabled, but the reason is not shown near the control.

## Improve First

1. Make Run Center the primary operator queue.
   Show actionable sections for needs approval, approved ready to plan, planned ready to execute, executing, blocked/failed, and completed. Default the review panel to the most urgent actionable item, not the latest run.

2. Replace raw plan/result JSON as the main workflow run UI.
   Keep JSON available behind a details disclosure, but add structured plan summary, stage timeline, review checklist, result summary, and artifact/report placeholders.

3. Add explicit button disable reasons and next-action prompts.
   Each lifecycle action should show why it is available or unavailable and what the operator should do next.

4. Promote readiness and blockers to dashboard/list views.
   The dashboard should show current blockers, stale/failed work, and next recommended actions, not only status counts.

5. Improve audit correlation.
   Add request/run links, IDs, filtering, and expandable event payload data to global and request-scoped audit tables.

## Recommended Next Codex Tasks

1. Refactor Run Center into an operator queue with prioritized actionable sections and correct selected-run behavior.
2. Build a structured Workflow Run Detail page with stage timeline, plan summary, execution result summary, logs/events, and artifact placeholders.
3. Add lifecycle action explanations/tooltips and disabled-state reason text on Request Detail.
4. Add full VM request list route with status/readiness filters, owner/environment/site filters, and next-action column.
5. Add dashboard readiness/blocker summary cards and a Run Center handoff panel.
6. Add artifact/report/history placeholder models and UI sections for planned and completed workflow runs.
7. Add global mock-mode safety banner or shell-level safety status so every page visibly inherits the mock-only posture.
8. Add audit event request/run links, payload expansion, and filtering.
9. Add frontend tests for request detail lifecycle controls, Run Center selection, and provider/mock warning visibility.

## Errors Observed

- Backend port `8000` was not listening. Backend was healthy on `8001`.
- API docs returned `200 OK` on `http://127.0.0.1:8001/docs`.
- No app-level frontend error banners were observed during screenshot capture.
- Firefox/geckodriver logs included browser-internal console noise from Firefox experiments and one shutdown-time `PrivateBrowsingUtils` JavaScript error. These did not appear to be application errors.
- Ruff was skipped by `make lint` because `app/backend/.venv/bin/ruff` is not installed.

## Commands Run

```bash
make smoke
```

Result: passed, `2 passed in 0.14s`.

```bash
make test
```

Result: passed, `52 passed in 1.17s`; frontend `npm run build` passed.

```bash
make lint
```

Result: passed. Shell syntax check and frontend build passed. Ruff was skipped because it is not installed in `app/backend/.venv`.

## Safety Notes

- All sample lifecycle data was created through the local API with mock providers.
- `GET /health` reported `provider_mode: mock`.
- No real vCenter, ESXi, iLO, Redfish, NetApp, switch, DNS, IPAM, AWX, Terraform, OpenTofu, PowerCLI, govc, OVF Tool, firmware tooling, or other infrastructure endpoint was called.
