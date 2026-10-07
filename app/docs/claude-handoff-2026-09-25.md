# Claude handoff: Lab Builder
Date: 2026-09-25. Prepared by Codex for an agent change, not a new hardware operation.

## Read this first

- Work in the EXISTING dirty worktree named `.claude/worktrees/suspicious-sammet-2cafbe`.
- Branch: `rack-workspace-visual-redesign`.
- HEAD: `943462d88ccd3cfc0aec8eabc639b5a00eccf42a` (`Hand off the drive allocation work`).
- HEAD and the locally recorded upstream are equal (0 ahead, 0 behind). No fetch was performed for this handoff.
- A large amount of subsequent work is modified/untracked, NOT committed. Checking out this branch elsewhere will NOT reproduce the app described here.
- Preserve this worktree, its ignored local configuration, database volumes, saved credentials, kit plans and installation media. Do not reset, clean, stash, replace the checkout, or recreate volumes.
- Read root `AGENTS.md`, `app/AGENTS.md`, and `app/docs/lab-build-rules.md` before making changes.
- The latest recorded wipe is VERIFIED COMPLETE for all six reviewed disks. Do not blindly retry it.
- This document is context, not fresh permission to erase, power-cycle, change firmware or rebuild arrays.

The handoff preparation read repository files and the app's recorded status endpoint.
It did not send a fresh hardware probe, wipe, power action, firmware update or RAID change.
Exact target addresses, device IDs, credentials and raw hardware responses are deliberately
omitted. Resolve the selected kit/device from the local app; saved access settings are authoritative.

## Immediate status: disk wipe succeeded

The app's latest stored operation has:

| Field | Recorded value |
| --- | --- |
| Operation | Physical-disk sanitization |
| Status | verified |
| Active | false |
| Submitted | 2026-09-24 14:34:02 -04:00 |
| Power-on requested | 2026-09-24 14:35:21 -04:00 |
| Verified complete | 2026-09-24 16:22:23 -04:00 |
| Latest stored check inspected | 2026-09-25 08:35:50 -04:00 |
| Power at that check | On |
| Drives | 6 of 6 completed; each had observed activity and EraseCompleted |

All timestamps are local Eastern daylight time. This is recorded evidence, not a
continuous live health check. The stored completion message says the reviewed
physical drives reported erase completion and arrays must be recreated separately.

The method that actually worked was `SanitizeRestrictedOverwrite`, staged through
HPE SmartStorageConfig v2 and applied after an explicitly approved power-on.
The observed time from power-on request to verified completion was approximately
1 hour 47 minutes. That is one run's duration, not a promised ETA.

Completion is based on correlated per-drive state transitions, not an estimated
progress bar. A displayed 100 at completion must not be described as continuous
percentage telemetry: the older iLO did not supply useful live percentages.

What this does NOT mean:

- No new arrays were created by this wipe.
- No ESXi or Windows installation was performed by this wipe.
- RAID deletion alone was not treated as erasure.
- Other controllers, USB/embedded boot media and NVMe outside this controller were not included.
- The report is device-reported evidence, not an independent compliance certificate.
- A historical wipe report does not prove disks remain empty after future writes.

The preceding turn ended while disks were erasing. This handoff supersedes that
in-progress status with the later stored verified result.

## What the user wants

Lab Builder is a guided infrastructure setup application for users who may not
be computer literate. The essential interaction is an installer: Next, Next,
Confirm, Progress, with one obvious next action.

The user has repeatedly rejected duplicate controls, technical noise, vague
Review labels on execution actions, hidden results, frozen-looking submissions,
and pages that require guessing the next step.

Product decisions to preserve:

