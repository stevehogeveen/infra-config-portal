# Next Workflow Roadmap

This roadmap defines the next safe workflow slices after the VM deployment MVP.
It is intentionally docs-only: no new workflow code, provider calls, real
credentials, hostnames, or lab addresses are introduced here.

The current MVP already proves the core lifecycle:

1. Capture structured intent.
2. Validate against schema and source-of-truth rules.
3. Require approval.
4. Persist a dry-run plan.
5. Execute through a mock adapter.
6. Record audit events and artifacts.
7. Block execution if the persisted plan no longer matches request intent.

Every future workflow below must keep that lifecycle. Real provider execution
stays disabled until a separate implementation task adds explicit adapter
contracts, tests, provider-mode gates, approval points, redaction, and audit
coverage.

## Product Scenarios

The next workflows should serve two deployment archetypes without letting an
operator confuse them:

| Archetype | Included systems | Storage intent | Primary risk |
| --- | --- | --- | --- |
| Single server - local RAID | Server, iLO, ESXi, optional local VM/template media | Local disks and RAID on the server | Destructive disk/RAID or reinstall actions |
| Server + NetApp + vCenter | Server, iLO, Cisco switch, NetApp ONTAP, ESXi, vCenter | Shared NFS or iSCSI datastore | Cross-device sequencing and stale readiness evidence |

Existing schema homes already support this split:

- `LabProfileFeatures.deployment_mode`
- `LabProfileFeatures.storage_location`
- `LabProfileFeatures.storage_protocol`
- `LabProfileDevices.server_model`
- `LabAddressPlan` device, management, NFS, and iSCSI fields

No UI or workflow should expose a saveable parameter unless it round-trips
through a real schema field or is clearly labeled as display-only.

## Dependency Order

### 1. Lab Profile And Inventory Planning

Purpose: make the selected system, subnet-derived address plan, deployment
archetype, server model, and device inventory the stable source of truth for
every later workflow.

Safe mock scope:

- Create, edit, activate, and version lab profiles.
- Resolve derived addresses from a selected subnet and topology.
- Show device inventory as planned or unknown.
- Detect invalid or stale profile state without probing hardware.

Provider adapter boundary:

- No provider adapter calls.
- Future source-of-truth adapters may validate profile names, sites, VLANs,
  templates, and storage tiers, but must remain read-only.

Validation needs:

- CIDR and address shape validation.
- Deployment archetype validation.
- Required device fields by archetype.
- Secret-shaped text rejection.
- Round-trip tests for `server_model`, storage protocol, and address overrides.

Approval points:

- No approval needed for local profile saves.
- Applying profile values into runtime environment files remains an explicit
  non-secret, allowlisted action.

Test expectations:

- Backend schema and profile service tests.
- Frontend component tests for archetype switching and derived addresses.
- E2E test proving create, edit, activate, reload, and stale profile warnings.

### 2. Provider Readiness Evidence Workflow

Purpose: provide one honest read model for current evidence, cached evidence,
historical artifacts, and unknown state across iLO, Cisco, ESXi, NetApp, and
vCenter.

Safe mock scope:

- Aggregate existing read-only registry actions and artifact metadata.
- Mark missing probes as `not_checked` or `unknown`.
- Show credential presence as configured, missing, or unverified without
  showing secret values.
- Generate a consolidated readiness packet for Run Center and handoff.

Provider adapter boundary:

- Mock mode reads local mock adapters only.
- Local read-only mode may call only existing GET-only or show-only probes.
- No write, reset, install, datastore, power, firmware, or console config path.

Validation needs:

- Evidence freshness and source classification.
- Redaction of endpoints, users, tokens, cookies, headers, and raw device
  output.
- Credential status must be presence/validation metadata only.

Approval points:

- No approval for read-only evidence refresh.
- Future transition from read-only evidence to apply planning requires a new
  workflow approval gate.

Test expectations:

- Backend tests for unknown defaults and evidence freshness.
- Regression tests proving historical artifacts never render as current live
  proof.
- E2E tests for read-only action grouping and no destructive controls.

### 3. Network Intent Planning

Purpose: model switch management, VLANs, gateways, trunk/access roles, BPDU
guard, ACL intent, blackhole VLANs, and port-to-device cabling before any Cisco
configuration path exists.

Safe mock scope:

