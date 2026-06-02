# 001d - Controlled Request Edit Path

## Goal

Add a formal backend request edit/update path for VM deployment requests.

The edit path must validate allowed lifecycle states and either:
- allow safe edits,
- reset/invalidate approval and plan state when execution-affecting fields change,
- or block edits when the request is locked.

Keep this backend-only and mock-only.

## Context

Previous backend lifecycle tasks added:
- cancellation support
- execution preflight guard
- request/plan immutability guard

The current app can detect request/plan drift at execution time, but it should also have a formal edit path so drift is handled intentionally instead of accidentally.

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

## Required Behavior

Add an API path for updating a VM deployment request.

Preferred endpoint:

- `PATCH /api/v1/requests/{id}`

If the current route structure suggests a different path, preserve the existing style.

## Edit Rules

### Editable states

Allow edits in:

- `draft`

For `draft`:
- execution-affecting fields may be edited
- non-execution-affecting fields may be edited
- request remains `draft`
- write an audit event

### Submitted / needs_approval / approved / planned states

For execution-affecting edits in:

- `submitted`
- `validating`
- `needs_approval`
- `approved`
- `planned`

Choose the cleanest behavior for the existing codebase:

Preferred behavior:
- allow the edit
- reset request state to `draft`
- invalidate any approval/workflow plan if present
- mark related planned workflow run as cancelled or invalidated if that state exists
- write an audit event explaining that approval/plan were invalidated by the edit

If that is too invasive, block execution-affecting edits in these states with a clear 409 API error.

Document whichever approach is implemented.

### Non-execution-affecting edits

For non-execution-affecting fields like `notes`, if such fields exist:
- allow notes-style edits in `draft`, `submitted`, `needs_approval`, `approved`, and `planned`
- do not invalidate approval or plan
- write an audit event

If the model does not clearly separate notes from execution-affecting fields, keep the implementation simple and document the choice.

### Locked states

Block edits in:

- `executing`
- `completed`
- `failed`
- `cancelled`
- `rejected`

Return a clear API error, preferably 409.

Do not change the request state.

## Execution-Affecting Fields

Treat these as execution-affecting if present in the current model:

- environment
- site
- cluster
- VM name
- template or OS image
- CPU
- memory
- disk
- network/VLAN
- datastore
- storage tier
- owner
- expiry date if policy-affecting

Notes should be treated as non-execution-affecting if the current model supports that cleanly.

## Plan / Approval Invalidation

When an execution-affecting edit is allowed after submission or planning:

- clear or invalidate persisted plan intent/hash if the model supports it
- mark planned workflow run as cancelled/invalidated if cleanly supported
- prevent execution until the request is resubmitted, approved, and planned again
- write an audit event

Do not overbuild a full versioning system.

## Tests Required

Add or update backend tests for:

1. Draft request can be edited.
2. Draft execution-affecting edit remains draft.
3. Notes/non-execution-affecting edit does not invalidate plan where allowed.
4. Execution-affecting edit in `needs_approval`, `approved`, or `planned` either:
   - resets to draft and invalidates approval/plan, or
   - is blocked with 409.
5. Planned request execution-affecting edit cannot leave a valid executable stale plan behind.
6. Locked states block edits:
   - executing
   - completed
   - failed
   - cancelled
   - rejected
7. Edit writes audit events.
8. API endpoint returns clear success/error responses.

Keep tests deterministic and fast.

## Documentation

Update workflow docs briefly to explain:

- when requests can be edited
- what happens to approval/plan when execution-affecting fields change
- which states are locked
- mock-only behavior

## Commands to run

Run:

make test
make lint

## Acceptance Criteria

- There is a formal request edit/update API path.
- Edits are state-aware.
- Execution-affecting edits cannot silently drift from approved/planned intent.
- Locked states reject edits.
- Tests cover allowed and blocked edits.
- Audit events are recorded for edits and invalidations where practical.
- No real provider calls are added.
- Final summary lists files changed, checks run, and next recommended task.
