# 001b - Execution Preflight Plan Guard

## Goal

Add an execution preflight check so a VM deployment request can only execute if its persisted dry-run plan still belongs to the same approved/planned request.

Keep this backend-only and mock-only.

## Context

The previous lifecycle task added cancel support.

Codex recommended this next task:
Add an execution preflight check that verifies the persisted dry-run plan still belongs to the approved request before mock execution starts.

## Safety

Do not call real vCenter, ESXi, iLO, Redfish, NetApp, switches, DNS, IPAM, AWX, Terraform, OpenTofu, NetBox, Nautobot, PowerCLI, govc, OVF Tool, storage, or production/lab infrastructure.

Do not add credentials, real IPs, hostnames, tokens, passwords, SSH keys, or customer data.

Keep PROVIDER_MODE=mock.

## Required behavior

Before execution starts:

1. Verify the request is in planned state.
2. Verify a persisted workflow run or plan exists for the request.
3. Verify the plan belongs to the same request ID being executed.
4. If the check fails:
   - do not call the mock execution provider
   - do not move the request to executing
   - return a clear API error
   - write an audit event if practical

## Tests required

Add or update backend tests for:

1. Execution succeeds when the plan belongs to the request.
2. Execution fails when no plan exists.
3. Execution fails when the plan/workflow run belongs to another request.
4. Failed preflight does not call mock execution.
5. Failed preflight does not move the request to executing.
6. Failed preflight writes an audit event if practical.

## Documentation

Update workflow docs briefly.

## Commands to run

Run:

make test
make lint

## Acceptance criteria

- Execution requires a valid persisted plan for the same request.
- Mismatched or missing plans are blocked.
- Mock execution is not called when preflight fails.
- Tests cover success and failure paths.
- No real provider calls are added.
- Final summary lists files changed, checks run, and next recommended task.
