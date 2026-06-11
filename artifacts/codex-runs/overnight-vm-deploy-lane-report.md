# Overnight VM Deploy Lane Report

## Implemented Lane

Added a guarded direct ESXi OVF deployment lane around the previously validated `govc import.ovf` pattern:

- Preview: `make provider-lab-esxi-vm-deploy-preview`
- Apply: `make provider-lab-esxi-vm-deploy-apply`
- Validate: `make provider-lab-esxi-vm-deploy-validate`
- API endpoints for preview/apply/validate.
- Control Center and workflow registry actions.
- Default datastore target: `netapp_nfs_ds01`
- Default power behavior: powered off unless `VM_DEPLOY_POWER_ON=true` and its separate confirmation are present.

## Result

- Preview status: `blocked`
- Apply status: `blocked`
- Validation status: `blocked`
- VM import attempted: `false`
- VM power action attempted: `false`

## Blockers

- Target datastore `netapp_nfs_ds01` is not visible to direct ESXi govc.
- NetApp NFS datastore is selected but is not mounted on ESXi yet.
- Apply flags are absent:
  - `VM_DEPLOY_APPLY=true`
  - `VM_DEPLOY_CONFIRM="DEPLOY ESXI OVF VM"`
  - `VM_DEPLOY_ALLOW_CREATE=true`

## Evidence

- `artifacts/codex-runs/esxi-vm-deploy-preview-report.md`
- `artifacts/codex-runs/esxi-vm-deploy-apply-report.md`
- `artifacts/codex-runs/esxi-vm-deploy-validation-report.md`
