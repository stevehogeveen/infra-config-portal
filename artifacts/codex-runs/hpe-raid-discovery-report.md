# HPE RAID Discovery Report

Date: 2026-06-06T02:48:16.421519+00:00
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
