# Workflows

## MVP: Deploy VM From vSphere Template

The MVP workflow accepts a request for a VM deployment and simulates planning
and execution through mocked provider adapters.

### Request Fields

- requester
- environment: `dev`, `test`, `prod`
- site
- cluster
- VM name
- OS/template
- CPU
- memory
- disk size
- network/VLAN
- datastore or storage tier
- owner
- expiry date
- notes

### API Sequence

1. Create draft request with `POST /api/v1/requests/vm-deploy`.
2. Edit it, when allowed, with `PATCH /api/v1/requests/{id}`.
3. Submit it with `POST /api/v1/requests/{id}/submit`.
4. Approve it with `POST /api/v1/requests/{id}/approve`.
5. Create a dry-run plan with `POST /api/v1/requests/{id}/plan`.
6. Execute the mock deployment with `POST /api/v1/requests/{id}/execute`.
7. Review the run with `GET /api/v1/workflow-runs/{id}`.
8. Review history with `GET /api/v1/audit-events`.

Requests that have not started execution can be cancelled with
`POST /api/v1/requests/{id}/cancel`.

### Validation

Validation happens in two places:

- Pydantic schemas enforce shape, size limits, required fields, enumerations,
  future expiry dates, and basic VM name safety.
- The mock source-of-truth adapter checks requested environment, site, cluster,
  template, network, datastore, and storage tier values.

### Planning

Planning returns a dry-run plan with deterministic steps:

- resolve template
- check placement
- select storage
- attach network
- clone VM from template
- apply CPU, memory, and disk sizing
- mark post-deploy checks as simulated

The persisted workflow run also stores a normalized request intent snapshot and
SHA-256 checksum. The intent includes execution-affecting fields such as
environment, site, cluster, VM name, template, CPU, memory, disk, network,
datastore or storage tier, owner, and expiry date. Informational notes are not
part of the execution intent.

### Edits

VM deployment requests can be updated through `PATCH /api/v1/requests/{id}`.
The endpoint is backend-only today and does not call any real or mock provider.

`notes` is the only non-execution-affecting field. Notes can be edited in
`draft`, `submitted`, `validating`, `needs_approval`, `approved`, and
`planned` without changing approval or dry-run plan state. A `request.updated`
audit event records the change.

All other PATCH fields are treated as approval/plan-affecting. In `draft`,
those edits are allowed and the request remains `draft`. In `submitted`,
`validating`, `needs_approval`, `approved`, or `planned`, a real change resets
the request to `draft`, records a `request.updated` audit event, and cancels any
planned workflow run by marking it `cancelled` with invalidation metadata in
the stored plan. Approval rows remain immutable history; the reset to `draft`
prevents execution until the request is submitted, approved, and planned again.

Requests in `executing`, `completed`, `failed`, `cancelled`, or `rejected` are
locked. Edits in locked states return a `409` response and do not change the
request state.

### Execution

Execution first runs a preflight guard before the mock vSphere adapter is
called. The request must still be `planned`, a persisted planned workflow run
must exist, and the dry-run plan payload must include the same `request_id` as
the request being executed. This plan ownership guard blocks execution if a
workflow run is missing, not planned, or attached to a different request.

The execution preflight also recomputes the current request intent checksum and
compares it with the checksum stored when the dry-run plan was created. If an
execution-affecting request field changed outside the formal edit path after
planning, execution is rejected with an audit event, the request remains
`planned`, and the mock execution provider is not called. The formal edit path
handles this intentionally earlier by resetting the request to `draft` and
cancelling planned workflow runs.

After preflight passes, execution uses the mock vSphere adapter. It returns
mock task and VM IDs and does not connect to any infrastructure endpoint.

### Cancellation

Cancellation is allowed for requests in `draft`, `submitted`, `validating`,
`needs_approval`, `approved`, or `planned`. Cancelling a planned request also
marks its planned workflow run as `cancelled`. Requests that are already
`executing`, `completed`, `failed`, or `cancelled` reject cancellation.

### Status Transitions

| Endpoint | Allowed From | Result |
| --- | --- | --- |
| create | none | `draft` |
| edit notes | `draft`, `submitted`, `validating`, `needs_approval`, `approved`, `planned` | current status is preserved |
| edit execution-affecting fields | `draft` | `draft` |
| edit execution-affecting fields | `submitted`, `validating`, `needs_approval`, `approved`, `planned` | `draft`; planned workflow runs are cancelled |
| submit | `draft` | `needs_approval` after `submitted` and `validating` audit events |
| approve | `needs_approval` | `approved` |
| plan | `approved` | `planned` |
| cancel | pre-execution states | `cancelled` |
| execute | `planned` with matching persisted plan | `completed` after `executing` audit event |

Provider execution failures after preflight are recorded as `failed` with an
audit event. Preflight failures are audited without changing the request state.
