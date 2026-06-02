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
2. Submit it with `POST /api/v1/requests/{id}/submit`.
3. Approve it with `POST /api/v1/requests/{id}/approve`.
4. Create a dry-run plan with `POST /api/v1/requests/{id}/plan`.
5. Execute the mock deployment with `POST /api/v1/requests/{id}/execute`.
6. Review the run with `GET /api/v1/workflow-runs/{id}`.
7. Review history with `GET /api/v1/audit-events`.

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

### Execution

Execution first runs a preflight guard before the mock vSphere adapter is
called. The request must still be `planned`, a persisted planned workflow run
must exist, and the dry-run plan payload must include the same `request_id` as
the request being executed. This plan ownership guard blocks execution if a
workflow run is missing, not planned, or attached to a different request.

The execution preflight also recomputes the current request intent checksum and
compares it with the checksum stored when the dry-run plan was created. If an
execution-affecting request field changed after planning, execution is rejected
with an audit event, the request remains `planned`, and the mock execution
provider is not called. A new dry-run plan must be generated from the updated
intent before execution can proceed.

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
| submit | `draft` | `needs_approval` after `submitted` and `validating` audit events |
| approve | `needs_approval` | `approved` |
| plan | `approved` | `planned` |
| cancel | pre-execution states | `cancelled` |
| execute | `planned` with matching persisted plan | `completed` after `executing` audit event |

Provider execution failures after preflight are recorded as `failed` with an
audit event. Preflight failures are audited without changing the request state.
