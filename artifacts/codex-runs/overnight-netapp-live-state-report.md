# Overnight NetApp Live State Report

Checked during the 2026-06-10 overnight local real-lab run.

## Commands

- `make provider-lab-live-status`: blocked.
- `make provider-lab-build-verification-live`: blocked with exit code 2 after writing reports.
- `PROVIDER_MODE=local-lab-readwrite make provider-lab-validation`: blocked.
- `make provider-lab-netapp-console-autodiscovery`: ready.
- `make provider-lab-netapp-console-login-state`: blocked.
- `make provider-lab-netapp-console-read-state`: ready.
- `make provider-lab-netapp-live-state`: blocked.
- `make provider-lab-ilo-reachability`: ready.
- `make provider-lab-ilo-inventory`: ready.
- `make provider-lab-cisco-console-ethernet-readiness`: blocked.
- `make provider-lab-esxi-detect-installer`: installed ESXi detected.
- `PROVIDER_MODE=local-readonly PROVIDER_SMOKE_PROVIDERS=esxi-readonly make provider-smoke`: ready.

## Current State

- NetApp console: discovered on `/dev/serial/by-id/usb-Microchip_Technology_Inc._MCP2221_USB-I2C_UART_Combo-if00` at `115200`.
- NetApp prompt state: `login_required`.
- NetApp cluster management REST: not reachable.
- NetApp API access: missing local redacted access values.
- iLO: Redfish reachable at the active lab profile target; iLO inventory succeeded.
- Server: HPE ProLiant DL360 Gen10; iLO 5 v3.19; BIOS U32 v3.30; Smart Array P408i-a firmware 1.98.
- ESXi: installed and running; VMware ESXi 8.0.3 build 24859861; HTTPS and SSH reachable; govc available.
- Cisco: console path discovered, Ethernet management configured, but console probe is login-gated for this workflow.

## Blockers

- NetApp console/API credentials are not configured in the local ignored environment.
- NetApp cluster management at `192.168.1.220` is not reachable over REST.
- NetApp is not live-configured, so NFS and datastore stages are blocked.
- vCenter/govc target is not configured for vCenter workflows.
- Cisco console firmware inventory hung after the login-gated readiness state and was terminated.

## Evidence

- `artifacts/codex-runs/provider-lab-live-status-report.md`
- `artifacts/codex-runs/build-verification-report.md`
- `artifacts/codex-runs/lab-validation-handoff-report.md`
- `artifacts/codex-runs/netapp-console-autodiscovery-report.md`
- `artifacts/codex-runs/netapp-console-login-state-report.md`
- `artifacts/codex-runs/netapp-console-state-report.md`
- `artifacts/codex-runs/netapp-live-state-report.md`
- `artifacts/real-lab/ilo-reachability-20260611T022438Z.md`
- `artifacts/real-lab/provider-smoke-20260611T022501Z.md`
- `artifacts/real-lab/provider-smoke-20260611T022550Z.md`
- `artifacts/codex-runs/cisco-console-ethernet-readiness-report.md`
- `artifacts/codex-runs/esxi-installer-boot-report.md`
