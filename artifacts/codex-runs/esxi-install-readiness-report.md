# ESXi Install Readiness Report

Date: 2026-06-08T13:48:33.923297+00:00
Mode: `mock`
Status: blocked
Message: ESXi install readiness is blocked until required capabilities and media are present.

## Inventory

- model: None
- power_state: None
- health: None
- redfish_root_status: None
- system_status: None
- manager_status: None

## Capabilities

- Virtual media supported: False
- ISO capable virtual media: False
- One-time boot supported: False
- Boot targets: unknown
- BIOS settings available: False
- BIOS version: None

## ISO Readiness

- Media inventory mode: sample
- ISO count: 1
- ESXi candidate count: 0
- Selected placeholder: none

## Milestones

- RAID reset/validate works: blocked
- Virtual media check works: blocked
- One-time boot works: set
- ESXi ISO boots: installed_esxi
- Automated/assisted ESXi install: future

## Boot Workflow

- Media URL: ready (artifacts/codex-runs/esxi-media-url-report.md)
- Virtual media: ejected (artifacts/codex-runs/esxi-virtual-media-eject-report.md)
- One-time boot: set (artifacts/codex-runs/esxi-one-time-boot-report.md)
- Reset/installer boot: installed_esxi (artifacts/codex-runs/esxi-installer-boot-report.md)

## Blockers

- RAID validation after reset must succeed before ESXi install readiness.
- iLO virtual media support was not discovered through Redfish.
- One-time boot override support was not discovered through Redfish.
- No ESXi ISO candidate is ready in local media inventory.

## Warnings

- BIOS settings discovery is unavailable or incomplete.

## Next Safe Action

- Resolve blockers, then rerun provider-lab-esxi-install-readiness.
