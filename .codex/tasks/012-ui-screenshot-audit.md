# 012 - UI Screenshot Audit

## Goal

Use Codex to inspect the running local app, take screenshots, and produce a UI/UX gap report.

The app should follow the Lab Builder direction:
- operator-focused workflow
- readiness and blockers visible
- Run Center central
- plan/review before execute
- artifacts/reports/history visible
- mock-only provider safety
- clear next actions

## Running App

Assume the app is already running with:

- Frontend: http://localhost:5173
- Backend: http://127.0.0.1:8000
- API docs: http://127.0.0.1:8000/docs

If port 8000 fails, also try 8001.

## Safety

Do not call real infrastructure.

Do not call real:
- vCenter
- ESXi
- iLO
- Redfish
- NetApp
- switches
- DNS
- IPAM
- AWX
- Terraform
- OpenTofu
- PowerCLI
- govc
- OVF Tool
- firmware tools

Do not copy or expose real secrets, IPs, hostnames, ISOs, OVFs, firmware, or customer data.

Keep PROVIDER_MODE=mock.

## Required Work

1. Inspect frontend routes and backend endpoints.
2. Use available browser/screenshot tooling to capture the running UI.
3. Save screenshots under:
   - artifacts/ui-audit/
4. Create:
   - artifacts/ui-audit/report.md
5. Do not commit screenshots unless artifacts are intentionally tracked. Prefer leaving screenshots local.
6. Do commit useful source/docs/test changes only if you make any.

## Pages / Areas To Review

Check whether the UI clearly exposes:

- Dashboard / landing page
- VM request list
- New VM request form
- Request detail page
- readiness and blockers
- lifecycle buttons:
  - edit
  - submit
  - approve
  - plan
  - execute
  - cancel
- audit events
- Run Center
- workflow run detail
- stage/event logs
- media inventory
- provider status
- artifact/report/history placeholders
- mock-only warning
- blocked-state explanations
- next recommended action

## Report Requirements

In `artifacts/ui-audit/report.md`, include:

1. Screenshot filenames.
2. What works well.
3. What is missing.
4. What is confusing.
5. What should be improved first.
6. Recommended next Codex tasks in priority order.
7. Any frontend/backend errors observed.

## Commands To Run

Run:

make smoke
make test
make lint

## Acceptance Criteria

- Screenshots are captured if tooling is available.
- A useful UI audit report exists.
- The report identifies gaps versus the Lab Builder-style target.
- No real provider calls are made.
- Tests still pass if source changes are made.
