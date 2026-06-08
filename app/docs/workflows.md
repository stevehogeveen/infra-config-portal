# Workflows

## Saved Lab Profile Selection

Lab profile selection mirrors the Lab Builder kit pattern at a smaller scope:
an operator can load the runtime profile, save a named lab address plan, activate
a previous lab, edit a saved profile, and inspect prior profile versions.

The current API surface is:

1. List profiles and the active profile with `GET /api/v1/lab/profiles`.
2. Create and activate a new profile with `POST /api/v1/lab/profiles`.
3. Save a new version with `PUT /api/v1/lab/profiles/{profile_id}`.
4. Activate a saved profile, or return to runtime environment values, with
   `POST /api/v1/lab/profiles/{profile_id}/activate`.

Profiles persist in ignored local runtime state under `.local/lab-profiles.json`
by default. The address plan is intent only. Activating a profile does not probe
devices, does not update provider environment variables, does not rewrite local
env files, and does not enable any real apply lane.

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
3. Check readiness with `GET /api/v1/requests/{id}/readiness`.
4. Submit it with `POST /api/v1/requests/{id}/submit`.
5. Approve it with `POST /api/v1/requests/{id}/approve`, or reject it with
   `POST /api/v1/requests/{id}/reject`.
6. Create a dry-run plan with `POST /api/v1/requests/{id}/plan`.
7. Execute the mock deployment with `POST /api/v1/requests/{id}/execute`.
8. Review local runs with `GET /api/v1/workflow-runs`.
9. Review a run with `GET /api/v1/workflow-runs/{id}`.
10. Review mock artifact/report metadata with
    `GET /api/v1/requests/{id}/artifacts` or
    `GET /api/v1/workflow-runs/{id}/artifacts`.
11. Review history with `GET /api/v1/audit-events`.

Requests that have not started execution can be cancelled with
`POST /api/v1/requests/{id}/cancel`.

### Readiness

`GET /api/v1/requests/{id}/readiness` returns an operator-facing summary of
the persisted request state. It does not mutate request state, create audit
events, execute anything, create a dry-run plan, or call real or mock provider
adapters.

The response includes:

- `request_id`
- `current_status`
- `ready_for_submit`
- `ready_for_approval`
- `ready_for_plan`
- `ready_for_execute`
- `next_action`
- `blockers`
- `warnings`
- `summary`

Each blocker or warning is structured as:

```json
{
  "code": "plan_missing",
  "message": "Request cannot execute because no persisted dry-run plan exists.",
  "severity": "blocking",
  "action": "Create a new dry-run plan before executing."
}
```

`next_action` is a stable machine-friendly recommendation for the UI. Current
values include `submit`, `approve_or_reject`, `plan`, `execute`, `replan`,
`edit_resubmit`, `wait`, `monitor`, `edit`, and `none`.

Readiness mirrors the execution preflight guard for planned requests. Missing
plans, plans attached to another request, tampered plan metadata, and request
intent drift are visible as blockers before an operator attempts execution.
Intent drift means the current execution-affecting request fields no longer
match the dry-run plan checksum. Notes are not part of the execution intent.

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

Plans also include mock stage events for `DISCOVER`, `VALIDATE`, `PLAN`,
`REVIEW`, `EXECUTE`, `COMPLETE`, and `BLOCKED`, plus a
`review_before_execute` marker. These fields are local workflow metadata for
Run Center review and do not call providers.

### Run Center

`GET /api/v1/workflow-runs` returns the latest local workflow runs for the Run
Center. The frontend Run Center combines this with the request list to show
pending requests, planned runs, executing runs, completed runs, selected request
context, stage status, and the mock-only review-before-execute warning.

Run Center is still a skeleton. It does not launch new real execution paths,
stream live logs, or contact external automation systems.

### Artifacts And Reports

Artifact APIs are mock metadata projections only. They derive dry-run plan
metadata, completed-run report metadata, request/run history links, a redacted
debug bundle placeholder, and an export package placeholder from existing
workflow runs and audit events.

