# NetApp Bring-Up Build Verification Report

Checked at: 2026-06-09T22:33:56.668389+00:00

## Command

- `PROVIDER_MODE=local-lab-readwrite make provider-lab-build-verification`

## Result

- Exit code: nonzero because Build Verification is blocked
- Overall status: `blocked`
- Certification state: `hard_fail`
- Source: `live_probe`
- Freshness: `current`
- Current: `True`

## NetApp Classification

- Lab IP profile: `ready`
- NetApp configured state: `setup_wizard`
- NetApp configured: `False`
- NetApp source: `live_verification`
- Manual env flag required: `False`
- NetApp console: `passed`
- NetApp REST: `operator_action_required`
- NetApp SSH: `operator_action_required`
- NetApp NFS/vCenter: `blocked_by_prior_stage`

## Current NetApp Evidence

- Discovered console port: `/dev/serial/by-id/usb-Microchip_Technology_Inc._MCP2221_USB-I2C_UART_Combo-if00`
- Console baud: `115200`
- Console confidence: `high`
- Last seen: `2026-06-09T22:26:10.370669`
- Live state report: `artifacts/codex-runs/netapp-live-state-report.md`
- State automanagement report: `artifacts/codex-runs/netapp-state-automanagement-report.md`
- Setup plan report: `artifacts/codex-runs/netapp-setup-plan-report.md`
- NFS/vCenter readiness report: `artifacts/codex-runs/netapp-nfs-vcenter-readiness-report.md`

## Next Action

For NetApp, continue from the detected cluster setup wizard state. Build Verification is not asking for a manual `.env` console port or `NETAPP_CONFIGURED` edit. The next NetApp action is to add or run a guarded setup workflow only after explicit apply flags and confirmation gates exist; until then REST/SSH and NFS/vCenter remain blocked by prior setup.

## Other Current Build Blockers

- Cisco SSH/SCP required port is not reachable.
- ESXi API required port is not reachable.
- ESXi SSH required port is not reachable.

## Safety

- No NetApp write, setup, storage, NFS, iSCSI, reboot, wipe, upgrade, vCenter, or ESXi datastore apply command was run.
- Credential values, tokens, and secrets were not printed.
