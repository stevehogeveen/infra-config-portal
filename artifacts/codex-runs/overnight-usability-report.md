# Overnight Usability Report

## Walked Views

- Dashboard
- Hardware
- Control Center / NetApp
- Firmware Upgrades
- Validation & Reports
- VM request deployment form
- Settings/Edit Config entry point

## Changes Made

- Added NetApp NFS setup preview/apply/validate controls and evidence links.
- Added guarded direct ESXi VM deploy preview/apply/validate lane with datastore selection through environment/config and Control Center actions.
- Added workflow registry and Control Center metadata so guarded actions are visible with reports, required flags, and confirmations.

## Observations

- Active lab setup values populate the main shell and hardware/control surfaces.
- Hardware page shows live iLO, ESXi, Cisco, and NetApp states after the latest reports load.
- NetApp and datastore actions are clearly blocked by live setup/API state and are not presented as silently runnable.
- Firmware page loads more slowly because it waits for Control Center action metadata; screenshots required a longer wait but no frontend exception was observed.
- VM request form supports datastore selection already; the real-lab direct ESXi lane is now surfaced separately through Control Center and Make/API targets.

## Screenshots

- `artifacts/screenshots/overnight-dashboard.png`
- `artifacts/screenshots/overnight-hardware.png`
- `artifacts/screenshots/overnight-netapp.png`
- `artifacts/screenshots/overnight-firmware-upgrades.png`
- `artifacts/screenshots/overnight-validation-reports.png`
- `artifacts/screenshots/overnight-vm-deployment.png`
