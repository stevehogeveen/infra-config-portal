# Firmware Upgrade Path Engine Audit

Generated: 2026-06-14

Scope: app/service/UI audit only. No datastore, ONTAP, vCenter, ESXi, NFS, storage, firmware, power, reset, or destructive action was run for this audit.

## Sources Inspected

- Backend firmware compliance and inventory service: `app/backend/app/services/firmware_compliance.py`
- Firmware summaries consumed by Control Center and Firmware Upgrades
- Golden State drift logic: `app/backend/app/services/golden_state.py`
- Validation and handoff reporting: `app/backend/app/services/lab_validation.py`
- Report Center firmware issue collection: `app/backend/app/services/report_center.py`
- Firmware UI surfaces: `app/frontend/src/App.tsx`, `app/frontend/src/styles.css`, `app/frontend/src/types.ts`
- Existing evidence: `artifacts/codex-runs/firmware-inventory-report.md`, `artifacts/codex-runs/firmware-compliance-report.md`
- Local package/media inventory: `artifacts/Media`

## Known Versions

| Component | Current Version | Target / Baseline | Classification Before This Pass |
| --- | --- | --- | --- |
| Cisco IOS XE | 17.15.05 | >= 17.9 | Current |
| Cisco ROMMON / bootloader | Unknown | Manual approval required | Manual review |
| iLO firmware | iLO 5 v3.19 | 3.19 | Current |
| HPE BIOS | U32 v3.30 (07/31/2024) | No approved baseline recorded | Manual review |
| Smart Array firmware | 1.98 | No approved baseline recorded | Manual review |
| ESXi image | 8.0.3 | ESXi ISO version 8.0.3 | Current |
| NetApp ONTAP | 9.17.1 | 9.17.1 | Current |
| NetApp disk firmware | Unknown | No approved baseline recorded | Manual review |
| NetApp shelf firmware | Unknown | No approved baseline recorded | Manual review |
| NetApp SP/BMC firmware | Unknown | No approved baseline recorded | Manual review |
| vCenter / VCSA | 8.0.3 | VCSA ISO version 8.0.3 | Current |

## Available Packages / Media

`artifacts/Media` currently contains:

- `9131P17_q_image.tgz`
- `9141P14_q_image.tgz`
- `9171_q_image.tgz`
- `VMware-ESXi-8.0.3-24859861-HPE-803.0.0.12.2.0.9-oct2025.iso`
- `VMware-VCSA-all-8.0.3-24853646.iso`
- `cat9k_iosxe.17.15.05.SPA.bin`
- `ilo5_319.fwpkg`
- `ilo6_176.fwpkg`

Normalized package availability from the app model:

- Cisco IOS XE: package available, current; no apply needed.
- iLO firmware: package available, current; no apply needed.
- ESXi image: ISO available, current; no apply needed.
- NetApp ONTAP: package available, current; no apply needed.
- vCenter / VCSA: ISO available, current; no apply needed.
- Cisco ROMMON, HPE BIOS, Smart Array, NetApp disk firmware, NetApp shelf firmware, and NetApp SP/BMC firmware: no actionable package mapping until current version, target baseline, and vendor path evidence are recorded.

## Unknown Upgrade Paths

- Cisco ROMMON / bootloader: current version and approved target baseline are missing. Needs read-only boot/ROMMON inventory plus vendor path evidence.
- HPE BIOS: current version is known, but target baseline is missing. Needs approved HPE baseline or SPP mapping before an upgrade path can be actionable.
- Smart Array firmware: current version is known, but target baseline is missing. Needs approved HPE storage firmware baseline or SPP mapping.
- NetApp disk firmware: current version and target baseline are missing. Needs read-only component firmware inventory and approved target baseline.
- NetApp shelf firmware: current version and target baseline are missing. Needs read-only component firmware inventory and approved target baseline.
- NetApp SP/BMC firmware: current version and target baseline are missing. Needs read-only component firmware inventory and approved target baseline.

## Why Golden State Still Marked Firmware as Needs Review

Golden State previously used a generic firmware row that collapsed all firmware state into `Needs manual baseline review`. That hid which components were already current and which components still lacked baseline/path evidence.

The actual firmware evidence shows five current components and six remaining manual-review components. The remaining drift is not a provider apply blocker; it is missing baseline/path evidence for named components.

## Required Product Change

The app needs a normalized firmware/software upgrade path model that exposes per-component current version, target, package status, path status, evidence gaps, disabled apply reason, and next action. Golden State, Report Center, Firmware Upgrades, Control Center, and handoff reporting should consume that same model so firmware drift is specific and operator-actionable.
