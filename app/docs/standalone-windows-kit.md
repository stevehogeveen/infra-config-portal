# Standalone Windows kit

## Media discovery (2026-09-25)

In live mode, inventory and ESXi ISO selection use the app's configured
`FIRMWARE_MEDIA_ROOT` when `MEDIA_INVENTORY_DIRS` is empty. This makes media placed
through the app's mounted media folder visible to both workflows. Explicit
`MEDIA_INVENTORY_DIRS` remains authoritative; the fallback does not broaden that
allowlist. Mock mode retains sample inventory unless directories are explicit.
Finding an ISO does not approve its compatibility or install it. Windows media
must still be supplied and selected for the intended build.

Post-erase `EraseCompleted` explains a drive status, not healthy RAID eligibility.
Health warnings and the recorded operation result remain separate. Creating a new
array still requires identified eligible drives and a healthy controller; saving
the same plan again cannot clear a hardware warning.

## Consolidated Workbench

Rack home (`/simple`) now opens the white-rack/orange Workbench directly, with top
navigation and Equipment/Firmware/ESXi/Windows stages. It no longer presents the
inventory/planner split. The old inventory workspace remains at `/rack-inventory`
as a recovery route, not in the primary navigation.

The hardware picker supports new servers, switches, UPSs, PDUs and storage arrays,
plus existing saved devices not currently placed. New rack saves create hardware
inventory records and store their device_id links in the same database transaction.
Subsequent saves reuse those IDs. Removal from the rack deliberately retains the
device/credential records. Existing records remain selectable in the hardware picker.
First-time layouts suggest positions for existing physical equipment; these are
plans, not detected locations. Missing chassis/drive data is not inferred.

HPE servers expose Equipment, Access, Drives and Checks tabs. iLO is an access method
inside a server, not an add-equipment choice. Access settings use the linked device
ID; save records credentials but never runs a probe. Checks reuse the queued inventory
workflow. All ports and bays remain data-rendered, with a generated white-metal texture
for the rack. Exact photographic product fronts and drag-and-drop are still pending.

Tests cover transactionally created inventory, identity reuse, retained records after
rack removal, and the browser path from hardware through iLO settings. The historical
first-increment notes below describe the previous separate-planner stage.

## Rack customization first increment

Rack home now has Equipment inventory and Plan rack views. Plans are stored in the
database in rack_layout_plans, keyed by the active profile identifier. Existing
inventory rows and credentials are not changed by planning. Startup creates the new
table through the existing database initialization path.

Plans support 4-60 rack units, server/switch/UPS/PDU equipment, editable model labels
(including Gen10 Plus and Gen11), 24/48 switch ports, rack positions and equipment
height. Side-mounted PDUs occupy separate left/right lanes. A server declares 0-24
bays independently of its occupied-bay list; a new server starts with ten empty bays.
Each drive toggle edits only planned occupancy, never physical disks or RAID intent.

Server and client validation reject overlaps and out-of-bounds placement. The API
also validates duplicate IDs, bay occupancy and type-specific fields. Revision-based
updates reject stale saves with HTTP 409. Saving records an audit event. The API is
`GET/PUT /api/v1/rack-plans/{profile_id}` and has no provider or execution calls.

This increment uses schematic hardware, not final photorealistic assets. Drag/drop,
drive capacity/media metadata, linking planned equipment to discovery, and automatic
plan-versus-observation comparison are not implemented. Existing inventory does not
automatically populate the plan. Use explicit U position fields to place equipment.
Tests: backend test_rack_plans.py and frontend tests/rack-planner.spec.ts.

## Accepted scope

Lab defaults includes an Initial iLO access entry opening per-server onboarding.
The operator supplies the initial DHCP address and credentials manually; no DHCP
lease lookup or DHCP-server permissions are needed. It reuses the device access
record rather than storing a shared bootstrap IP. Saving never probes hardware.
Existing server addresses remain editable from the rack workspace.

