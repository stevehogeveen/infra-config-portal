# NetApp Setup + Upgrade Baseline Report

- Checked at: `2026-06-10T00:35:57.158092+00:00`
- Status: `ready`
- Provider mode: `local-lab-readwrite`
- Detected state: `cluster_setup_wizard`
- Address scan: `ready` free=`True`
- Setup/apply commands run: `no`
- Upgrade/apply commands run: `no`

## Console
- selected_port: `/dev/serial/by-id/usb-Microchip_Technology_Inc._MCP2221_USB-I2C_UART_Combo-if00`
- selected_baud: `115200`
- prompt_state: `cluster_setup_prompt`
- prompt_label: `NetApp cluster setup wizard`
- source: `autodiscovery`
- confidence: `high`
- checked_at: `2026-06-10T00:35:43.149970`

## Planned Address Scan

| Role | Address | Classification |
| --- | --- | --- |
| `Controller A SP` | `192.168.1.210` | `unused_free` |
| `Controller B SP` | `192.168.1.211` | `unused_free` |
| `Cluster management` | `192.168.1.220` | `unused_free` |
| `Node A management` | `192.168.1.221` | `unused_free` |
| `Node B management` | `192.168.1.222` | `unused_free` |
| `SVM management` | `192.168.1.223` | `unused_free` |
| `NFS LIF 1` | `192.168.1.230` | `unused_free` |
| `NFS LIF 2` | `192.168.1.231` | `unused_free` |

## Reports Read
- `artifacts/codex-runs/netapp-console-current-report.md`
- `artifacts/codex-runs/netapp-console-state-report.md`
- `artifacts/codex-runs/netapp-management-network-scan-report.md`
- `artifacts/codex-runs/netapp-setup-plan-report.md`
- `artifacts/codex-runs/netapp-live-state-report.md`
- `artifacts/codex-runs/netapp-real-bringup-final-report.md`

## Blockers
- None

## Safety
- No secrets are written to this report.
- Historical artifacts are evidence only.
