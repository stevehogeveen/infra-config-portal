# Physical-disk sanitization

Connect equipment > Drives & RAID > Physical-disk sanitization is separate from RAID
deletion. It covers every detected disk on the one identified HPE SR controller,
including former hot spares and unassigned disks. It does not cover other
controllers, USB media, embedded boot devices or NVMe devices outside that controller.
The current executor supports HPE SmartStorageConfig v2, not Gen11/RDE.

## Operator sequence

Erase method opens a device-aware options list. Selecting an implemented method
changes the draft and clears destructive consent. Next requests a fresh preview
if the method changed; neither action sends a hardware command.
The selection survives shutdown/readiness refresh and support
authorization. Each method needs its own matching approval. HDD-only sets offer
single-pass and device overwrite; SSD-only sets offer block erase; mixed sets use
per-drive automatic selection. RAID reset remains a separately confirmed operation,
explicitly not secure erasure.

Gen10, Gen10 Plus and Gen11 names are not capability evidence. This release can
execute only through the validated SmartStorageConfig v2 path. When that path is
unavailable, a read-only options list remains visible with execution disabled.
Gen11/RDE/MR/NVMe native erase and cryptographic erase are shown as not implemented;
no cross-generation command substitution or encryption assumption is made.

The review assigns a method independently to each freshly identified disk: HDDs
use SanitizeRestrictedOverwrite and SSDs use SanitizeRestrictedBlockErase. Unknown
or unsupported media types block submission rather than inherit another disk's
method. These are proposed methods, not proof of vendor support; exact firmware
capability approvals are still required. The PATCH groups disk bays by method.
Each drive's assigned method is retained by identity in the audit record, progress
checks and report. Completion using a different method is not accepted. Existing
single-method audit records remain readable. No fixed erase duration is promised.

1. Review the exact server, controller and disk identities. Save the desired future
   RAID plan separately. Opening this panel does not erase data.
2. Resolve hardware problems. Delete the existing arrays using the separately
   confirmed RAID workflow and verify that no logical volumes remain. This includes
   newly created arrays; sanitization must come before rebuilding them.
3. Open Erase support in the wipe window. Record the vendor document or support
   case and applicability notes for each exact drive/controller firmware and
   method. Confirm the server-specific phrase. This saves an audited, 24-hour
   authorization in the app database without changing hardware. Unknown support
   is not approval; do not invent evidence to clear a warning.
4. Shut down cleanly, then open a fresh erase review. Every disk must be uniquely
   identified, healthy, unassigned and covered by the capability approval.
   Validated SR Gen10 mixed-mode Raw disks follow the same guarded erase path.
5. Choose Wipe drives, review the included disks, two consolidated acknowledgements
   and exact confirmation phrase. Confirm wipe request stages one conditional PATCH;
   it does not reboot the server.
6. Separately approve Start server and begin erasure. Maintain uninterrupted power.
   Erasure can take hours. Closing the page stops observation, not physical erasure.
7. Keep the page open to collect per-drive progress and completion. Read-only polling
   resumes on reopening within 24 hours of the recorded boot; manual checks remain
   available afterward. No erase, power or retry request is sent by polling.
8. Download Erasure report. Recreate arrays only after every drive is verified.

## Administrator enrollment

Use the in-app Erase authorization form for normal operation. The operator must
already have the runtime's guarded RAID-write permissions; this form does not
switch mock/read-only mode into live-write mode or grant global hardware access.
The authenticated actor model remains the existing local-operator model; this
is not a new multi-user administrator security boundary.
The erase review embeds shutdown confirmation and live power monitoring.
Verified power-off automatically refreshes erase readiness. Array deletion opens
the existing guarded review; refresh readiness after deletion is verified.
The wipe window shows one task at a time: readiness, shutdown, support authorization
or final confirmation. Disk lists and technical payloads are collapsed during
preparation; the disk list is expanded for final consent. Repeated requirements
are deduplicated under All readiness issues. Recorded power is labeled as a review
reading, not a continuous live signal.

Raw is not equivalent to Unconfigured, but is not automatically a blocker either.
The earlier literal Unconfigured-only check was too restrictive for SR Gen10 mixed
mode. HPE's iLO 5 drivesanitize implementation selects physical disks by bay and
checks that they are not logical-drive members; it does not convert them to RAID
mode first. This must not be confused with MR/JBOD conversion procedures.

The app's narrow Raw path requires a detected HPE Smart Array SR Gen10 model,
observed Mixed mode, SmartStorageConfig v2, matching complete physical-bay lists,
no logical drives in either inventory or configuration, and unchanged Mixed port
settings. Missing/conflicting evidence, Data/Spare roles, unknown modes, pending
operations, an online server, missing method approvals and unhealthy drives still
block erasure. Readiness is checked automatically when opening the wipe window or
choosing Check disk readiness; it does not change modes or create temporary arrays.

