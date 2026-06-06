# iLO Real Run Report

Date: 2026-06-05T16:32:55.790364+00:00

## Scope

- Mode: `PROVIDER_MODE=local-lab-readwrite`
- Env file: repo-root `.env.local.real-lab`
- Target access: real iLO Redfish GET-only inventory
- Mock results: not used

## Inventory

- Probe status: ok
- Redfish message: Read-only Redfish probe completed.
- Server model: ProLiant DL360 Gen10
- Product info present: True
- Serial present: True
- iLO model: iLO 5
- iLO firmware: iLO 5 v3.19
- BIOS version: U32 v3.30 (07/31/2024)
- Power state: On
- Health: Warning
- NIC inventory count: 4
- Storage discovery status: available
- Storage controllers: 1
- Physical drives: 8
- Logical drives: 2

## Safety

- not attempted: firmware update
- not attempted: power on/off/reset
- not attempted: virtual media mount
- not attempted: boot order change
- not attempted: BIOS change
- not attempted: user/password change
- not attempted: iLO network change
- not attempted: factory reset
- not attempted: device POST/PATCH/PUT/DELETE
