# Serial Console Autodiscovery Final Report

Checked at: 2026-06-07

## Implementation Summary

- Added a shared serial console discovery/probe engine for Cisco and NetApp.
- Enumerates `/dev/serial/by-id/*`, `/dev/ttyUSB*`, `/dev/ttyACM*`, and `/dev/ttyS*`.
- Collects path, resolved path, access, owner/group/mode, modified time, in-use state, udevadm/setserial status, and sudo-free dmesg availability/clues.
- Ranks stable by-id USB paths first, ttyUSB/ttyACM next, fresh or hinted ttyS next, stale ttyS lower, and inaccessible/in-use ports lower.
- Keeps ttyS candidates visible and selectable; NetApp autodiscovery selected `/dev/ttyS4`.
- Safe probe sends only newline, carriage return, and Ctrl+C wake bytes. No credentials, show commands, config commands, boot menu selections, API calls, or apply actions were sent.

## Real Discovery Results

Generic serial discovery:

- Command: `make provider-lab-serial-console-discovery`
- Status: `blocked`
- Candidate count: `32`
- Selected port: `/dev/ttyS4`
- Selected baud: `115200`
- Classification: `no_bytes_read`
- Reason: `ttyS device has a recent modified timestamp`
- Report: `artifacts/codex-runs/serial-console-discovery-report.md`
- JSON: `artifacts/codex-runs/serial-console-discovery-redacted.json`

NetApp console autodiscovery:

- Command: `make provider-lab-netapp-console-autodiscovery`
- Status: `blocked`
- Candidate count: `32`
- Selected port: `/dev/ttyS4`
- Selected baud: `115200`
- Prompt state: `no_output`
- Confidence: `medium`
- Reason: `ttyS device has a recent modified timestamp`
- Report: `artifacts/codex-runs/netapp-console-autodiscovery-report.md`
- JSON: `artifacts/codex-runs/netapp-console-autodiscovery-redacted.json`

NetApp console read-state:

- Command: `make provider-lab-netapp-console-read-state`
- Status: `blocked`
- Selected port: `/dev/ttyS4`
- Selected baud: `115200`
- Prompt state: `no_output`
- Report: `artifacts/codex-runs/netapp-console-state-report.md`
- JSON: `artifacts/codex-runs/netapp-console-state-redacted.json`

## Blocker

The OS-visible best candidate is `/dev/ttyS4`, but the safe probe read zero bytes at configured/common baud rates. The next operator action is physical validation: confirm the NetApp console cable is on `/dev/ttyS4`, confirm the controller is powered and emitting console output, and rerun autodiscovery.

## UI Validation

- Screenshot: `artifacts/screenshots/netapp-run-center-serial-autodiscovery.png`
- Covered Run Center / NetApp blocked no-prompt state with selected port, confidence, why-selected, next action, and collapsed raw console details.

## Verification

- `make test`
- Result: `268 passed`; frontend `npm run build` completed successfully through the root test target.