Preparation evidence is bound to the preview, audited with the wipe attempt, and
rechecked before staging and power-on. Mode/assignment validation is not proof of
exact firmware/method compatibility. No new write command or retry path is added.

The preparation screen distinguishes a passed disk-assignment check from permission
to submit a wipe. It says erasure has not started while prerequisites remain, and
shows the selected method and timing caveat before confirmation. HDD overwrite can
take hours; SSD block erase is not instant crypto erase. No precise ETA is invented,
no unverified crypto method is selected, and RAID deletion is not called sanitization.

Legacy deployment configuration remains supported for existing installations:
the default is disabled. Existing RAID-write permissions do not enable erasure.
Add `ilo-redfish.disk-sanitize` to the explicit action allowlist and enroll the exact
device ID in `HPE_SANITIZE_DEVICE_IDS` on the backend. Existing real-lab/data-loss
acknowledgements, storage-write and guarded power-on policies still apply.
Never enable this by changing the default provider mode.

Maintain the ignored, administrator-controlled file
`.local/sanitization-capabilities.json` in the existing mounted local directory.
No UI input can assert that an unsupported drive supports a method. Each approval
must match fresh server identity, controller model/firmware, drive identity,
drive model/firmware and method. Obtain these values from the live review;
identity values are SHA-256 fingerprints, not drive bay numbers.

Example structure (replace placeholders only after reviewing vendor evidence):

```json
{
  "approvals": [
    {
      "server_identity": "SERVER_FINGERPRINT_FROM_REVIEW",
      "controller_model": "EXACT_CONTROLLER_MODEL",
      "controller_firmware": "EXACT_CONTROLLER_FIRMWARE",
      "drive_identity": "DRIVE_FINGERPRINT_FROM_REVIEW",
      "drive_model": "EXACT_DRIVE_MODEL",
      "drive_firmware": "EXACT_DRIVE_FIRMWARE",
      "method": "SanitizeRestrictedOverwrite",
      "source": "Vendor document or support-case reference confirming this combination",
      "reviewed_by": "Responsible administrator",
      "expires_at": "REPLACE_WITH_FUTURE_ISO_8601_TIME_WITH_TIMEZONE"
    }
  ]
}
```

Methods offered: `SanitizeRestrictedOverwrite`, `SanitizeRestrictedBlockErase`, and
HDD-only `OnePass`. OnePass is a controller overwrite, not a purge claim. No crypto
erase is offered: trustworthy key lifecycle evidence is not implemented. A schema's
list of erase patterns is not evidence that a particular drive supports them.

## Evidence and failure behavior

The existing audit database stores the reviewed scope, method approvals, operator,
single-use attempt, acceptance, boot and per-drive observations. No new dependency
or database migration is needed. The report is historical evidence, not proof that
a disk remains empty after later writes and not an independent compliance certificate.

Successful staging, boot, an empty RAID layout, 100% alone, or an old EraseCompleted
flag cannot verify sanitization. For each exact drive the app must observe a queued
or running state for the selected method after its recorded boot, followed by
EraseCompleted, a fresh successful controller result, no pending changes and no
logical volumes. A firmware version that cannot report these states remains
unverified. Fast operations whose active state was missed also remain unverified;
an attended vendor verification path would be needed, not a fabricated success.

A missing/replaced disk, changed identity, failed/aborted erase or lost response
never authorizes retry or array recreation. The current workflow deliberately has
no automatic cancellation, retry, forced reboot, or recovery bypass. Unresolved
sanitization blocks RAID changes and the guided shutdown controls. Other tools and
out-of-band operators must also avoid modifying the server during erasure.

## Vendor references

