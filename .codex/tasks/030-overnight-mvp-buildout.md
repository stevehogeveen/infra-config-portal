# 030 - Overnight MVP Buildout

## Goal

Run an overnight safe/mock buildout toward a Lab Builder-style infrastructure configuration portal.

Use these as references whenever useful:

- `reference/lab-builder-reference.md`
- `artifacts/ui-audit/report.md`
- `artifacts/ui-audit/after-013/report.md`
- existing UI screenshots under `artifacts/ui-audit/`

The direction is:
- staged guarded workflows
- readiness and blockers
- Run Center as the primary operator queue
- plan/review before execute
- artifacts, reports, history, and debug bundle placeholders
- provider status and adapter readiness
- mock-first safety
- real provider probes only when explicit and read-only

## Safety

Keep default behavior mock-first.

Do not perform destructive or persistent real infrastructure actions.

Do not call real:
- vCenter
- ESXi
- HPE iLO destructive actions
- Redfish destructive actions
- NetApp ONTAP changes
- switches config mode
- DNS changes
- IPAM changes
- storage changes
- AWX job launches
- Terraform/OpenTofu apply
- PowerCLI modifying commands
- govc modifying commands
- OVF deploys
- firmware upgrades
- boot order changes
- virtual media mounting
- power reset/off/on
- Cisco `conf t`
- Cisco `write memory`
- Cisco `reload`
- Cisco erase/copy/config commands

Read-only local probes are allowed only where already implemented as explicit opt-in provider probes. They must never run automatically on page load.

Do not commit:
- `.env.local.providers`
- credentials
- real passwords
- secrets
- tokens
- private keys
- real IP inventory dumps
- generated screenshots unless repo policy changes
- ISO/OVF/OVA/VMDK/firmware/media files
- generated debug bundles containing local data

## Work Priorities

Work in small tested slices. After each slice, run checks and commit only when green.

### 1. Stabilize provider status preview

Improve Provider Status for iLO and Cisco:

- show dynamic Cisco candidates clearly
- show selected/effective path clearly
- show missing/multiple candidate blockers
- show iLO configured/missing status without leaking secrets
- show read-only probe buttons only when safe
- show dangerous actions disabled with clear reasons
- improve raw probe result disclosure and redaction
- add optional provider-smoke tests if useful
- never require real hardware for normal tests

### 2. Artifacts and reports skeleton

Add mock artifact/report/history surfaces:

- completed-run report metadata
- artifact listing API/UI
- request history/report links
- redacted debug bundle placeholder
- export/report placeholder
- artifact cards on workflow run detail
- artifact/report links from request detail and Run Center

Do not generate real debug bundles with local secrets.
Do not commit generated artifacts.

### 3. Full VM request list route

Add a real request list page beyond dashboard:

- filters by status
- filters by owner/environment/site if easy
- search by VM name/request ID
- readiness/next-action column
- blocked indicator
- links to request detail
- clear mock-only banner inherited from shell

### 4. Audit event usability

Improve audit UI:

- filter by request ID
- filter by workflow run ID
- filter by event type/status if easy
- links to request/run detail
- expandable payload/details
- better timestamp/status display
- no secret leakage

### 5. Frontend tests

Add focused frontend tests if test tooling exists or can be added lightly:

- global mock-mode banner visible
- Run Center queue sections render
- request detail lifecycle reasons render
- provider status cards render
- audit links/details render

If adding frontend test tooling is too invasive, document the blocker and add smaller testable utilities instead.

### 6. Run Center polish

Improve Run Center as the cockpit:

- actionable queue grouping
- selected item behavior
- plan/review summary
- stage/event timeline
- completed/blocked/failed sections
- handoff links to artifacts/reports/history
- clearer operator next action

### 7. Media inventory polish

Improve media inventory safely:

- mock/sample data clarity
- optional metadata-only local directory scanning
- no media copying
- no mount/deploy/parse behavior
- redacted or placeholder display where appropriate
- warnings when configured media directories are missing/inaccessible

### 8. Provider adapter contracts

Harden provider contract shape:

- common status model
- common probe result model
- common blocker/warning model
- capability flags
- dangerous action metadata disabled by default
- normalized errors
- redaction helper tests

## Screenshot / UI Audit Use

When UI changes are made:

1. Use existing UI audit reports first.
2. If browser tooling is available and app is running, capture updated screenshots.
3. Save screenshots under `artifacts/ui-audit/overnight/`.
4. Create or update `artifacts/ui-audit/overnight/report.md`.
5. Do not commit screenshots unless artifacts are intentionally tracked.

## Quality Gates

After each coherent slice, run:

- `make provider-smoke` if available
- `make smoke`
- `make test`
- `make lint`
- `git diff --check`

Commit only when checks pass.

Use clear commit messages.

## Failure Handling

If checks fail:

1. inspect the failure
2. make the smallest safe fix
3. rerun checks
4. if still failing after repeated attempts, leave changes uncommitted and stop
5. document blocker in `.codex/runs/latest.md`

Do not loop forever on the same failure.
Do not bury failures under more changes.

## Final Summary

At the end, summarize:

- commits made
- files changed
- tests/checks run
- what works now
- what remains mock-only
- what still needs real-infrastructure safety work
- screenshots/reports created
- exact next recommended task
