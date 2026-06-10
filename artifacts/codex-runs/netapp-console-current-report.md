# NetApp Console Current Report

Checked at: 2026-06-09T22:26:10.370669+00:00

## Commands Run

- `PROVIDER_MODE=local-lab-readwrite make provider-lab-serial-console-discovery`
- `PROVIDER_MODE=local-lab-readwrite make provider-lab-netapp-console-autodiscovery`
- `PROVIDER_MODE=local-lab-readwrite make provider-lab-netapp-console-read-state`

## Result

- Generic serial discovery: `blocked`
- NetApp console autodiscovery: `ready`
- NetApp console read-state: `ready`
- Selected port: `/dev/serial/by-id/usb-Microchip_Technology_Inc._MCP2221_USB-I2C_UART_Combo-if00`
- Selected baud: `115200`
- Prompt state: `cluster_setup_prompt`
- Prompt label: `NetApp cluster setup wizard`
- Selection source: `prompt-evidence`
- Selection origin: `autodiscovery`
- Selection confidence: `high`
- Manual env update required: `False`

## Why This Port Was Selected

The NetApp-specific autodiscovery found prompt evidence on the stable MCP2221 by-id adapter. This supersedes the older historical artifact where `/dev/ttyACM0` showed a login prompt. No manual `NETAPP_CONSOLE_PORT` update is required.

## Evidence

- `artifacts/codex-runs/serial-console-discovery-report.md`
- `artifacts/codex-runs/serial-console-discovery-redacted.json`
- `artifacts/codex-runs/netapp-console-autodiscovery-report.md`
- `artifacts/codex-runs/netapp-console-autodiscovery-redacted.json`
- `artifacts/codex-runs/netapp-console-state-report.md`
- `artifacts/codex-runs/netapp-console-state-redacted.json`
- `artifacts/codex-runs/netapp-console-last-known-good-redacted.json`

## Safety

- No credentials were sent.
- No ONTAP, setup, boot menu, SP, node, SVM, LIF, volume, export, datastore, reboot, takeover/giveback, wipe, or upgrade command was run.
- Only NetApp console wake/read-state behavior from the workflow was used.