- [HPE OEM drive-sanitize payload](https://github.com/HewlettPackard/ilo-rest-api-docs/blob/master/source/includes/_ilo5_smartstoragedoc.md)
- [HPE iLOrest iLO 5 drive selection and sanitize implementation](https://github.com/HewlettPackard/python-redfish-utility/blob/master/ilorest/extensions/SMART_ARRAY_COMMANDS/DriveSanitizeCommand.py)
- [HPE drive erase status fields](https://servermanagementportal.ext.hpe.com/docs/redfishservices/ilos/ilo5/ilo5_307/ilo5_hpe_resourcedefns307)
- [HPE SmartStorageConfig erase methods](https://servermanagementportal.ext.hpe.com/docs/redfishservices/ilos/ilo5/ilo5_304/ilo5_other_resourcedefns304)

Tests: backend `tests/test_disk_sanitization.py` plus RAID/provider regressions;
frontend `tests/disk-sanitization.spec.ts` checks confirmation, no duplicate writes
and 1440/768/390/320-pixel layouts. Tests use fixtures, never real erase commands.
# Operator feedback

The dialog is a four-step installer-style wizard: Choose method, Prepare server,
Confirm wipe, Progress. Back and Next navigate without sending hardware writes.
Method choices update the preview only. Shutdown, support authorization, wipe
submission and power-on still require their specifically labeled confirmations.
Back preserves the selected method; Next validates a changed method with a fresh
preview. Unsupported choices remain disabled with reasons.

Read-only reviews show elapsed time and allow Cancel to stop waiting. Late
responses from a closed review cannot overwrite a newer review. Cancelling waiting
does not cancel a hardware operation. Writes still lock dismissal until their
response is handled, and an uncertain write is never automatically retried.
Failed reads offer Retry check; expired evidence offers Refresh check before
authorization or erasure, with reference notes retained and consent cleared.

Support authorization accepts a shared vendor reference or separate per-disk
references. The operator must still confirm coverage for every exact disk,
firmware and selected method; the backend records the reference against each
disk identity. Missing evidence is a prerequisite, not an automatic compatibility
claim or a server fault. The form explains what is needed to enable Save and Next.
The required reference field is highlighted, with the specific missing requirement
beside the sticky Next button. HPE's Redfish erase procedure is linked in the form;
Add HPE reference appends its URL without replacing notes. This is procedure
documentation, not certification for a particular drive/firmware combination.
Operators must still establish applicability, explicitly confirm support and
enter the server-specific phrase. Adding or editing a reference clears the support
attestation. Nothing is saved or enabled merely by opening the documentation or
adding its link; existing backend approval and fresh-target checks remain unchanged.

Erase preparation shows one next action: shutdown, array removal, support approval,
or wipe confirmation. It never sends an erase request automatically. Manual
power checks are hidden during automatic shutdown monitoring, and the completed
shutdown form is replaced by waiting status. Readiness refreshes after shutdown
and authorization; unresolved requirements retain an explicit recheck action.
Reports appear after submission, not as a competing preparation action.
Staged settings and verified completion remain distinct.

## Drive progress

The storage result and the wipe wizard share one Disk wipe progress view. It lists
every disk from the recorded operation even before the first controller reading.
Each bay shows the requested method, reported state and a real percentage when the
controller supplies one. The overall bar counts verified disks, not estimated
bytes erased or elapsed time. A missing percentage stays unknown; 100% alone is
not accepted as completion evidence.

Power is labeled as the last check, with a reading time. Read failures and readings
older than two minutes are visibly marked as last known. Controller errors appear
above the disk list; their raw message IDs remain available under details. A rejected
setting does not by itself prove that every disk was untouched. Ambiguous results
stay unresolved; there is no automatic erase retry, fallback method or reboot.

The app can close a precisely identified rejected-method attempt as failed, never
erased: a fresh post-boot response must reject the exact single action's
ErasePattern, the same disks and controller firmware must still be present, every
disk must explicitly report idle with no erase pattern or progress, and no pending
action or logical volume may remain. Any previously observed erase activity,
additional error, changed identity or partial result prevents this recovery.
The failed attempt stays in the audit log. Set up another wipe attempt opens the
normal wizard with fresh method approval, shutdown, wipe and power-on confirmations.
The rejected method is disabled for that exact hardware/firmware scope; approval
alone cannot enable it. A schema listing a value is not proof that a controller
will execute it.

Automatic read-only verification continues while disks report queued/erasing,
including a partial operation with other errors. If an error leaves no active
disks, automatic checking stops and a single read-only Check every disk's erase
result action remains at the top of the progress view. Existing monitoring windows
and per-disk completion guards still apply.

HPE documents `EraseCompletionPercentage` and `DiskDriveStatusReasons` in its
[physical-drive resource reference](https://servermanagementportal.ext.hpe.com/docs/redfishservices/ilos/ilo5/ilo5_307/ilo5_hpe_resourcedefns307).
Firmware may omit these values; the app does not synthesize progress or an ETA.
Older iLO can report EraseInProgress/EraseCompleted without ErasePattern. The app
associates those readings with a requested method only when the exact disks were
explicitly idle before submission, the requested action names each bay and method,
and the same controller reports fresh post-boot settings success with no pending
action or arrays. A reported different method is never overridden. Completion
still requires observed activity followed by a per-drive completion flag; returning
to idle, an empty array list or a successful boot is not completion evidence.
