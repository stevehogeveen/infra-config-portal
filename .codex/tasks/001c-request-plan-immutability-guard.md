# 001c - Request/Plan Immutability Guard

## Goal

Add a request/plan immutability guard so the approved VM request intent cannot drift from the persisted dry-run plan before execution.

Keep this backend-only and mock-only.

## Context

Previous backend lifecycle tasks added:
- cancellable VM requests
- execution preflight guard
- persisted plan ownership checks before mock execution

Next we need to make sure the request details used to generate the plan still match the request details at execution time.

This prevents a user or future API path from approving one request, generating a plan, then changing request fields before execution.

## Safety

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

Do not add credentials, real IPs, real hostnames, tokens, passwords, SSH keys, or customer data.

Keep PROVIDER_MODE=mock.

## Required behavior

When a plan is generated:

1. Capture the request intent used for the plan.
2. Store enough request fields in the persisted plan to compare later.
3. Prefer a deterministic hash/checksum of normalized request intent if the current model supports it cleanly.
4. The stored intent should include fields that affect execution, such as:
   - environment
   - site
   - cluster
   - VM name
   - template or OS image
   - CPU
   - memory
   - disk
   - network/VLAN
   - datastore or storage tier
   - owner
   - expiry date if it affects policy
5. Ignore purely informational fields if appropriate, such as notes, unless the current model treats them as execution-affecting.

Before execution starts:

1. Run the existing execution preflight checks.
2. Verify the current request intent still matches the persisted plan intent.
3. If the request and plan do not match:
   - do not call the mock execution provider
   - do not move the request to executing
   - return a clear API error
   - write an audit event if practical

## Tests required

Add or update backend tests for:

1. Plan stores request intent or intent hash.
2. Execution succeeds when request intent matches the persisted plan.
3. Execution fails when an execution-affecting field changes after planning.
4. Execution failure does not call the mock execution provider when intent mismatch is detected.
5. Execution failure does not move the request to executing.
6. Intent mismatch writes an audit event if practical.
7. Non-execution-affecting fields, if any are intentionally ignored, do not break execution.

## Documentation

Update workflow docs briefly to explain:
- plan ownership guard
- plan/request intent immutability guard
- mock-only behavior

## Commands to run

Run:

make test
make lint

## Acceptance criteria

- Persisted plans include enough request intent information to detect drift.
- Execution is blocked if the request changed after planning.
- Mock execution is not called when drift is detected.
- Tests cover matching and mismatched intent.
- No real provider calls are added.
- Final summary lists files changed, checks run, and next recommended task.
