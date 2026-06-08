# HPE RAID After Reset Validation Report

Started: 2026-06-08T13:48:42.124461+00:00
Finished: 2026-06-08T14:04:05.440131+00:00
Status: failed
Message: Live SmartStorage layout does not yet match the saved RAID intent.

## Wait

- Reachable: False
- Attempts: 44
- Elapsed seconds: 923
- Power state: None

## Validation

- Matches saved intent: False

### Expected Logical Drives

- ESXi-OS: raid=Raid1 data_count=2 data=1I:1:1, 1I:1:2 spare_count=0 spare=-
- VM-Datastore: raid=Raid6 data_count=5 data=1I:1:3, 1I:1:4, 2I:1:5, 2I:1:6, 2I:1:7 spare_count=1 spare=2I:1:8

### Current Live Logical Drives

- none

## Mismatches

- Logical drive count differs: current=0 expected=2.

## Next Safe Action

- Wait longer for POST/reset processing, then rerun provider-lab-hpe-raid-validate-after-reset.
