# Overnight NetApp NFS Setup Report

## Implemented Lane

Added a guarded NFS-only workflow with:

- Preview: `make provider-lab-netapp-nfs-setup-preview`
- Apply: `make provider-lab-netapp-nfs-setup-apply`
- Validate: `make provider-lab-netapp-nfs-setup-validate`
- API endpoints for preview/apply/validate.
- Control Center and workflow registry actions.
- UI surfacing in the NetApp real-lab panel.

The workflow explicitly ignores future iSCSI LIFs for this operation.

## Live Result

- Preview status: `blocked`
- Apply status: `blocked`
- Validation status: `blocked`
- ONTAP writes attempted: `false`
- ESXi/vCenter writes attempted: `false`

## Blockers

- NetApp ONTAP cluster is not live-configured yet.
- NetApp API access fields are missing: `NETAPP_API_USERNAME`, `NETAPP_API_PASSWORD`.
- Guarded apply flags are absent.
- vCenter/govc target is not configured for vCenter datastore validation.

## Evidence

- `artifacts/codex-runs/netapp-nfs-setup-preview-report.md`
- `artifacts/codex-runs/netapp-nfs-setup-apply-report.md`
- `artifacts/codex-runs/netapp-nfs-setup-validation-report.md`
- `artifacts/codex-runs/netapp-nfs-vcenter-readiness-report.md`
