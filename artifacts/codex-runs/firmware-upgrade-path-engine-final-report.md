# Firmware Upgrade Path Engine Final Report

Generated: 2026-06-14

## Scope

- Worktree: `/home/administrator/infra-config-portal`
- Safety posture: UI/service/reporting change only.
- Firmware apply run: not run.
- Provider write/destructive action run: not run.
- Secrets: not printed, copied, or added to artifacts.

## Result

Firmware/software baseline review is now modeled as per-component upgrade path evidence instead of a generic manual review row.

Current app classification:

- Current: Cisco IOS XE, iLO firmware, ESXi image, NetApp ONTAP, vCenter/VCSA.
- Manual review: Cisco ROMMON / bootloader, HPE BIOS, Smart Array firmware, NetApp disk firmware, NetApp shelf firmware, NetApp SP/BMC firmware.
- Blocked: none.
- Unknown scan-needed paths: none in the current evidence set.
- Apply enabled: false for all paths.

## Product Changes

- Added normalized firmware/software upgrade path fields to backend schema and service payloads.
- Added package/media awareness, missing-evidence reasons, disabled apply reasons, prechecks, impact/reboot metadata, and next actions per component.
- Updated Firmware Upgrades with a compact path table and selected-row detail panel.
- Updated Control Center device firmware strips with current version, baseline, path status, package status, scan action, and Firmware Upgrades entry point.
- Updated Golden State to derive firmware drift from normalized path statuses and list exact components needing review.
- Updated Report Center and Validation/Handoff to surface current version, target, path status, package status, and what remains without default raw dumps.

## Screenshots Captured

- `artifacts/screenshots/firmware-upgrade-path-table.png`
- `artifacts/screenshots/firmware-upgrade-path-detail.png`
- `artifacts/screenshots/control-center-firmware-strip-cisco.png`
- `artifacts/screenshots/control-center-firmware-strip-ilo.png`
- `artifacts/screenshots/control-center-firmware-strip-netapp.png`
- `artifacts/screenshots/golden-state-firmware-drift-detail.png`

Screenshots are intentionally not staged.

## Validation

- Focused backend tests: `72 passed`
- `make lint`: passed
- Final `make test`: `458 passed` plus frontend build
- App restart for screenshots: passed built-in mock smoke test, `3 passed`

## Remaining Operator Work

Firmware is still partial only because manual baseline/path evidence is missing for the named components:

- Cisco ROMMON / bootloader
- HPE BIOS
- Smart Array firmware
- NetApp disk firmware
- NetApp shelf firmware
- NetApp SP/BMC firmware

No firmware apply, power, reset, datastore, ONTAP, vCenter, ESXi, NFS, storage, or destructive action was run in this pass.
