# ESXi VM Deploy Vm Deploy Preview Report

- Checked at: `2026-07-01T17:19:36.257803+00:00`
- Status: `preview_ready`
- Apply enabled: `False`
- Provider mode: `local-lab-readwrite`
- ESXi configured: `True`
- govc available: `True`
- Target datastore visible: `True`

## Deployment Plan
- VM name: `netapp-nfs-ovf-preview-vm`
- OVF path: `template.ovf`
- Datastore: `netapp_nfs_ds01`
- Network: `VM Network`
- Disk provisioning: `thin`
- Power on: `False`

## Command Preview
- `govc datastore.info -json netapp_nfs_ds01`
- `govc import.spec template.ovf`
- `govc import.ovf -ds netapp_nfs_ds01 -name netapp-nfs-ovf-preview-vm -options <generated-options.json> template.ovf`
- `govc vm.info -json netapp-nfs-ovf-preview-vm`

## Required Flags
- `PROVIDER_MODE=local-lab-readwrite`
- `VM_DEPLOY_APPLY=true`
- `VM_DEPLOY_CONFIRM="DEPLOY ESXI OVF VM"`
- `VM_DEPLOY_ALLOW_CREATE=true`

## Blockers
- None

## Safety
- No VM, datastore, network, host, vCenter, or power write action is run unless apply gates pass.
