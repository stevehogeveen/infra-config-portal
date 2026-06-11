# Overnight ESXi NetApp Datastore Report

## Desired Datastore

- Datastore name: `netapp_nfs_ds01`
- Remote host: `192.168.1.230`
- Remote path: `/esxi_datastore_01`
- Backing volume: `esxi_datastore_01`

## Result

- ESXi management: reachable over HTTPS and SSH.
- ESXi installed version: VMware ESXi 8.0.3 build 24859861.
- NetApp NFS datastore mount: not attempted.
- `netapp_nfs_ds01` visibility through direct ESXi govc: not visible.

## Blockers

- NetApp ONTAP/NFS is not configured yet.
- NetApp cluster management REST is not reachable.
- NetApp API access is missing.
- vCenter/govc target is not configured for vCenter workflows.

## Evidence

- `artifacts/codex-runs/netapp-nfs-vcenter-readiness-report.md`
- `artifacts/codex-runs/vcenter-netapp-datastore-plan-report.md`
- `artifacts/codex-runs/esxi-vm-deploy-preview-report.md`
- `artifacts/codex-runs/esxi-vm-deploy-validation-report.md`
