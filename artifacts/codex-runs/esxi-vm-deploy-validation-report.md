# ESXi VM Deploy Vm Deploy Validation Report

- Checked at: `2026-06-11T02:34:36.787734+00:00`
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

## Required Flags

## Blockers
- Target datastore `netapp_nfs_ds01` is not visible to direct ESXi govc.

## Safety
- No VM, datastore, network, host, vCenter, or power write action is run unless apply gates pass.
