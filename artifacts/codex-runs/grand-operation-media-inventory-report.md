# Grand Operation Stage 1 Media Inventory Report

Generated: 2026-06-10T18:13:14-04:00

## Summary

Media root scanned: `artifacts/Media`

Fresh filesystem inventory found the media needed for the requested run:

- ESXi installer ISOs: found.
- VCSA/vCenter installer ISO: found.
- ONTAP image packages: found.
- iLO firmware packages: found.
- Cisco image package: found.
- OVF/VMDK VM template: found.
- HPE SPP/SUM package: not found.

## Identified Media

### ESXi ISO

| File | Size | Notes |
| --- | ---: | --- |
| `artifacts/Media/VMware-ESXi-8.0.3-24859861-HPE-803.0.0.12.2.0.9-oct2025.iso` | 0.71 GiB | Preferred current HPE ESXi 8 installer candidate |
| `artifacts/Media/VMware-ESXi-7.0.3-23794027-HPE-703.0.0.11.8.0.4-Sep2024.iso` | 0.45 GiB | Older HPE ESXi 7 installer candidate |

### VCSA / vCenter Installer ISO

| File | Size | Notes |
| --- | ---: | --- |
| `artifacts/Media/VMware-VCSA-all-8.0.3-24853646.iso` | 11.67 GiB | VCSA/vCenter installer candidate |

### ONTAP Images / Packages

| File | Size | App version hint |
| --- | ---: | --- |
| `artifacts/Media/9131P17_q_image.tgz` | 2.61 GiB | `9.13.1P17` |
| `artifacts/Media/9141P14_q_image.tgz` | 2.73 GiB | `9.14.1P14` |
| `artifacts/Media/9171_q_image.tgz` | 2.99 GiB | `9.17.1` |

### iLO Firmware Packages

| File | Size | App hint |
| --- | ---: | --- |
| `artifacts/Media/ilo5_319.fwpkg` | 0.03 GiB | iLO5 `3.19` |
| `artifacts/Media/ilo6_176.fwpkg` | 0.03 GiB | iLO6 `1.76` |

### Cisco Images / Packages

| File | Size | App hint |
| --- | ---: | --- |
| `artifacts/Media/cat9k_iosxe.17.15.05.SPA.bin` | 1.20 GiB | Cisco IOS XE `17.15.5` |

### OVF / OVA / VM Templates

| File | Size | Notes |
| --- | ---: | --- |
| `artifacts/Media/OVF_Templates/DepOps_W2K22_Template_VMware7.0_Feb2025-1.0/DepOps_W2K22_Template_VMware7.0_Feb2025-v1.0.ovf` | 7.4 KiB | OVF descriptor |
| `artifacts/Media/OVF_Templates/DepOps_W2K22_Template_VMware7.0_Feb2025-1.0/DepOps_W2K22_Template_VMware7.0_Feb2025-v1.0-1.vmdk` | 9.03 GiB | VM disk |
| `artifacts/Media/OVF_Templates/DepOps_W2K22_Template_VMware7.0_Feb2025-1.0/DepOps_W2K22_Template_VMware7.0_Feb2025-v1.0-2.nvram` | 264.5 KiB | Template sidecar |

### HPE SPP / SUM Packages

No HPE SPP or SUM package was found under `artifacts/Media`.

## App Inventory Improvements Made

The app media inventory needed a small product fix before later stages:

- Recursively scans configured media directories, so nested OVF/VMDK template files are visible.
- Treats `.tgz`, `.tar`, `.tar.gz`, `.zip`, `.pkg`, and `.image` as firmware/upgrade package candidates.
- Adds safe product/version hints for:
  - ONTAP `q_image` packages.
  - Cisco IOS XE `cat9k_iosxe` packages.
  - VCSA/vCenter ISO media.
  - HPE iLO firmware packages.
- Keeps local filenames redacted in the API by returning placeholder names such as `firmware-1.tgz` and `iso-12.iso`.
- Fixed firmware rollup grouping so Cisco counts no longer match the word `category`.

Touched files:

- `app/backend/app/services/media_inventory.py`
- `app/backend/app/services/firmware_compliance.py`
- `app/backend/tests/test_media_inventory.py`
- `app/backend/tests/test_firmware_compliance.py`

## Current App Media API Result

Fresh `/api/v1/media-inventory` after the fix:

```json
{
  "mode": "local",
  "item_count": 12,
  "category_counts": {
    "firmware": 6,
    "iso": 3,
    "other": 1,
    "ovf": 1,
    "vmdk": 1
  },
  "product_hint_counts": {
    "cisco-ios-xe": 1,
    "hpe": 2,
    "hpe-ilo": 2,
    "netapp-ontap": 3,
    "unhinted": 3,
    "vmware-esxi": 2,
    "vmware-vcenter": 1
  },
  "warnings": []
}
```

Fresh `/api/v1/lab/firmware-inventory` after the fix:

```json
{
  "status": "completed",
  "source_type": "not_checked",
  "candidate_count": 6,
  "grouped_counts": {
    "cisco": 1,
    "hpe": 2,
    "netapp": 3
  },
  "evidence_artifacts": [
    "artifacts/codex-runs/firmware-inventory-report.md"
  ]
}
```

The inventory is current for local media metadata only. Live device firmware state is still `not_checked` until the provider stages run.

## Validation

Targeted tests:

```text
app/backend/tests/test_media_inventory.py: 8 passed
app/backend/tests/test_firmware_compliance.py and related media/upgrade tests: 68 passed
ruff on touched backend/test files: passed
```

Next action: Stage 2 toolchain readiness.
