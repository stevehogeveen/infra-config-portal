# Cisco Console Recovery Baseline

- Saved at: `2026-06-06T18:19:52Z`
- Provider mode requested: `local-lab-readwrite`
- Env file requested: `.env.local.real-lab` (values not printed)

## artifacts/codex-runs/cisco-4h-lab-run-report.md

# Cisco 4h Lab Run Report

## Summary

- Checked at: 2026-06-06T16:55:41.651718+00:00
- Provider mode: `local-lab-readwrite`
- Overall status: `blocked`
- Console adapter detected: `/dev/serial/by-id/usb-Prolific_Technology_Inc._USB-Serial_Controller_D-if00-port0`
- Prompt detected: `True`
- Prompt state: `login-required`
- Selected baud: `9600`
- Switch identity status: `blocked`
- Bootstrap plan status: `ready`
- Apply status: `not-attempted`
- Ethernet management status: `not-attempted`

## Blockers

- Exec prompt is required for identity capture; got login-required.
- Privileged exec prompt is required for bootstrap apply.

## Warnings

- Preferred console path: /dev/serial/by-id/usb-Prolific_Technology_Inc._USB-Serial_Controller_D-if00-port0. Use this stable path for CISCO_CONSOLE_PORT instead of /dev/ttyUSB0 when possible.

## Code Inspection

- Enable from exec prompt: `yes`; `_ensure_privileged` calls `_enter_enable` when prompt state is `exec`.
- Enable commands attempted: `enable`, then `enable 15`.
- Password prompt after enable handled: `yes`; `_answer_enable_challenge` responds to `Password:` without logging the value.
- Enable password aliases tried: `CISCO_ENABLE_PASSWORD`, `ANSIBLE_CISCO_ENABLE_PASSWORD`, `settings.cisco_enable_password`, then login-password fallback.
- Configuration apply: `not run` unless `--apply` is passed.

## Stage Evidence

- Adapter discovery: `ready`; source `auto-stable-candidate`.
- Port ownership: `False`.
- Console prompt detection: tried `[9600, 19200, 38400, 57600, 115200]` and wake sequences `['newline', 'enter', 'ctrl-c', 'ctrl-z']`.
- Privilege initial prompt state: `login-required`.
- Enable command sent: `False`.
- Enable password prompt seen: `False`.
- Privilege final prompt state: `login-required`.
- Readable privilege level: `None`.
- Enable password rejected: `False`.
- Password recovery/factory reset required: `unknown`.
- Operator next action: Recover Cisco password from console or provide valid console login credentials, then rerun Cisco bootstrap.
- Bootstrap commands redacted artifact: `artifacts/codex-runs/cisco-bootstrap-commands-redacted.json`.
- Console samples redacted artifact: `artifacts/codex-runs/cisco-console-samples-redacted.json`.
- Details artifact: `artifacts/codex-runs/cisco-4h-lab-run-details-redacted.json`.

## Safety

- Raw console logs and secrets were not saved.
- Reboot/reload was not attempted unless explicitly reported in apply status.
- Mock results were not used as substitutes for real lab evidence.

## artifacts/codex-runs/cisco-console-discovery-report.md

# Cisco Console Discovery

- Status: blocked
- Prompt state: unknown
- Configured port hint: REDACTED
- Auto-discovered selected port: REDACTED
- Selected baud: not selected
- Candidate count: 1
- Last console blocker: Console port opened but no prompt text was captured. Verify the console cable is connected to the Cisco console port, confirm the switch is powered on, confirm no other process owns the serial port, and verify the baud rate such as 9600 or 115200.

## Candidate Summary
- REDACTED | stable=False | exists=True | readable=True | writable=True | in_use=False | rank=-125 | recommendation=selected-auto

