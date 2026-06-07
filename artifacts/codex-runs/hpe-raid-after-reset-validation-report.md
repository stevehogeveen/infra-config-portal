# HPE RAID After Reset Validation Report

Started: 2026-06-07T00:03:41.000951+00:00
Finished: 2026-06-07T00:04:14.166616+00:00
Status: succeeded
Message: Live SmartStorage layout matches the saved RAID intent.

## Wait

- Reachable: True
- Attempts: 1
- Elapsed seconds: 1
- Power state: On

## Validation

- Matches saved intent: True

### Expected Logical Drives

- ESXi-OS: raid=Raid1 data_count=2 data=1I:1:1, 1I:1:2 spare_count=0 spare=-
- VM-Datastore: raid=Raid6 data_count=5 data=1I:1:3, 1I:1:4, 2I:1:5, 2I:1:6, 2I:1:7 spare_count=1 spare=2I:1:8

### Current Live Logical Drives

- ESXi-OS: raid=Raid1 data_count=2 data=1I:1:1, 1I:1:2 spare_count=0 spare=-
- VM-Datastore: raid=Raid6 data_count=5 data=1I:1:3, 1I:1:4, 2I:1:5, 2I:1:6, 2I:1:7 spare_count=1 spare=2I:1:8

## Mismatches

- none

## Next Safe Action

- Continue with ESXi install preparation.
