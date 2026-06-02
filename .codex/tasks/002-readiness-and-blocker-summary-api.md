# 002 - Readiness and Blocker Summary API

## Goal

Add a backend readiness and blocker summary API for VM deployment requests.

This should move the app toward the Lab Builder-style operator flow:
- show readiness
- show blockers
- explain why actions are blocked
- recommend the next safe action
- keep execution guarded and mock-only

## Context

The backend now supports:
- create VM deployment request
- patch/edit request
- submit
- approve
- plan
- execute
- cancel
- audit events
- execution preflight guard
- request/plan immutability guard
- local mock smoke tests

The Lab Builder reference pattern is:
define intent → validate → plan/preview → review → confirm → execute → monitor/report.

This task adds the backend API needed to show an operator-friendly readiness panel.

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

Do not add credentials, real IPs, hostnames, tokens, passwords, SSH keys, or customer data.

Keep PROVIDER_MODE=mock.

## Required API

Add a request readiness endpoint.

Preferred endpoint:

- GET /api/v1/requests/{id}/readiness

If the current route style suggests another path, preserve the existing style.

## Required Readiness Response

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

Blockers should be structured objects, not just strings.

Suggested blocker fields:

- code
- message
- severity
- action

Examples:

- request_not_draft
- request_not_approved
- plan_missing
- plan_belongs_to_different_request
- request_plan_intent_drift
- request_locked
- already_completed
- cancelled_request
- rejected_request

Warnings should be similar but non-blocking.

## Required Behavior

The readiness endpoint should inspect current persisted state and report:

1. Draft request:
   - ready_for_submit true if required fields are present
   - next_action submit

2. Needs approval:
   - ready_for_approval true
   - next_action approve or reject

3. Approved:
   - ready_for_plan true
   - next_action plan

4. Planned with valid plan:
   - ready_for_execute true
   - next_action execute

5. Planned with missing/tampered/drifted plan:
   - ready_for_execute false
   - blocker explaining the issue
   - next_action replan or edit/resubmit depending current lifecycle behavior

6. Completed:
   - all ready flags false
   - next_action none
   - summary says complete

7. Cancelled/rejected/failed:
   - all ready flags false
   - blocker or summary explains locked terminal state

Do not execute anything from this endpoint.

Do not mutate request state from this endpoint.

## Tests Required

Add or update backend tests for:

1. Draft readiness.
2. Needs approval readiness.
3. Approved readiness.
4. Planned readiness with valid plan.
5. Planned readiness with missing plan.
6. Planned readiness with intent drift.
7. Completed readiness.
8. Cancelled/rejected/failed readiness if those states are available.
9. API response shape.

## Documentation

Update workflow docs and README/app docs if appropriate.

Explain:
- readiness endpoint
- blocker structure
- next_action behavior
- mock-only behavior

## Commands to run

Run:

make backend-smoke
make smoke
make test
make lint

## Acceptance Criteria

- A readiness endpoint exists.
- Readiness response is structured and operator-friendly.
- Blocked execution reasons are visible without attempting execution.
- Endpoint is read-only and does not mutate state.
- Tests cover key lifecycle states.
- Smoke and full tests pass.
- No real provider calls are added.
- Final summary lists files changed, checks run, and next recommended task.
