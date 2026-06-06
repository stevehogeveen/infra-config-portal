# HPE RAID Apply Report

Started: 2026-06-05T18:52:57.361159+00:00
Finished: 2026-06-05T18:53:18.745324+00:00
Status: succeeded
Message: HPE RAID apply request was accepted by Redfish SmartStorageConfig settings.

## Before

- Storage inventory available: True
- Controller count: 1
- Physical drive count: 8
- Logical drive count: 2
- Logical drive: OS RAID 1 logical drive raid=RAID1 capacity=500.0 GiB health=OK
- Logical drive: Data RAID 6 logical drive raid=RAID6 capacity=3.27 TiB health=OK

## After

- Storage inventory available: True
- Controller count: 1
- Physical drive count: 8
- Logical drive count: 2
- Logical drive: OS RAID 1 logical drive raid=RAID1 capacity=500.0 GiB health=OK
- Logical drive: Data RAID 6 logical drive raid=RAID6 capacity=3.27 TiB health=OK

## Redfish Result

- Method/path: PATCH /redfish/v1/systems/1/smartstorageconfig/settings/
- HTTP status: 200
- Redfish error code: iLO.0.10.ExtendedInfo
- Redfish message: See @Message.ExtendedInfo for more information.
- ExtendedInfo count: 1

## Blockers

- none

## Warnings

- RAID apply is destructive; verify iLO SmartStorage pending settings and reboot requirements manually.
