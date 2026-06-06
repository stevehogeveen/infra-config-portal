# HPE RAID Plan Report

Date: 2026-06-06T02:48:36.913848+00:00
Mode: `local-lab-readwrite`
Status: warning

## Current Layout

- Controller: HPE Smart Array P408i-a SR Gen10 location=Slot 0 health=OK
- Physical drive: Bay 1I:1:1 capacity=1.09 TiB media=HDD health=OK
- Physical drive: Bay 1I:1:2 capacity=1.09 TiB media=HDD health=OK
- Physical drive: Bay 1I:1:3 capacity=1.09 TiB media=HDD health=OK
- Physical drive: Bay 1I:1:4 capacity=1.09 TiB media=HDD health=OK
- Physical drive: Bay 2I:1:5 capacity=1.09 TiB media=HDD health=OK
- Physical drive: Bay 2I:1:6 capacity=1.09 TiB media=HDD health=OK
- Physical drive: Bay 2I:1:7 capacity=1.09 TiB media=HDD health=OK
- Physical drive: Bay 2I:1:8 capacity=1.09 TiB media=HDD health=OK
- Logical drive: ESXi-OS raid=RAID1 capacity=500.0 GiB health=OK
- Logical drive: VM-Datastore raid=RAID6 capacity=3.27 TiB health=OK

## Planned Layout

- Summary: Plan-only preview with existing logical drive wipe/delete requested: ESXi-OS RAID1 on bays 1I:1:1, 1I:1:2; VM-Datastore RAID6 on bays 1I:1:3, 1I:1:4, 2I:1:5, 2I:1:6, 2I:1:7.
- ESXi-OS: raid=RAID1 bays=1I:1:1, 1I:1:2 estimated_usable_bytes=1200243081216
- VM-Datastore: raid=RAID6 bays=1I:1:3, 1I:1:4, 2I:1:5, 2I:1:6, 2I:1:7 estimated_usable_bytes=3600729243648

## Apply Gate

- Apply available: False
- Mechanism: redfish-smartstorageconfig-settings
- Confirmation phrase: `APPLY HPE RAID PLAN`

## Blockers

- HPE_RAID_ALLOW_DESTRUCTIVE=true is required for destructive RAID apply.
