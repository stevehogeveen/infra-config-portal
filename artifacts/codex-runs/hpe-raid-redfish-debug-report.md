# HPE RAID Redfish Debug Report

Date: 2026-06-05T18:52:10.806151+00:00
Mode: `local-lab-readwrite`
PATCH run by this report: no

## GET Captures

- /redfish/v1/systems/1/smartstorageconfig/: HTTP 200
- /redfish/v1/systems/1/smartstorageconfig/settings/: HTTP 200

## Last Apply Error

- HTTP status: 400
- Error code: iLO.0.10.ExtendedInfo
- Message: See @Message.ExtendedInfo for more information.
- ExtendedInfo: iLO.2.25.ArrayPropertyOutOfBound args=['DataDrives', '6', '1', '5']

## Payload Comparison

- Diagnosis: iLO rejected DataDrives because the payload supplied 6 entries; the accepted range reported by iLO is 1 to 5.

### Planned Logical Drives

- ESXi-OS: raid=Raid1 data_count=2 data=1I:1:1, 1I:1:2 spare_count=0 spare=-
- VM-Datastore: raid=Raid6 data_count=5 data=1I:1:3, 1I:1:4, 2I:1:5, 2I:1:6, 2I:1:7 spare_count=1 spare=2I:1:8

### SmartStorage Settings Logical Drives

- OS RAID 1 logical drive: raid=Raid1 data_count=2 data=1I:1:1, 1I:1:2 spare_count=0 spare=-
- Data RAID 6 logical drive: raid=Raid6 data_count=5 data=1I:1:3, 1I:1:4, 2I:1:5, 2I:1:6, 2I:1:7 spare_count=1 spare=2I:1:8

## Artifacts

- debug_report: `artifacts/codex-runs/hpe-raid-redfish-debug-report.md`
- payload: `artifacts/codex-runs/hpe-raid-apply-payload-redacted.json`
- current: `artifacts/codex-runs/hpe-smartstorage-current.json`
- settings: `artifacts/codex-runs/hpe-smartstorage-settings.json`