The artifact endpoints do not generate files, collect local data, package debug
bundles, copy provider artifacts, or expose a download URL. All returned
records are marked `mock_only`, `redacted`, and `downloadable: false` until a
future task adds a guarded file-generation flow.

### Media Inventory

`GET /api/v1/media-inventory` returns mock/sample media metadata unless
`MEDIA_INVENTORY_DIRS` is explicitly configured. When configured, the scanner
reads only directory entries from those paths and records placeholder name,
extension, size, category, source label, and whether the actual local filename
was redacted.

Media categories are `iso`, `ovf`, `ova`, `vmdk`, `firmware`, and `other`.
The scanner does not copy files, parse media contents, mount ISOs, deploy OVFs
or OVAs, inspect firmware, or expose real local filenames in API responses.
Configured directory paths are returned as redacted labels such as
`configured-directory-1`; missing or unreadable directory warnings use those
labels and do not echo the local path.

## Full Lab Rebuild

The full rebuild workflow is split into separate report-only and real execution
targets:

```bash
make provider-lab-full-rebuild-summary
make provider-lab-full-rebuild
make provider-lab-build-verification
```

`make provider-lab-full-rebuild-summary` only refreshes dashboard/report
summaries from repository state and existing redacted artifacts. It does not
open serial consoles, contact iLO, configure RAID, insert ESXi media, reset
servers, or make network calls to lab devices.

`make provider-lab-full-rebuild` is the real local lab execution path. It runs
with `PROVIDER_MODE=local-lab-readwrite`, loads `.env.local.real-lab`, and calls
the live Cisco console/bootstrap, iLO reachability/inventory, HPE RAID, and
ESXi media/boot workflow stages. It does not block merely because the caller is
Codex or `codex exec`; it records real physical/configuration blockers in the
stage reports under `artifacts/codex-runs/`.

`make provider-lab-build-verification` writes
`artifacts/codex-runs/build-verification-report.md` and a redacted JSON summary.
It checks credential compatibility and escaping, MTU consistency, protocol and
port readiness, post-build checklist status, failure classification, and exact
next actions.
The report uses staged classifications: `passed`, `hard_fail`,
`blocked_by_prior_stage`, `not_configured_yet`, `stale_config`,
`operator_action_required`, and `warning`. Cisco SSH/SCP before confirmed
console bootstrap, ESXi API/SSH before install/config, and unconfigured NetApp
readiness are staged instead of reported as generic port failures. Additional
artifacts are written to
`artifacts/codex-runs/build-verification-classification-report.md`,
`artifacts/codex-runs/lab-ip-profile-hardening-report.md`, and
`artifacts/codex-runs/failure-case-hardening-report.md`.

The Provider Status page reads `GET /api/v1/lab/full-rebuild-summary` and
`GET /api/v1/lab/build-verification` to show real execution state, report-only
summary state, Cisco, iLO, RAID, ESXi, and product certification status.

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
`executing`, `completed`, `failed`, `cancelled`, or `rejected` reject
cancellation.

### Status Transitions

| Endpoint | Allowed From | Result |
| --- | --- | --- |
| create | none | `draft` |
| edit notes | `draft`, `submitted`, `validating`, `needs_approval`, `approved`, `planned` | current status is preserved |
| edit execution-affecting fields | `draft` | `draft` |
| edit execution-affecting fields | `submitted`, `validating`, `needs_approval`, `approved`, `planned` | `draft`; planned workflow runs are cancelled |
| submit | `draft` | `needs_approval` after `submitted` and `validating` audit events |
| approve | `needs_approval` | `approved` |
| reject | `needs_approval` | `rejected` |
| plan | `approved` | `planned` |
| cancel | pre-execution states | `cancelled` |
| execute | `planned` with matching persisted plan | `completed` after `executing` audit event |

Provider execution failures after preflight are recorded as `failed` with an
audit event. Preflight failures are audited without changing the request state.