- My Rack is a visual, informational overview with selected-device details.
- Setup is where equipment, shared settings and execution workflows live.
- Use physical hardware in the rack. iLO is a server connection, not another rack device; ESXi is software on a server.
- Generic DL360/DL380 labels are appropriate before contact. Detect actual generation/model during connection; never invent Gen11 from a picker default.
- Hardware selection is visual, with drag/drop placement/removal/repositioning, slot displacement and rack shrinking handled coherently.
- DL360 planning supports up to 10 bays; DL380 up to 24. Planned occupancy is not discovered hardware inventory.
- Keep realistic equipment assets, a white-metal rack, meaningful contrast and restrained orange accents. Keep forms and next actions obvious at narrow widths.
- Save/load/save-as named kits and rack plans; preserve credentials and network drafts across navigation.
- Shared DNS/NTP/SNMP/gateway/subnet belong in network defaults. No fixed /24 host offsets or baked-in target IPs.
- The initial DHCP iLO address is entered per server. The user does not control the DHCP network.
- Connection and physical drives/RAID belong together on Connect equipment. Prepare ESXi contains hypervisor configuration/install work.
- A two-drive RAID1 boot pair is separate from data RAID and an optional dedicated hot spare. A hot spare is not a backup.
- All supported normal actions, shutdown/restart/recovery included, must be accessible from the app.
- Keep technical payloads and detailed diagnostics behind disclosure; never hide a real blocker or destructive scope.
- Firmware checks must show which uploaded/local package is selected, detected hardware applicability, and what is known versus unassessed.
- A build report should record actual upgrades/changes and be associated with the named kit for later reference.
- First useful outcome: standalone ESXi ready for a Windows OVF/OVA, then the deployed VM. vCenter is secondary, not a prerequisite.
- Final deployment should not require every operator to install Docker. Standalone packaging is a direction, not a finished deliverable.

The user explored Ansible/Linux automation and later deferred adding that dependency
to solve the immediate storage reset. Automation integration files exist, but the
proven wipe in this handoff uses the guarded Redfish provider, NOT an Ansible job.

## Guardrails that must remain

Follow discover/read, plan, preview, explicit confirmation, apply, verify, audit.
Simplifying the UI must not remove this separation.

- Mock remains the default provider mode. Live mode and action scope are explicitly configured.
- Load secrets from existing private local configuration; never print or commit them.
- Bind every operation to the exact saved server, controller, disks, firmware and reviewed intent.
- Do not infer the target from an old screenshot, hard-coded IP, hostname, or sibling device.
- Keep previews single-use and revalidate identity, readiness, pending settings and power state.
- A submitted request, successful HTTP response, boot, empty RAID list, idle drive, or percentage alone is not proof of erasure.
- Never automatically resubmit an uncertain/active write. A timeout is not evidence that nothing happened.
- Preserve pending, running, uncertain, failed and verified as different outcomes.
- Approval and vendor references are not automatic proof of method support.
- Acknowledging a health warning records awareness; it does not repair hardware or clear the fault.
- Do not treat a missing bay as a failed populated drive; do not suppress genuine drive failure.
- Do not reboot, shut down, recreate arrays, or change firmware while a wipe may be active.
- Unsupported Gen11/RDE/MR/NVMe/crypto paths must not inherit commands from this working SR controller.

Root AGENTS.md still has two explicitly marked incomplete instructions: a sentence
ending in "real-lab workflow." and a truncated danger-full-access condition. Do not
invent the missing text or treat it as permission. They remain documentation gaps.

## Why previous attempts looked stuck

The test system is an HPE ProLiant DL360 Gen10 with an HPE Smart Array P408i-a SR
Gen10 controller in Mixed mode, older iLO 5 and controller firmware. Six HDDs were
included: two 300 GB and four 1.2 TB. Use fresh inventory for exact current identity
and firmware; this description must never select a live target.

Earlier arrays had been removed. The controller reported the unassigned disks as
Raw. A blanket "Unconfigured only" rule was too restrictive for this validated SR
Gen10 Mixed-mode path. The app now distinguishes proven unassigned Raw disks from
logical-drive members, spares, unknown assignment and unsupported controller modes.

A later single-pass attempt used `OnePass`. The controller rejected it with:
`SmartStorageMessages.2.0.1.PropertyValueEnumNotInList`, identifying ErasePattern
and OnePass at `#/Actions/0/ErasePattern`. The response also contained a Success
message, so reading only one success entry was misleading.

The published schema listed OnePass, but this real controller rejected it.
A schema enum is not a hardware capability guarantee.

Recovery was implemented only after confirming exact scope, fresh post-boot
rejection evidence, no pending action, no logical volumes, complete unchanged
inventory, and idle disks with no previously observed erasure. That attempt was
closed as failed in the audit, not erased.

The successful attempt then used a new method review and scoped support approval,
clean shutdown with Off verified, one conditional sanitize PATCH, separately
approved power-on, and read-only verification. Once activity was observed, no
second wipe or reboot was sent.

The successful payload shape was:

```json
{
  "DataGuard": "Disabled",
  "LogicalDrives": [],
  "Actions": [
    {
      "Action": "PhysicalDriveErase",
      "ErasePattern": "SanitizeRestrictedOverwrite",
      "PhysicalDriveList": ["<exact reviewed bay list>"]
    }
  ]
}
```

