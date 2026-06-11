# Grand Operation RAID Report

- Generated at: `2026-06-10T22:51:50.056171+00:00`
- Scope: Stage 5 RAID / local storage validation.
- Credentials and hardware serial values are redacted.

## Status

- Overall status: `ready`.
- Current Smart Array layout was discovered through iLO Redfish.
- Current layout already matches the intended ESXi split: RAID1 `ESXi-OS` and RAID6 `VM-Datastore`.
- Destructive RAID apply was not run because no rebuild was needed and live settings already match expected state.
- Pending settings check: `pending_config_exists=false`, `live_matches_expected=true`, `reset_required=false`.

## Current Layout Summary

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

## Decision

- The plan preview requested destructive wipe/delete only as an apply mechanism; the actual live layout already satisfies the intended OS and datastore RAID design.
- No reset/commit was required after the pending-state check.

## Artifacts

- `artifacts/codex-runs/hpe-raid-discovery-report.md`
- `artifacts/codex-runs/hpe-raid-plan-report.md`
- `artifacts/codex-runs/hpe-raid-pending-report.md`

## Remaining RAID Blockers

- none

## Next Action

- Continue to ESXi rebuild/configuration readiness using the existing RAID layout.
