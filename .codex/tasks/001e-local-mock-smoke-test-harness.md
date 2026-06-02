# 001e - Local Mock Smoke Test Harness

## Goal

Add a local mock smoke test harness for the VM deployment request lifecycle.

This should test the backend API end-to-end using only the local/mock app and mock providers.

## Context

The backend now supports:
- create VM deployment request
- patch/edit request
- submit
- approve
- plan
- execute
- cancel
- execution preflight guard
- request/plan immutability guard
- audit events

We need a repeatable smoke test that proves the MVP lifecycle works outside individual unit tests.

## Safety

Use mock providers only.

Do not call real vCenter, ESXi, iLO, Redfish, NetApp, switches, DNS, IPAM, AWX, Terraform, OpenTofu, NetBox, Nautobot, PowerCLI, govc, OVF Tool, storage, or lab/production infrastructure.

Do not add credentials, real IPs, real hostnames, tokens, passwords, SSH keys, or customer data.

Keep PROVIDER_MODE=mock.

## Required Work

Add a local smoke test script, preferably one of:

- `scripts/smoke-vm-lifecycle.sh`
- or `app/backend/tests/test_smoke_vm_lifecycle.py`
- or both, if lightweight

The smoke test should verify:

1. Backend health endpoint works.
2. A VM deployment request can be created.
3. The request starts in draft.
4. A draft request can be patched.
5. The request can be submitted.
6. The request reaches needs_approval.
7. The request can be approved.
8. The request can be planned.
9. The request can be executed.
10. The request reaches completed.
11. Audit events exist for major transitions.
12. Executing before plan returns 409.
13. Editing execution-affecting fields after planning invalidates or blocks stale execution according to current backend behavior.
14. Canceling a completed request returns 409.

Prefer deterministic API-level tests that do not require a real running external service if the existing test framework can use FastAPI TestClient.

If a shell smoke script is added, document how to run it against a local backend.

## Documentation

Update README or app docs with:

- how to run automated tests
- how to run the smoke test
- what the smoke test covers
- mock-only warning

## Commands to run

Run:

make test
make lint

If a shell smoke script is added, run it if practical.

## Acceptance Criteria

- There is a repeatable smoke test for the mock VM lifecycle.
- The smoke test covers the happy path and key blocked paths.
- The smoke test is included in normal test flow if practical.
- No real provider calls are added.
- Tests pass.
- Final summary lists files changed, checks run, and next recommended task.