- Save switch and port intent as structured local state.
- Produce a mock plan with exact intended changes and blockers.
- Show cabling and per-port planned state in the topology/device workspace.
- Compare planned values to cached read-only show-command evidence when
  available.

Provider adapter boundary:

- Cisco console and Ansible adapters remain read-only for this workflow.
- Future write adapter must expose `plan_network_intent()` before any apply
  method exists.
- Arbitrary commands, `conf t`, `write memory`, reload, erase, copy, and raw
  Ansible variables remain forbidden.

Validation needs:

- VLAN ID range and uniqueness.
- Port role compatibility.
- Gateway/subnet consistency.
- ACL and blackhole intent allowlists.
- Target identity check before any future apply lane.

Approval points:

- Approval is required before generating an apply-capable plan.
- A separate exact confirmation is required before any future switch write.

Test expectations:

- Schema tests for VLANs, ports, and ACL intent.
- Plan contract tests that reject secret-like or command-like keys.
- E2E tests for editing port intent without exposing write buttons.

### 4. Server And Local RAID Planning

Purpose: support the single-server archetype with server model, bay inventory,
RAID controller intent, boot/data logical drives, ESXi install readiness, and
local datastore planning.

Safe mock scope:

- Save RAID and drive-bay intent.
- Generate mock RAID and ESXi install previews.
- Display discovered or unknown drive state honestly.
- Explain local-storage blockers before any destructive path appears.

Provider adapter boundary:

- iLO/Redfish remains GET-only unless a future allowlisted lane is approved.
- RAID apply, delete, reset, factory reset, wipe, and rebuild stay outside this
  workflow until a dedicated destructive workflow is implemented.
- ESXi install/media steps remain preview-only here.

Validation needs:

- Server model and drive count compatibility.
- RAID level support by controller and available drives.
- Boot volume and data volume sizing rules.
- Confirmation that local mode excludes NetApp and vCenter dependencies.

Approval points:

- No approval for preview.
- Destructive RAID or reinstall work requires a separate workflow, explicit
  destructive acknowledgement, and exact confirmation phrase.

Test expectations:

- Round-trip tests for `server_model` and RAID intent.
- Plan tests proving destructive actions are absent from preview.
- E2E tests for local mode showing server storage as the hero and NetApp/vCenter
  as out of scope.

### 5. NetApp Storage Intent Planning

Purpose: model NetApp setup choices for shared NFS and iSCSI storage without
creating clusters, SVMs, LIFs, volumes, igroups, LUNs, or datastore mounts.

Safe mock scope:

- Save storage protocol selection and planned NetApp addresses.
- Generate NFS and iSCSI setup previews.
- Show exact intended changes, blockers, required evidence, and exportable
  report metadata.
- Keep NFS and iSCSI selectable without applying either protocol.

Provider adapter boundary:

- ONTAP adapter remains setup/status preview or explicit read-only validation.
- Future write methods must be protocol-specific and guarded.
- No cluster create, IP change, SVM create, LIF create, volume create, LUN map,
  controller reboot, disk wipe, or upgrade in this workflow.

Validation needs:

- Protocol-specific required fields.
- LIF count and address shape.
- MTU and VLAN consistency with network intent.
- ESXi datastore dependency readiness.
- Storage profile consistency between NetApp workspace and system setup.

Approval points:

- Approval before any protocol apply plan becomes executable.
- Exact protocol-specific confirmation before any future write lane.

Test expectations:

- Backend preview tests for NFS and iSCSI blockers.
- Tests proving apply flags remain blocked by default.
- E2E tests for protocol switching, grouped read-only checks, and guarded apply
  separation.

### 6. ESXi Host Preparation And Datastore Attach Planning

Purpose: prepare ESXi management readiness, target identity, datastore attach
preview, and post-config validation for both local and shared-storage modes.

Safe mock scope:

- Preview ESXi management requirements.
- Preview local datastore or NetApp datastore attach steps.
- Validate required media/template metadata without mounting or deploying.
- Produce a post-config checklist and handoff packet.

Provider adapter boundary:

- ESXi adapter may perform HTTPS/TCP/read-only checks only in local-readonly
  mode.
- Future write adapter must separate host networking, datastore attach, and VM
  import operations behind different allowlisted workflow steps.