This is illustrative, not a ready-to-run command or substitute for an app preview.

## Latest implementation changes

### Backend

`app/backend/app/services/disk_sanitization.py`:

- Narrow rejected-method recognition for the exact single action, scope and controller firmware.
- Rejects recovery on stale/conflicting settings, other errors, pending actions, partial inventories, changed identity or any observed erase activity.
- Legacy iLO correlation when ErasePattern is omitted: require explicit idle preflight, exact requested bays/methods, same target/controller, SmartStorageConfig v2, fresh successful post-boot settings, no pending action and no arrays.
- A reported different method is never overridden.
- Completion still needs observed queued/erasing followed by per-drive EraseCompleted. Missing progress stays unknown.

`app/backend/app/api/raid_rebuild.py`:

- Reconciles a proven rejected-method attempt into an audited failed result.
- Unresolved/ambiguous attempts remain blocking.
- Exposes erase_recovery so the UI can open a fresh normal wizard.
- Disables the proven rejected method only for the same hardware/firmware/scope.
- Permits reviewed shutdown after that narrow idle rejection; never during active/queued erasure.
- Includes rejection evidence in reports and retains confirmation/authorization requirements.

### Frontend

- `api.ts`: recovery and drive-progress response types.
- `RaidOperation.tsx`: visible operation result/recovery next step, corrected active-state notification and fewer conflicting retry/monitor messages.
- `DiskSanitization.tsx`: fresh review for another attempt and recovery action in wizard progress.
- `DiskPreparation.tsx`: routes recovery into the wipe wizard without a competing duplicate entry in that state.
- `DiskEraseProgress.tsx`: per-disk real states, indeterminate activity when no percentage, explicit evidence/source wording, actionable errors.
- `RackConnection.tsx`: background storage verification no longer disables Connection/Drives tabs or Continue to drives. Both panels remain mounted so drafts persist; equipment switching stays guarded during busy work.

Frontend component paths above are under `app/frontend/src/components/`.
These changes were made in the preceding implementation turn, not during handoff preparation.

## Architecture and file map

Stack: FastAPI/Pydantic/SQLAlchemy backend; React/TypeScript/Vite frontend with
lucide-react; PostgreSQL in the current Compose deployment. pytest and Playwright
provide targeted coverage. Keep API, domain/evidence logic, providers and UI separate.

| Area | Start here |
| --- | --- |
| Live storage orchestration/audit | app/backend/app/api/raid_rebuild.py |
| Conditional hardware writes/readback/power | app/backend/app/providers/hpe_storage_rebuild.py |
| Redfish inventory/progress/health collection | app/backend/app/providers/ilo_redfish.py |
| Sanitize preparation and completion rules | app/backend/app/services/disk_sanitization.py |
| Device-aware erase methods | app/backend/app/services/erase_options.py |
| Diagnosis/recovery/health | app/backend/app/services/storage_diagnostics.py, storage_recovery.py, hardware_health.py |
| RAID intent/planning | app/backend/app/api/disk_preparation.py, app/backend/app/services/hpe_raid.py |
| Exact saved target/access | app/backend/app/services/ilo_access_settings.py, ilo_write_target.py |
| Rack and named-kit persistence | app/backend/app/api/rack_plans.py |
| Firmware/media | app/backend/app/api/firmware_review.py; services/firmware_packages.py, spp_assessment.py, media_upload.py |
| Rack/setup UI | RackWorkbench, RackPlanner, SetupJourney, RackConnection, RackServerAccess |
| Storage UI | DiskPreparation, DiskSanitization, RaidOperation, DiskEraseProgress, ShutdownForReset, RaidRebuildReview, StorageTroubleshooting |
| Health and kit UI | HardwareHealthReview, KitLibrary |
| Visual assets/layout | hardwareCatalog.ts, HardwareThumbnail, rack placement helpers, workflow.css, workbenchTheme.css, styles.css |

App.tsx, operatorPages.tsx and simplePages.tsx still contain integration/legacy
surfaces. Do not remove them wholesale because a route looks redundant.

Useful docs:
- `app/docs/lab-build-rules.md`: governing product/evidence rules.
- `app/docs/disk-sanitization.md`: current detailed erase contract and recovery logic.
- `app/docs/disk-preparation.md`, `storage-reset.md`: RAID preparation/reset.
- `app/docs/spp-assessment.md`: firmware comparisons and limits.
- `app/docs/automation-architecture.md`, `maintenance-ssa.md`: automation context.
- `app/docs/hardware-visuals.md`, `app/docs/design/`: visual context.
- `app/docs/standalone-windows-kit.md`: desired first kit outcome; contains older implementation notes.
- `app/docs/agent-chat.md`: append-only history, not a current feature inventory.