## Attempts
- REDACTED @ 9600 via newline: checked prompt=unknown captured=False
- REDACTED @ 9600 via enter: checked prompt=unknown captured=False
- REDACTED @ 9600 via ctrl-c: checked prompt=unknown captured=False
- REDACTED @ 9600 via ctrl-z: checked prompt=unknown captured=False
- REDACTED @ 19200 via newline: checked prompt=unknown captured=False
- REDACTED @ 19200 via enter: checked prompt=unknown captured=False
- REDACTED @ 19200 via ctrl-c: checked prompt=unknown captured=False
- REDACTED @ 19200 via ctrl-z: checked prompt=unknown captured=False
- REDACTED @ 38400 via newline: checked prompt=unknown captured=False
- REDACTED @ 38400 via enter: checked prompt=unknown captured=False
- REDACTED @ 38400 via ctrl-c: checked prompt=unknown captured=False
- REDACTED @ 38400 via ctrl-z: checked prompt=unknown captured=False
- REDACTED @ 57600 via newline: checked prompt=unknown captured=False
- REDACTED @ 57600 via enter: checked prompt=unknown captured=False
- REDACTED @ 57600 via ctrl-c: checked prompt=unknown captured=False
- REDACTED @ 57600 via ctrl-z: checked prompt=unknown captured=False
- REDACTED @ 115200 via newline: checked prompt=unknown captured=False
- REDACTED @ 115200 via enter: checked prompt=unknown captured=False
- REDACTED @ 115200 via ctrl-c: checked prompt=unknown captured=False
- REDACTED @ 115200 via ctrl-z: checked prompt=unknown captured=False

## artifacts/codex-runs/cisco-firmware-inventory-report.md

# Cisco Firmware Inventory Report

- Status: blocked
- Source: console
- Prompt state: unknown
- Selected baud: not selected
- IOS XE version: unknown
- Bootloader/ROMMON: unknown

## Command Evidence
- No show-command evidence was captured.

## Blockers
- Console port opened but no prompt text was captured. Verify the console cable is connected to the Cisco console port, confirm the switch is powered on, confirm no other process owns the serial port, and verify the baud rate such as 9600 or 115200.

## Warnings
- none

## Safety
- Read-only console path only.
- No privileged exec requirement was used for show version.
- No firmware update commands were run.
- Raw console output was not saved.

## artifacts/codex-runs/cisco-privilege-check-report.md

# Cisco Console Privilege Check Report

## Summary

- Checked at: `2026-06-05T20:53:08.848579+00:00`
- Provider mode: `local-lab-readwrite`
- Env file: `.env.local.real-lab` loaded by `app.core.config`
- Console adapter: `[REDACTED]`
- Baud: `9600`
- Initial prompt state: `exec`
- Final prompt state: `exec`
- Privileged exec confirmed: `False`

## Env Var Usage Confirmed

- Login username: `settings.cisco_test_username` from `CISCO_TEST_USERNAME`, fallback `ANSIBLE_CISCO_USERNAME`, fallback `LAB_USERNAME`.
- Login password: `settings.cisco_test_password` from `CISCO_TEST_PASSWORD`, fallback `ANSIBLE_CISCO_PASSWORD`, fallback `LAB_PASSWORD`.
- Enable password setting: `settings.cisco_enable_password` from `CISCO_ENABLE_PASSWORD`, fallback `ANSIBLE_CISCO_ENABLE_PASSWORD`.
- Enable escalation candidates now tried directly from `CISCO_ENABLE_PASSWORD`, `ANSIBLE_CISCO_ENABLE_PASSWORD`, `settings.cisco_enable_password`, then login-password fallback.
- Login username configured: `True`
- Login password configured: `True`
- `CISCO_ENABLE_PASSWORD` configured: `True`
- `ANSIBLE_CISCO_ENABLE_PASSWORD` configured: `True`
- Login and selected enable password values same: `True`

## Workflow Fix

- `app/backend/scripts/cisco_real_lab_workflow.py` now uses the login password for console login exchange.
- Prompt classification now recognizes a trailing `#` or `>` prompt even when earlier output includes `Password:`.
- Enable escalation now tries both `CISCO_ENABLE_PASSWORD` and `ANSIBLE_CISCO_ENABLE_PASSWORD` when present.
- Redaction now includes both raw enable-password aliases.

## Console Steps

- wake prompt result: exec
- sent enable
- sent enable password candidate from CISCO_ENABLE_PASSWORD/ANSIBLE_CISCO_ENABLE_PASSWORD/login-password-fallback

## Blockers

- Did not reach privileged exec # prompt.

## Warnings

- none

## Read-Only Command Evidence

- Skipped because privileged exec was not confirmed.
## Safety

- No configuration commands were sent.
- No raw console transcript was saved.
- Secrets, usernames, console path, and IP addresses are redacted in this report.

