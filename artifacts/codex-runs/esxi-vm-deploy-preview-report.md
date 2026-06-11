# ESXi VM Deploy Vm Deploy Preview Report

- Checked at: `2026-06-11T02:34:36.715815+00:00`
- Status: `blocked`
- Apply enabled: `False`
- Provider mode: `local-lab-readwrite`
- ESXi configured: `True`
- govc available: `True`
- Target datastore visible: `False`

## Deployment Plan
- VM name: `netapp-nfs-ovf-preview-vm`
- OVF path: `artifacts/Media/OVF_Templates/DepOps_W2K22_Template_VMware7.0_Feb2025-1.0/DepOps_W2K22_Template_VMware7.0_Feb2025-v1.0.ovf`
- Datastore: `netapp_nfs_ds01`
- Network: `VM Network`
- Disk provisioning: `thin`
- Power on: `False`

## Command Preview
- `govc datastore.info -json netapp_nfs_ds01`
- `govc import.spec artifacts/Media/OVF_Templates/DepOps_W2K22_Template_VMware7.0_Feb2025-1.0/DepOps_W2K22_Template_VMware7.0_Feb2025-v1.0.ovf`
- `govc import.ovf -ds netapp_nfs_ds01 -name netapp-nfs-ovf-preview-vm -options <generated-options.json> artifacts/Media/OVF_Templates/DepOps_W2K22_Template_VMware7.0_Feb2025-1.0/DepOps_W2K22_Template_VMware7.0_Feb2025-v1.0.ovf`
- `govc vm.info -json netapp-nfs-ovf-preview-vm`

## Required Flags
- `PROVIDER_MODE=local-lab-readwrite`
- `VM_DEPLOY_APPLY=true`
- `VM_DEPLOY_CONFIRM="DEPLOY ESXI OVF VM"`
- `VM_DEPLOY_ALLOW_CREATE=true`

## Blockers
- Target datastore `netapp_nfs_ds01` is not visible to direct ESXi govc.
- NetApp NFS datastore is selected but is not mounted on ESXi yet.

## Safety
- No VM, datastore, network, host, vCenter, or power write action is run unless apply gates pass.
