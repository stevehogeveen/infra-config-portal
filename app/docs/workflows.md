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

### Execution

Execution uses the mock vSphere adapter. It returns mock task and VM IDs and
does not connect to any infrastructure endpoint.

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
| execute | `planned` | `completed` after `executing` audit event |

Failures are recorded as `failed` with an audit event.
