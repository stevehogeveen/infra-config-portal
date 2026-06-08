# Cisco Password Recovery Guidance Report

- Checked at: `2026-06-07T12:55:44.526936+00:00`
- Provider mode: `local-lab-readwrite`
- Initial prompt state: `privileged-exec`
- Enable command sent: `False`
- Password prompt seen: `False`
- Enable rejected: `no`
- Final prompt state: `privileged-exec`
- Privilege level: `15`
- Password recovery status: `false`
- Next action: Privilege is confirmed; continue Cisco management network validation.

## Detection Text

- `user exec only`: enable is required before bootstrap apply; no configuration is sent from `DEVICE>`.
- `enable password rejected`: enable was sent, a password prompt was seen, and the final prompt did not become `DEVICE#`.
- `setup wizard`: stop at the initial configuration dialog; do not answer wizard prompts from automation.
- `ROMMON/bootloader prompt`: use the physical-console recovery path before normal bootstrap.
- `password recovery ready`: bootloader recovery prompt is present; recover credentials from console, then rerun bootstrap.

## Manual Password Recovery Runbook

1. Connect the console cable to the Cisco console port and confirm the selected serial port and baud.
2. Power cycle or reload only under local operator control, then interrupt boot if the platform recovery procedure requires it.
3. At ROMMON or bootloader, use the platform-supported method to ignore startup configuration.
4. Boot the switch and reach user or privileged exec without printing credentials in this app.
5. Set new local admin and enable credentials manually on the console.
6. Save the configuration manually after verifying the intended target.
7. Update `.env.local.real-lab` locally with the new credential values, then rerun the Cisco privilege check.

## Blockers

- none

## Safety

- No secrets, raw console transcript, or raw running-config are stored here.
- No bootstrap configuration is applied unless privileged exec is confirmed.
- Password recovery requires local operator control of the physical console.
