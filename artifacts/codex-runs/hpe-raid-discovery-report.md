# HPE RAID Discovery Report

Date: 2026-06-10T18:46:03.822179+00:00
Mode: `local-lab-readwrite`
Probe status: ok
Probe message: Read-only Redfish probe completed.

## Summary

- Storage inventory available: True
- Controller count: 1
- Physical drive count: 8
- Logical drive count: 2

## Blockers

- none

## Current Layout

- Controller: HPE MR416i-a Gen10+ location={'PartLocation': {'ServiceLabel': 'Slot=12', 'LocationType': 'Slot', 'LocationOrdinalValue': 12}} health=OK
- Physical drive: Bay 0 capacity=894.3 GiB media=SSD health=OK
- Physical drive: Bay 1 capacity=894.3 GiB media=SSD health=OK
- Physical drive: Bay 2 capacity=894.3 GiB media=SSD health=OK
- Physical drive: Bay 3 capacity=894.3 GiB media=SSD health=OK
- Physical drive: Bay 4 capacity=894.3 GiB media=SSD health=OK
- Physical drive: Bay 64518 capacity=unknown media=None health=OK
- Physical drive: Bay 64520 capacity=unknown media=None health=OK
- Physical drive: Bay 64519 capacity=unknown media=None health=OK
- Logical drive: Data RAID 1 log raid=RAID1 capacity=893.8 GiB health=OK
- Logical drive: OS RAID 1 logic raid=RAID1 capacity=500.0 GiB health=OK

## Not Attempted

- firmware update
- power on/off/reset
- virtual media mount
- boot order change
- BIOS change
- user/password change
- iLO network change
- factory reset
- device POST/PATCH/PUT/DELETE