- No reinstall, reboot, VM deploy, datastore create/remove, firewall, or power
  operations in this planning workflow.

Validation needs:

- Target identity and management reachability classification.
- Storage mode consistency.
- Datastore name uniqueness in mock/source-of-truth data.
- Media inventory availability without exposing local filenames.

Approval points:

- Approval before any datastore attach or host configuration plan can execute.
- Separate confirmation for install/reinstall or power-affecting work.

Test expectations:

- Backend tests for local versus NetApp datastore plans.
- Contract tests that block stale target identity.
- E2E tests for storage path visualization and read-only validation controls.

### 7. vCenter And VM Template Handoff

Purpose: extend the VM deployment MVP into a richer vCenter/template workflow
after host and storage readiness are planned.

Safe mock scope:

- Register or select mock template/media inventory.
- Plan vCenter install/readiness and ESXi attach without executing.
- Keep VM deployment request lifecycle as the only executable mock path.
- Generate a handoff report from profile, storage, host, and template evidence.

Provider adapter boundary:

- vSphere/vCenter remains mock for execution until a real adapter contract is
  separately approved.
- Future real adapter must use credential references, dry-run support, task IDs,
  structured vendor errors, redaction, and audit events.
- No OVF deploy, datastore write, host attach, VM power, or inventory mutation
  from this roadmap task.

Validation needs:

- Template/media category and compatibility.
- Cluster, network, datastore, and storage tier source-of-truth checks.
- Existing VM request plan checksum and lifecycle guards.
- Explicit vCenter-in-scope behavior by archetype.

Approval points:

- Continue requiring approval before planning and before execution.
- Replanning required after execution-affecting edits.

Test expectations:

- Existing VM lifecycle smoke stays green.
- Provider plan contract tests expand for future real adapter fields.
- E2E tests cover full draft, submit, approve, plan, execute, audit, and
  artifact review in mock mode.

### 8. Golden State And Handoff Certification

Purpose: turn the planned and read-only evidence from earlier workflows into a
clear "ready to ship" package for the selected lab system.

Safe mock scope:

- Compile non-secret profile, readiness, workflow-run, and artifact metadata.
- Classify each area as passed, blocked, warning, not checked, or out of scope.
- Generate a redacted operator handoff summary.
- Recommend the next safe action.

Provider adapter boundary:

- Reads application state and redacted evidence artifacts only.
- No provider calls and no workflow execution.

Validation needs:

- Evidence freshness checks.
- Required sections by archetype.
- Redaction checks for every generated report field.
- No live-state claims from historical-only artifacts.

Approval points:

- No approval for report generation.
- Certification is informational and cannot unlock destructive or write gates.

Test expectations:

- Backend tests for classification by archetype.
- Snapshot-style tests for redacted report payloads.
- E2E test for local-RAID and NetApp/vCenter handoff summaries.

## Implementation Rules For Every Workflow

- Start mock-first and keep `PROVIDER_MODE=mock` as the default.
- Add schema homes before UI controls.
- Add provider contract tests before real provider code.
- Treat live, cached, historical, mock, and unknown evidence as separate states.
- Persist dry-run plans before execution.
- Store request intent snapshots and checksums for executable workflows.
- Invalidate approval and plans after execution-affecting edits.
- Use credential references or presence checks only; never store secrets.
- Emit audit events for creation, validation, approval, planning, execution,
  completion, failure, cancellation, and blocked preflight states.
- Keep destructive workflows separate from routine planning surfaces.

## Recommended Next Task

Implement the Lab Profile And Inventory Planning workflow hardening first. It
unblocks every later workflow by making the chosen archetype, server model,
storage mode, protocol, and address plan trustworthy across commit and reload.

Suggested task:

> Add backend contract coverage and frontend E2E coverage proving lab profile
> archetype, `server_model`, storage location, storage protocol, subnet-derived
> addresses, and manual overrides round-trip through create, edit, activate,
> reload, and stale-runtime warning flows.

## Project OS Promotion Candidates

If a second product needs similar workflow governance, promote these patterns to
Project_OS standards instead of duplicating them in product repositories:

- Mock-first workflow lifecycle checklist.
- Plan contract secret-key scanner.
- Evidence source and freshness taxonomy.
- Approval and plan invalidation rules for execution-affecting edits.
- Redacted handoff report schema.
