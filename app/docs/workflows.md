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

When runtime IP values are stale, the Active Lab strip can explicitly run
`POST /api/v1/lab/profiles/active/apply-runtime-env`. That action rewrites only
allowlisted non-secret profile runtime keys in repo-root `.env.local.real-lab`
and updates the current backend process environment so profile mismatch warnings
clear. It does not write credentials, call providers, configure devices, reset
hardware, or replace the required backend restart before live provider checks.

Lab creation includes topology, subnet CIDR, gateway, domain, DNS, NTP, VLAN,
MTU, device addresses, and feature flags. The subnet size selector offers `/29`
through `/23`, but the supported default layouts are:

- `/24` high-address profiles: iLO `.201`, server NIC `.202`, ESXi `.203`,
  Cisco `.204`, Ansible/control `.205`, NetApp SPs `.210/.211`, cluster/node/SVM
  management `.220` through `.223`, NFS LIFs `.230/.231`, and iSCSI LIFs
  `.240` through `.243`.
- `/26` compact edge profiles: gateway `+1`, switch `+2/+3`, reserved `+4`
  through `+6`, UPS `+7`, backup storage `+8`, utility VM `+9`, ESXi `+10`,
  and iLO `+11`.

Compact profiles disable NetApp and vCenter by default. Those stages are
reported as `not_in_scope`, not as blockers. Profile-derived values drive
Dashboard, Lab Setup, Control Center, Firmware Upgrades, Validation & Reports,
NetApp setup/upgrade, vCenter-NetApp readiness, Build Verification, and workflow
registry action defaults. Stale `.env.local.real-lab` values produce exact
remediation guidance with the mismatched field and the active profile value.
See `app/docs/lab-profile-examples.md` for concrete `/24` and `/26` examples.

## Operational Mode

The Settings page opens on an Operational Mode panel so the operator can choose
between `Simulation`, `Local Read-only Lab`, and `Local Lab Read/write`.
`Simulation` is the committed safe default and maps to `PROVIDER_MODE=mock`
internally. The local lab choices write ignored runtime state to
`.local/provider-mode-settings.json` and `.local/app-mode.env`; the app must be
restarted before the selected mode becomes active.

The mode selector does not store secrets, does not call providers, and does not
grant apply permissions by itself. Explicit shell `PROVIDER_MODE=...` values
remain higher priority than `.local/app-mode.env`.

## Control Center

The Control Center main flow is the sidebar app mounted at `/dashboard`,
`/configure`, `/run`, `/firmware`, `/results`, `/logs`, and `/settings`.
Legacy `/control-center` links redirect into that current flow instead of
showing the older action-catalog UI as the primary surface. The visible
operator path is configure target/settings, run one selected backend action,
then review results and logs.

The Control Center uses these backend APIs when available:

1. Save/load current target, IP mode, SNMP version, credential presence,
   timeout, and retry settings with `/api/v1/control-center/config`.
2. Save/load global defaults, API URL, firmware source, and logging verbosity
   with `/api/v1/control-center/settings`.
3. Read backend status, workflow actions, firmware status, and activity logs
   with `/health`, `/api/v1/workflows/actions`,
   `/api/v1/control-center/firmware-status`, and
   `/api/v1/control-center/logs`.
4. Run the selected safe action with
   `POST /api/v1/workflows/actions/{action_id}/run`.
5. Read firmware visibility with `GET /api/v1/firmware/summary` and
   `GET /api/v1/firmware/file-selections`.
6. Check and validate firmware with `GET /api/v1/lab/firmware-inventory`,
   `GET /api/v1/lab/firmware-compliance`, and provider-specific validation
   endpoints such as
   `POST /api/v1/providers/netapp-ontap/ontap-upgrade/validate`.

The Run page saves the current non-secret configuration to backend runtime
state before it requests a workflow action. If the config cannot be validated
or saved to backend state, the action is blocked so the backend cannot use stale
target data.

Firmware Check also syncs current config first. Firmware Validate requires a
firmware path and selected image/version, then saves the file selection before
calling the validation endpoint. Firmware Upgrade is disabled until validation
matches the current config and selected firmware, the validation result passed,
and the operator enters the exact confirmation phrase and checkbox. Failed or
stale validation blocks the upgrade; the guarded backend runner can still
refuse the request if runtime gates are not satisfied.

Firmware upgrade execution is never triggered by page load. The start button
stays disabled until fields are complete, validation passes for the current
selection, backend support is present, and the operator supplies the required
confirmation. Missing backend functionality is surfaced as a safe pending
integration state, not as a fake successful upgrade.

## Workflow Action Registry

The shared workflow/action registry is the canonical read model for hardware
stage and action definitions consumed by Run Center, Control Center, Reports,
and future provider pages.

The registry read API surface is:

1. `GET /api/v1/workflows/stages`
2. `GET /api/v1/workflows/actions`
3. `GET /api/v1/workflows/stages/{stage_id}`
4. `GET /api/v1/workflows/actions/{action_id}`
5. `GET /api/v1/workflows/actions/{action_id}/runs`

The guarded safe-run API is:

1. `POST /api/v1/workflows/actions/{action_id}/run`

The run endpoint is allowlist-only. It refuses any action whose mode is not
`read_only` or `report_only`, any action with required confirmations, and any
registry command or API endpoint that does not exactly match the safe runner
allowlist. Refused actions return a normalized blocked run result for known
actions, or a clear 404 blocker for unknown action IDs.

Runnable results include `started_at`, `finished_at`, `checked_at`, `status`,
`source_type=live_probe`, `freshness=current`, `not_mock=true`, the redacted
stdout/stderr summaries, return code, evidence artifact links, a trace artifact
under `artifacts/codex-runs/workflow-action-runs/`, blockers, warnings, and a
next action. Destructive, write, reset, install, bootstrap, and upgrade actions
remain guarded/copy-only and are not run from this endpoint.

Registry actions include provider, stage, category, mode, source type,
copyable command or API endpoint, required mode, gates, confirmations,
presence-only credential requirements, reports, evidence artifacts, current
availability, UI run support/blockers, run endpoints, blockers, next action,
and an artifact-backed `last_run_trace`.

Registry reads do not run commands, probe providers, call hardware, apply
configuration, reset devices, install ESXi, provision storage, or update
firmware. Existing report artifacts are surfaced as `historical_artifact`
evidence only. A newly saved workflow action run trace overrides older
historical artifact status for that action. Missing traces are `not_checked`.
Mock and test state must not be treated as current real-lab state.

The iLO stage includes `ilo.baseline-preview` as a read-only API action for
`GET /api/v1/providers/hpe-ilo/baseline-preview`. It produces Kit Profile,
Discovery, Connection Readiness, Expected Baseline, Compare / Preview Plan, and
reset-handling data with `apply_enabled=false`; it does not apply settings or
reset hardware.

The first stage order is:

1. `lab-profile`
2. `firmware`
3. `cisco`
4. `ilo`
5. `raid`
6. `esxi`
7. `netapp`
8. `build-verification`
9. `reports`

## Lab Validation / Handoff

The Lab Validation page at `/lab-validation` summarizes setup state across the
lab without turning historical evidence into current truth. It is a handoff
view: each row shows component status, setup summary, login/proof target, next
action, source type, freshness, proof points, collapsed evidence artifacts, and
the linked workflow action.

The API surface is:

1. `GET /api/v1/lab/validation`
2. `GET /api/v1/lab/validation/handoff`
3. `GET /api/v1/lab/vcenter-netapp/readiness`
4. `GET /api/v1/lab/vcenter-netapp/datastore-plan`

The local report targets are:

```bash
make provider-lab-validation
make provider-lab-vcenter-netapp-readiness
make provider-lab-vcenter-netapp-datastore-plan
make provider-lab-vcenter-install-readiness
make provider-lab-vcenter-install-plan
make provider-lab-vcenter-install-preview
make provider-lab-netapp-setup-preview
make provider-lab-netapp-ontap-upgrade-inventory
make provider-lab-netapp-ontap-upgrade-plan
make provider-lab-netapp-ontap-upgrade-validate
```

These targets write redacted reports under `artifacts/codex-runs/`. They do
not run datastore apply, ONTAP writes, ESXi writes, vCenter writes, storage
provisioning, reboot, wipe, or upgrade actions. The vCenter-NetApp readiness
lane classifies datastore work as `blocked_by_prior_stage` while NetApp is
still at `cluster_setup_wizard` or until ONTAP/NFS setup is proven.

The vCenter install lane is report-only. It models the local-only VCSA
deployment values and credential presence needed before any future deploy lane:
appliance name, management IP, subnet, gateway, DNS, NTP, SSO domain/admin,
ESXi target, NetApp datastore target, VCSA ISO path, deployment size, and
network/portgroup. Secret values stay in `.env.local.real-lab` or the operator
environment and reports show only configured/missing status. The preview target
writes redacted plan artifacts and does not start `vcsa-deploy`.

## Hardware Power-Down

The current real-lab power-down sequence is VM shutdown, HPE/ESXi host shutdown
through iLO, then NetApp ONTAP halt followed by NetApp BMC host power-off. Do
not treat ONTAP `LOADER` as full controller power-off. The NetApp BMC must
report `Host Power is off` before the software-controlled NetApp power-down is
complete.

See `app/docs/netapp-powerdown-runbook.md` for the corrected NetApp BMC serial
sequence and the standby fan/LED expectation.

## Golden State

The Golden State page at `/golden-state` productizes the known-good real-lab
path into compact rows for Cisco, iLO, RAID, ESXi, NetApp, NetApp NFS
datastore, VM deployment, vCenter, and firmware.

The API and report target are:

```bash
GET /api/v1/lab/golden-state
make provider-lab-golden-state
```

`make provider-lab-golden-state` writes
`artifacts/codex-runs/golden-state-productization-report.md` and a redacted JSON
summary. It reads existing redacted evidence and configured/missing status only;
it does not run provider writes, vCenter deployment, datastore changes, VM
power actions, firmware apply, RAID apply, or console configuration.

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
