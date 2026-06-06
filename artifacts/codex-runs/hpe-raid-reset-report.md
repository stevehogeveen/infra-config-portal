# HPE RAID Server Reset Report

Started: 2026-06-05T19:00:27.779628+00:00
Finished: 2026-06-05T19:00:29.395583+00:00
Status: blocked
Message: Server reset for RAID pending settings did not run.

## Before

- Reachable: True
- Power state: On
- Health: Warning
- Current GET: HTTP 200
- Settings GET: HTTP 200
- Current logical drives:
  - OS RAID 1 logical drive: raid=Raid1 data_count=2 data=1I:1:1, 1I:1:2 spare_count=0 spare=-
  - Data RAID 6 logical drive: raid=Raid6 data_count=5 data=1I:1:3, 1I:1:4, 2I:1:5, 2I:1:6, 2I:1:7 spare_count=1 spare=2I:1:8
- Pending settings logical drives:
  - ESXi-OS: raid=Raid1 data_count=2 data=1I:1:1, 1I:1:2 spare_count=0 spare=-
  - VM-Datastore: raid=Raid6 data_count=5 data=1I:1:3, 1I:1:4, 2I:1:5, 2I:1:6, 2I:1:7 spare_count=1 spare=2I:1:8

## Reset Request

- Method/path: not-run 
- HTTP status: not-run
- ResetType: not-run

## After

- none

## Blockers

- HPE_RAID_ALLOW_RESET=true is required for server reset.
- Exact confirmation phrase is required: RESET SERVER FOR HPE RAID APPLY

## Next Safe Action

- Set the reset gates and exact confirmation phrase from a terminal.
