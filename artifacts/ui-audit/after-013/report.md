# UI After-Audit 013

Date: 2026-06-02

Target app:

- Frontend: http://127.0.0.1:5173
- Backend: http://127.0.0.1:8001
- Provider mode: mock

Method:

- Read `reference/lab-builder-reference.md` and `artifacts/ui-audit/report.md` before changes.
- Reused the local mock-only sample data from the previous UI audit.
- Verified `/health` reported `provider_mode: mock`.
- Captured screenshots with Playwright Chromium after Firefox headless screenshot mode hung on temporary profiles.
- No real infrastructure/provider endpoints were called.

## Screenshots

- `dashboard.png`
- `run-center.png`
- `request-detail-planned.png`
- `workflow-run-planned.png`
- `workflow-run-completed.png`
- `audit-events.png`

## What Improved

- Dashboard now shows readiness-oriented cards for ready-to-approve, ready-to-plan, ready-to-execute, and blocked/failed work.
- Dashboard includes a next recommended actions panel and Run Center handoff.
- Run Center is now organized as an operator queue: needs approval, approved ready to plan, planned ready to execute, executing, blocked/failed, and completed.
- Run Center defaults to the planned ready-to-execute item instead of the latest completed run.
- Completed runs show a completed review message instead of reusing the pending pre-execution review text.
- Workflow run detail now shows structured plan summary, stage timeline, execution result summary, audit/log events, artifact/report placeholders, and raw JSON behind disclosures.
- Request detail lifecycle buttons now include nearby enabled/disabled explanations for submit, approve, plan, execute, and cancel.
- Every page inherits a visible mock-mode safety banner.
- Audit event tables now show request/run links and expandable payload details.

## Checks Run

```bash
npm run build
make smoke
make test
make lint
```

Results:

- Frontend build passed.
- `make smoke` passed: `2 passed`.
- `make test` passed: `52 passed`; frontend build passed.
- `make lint` passed. Backend Ruff was skipped because `app/backend/.venv/bin/ruff` is not installed.

## Notes

- Screenshots are local generated artifacts and are not intended to be committed unless repo policy changes.
- Playwright Chromium was installed into the local user cache for screenshot capture.
- Providers remain mocked by default; no real vCenter, ESXi, iLO, Redfish, NetApp, switch, DNS, IPAM, AWX, Terraform, OpenTofu, or storage calls were made.
