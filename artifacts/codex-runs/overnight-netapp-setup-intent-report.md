# Overnight NetApp Setup Intent Report

## Intent Defaults

The setup intent now fills non-secret defaults from the active lab profile and repo defaults:

- Cluster name: `lab-netapp-cluster`
- Node A name: `lab-netapp-node-a`
- Node B name: `lab-netapp-node-b`
- SVM name: `esxi_svm`
- DNS: populated from the active lab/default gateway path.
- NTP: populated from the active lab/control host path.
- Search domain: `lab.local`
- Storage protocol: `nfs`
- NFS volume: `esxi_datastore_01`
- NFS mount path: `/esxi_datastore_01`
- Export policy: `esxi_nfs_policy`
- Export client match: `192.168.1.0/24`
- NFS LIFs: `192.168.1.230`, `192.168.1.231`
- Datastore name: `netapp_nfs_ds01`

## Remaining Missing Field

- `admin_access_source`

Credential values were not invented and were not printed. NetApp API access remains missing:

- `NETAPP_API_USERNAME`
- `NETAPP_API_PASSWORD`

## Evidence

- `artifacts/codex-runs/netapp-setup-plan-report.md`
- `artifacts/codex-runs/netapp-setup-preview-report.md`