Some old handoffs/docs still say rack artwork is schematic, drag/drop is pending,
or older navigation is current. These historical notes have been superseded by
subsequent code. Inspect current components/tests before treating them as missing
features. This handoff is focused on storage and does not certify every other
installation workflow as end-to-end complete.

## API reference for continuing safely

Base: `/api/v1/rack-plans/{profile_id}/raid-rebuild`.
Resolve profile/device from the current saved kit; do not invent IDs.

| Endpoint | Effect |
| --- | --- |
| GET /status?device_id=... | Recorded audit status; no new hardware probe |
| GET /sanitization-report?device_id=... | Recorded erasure report |
| POST /verify?device_id=... | Fresh read-only hardware verification, records evidence |
| GET /power-state?device_id=... | Fresh read-only power observation |
| POST /diagnose | Read-only troubleshooting |
| GET /erase-options?device_id=... | Device-aware methods and availability reasons |
| POST /preview | Fresh scoped operation review; no erase |
| POST /sanitize-authorization | Audited scoped support approval; no erase |
| POST /apply | Irreversible conditional storage write |
| POST /shutdown-preview, /shutdown | Preview then explicitly confirmed power operation |
| POST /boot-preview, /boot | Preview then explicitly confirmed power-on of pending operation |

Read route schemas before using endpoints. UI navigation/Next must never implicitly
call apply or power endpoints. Do not use live destructive endpoints as test fixtures.

## Development runtime and preservation

Current local endpoints:
- Frontend: http://127.0.0.1:15173
- Backend: http://127.0.0.1:18001
- Compose project: `infra-automation-dev`
- Containers include `infra-automation-dev-backend-1` and `infra-automation-dev-frontend-1`.

The running deployment uses:
1. `app/docker-compose.yml`
2. `app/docker-compose.automation.yml`
3. ignored `.local/live-access.compose.yml`

Keep this combination, project name, database and mounts intact. Starting only
the base mock Compose file can change mode/configuration and make the app appear
to have lost capability. Do not print resolved Compose config or secret env values.

Docker executable on this machine:
`$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe`

If code changes actually require a backend rebuild, from this worktree's root:

```powershell
$docker = Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'
$env:BACKEND_PORT = '18001'
$env:FRONTEND_PORT = '15173'
$env:FIRMWARE_MEDIA_HOST_PATH = Join-Path $PWD.Path 'artifacts\Media'
& $docker compose -p infra-automation-dev -f app/docker-compose.yml -f app/docker-compose.automation.yml -f .local/live-access.compose.yml up -d --build --no-deps backend
```

This restarts the app backend, not the physical server. Avoid interrupting in-flight
hardware submissions; no rebuild is needed just to read the handoff.

Windows bind-mount changes have sometimes required restarting only the frontend:
`& $docker restart infra-automation-dev-frontend-1`.
Wait for the page to respond before reloading.

Never use `docker compose down -v`, factory reset Docker, delete database volumes,
or delete ignored state/media to resolve a frontend problem. There were earlier
backup/Docker-repair discussions, but this handoff does not attest to a current
complete backup.

Native helper scripts also exist under `app/scripts/`: start-lab-builder.ps1,
stop-lab-builder.ps1, windows-doctor.ps1, and backend/frontend launchers. Their
default ports are different (8001/5173); they are not interchangeable with this
running Compose deployment's database/config. Do not switch runtime casually.

## Validation already performed

These are the preceding implementation turn's results, NOT a new full-suite run
during this handoff:

- 123 backend tests passed across test_disk_sanitization.py, test_raid_rebuild.py and test_erase_options.py.
- 15 unique Playwright tests passed across the seven storage/connection specs below.
- TypeScript project check passed.
- git diff --check passed, with existing line-ending warnings only.
- Progress views were inspected across desktop/mobile widths including 1440, 768, 390 and 320, with horizontal-overflow checks.
- Live UI showed all six disks erasing with automatic read-only checks.
- Stored app evidence inspected today now verifies all six complete.

Important regression cases include stale/wrong rejection evidence, active or
partial operations, pending changes, method mismatch, missing method echo,
idle-not-complete, missing percentage, duplicate write prevention, and navigating
to progress while verification is slow without losing input.