Lab defaults is organized into unframed Management network, Shared services and
Connect your server sections. The onboarding action is named Initial iLO connection;
the redundant existing-server link and non-editable shared-sign-in panel were removed.
Profile persistence and per-device credential storage are unchanged.

Defaults now exposes the existing domain/timezone settings and tracks unsaved edits.
Reset restores the last loaded/saved form; failed saves keep entered values. A browser
reload/close warning protects dirty drafts, but internal route navigation is not yet
blocked. Adding an iLO no longer reloads the shared profile and discards draft defaults.
Subnet rebasing preserves the initial iLO address, which may be on another network.

The Windows kit review groups equipment, ESXi and Windows stages in expandable rows.
The selected device is kept in the URL and carried to rack review links. Other legacy
tools still require checking their displayed target. The review no longer fetches
unneeded storage/vSAN/provider data. Secondary navigation opens on its active pages.

Regression coverage: `tests/lab-defaults.spec.ts` tests reset, failed save preservation,
successful profile payload, initial-address preservation and the onboarding entry.
All API calls in this test are intercepted; no hardware is contacted.

First outcome: a Windows-bearing OVF/OVA deployed and booted on standalone ESXi,
with intended guest connectivity verified. Required equipment is the selected HPE
server/iLO and switch. vCenter is secondary. Firmware readiness precedes installation.
The boot mirror remains exactly two drives under lab-build-rules.md; a separate
writable datastore is required for VM disks. Shared storage is conditional.

## Keep, defer, remove

| Classification | Existing surface | Decision |
| --- | --- | --- |
| Keep | Rack inventory and per-device access | Resolve current target; no static address assumptions |
| Keep | Firmware inventory, baseline and guarded upgrade tools | Bind compatibility decisions to hardware identity and intended ESXi image |
| Keep | Switch setup, RAID preview, ESXi install and readiness | Preserve explicit confirmations and post-change verification |
| Keep | OVF media, VM deployment, audit and reports | Verify datastore, port group, guest boot and connectivity |
| Conditional | NetApp/shared storage | Needed only when chosen VM datastore depends on it |
| Defer | vCenter, vSAN, clustering, HA and migration | Not prerequisites for this milestone; retain existing implementations |
| Remove now | Old abbreviated runbook and stale provider-only completion inference | Replaced by standalone readiness review |
| Consolidate later | Duplicate server/storage/virtualization controls | Migrate only after target-bound operation parity is tested |

## Required evidence contracts

Every stage needs device identity, target/profile revision, source, timestamp,
freshness and an explicit result. Mock, unknown and stale results cannot authorize
the next operation. Any address, credential, image or plan change invalidates the
relevant evidence and approval. Recheck gates at execution, not only in the UI.

Firmware assessment must distinguish compatible, update required, update recommended
and unknown. A version comparison alone cannot establish compatibility. Record the
vendor compatibility reference, retrieval date, exact hardware identifiers, installed
versions, chosen ESXi image and approved baseline. No specific versions are selected
by this change. Updates require exact package identity, supported sequencing,
maintenance/reboot and recovery notes, separate confirmation and a subsequent read.

## Implemented and remaining

The Windows kit route `/simple-steps` now presents the nine-stage sequence and
explicit server selection. Only current, target-bound non-mock iLO access can show
completion. Other stages intentionally remain unverified. Links open existing review
tools; they do not carry approval or guarantee that legacy tools target this selected
server. Operators must check the target in those tools.

This is a readiness review, not a new enforced execution pipeline. Next implement
target-bound firmware inventory/assessment, then migrate boot/ESXi/resource/deployment
operations to the queued typed contract. Add backend gate tests before enabling
progression or writes. No old provider implementation is deleted in this pass.

The sidebar keeps rack, Windows kit, firmware and runs primary; settings and reports
remain available in an expandable group. Existing direct routes are retained.
