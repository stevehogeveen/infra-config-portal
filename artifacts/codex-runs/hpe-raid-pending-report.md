# HPE RAID Pending Report

Date: 2026-06-06T18:25:25.619982+00:00
Mode: `local-lab-readwrite`

## SmartStorage GETs

- Current: HTTP 200
- Settings: HTTP 200

## Pending State

- Pending config exists: False
- Settings match saved intent: True
- Live config matches saved intent: True
- Pending differs from live: False
- Reset required: False
- Last apply reported SystemResetRequired: True

## Expected Logical Drives

- ESXi-OS: raid=Raid1 data_count=2 data=1I:1:1, 1I:1:2 spare_count=0 spare=-
- VM-Datastore: raid=Raid6 data_count=5 data=1I:1:3, 1I:1:4, 2I:1:5, 2I:1:6, 2I:1:7 spare_count=1 spare=2I:1:8

## Current Live Logical Drives

- ESXi-OS: raid=Raid1 data_count=2 data=1I:1:1, 1I:1:2 spare_count=0 spare=-
- VM-Datastore: raid=Raid6 data_count=5 data=1I:1:3, 1I:1:4, 2I:1:5, 2I:1:6, 2I:1:7 spare_count=1 spare=2I:1:8

## Pending Settings Logical Drives

- ESXi-OS: raid=Raid1 data_count=2 data=1I:1:1, 1I:1:2 spare_count=0 spare=-
- VM-Datastore: raid=Raid6 data_count=5 data=1I:1:3, 1I:1:4, 2I:1:5, 2I:1:6, 2I:1:7 spare_count=1 spare=2I:1:8

## Next Safe Action

- No reset-required pending RAID state was detected.