Backend isolated test command, from repository root (uses the existing image,
source bind read-only, mock mode and NO network):

```powershell
$docker = Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'
& $docker run --rm --network none -e DATABASE_URL=sqlite:// -e PROVIDER_MODE=mock --mount "type=bind,source=$($PWD.Path)\app\backend,target=/workspace/app/backend,readonly" infra-automation-dev-backend python -m pytest tests/test_disk_sanitization.py tests/test_raid_rebuild.py tests/test_erase_options.py -q -p no:cacheprovider
```

Frontend commands from `app/frontend`:

```powershell
node node_modules/typescript/bin/tsc -b
node node_modules/@playwright/test/cli.js test tests/disk-sanitization.spec.ts tests/erase-options.spec.ts tests/erase-progress.spec.ts tests/erase-support-reference.spec.ts tests/erase-wizard-recovery.spec.ts tests/raid-rebuild.spec.ts tests/connection-storage.spec.ts --workers=1
```

Playwright uses its fixture Vite server on port 4173. These targeted tests intercept
API calls; they must not be redirected to the live backend. Inspect a test's
fixtures before extending it. A full repository suite has not been claimed.

## Remaining issues and next priorities

1. Start by inspecting the recorded completed operation and erasure report in the app. Do not repeat the wipe.
2. If continuing hardware work is requested, get fresh read-only inventory, power and health evidence for the exact selected device before planning any new operation.
3. Make the completed outcome unmistakable: six disks verified, evidence time, erasure report, and one next action to plan arrays. Keep historical completion distinct from current health.
4. Continue toward an explicitly reviewed new OS RAID1/data/hot-spare layout, with firmware prerequisites reviewed before creation and ESXi. A saved layout is not an applied layout.
5. Persistent monitoring is still a gap: current polling is browser-driven while the page is open, up to 24 hours after recorded boot for sanitize (20 minutes for RAID). Closing the page does not stop erasure. Reopening resumes within the window; manual read checks remain. There is no durable backend erase monitor.
6. If active-state evidence was missed while the browser was closed, do not manufacture completion from a later idle/complete flag. Improve durable collection and recovery deliberately, with tests.
7. The page can still become long, and some active-operation states retain a standalone sanitization section or planned-RAID controls beneath the prominent result. Remove redundant entry points carefully while preserving reports and unresolved faults.
8. Support authorization is still an operator-reviewed vendor-evidence step, not automated exact-firmware certification. Keep unknown support honest, but make missing requirements and the next action plain.
9. Gen11/RDE/MR/NVMe-native and cryptographic erase remain unsupported where the options catalog says so. The successful SR/iLO5 run is not proof for all generations/controllers.
10. Power-supply redundancy/input warnings were observed before the erase. Do not assume every warning is the controller, or that historical PSU evidence explains all new alerts. Distinguish expected erase-in-progress state from a real hardware fault.
11. Firmware upgrades, ESXi installation and Windows deployment still need their own current-path review and end-to-end verification. Do not declare the entire build complete because erasure completed.
12. Standalone distribution, dependency packaging, durable monitoring and eventual review/commit of the broad dirty worktree are follow-up work, not completed deliverables.

## Primary technical references

These informed the implementation; procedure/schema documentation alone does not
certify support for a particular disk/controller/firmware combination.

- [HPE iLOrest drive sanitize implementation](https://github.com/HewlettPackard/python-redfish-utility/blob/master/ilorest/extensions/SMART_ARRAY_COMMANDS/DriveSanitizeCommand.py)
- [HPE Smart Array commands](https://servermanagementportal.ext.hpe.com/docs/redfishclients/ilorest-userguide/smartarraycommands)
- [HPE SmartStorageConfig documentation](https://github.com/HewlettPackard/ilo-rest-api-docs/blob/master/source/includes/_ilo5_smartstoragedoc.md)
- [HPE physical-drive resource/status fields](https://servermanagementportal.ext.hpe.com/docs/redfishservices/ilos/ilo5/ilo5_307/ilo5_hpe_resourcedefns307)
- [HPE storage management with Redfish](https://developer.hpe.com/blog/storage-management-with-redfish/)

## Handoff discipline

Keep progress updates brief and concrete. Do not ask the user to perform normal
workflow steps through a terminal or edit JSON. Do not silently take over another
hardware operation based on old approvals. Verify state first, preserve data and
audit history, and implement missing supported controls inside the app.

No commit, push, physical-server action, runtime rebuild or new backup was made
as part of preparing this handoff.
