# HPE RAID Pending Report

Date: 2026-06-10T19:36:57.363264+00:00
Mode: `local-lab-readwrite`

## SmartStorage GETs

- Current: HTTP 404
- Settings: HTTP 404

## Pending State

- Pending config exists: False
- Settings match saved intent: False
- Live config matches saved intent: False
- Pending differs from live: False
- Reset required: True
- Last apply reported SystemResetRequired: True

## Expected Logical Drives

- ESXi-OS: raid=Raid1 data_count=2 data=1I:1:1, 1I:1:2 spare_count=0 spare=-
- VM-Datastore: raid=Raid6 data_count=5 data=1I:1:3, 1I:1:4, 2I:1:5, 2I:1:6, 2I:1:7 spare_count=1 spare=2I:1:8

## Current Live Logical Drives

- none

## Pending Settings Logical Drives

- none

## Next Safe Action

- Run `HPE_RAID_ALLOW_RESET=true HPE_RAID_RESET_CONFIRM="RESET SERVER FOR HPE RAID APPLY" LAB_ALLOW_POWER_ACTIONS=true make -C app provider-lab-server-reset-for-raid` when ready.
