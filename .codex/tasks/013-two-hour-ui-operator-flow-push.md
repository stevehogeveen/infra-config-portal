# 013 - Two Hour UI Operator Flow Push

## Goal

Spend up to two hours improving the mock/local MVP toward the Lab Builder-style operator flow.

Use the UI screenshot audit whenever useful:

- `artifacts/ui-audit/report.md`
- screenshots under `artifacts/ui-audit/`

Also use:

- `reference/lab-builder-reference.md`

Do not guess blindly. If working on UI, inspect existing screenshots/report first and take updated screenshots when useful.

## Stop Condition

Work in small, testable slices.

Stop when:
- the two-hour run script stops,
- no safe progress can be made,
- checks fail and cannot be fixed safely,
- a task would require real infrastructure/provider execution.

## Safety

Keep `PROVIDER_MODE=mock`.

Do not call real:

- vCenter
- ESXi
- HPE iLO
- Redfish
- NetApp ONTAP
- switches
- DNS
- IPAM
- storage arrays
- AWX
- Terraform
- OpenTofu
- NetBox
- Nautobot
- PowerCLI
- govc
- OVF Tool
- firmware tools
- upgrade tools
- physical lab hardware
- production or lab infrastructure endpoints

Do not copy real credentials, IPs, hostnames, secrets, media files, firmware, ISOs, OVFs, VMDKs, or generated lab-builder artifacts into this repo.

## Priority Work

Follow this order unless inspection shows a safer/better nearby improvement.

### 1. Run Center operator queue

Refactor Run Center toward an operator queue.

It should show actionable sections:

- needs approval
- approved ready to plan
- planned ready to execute
- executing
- blocked/failed
- completed

Improve selected-run behavior:
- default to the most urgent actionable item
- do not show a completed run as pending review
- planned ready-to-execute work should appear as actionable

### 2. Workflow Run Detail structured view

Replace raw JSON as the main experience.

Keep JSON behind a disclosure/details area, but add:

- plan summary
- stage timeline
- execution result summary
- logs/events
- artifact/report placeholders
- mock-only safety note

### 3. Request Detail action explanations

Add clear disabled-state reasons near lifecycle buttons:

- why submit is disabled
- why approve is disabled
- why plan is disabled
- why execute is disabled
- why cancel is disabled

Use readiness/blocker data where possible.

### 4. Dashboard readiness/blocker cards

Promote readiness to dashboard/list views:

- blocked requests
- next recommended actions
- ready-to-approve
- ready-to-plan
- ready-to-execute
- failed/blocked work
- Run Center handoff

### 5. Global mock-mode safety banner

Add a shell-level visible mock-only banner/status so every page inherits the safety posture.

It should make clear:
- provider mode is mock
- no real infrastructure calls are made
- real adapters require explicit future configuration

### 6. Audit event correlation

Improve audit UI if time remains:

- request links
- workflow run links
- request/run IDs
- filtering or grouped display
- expandable payload/details if present

## Screenshot Use

When UI changes are made:

1. Use existing screenshots/report as baseline.
2. Start or use the local app if available.
3. Capture updated screenshots if browser tooling is available.
4. Save updated screenshots under:
   - `artifacts/ui-audit/after-013/`
5. Update or create:
   - `artifacts/ui-audit/after-013/report.md`

Do not commit generated screenshots unless the repo intentionally tracks artifacts. Prefer leaving artifacts local unless existing policy says otherwise.

## Quality Gates

After each coherent slice, run:

- `make smoke`
- `make test`
- `make lint`

If frontend changed, ensure the frontend build passes.

Commit only when checks pass.

Use clear commit messages.

## Final Summary

At the end, summarize:

- commits made
- files changed
- screenshots/report generated if any
- tests/checks run
- what improved in the UI
- what still needs to be done
- exact next recommended task
