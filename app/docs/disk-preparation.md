# Disk preparation in guided setup

Connect equipment contains Connection and Drives & RAID tabs for the same server.
Prepare ESXi contains host settings and installer actions, not RAID editing.
Opening the page never contacts equipment. Refresh drive inventory runs the
existing explicit read-only iLO probe. RAID review also performs a fresh read;
only a separately confirmed apply request can stage a hardware change.

The planner requires a successful target-matched observation less than five minutes
old, one identified controller, and two healthy, identified drives with equal
capacity and media type. Failed or unidentified drives cannot be selected. The
request includes an inventory digest; changed observations invalidate the review.
Existing volumes require explicit removal intent and a data-loss acknowledgement.
Saving writes the existing per-device HpeRaidIntent and a kit-linked audit event,
not the controller. An optional, separate VM-data array supports RAID1 (2 drives),
RAID5 (3+), RAID6 (4+) or RAID10 (an even count of 4+). Boot and data membership
cannot overlap. Unselected drives remain unassigned. The single assignment table
saves OS, storage and an optional backup hot spare together. A hot spare is not a
file backup: choose which array it protects. It must be healthy, on the same
controller, match the array's media type and be at least as large as each member.
The existing intent stores its bay and Dedicated spare mode. Fresh preflight
revalidates it and readback verifies both spare membership and mode.

Health alerts are grouped into one expandable summary; critical severities remain
visible when collapsed. Existing volume details and removal acknowledgement are
kept separate from assignments. Review RAID changes opens deletion while old
volumes exist, then creation after an empty controller is verified. Unsaved edits
disable this review so the displayed plan cannot be mistaken for the saved one.
Switching the two tabs preserves unsaved entries; saved roles survive reload.

Absent bays are warnings. Records with no model, serial identity or capacity are
labelled "Missing or unidentified", not diagnosed as a failed physical drive.
Original iLO health and reason codes are retained. Neither classification makes
a bay eligible for RAID. Identified failed drives remain critical. An operator
must physically confirm every absent/unidentified bay before a staged rebuild;
if a drive is actually present, stop and diagnose it instead.

Old logical volumes can be removed through an attended HPE Smart Storage
Administrator session reached through the server's iLO. Review the exact server,
controller and listed volumes first. This is not secure erasure of physical media.
Do not factory-reset the controller or reset iLO as a shortcut. Firmware approval,
backup review and hardware health issues must be resolved before rebuilding.

## Guarded Gen10 SR rebuild

The new device-scoped adapter uses HPE's SmartStorageConfig v2 pending-settings
API for a single SR controller. It requires the advertised settings endpoint,
matching controller location, complete memberships and an exact ETag. It does not
guess another controller or fall back to a global iLO credential. Gen11/RDE and
unsupported layouts use attended HPE SSA; the old global factory-reset stub is
not used or enabled by this path.

1. Save the desired boot, optional data array and hot spare, including removal intent.
2. Select Review RAID changes. This reads the exact target and previews a PUT that
   removes all logical volumes and clears RAID metadata on that controller.
3. Confirm backups/data loss, health and firmware review, any empty bays, and the
   server-specific phrase. The server must be Off. Staging does not reboot it.
4. Inspect pending settings in iLO, then perform an attended boot and let POST
   complete. Verify RAID changes checks the empty configuration and HPE Success messages.
5. Review and separately confirm RAID creation, then repeat the attended boot and
   read-back verification. Only healthy identified drives enter the new arrays.

Writes require existing isolated-lab policy acknowledgements,
`PROVIDER_MODE=local-lab-readwrite`, and `HPE_RAID_ALLOW_DESTRUCTIVE=true` in the
backend environment. Read-only and mock modes cannot write. These gates are not
changed by visiting the page or acknowledging a warning. Firmware review is an
explicit operator attestation, not automatic proof of compatibility.

POST `/{profile_id}/raid-rebuild/preview`, `/apply` and `/verify` live under
`/api/v1/rack-plans` with a required exact `device_id`. Previews expire in five
minutes and bind server identity, inventory, saved plan and pending configuration.
Apply repeats read-only preflight and uses conditional PUT with If-Match. A durable
audit claim is committed before the write; the same preview cannot be replayed.
Lost, rejected or ambiguous responses stay unverified. No automatic retry is
made, and another operation is blocked until readback verifies the prior result.
Pending settings are never silently overwritten. Audit events appear in kit
history and later report snapshots. No physical-drive sanitize/secure erase,
controller factory reset or power command is sent.

After attended changes, refresh inventory. A boot mirror is marked as matching
only when a healthy RAID1 logical drive reports exactly the two saved physical
drive resource paths. A matching mirror is not ESXi installation approval. No
button claiming manual completion can substitute for hardware readback.

Tests run with an isolated SQLite database, no network, and ephemeral artifact
storage. Browser tests mock planning and abort all non-GET calls during live
visual checks. Do not exercise destructive lab operations as automated UI tests.

Vendor references: [HPE Gen10 SR storage API](https://hewlettpackard.github.io/ilo-rest-api-docs/ilo5/)
and [HPE storage data models](https://servermanagementportal.ext.hpe.com/docs/redfishservices/ilos/supplementdocuments/storage/).
Dedicated spare semantics: [HPE SmartStorageConfig reference](https://servermanagementportal.ext.hpe.com/docs/redfishservices/ilos/ilo5/ilo5_273/ilo5_other_resourcedefns273).
# Operator Action Labels

Save proposed layout stores the intended drive assignments, not a completion report.
Delete old RAID opens the destructive confirmation while volumes exist;
Create new RAID replaces it after the controller is verified empty. The final
Confirm and stage RAID deletion/creation button submits the actual pending change.
Check applied RAID after restart performs readback verification, not a reboot.
Per-operation confirmations, current identity, power-off and pending-state checks
remain required. Saving or opening a preview never stages a hardware operation.

`LAB_ALLOWED_WRITE_ACTIONS`, when present, narrows the shared live hardware-action
policy to the listed action IDs. An empty value blocks all hardware writes through
that policy; it does not block read-only or application-state operations. This is
an additional restriction, not a substitute for the existing acknowledgement gates.
The local RAID deployment allows only `ilo-redfish.hpe-raid-apply` through this
policy and keeps power, firmware and factory-reset flags off. Its ignored Compose
override enables guarded RAID staging, not automatic erase, creation or restart.
