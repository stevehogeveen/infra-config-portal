# Cisco 4h Lab Run Report

## Summary

- Checked at: 2026-06-05T21:10:26.519121+00:00
- Provider mode: `local-lab-readwrite`
- Overall status: `blocked`
- Console adapter detected: `/dev/serial/by-id/usb-Prolific_Technology_Inc._USB-Serial_Controller_D-if00-port0`
- Prompt detected: `True`
- Prompt state: `exec`
- Selected baud: `9600`
- Switch identity status: `captured`
- Bootstrap plan status: `ready`
- Apply status: `not-attempted`
- Ethernet management status: `not-attempted`

## Blockers

- Privileged exec prompt is required for bootstrap apply.

## Warnings

- Preferred console path: /dev/serial/by-id/usb-Prolific_Technology_Inc._USB-Serial_Controller_D-if00-port0. Use this stable path for CISCO_CONSOLE_PORT instead of /dev/ttyUSB0 when possible.
- Bootstrap plan was built but not applied because --apply was not set.

## Stage Evidence

- Adapter discovery: `ready`; source `auto-stable-candidate`.
- Port ownership: `False`.
- Console prompt detection: tried `[9600, 19200, 38400, 57600, 115200]` and wake sequences `['newline', 'enter', 'ctrl-c', 'ctrl-z']`.
- Bootstrap commands redacted artifact: `artifacts/codex-runs/cisco-bootstrap-commands-redacted.json`.
- Console samples redacted artifact: `artifacts/codex-runs/cisco-console-samples-redacted.json`.
- Details artifact: `artifacts/codex-runs/cisco-4h-lab-run-details-redacted.json`.

## Safety

- Raw console logs and secrets were not saved.
- Reboot/reload was not attempted unless explicitly reported in apply status.
- Mock results were not used as substitutes for real lab evidence.
