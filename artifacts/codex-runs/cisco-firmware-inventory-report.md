# Cisco Firmware Inventory Report

- Status: ok
- Source: console-user-exec-show-version
- Prompt state: exec
- Console classification: user_exec
- Selected baud: 9600
- IOS XE version: 17.15.05
- Bootloader/ROMMON: unknown
- Next physical/operator action: Keep this as readiness evidence only; run any future show-command check through a separate explicit read-only action.

## Command Evidence
- show version: captured=True version_hint=17.15.05 raw_output_redacted=True

## Historical Evidence
- none

## Blockers
- none

## Warnings
- none

## Safety
- Read-only console path only.
- No privileged exec requirement was used for show version.
- No firmware update commands were run.
- Raw console output was not saved.
