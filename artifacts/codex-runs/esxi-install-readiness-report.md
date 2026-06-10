# ESXi Install Readiness Report

Date: 2026-06-10T19:44:46.296839+00:00
Mode: `local-lab-readwrite`
Status: blocked
Message: ESXi install readiness is blocked until required capabilities and media are present.

## Inventory

- model: ProLiant DL360 Gen10 Plus
- power_state: On
- health: OK
- redfish_root_status: 200
- system_status: 200
- manager_status: 200

## Capabilities

- Virtual media supported: True
- ISO capable virtual media: True
- One-time boot supported: True
- Boot targets: None, Cd, Hdd, Usb, SDCard, Utilities, Diags, BiosSetup, Pxe, UefiShell, UefiHttp, UefiTarget
- BIOS settings available: True
- BIOS version: U46 v1.80 (07/05/2023)

## ISO Readiness

- Media inventory mode: local
- ISO count: 3
- ESXi candidate count: 3
- Selected placeholder: iso-7.iso

## Milestones

- RAID reset/validate works: blocked
- Virtual media check works: complete
- One-time boot works: ready_to_run
- ESXi ISO boots: installed_esxi
- Automated/assisted ESXi install: future

## Boot Workflow

- Media URL: ready (artifacts/codex-runs/esxi-media-url-report.md)
- Virtual media: ejected (artifacts/codex-runs/esxi-virtual-media-eject-report.md)
- One-time boot: set (artifacts/codex-runs/esxi-one-time-boot-report.md)
- Reset/installer boot: installed_esxi (artifacts/codex-runs/esxi-installer-boot-report.md)

## Blockers

- RAID validation after reset must succeed before ESXi install readiness.

## Warnings

- none

## Next Safe Action

- Resolve blockers, then rerun provider-lab-esxi-install-readiness.
