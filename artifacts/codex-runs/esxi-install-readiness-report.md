# ESXi Install Readiness Report

Date: 2026-06-06T18:25:21.869644+00:00
Mode: `local-lab-readwrite`
Status: ready
Message: Server is ready to plan ESXi ISO virtual-media boot.

## Inventory

- model: ProLiant DL360 Gen10
- power_state: On
- health: Warning
- redfish_root_status: 200
- system_status: 200
- manager_status: 200

## Capabilities

- Virtual media supported: True
- ISO capable virtual media: True
- One-time boot supported: True
- Boot targets: None, Cd, Hdd, Usb, SDCard, Utilities, Diags, BiosSetup, Pxe, UefiShell, UefiHttp, UefiTarget
- BIOS settings available: True
- BIOS version: U32 v3.30 (07/31/2024)

## ISO Readiness

- Media inventory mode: local
- ISO count: 3
- ESXi candidate count: 3
- Selected placeholder: iso-7.iso

## Milestones

- RAID reset/validate works: complete
- Virtual media check works: complete
- One-time boot works: set
- ESXi ISO boots: boot_requested
- Automated/assisted ESXi install: future

## Boot Workflow

- Media URL: ready (artifacts/codex-runs/esxi-media-url-report.md)
- Virtual media: inserted (artifacts/codex-runs/esxi-virtual-media-report.md)
- One-time boot: set (artifacts/codex-runs/esxi-one-time-boot-report.md)
- Reset/installer boot: boot_requested (artifacts/codex-runs/esxi-installer-boot-report.md)

## Blockers

- none

## Warnings

- none

## Next Safe Action

- Continue with Cisco console and Ethernet bootstrap readiness.
