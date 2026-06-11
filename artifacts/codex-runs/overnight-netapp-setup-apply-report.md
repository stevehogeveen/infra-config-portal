# Overnight NetApp Setup Apply Report

## Result

- Command: `make provider-lab-netapp-setup-apply`
- Status: `blocked`
- Detected state: `login_required`
- Apply enabled: `false`
- Serial writes attempted: `false`
- ONTAP writes attempted: `false`

## Apply Gate Blockers

- Console state is `login_required`; setup apply supports only cluster/node setup wizard states.
- NetApp setup intent has missing required fields.
- `NETAPP_SETUP_APPLY=true` is required.
- `NETAPP_SETUP_CONFIRM="APPLY NETAPP CLUSTER SETUP"` is required.
- `NETAPP_SETUP_ALLOW_CLUSTER_CREATE=true` is required.

## Evidence

- `artifacts/codex-runs/netapp-cluster-setup-apply-report.md`
- `artifacts/codex-runs/netapp-cluster-setup-apply-redacted.json`
