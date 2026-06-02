# 010 - Big MVP Push Toward Lab Builder Track

## Goal

Make a large safe push toward a usable mock/local MVP before the stop time.

Use `/home/administrator/lab-builder` as a product/workflow reference, not as source code to blindly port.

## Stop Condition

Work in small, testable chunks.

Stop when:
- local time is at or after 5:00 PM.
- no safe progress can be made after repeated failures.
- a task would require real infrastructure/provider execution.

## Reference Source

You may inspect:
- `/home/administrator/lab-builder`
- `/home/administrator/infra-config-portal/reference/lab-builder-reference.md`

Use Lab Builder as reference for:
- staged guarded workflows
- readiness and blocker panels
- Run Center shape
- execution review
- logs and stage events
- reports, history, and artifacts
- module boundaries
- media inventory patterns

Do not copy:
- real credentials
- real hostnames
- real IP addresses
- secrets
- customer data
- generated artifacts
- local media files
- ISO, OVF, OVA, VMDK, or firmware binary contents

If inspecting media directories, only record safe metadata such as extension, category, placeholder name, size, and mock inventory behavior.

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

Do not install firmware.
Do not mount ISOs.
Do not deploy OVFs.
Do not run upgrade commands.
Do not copy large binaries into the repo.

## Preferred Work Order

Work through these in order, stopping after each coherent tested slice.

### 1. Commit/verify current smoke target state

Ensure these exist and pass:
- `make smoke`
- `make backend-smoke`
- `make test`
- `make lint`

If smoke targets are missing, add them.

### 2. Readiness and Blocker Summary API

Add:
- `GET /api/v1/requests/{id}/readiness`

The response should include:
- request_id
- current_status
- ready_for_submit
- ready_for_approval
- ready_for_plan
- ready_for_execute
- next_action
- blockers
- warnings
- summary

Keep it read-only. Do not mutate state.

### 3. Frontend lifecycle wiring

Add or improve frontend screens so an operator can:
- create VM request
- view request detail
- patch/edit draft or notes
- submit
- approve
- plan
- execute
- cancel
- see status
- see readiness/blockers if backend exists
- see audit events if already available

Keep UX simple but operator-focused.

### 4. Run Center skeleton

Add a basic Run Center page or backend model if practical.

It should show:
- pending, planned, executing, and completed workflow runs
- selected request
- stage/status summary
- mock-only warning
- review-before-execute concept

Do not add real execution.

### 5. Stage/Event log skeleton

Add structured stage/event concepts if practical:
- DISCOVER
- VALIDATE
- PLAN
- REVIEW
- EXECUTE
- COMPLETE
- BLOCKED

This can be mock-only and stored as audit/workflow events.

### 6. Media inventory skeleton

Using Lab Builder only as a reference, add a mock/local media inventory concept if practical.

It may scan configured safe directories only for metadata:
- file name
- extension
- size
- category: iso, ovf, ova, vmdk, firmware, other

Do not copy files.
Do not parse secrets.
Do not mount, run, or deploy media.
Do not commit generated media inventory from the local machine unless it is mock/sample data.

### 7. Provider adapter contracts

If time remains, strengthen provider boundaries:
- base protocols/interfaces
- mock provider registry
- provider status endpoint
- clear errors
- no real adapters yet

## Quality Gates

After each coherent slice, run:
- `make smoke`
- `make test`
- `make lint`

If frontend changed, ensure the frontend build passes.

Commit only if checks pass.

Use clear commit messages.

## Failure Handling

If a task fails:
1. Inspect the failure.
2. Make the smallest safe fix.
3. Rerun checks.
4. If still failing after repeated attempts, document the blocker in `.codex/runs/`.
5. Move to the next safe smaller task if possible.

Do not loop forever on the same failure.

## Final Summary

At the end, write a final summary including:
- commits made
- files changed
- tests/checks run
- what works now
- what is still mock-only
- what still needs to be done before real infrastructure
- exact next recommended task
