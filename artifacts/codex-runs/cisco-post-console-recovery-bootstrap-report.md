# Cisco Post-Console Recovery Bootstrap Report

- Completed at: `2026-06-06T19:00:08Z`
- Repository: `/home/administrator/infra-config-portal`
- Provider mode: `local-lab-readwrite`
- Env file used: `.env.local.real-lab` (values not printed)
- Target management IP: `192.168.1.204`
- Mock substitution: `not used`

## Summary

- Overall status: `blocked`
- Console adapter auto-discovery: `ready`
- Selected adapter: `/dev/serial/by-id/usb-Prolific_Technology_Inc._USB-Serial_Controller_D-if00-port0`
- Prompt confirmation: `blocked`
- Privileged exec: `not reached`
- Bootstrap apply: `not attempted`
- Save config: `not attempted`
- Firmware inventory: `blocked`
- Ping validation: `failed`
- SSH validation: `failed`
- SCP validation: `failed`

## Blocker

- A root-owned `screen` process is attached to the Cisco console adapter:
  `SCREEN /dev/serial/by-id/usb-Prolific_Technology_Inc._USB-Serial_Controller_D-if00-port0 9600`.
- This shell cannot access or close that root screen session because `sudo -n screen -ls` requires a password.
- Automated Cisco console workflows cannot open the adapter while that session owns it.

## Requested Task Results

1. Auto-discover the console adapter: `completed`.
2. Confirm prompt: `blocked`; automated prompt detection could not open/read the console after the manual `screen` session took ownership.
3. Reach privileged exec: `not attempted`; prompt confirmation did not complete.
4. Run `show privilege`, `show version` summary, `show ip interface brief`, and redacted running-config summary: `not attempted`; privileged exec was not reached.
5. Run Cisco firmware inventory: `blocked`; report classified the serial console as already in use.
6. Apply Cisco bootstrap for management IP `192.168.1.204`: `not attempted`; privileged exec gate did not pass.
7. Save config: `not attempted`; bootstrap did not run.
8. Validate ping/SSH/SCP to `192.168.1.204`: `completed`; all failed because management bootstrap is not currently reachable.
9. Save report: `completed`; this file is the requested report.

## Evidence

- Guarded apply command:
  `set -a; source .env.local.real-lab; set +a; cd app/backend && PROVIDER_MODE=local-lab-readwrite CISCO_TARGET_IP=192.168.1.204 PYTHONPATH=. .venv/bin/python scripts/cisco_real_lab_workflow.py --apply`
- Guarded apply result:
  - status: `blocked`
  - prompt state: `unknown-no-output`
  - prompt detected: `false`
  - blocker: `Console adapter opened across common baud rates, but no supported Cisco prompt was detected.`
  - redacted details: `artifacts/codex-runs/cisco-4h-lab-run-details-redacted.json`
- Firmware inventory command:
  `PROVIDER_MODE=local-lab-readwrite CISCO_TARGET_IP=192.168.1.204 make provider-lab-firmware-cisco-inventory`
- Firmware inventory result:
  - status: `blocked`
  - source: `console`
  - prompt state: `unknown`
  - blocker: `Serial console port is already in use by another process.`
  - report: `artifacts/codex-runs/cisco-firmware-inventory-report.md`
- Console and Ethernet readiness command:
  `PROVIDER_MODE=local-lab-readwrite CISCO_TARGET_IP=192.168.1.204 make provider-lab-cisco-console-ethernet-readiness`
- Console and Ethernet readiness result:
  - console status: `ready`
  - prompt state: `unknown`
  - prompt captured: `false`
  - Ethernet ready: `false`
  - management configured: `false`
  - report: `artifacts/codex-runs/cisco-console-ethernet-readiness-report.md`

## Port Ownership Checks

- `fuser -v` and `lsof` did not report an owner for `/dev/ttyUSB0` at the instant checked.
- Process scan did report a root `screen` process attached to the selected adapter.
- `/dev/ttyUSB0` exists as `root:dialout` with mode `660`.
- Stable adapter symlink resolves to `/dev/ttyUSB0`.
- No stale `LCK..ttyUSB0` lock file was found under `/run/lock` or `/var/lock`.
- Low-level pyserial probes with exclusive and non-exclusive open both failed as `port-in-use`.

## Management Validation

- Ping command: `ping -c 2 -W 2 192.168.1.204`
- Ping result: `2 packets transmitted, 0 received, 100% packet loss`
- SSH TCP/22 result: `unreachable`, error `No route to host`
- SCP TCP/22 readiness result: `unreachable`, error `No route to host`
- Route used by host: `192.168.1.204 dev wlp0s20f3 src 192.168.1.19`

## Safety

- Secrets were not printed.
- Raw console output was not saved in this report.
- No configuration mode commands were sent by the blocked automated workflow.
- No bootstrap commands were sent.
- `write memory` was not sent.
- Reload, erase, copy, firmware update, and factory reset actions were not attempted.

## Next Operator Action

Detach or terminate the root-owned manual `screen` session, or run the automated workflow from the same root session context that owns the console. Then rerun the guarded apply workflow with `.env.local.real-lab` loaded and `CISCO_TARGET_IP=192.168.1.204`.
