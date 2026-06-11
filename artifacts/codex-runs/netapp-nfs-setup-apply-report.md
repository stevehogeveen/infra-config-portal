# NetApp NFS Setup Apply Report

- Checked at: `2026-06-11T02:22:05.283923+00:00`
- Status: `blocked`
- Apply enabled: `False`
- Configured state: `login_required`
- API access present: `False`
- ONTAP writes attempted: `False`
- ESXi/vCenter writes attempted: `False`

## NFS Plan
- SVM: `esxi_svm`
- SVM management IP: `192.168.1.223`
- NFS LIFs: `192.168.1.230, 192.168.1.231`
- Volume: `esxi_datastore_01`
- Mount path: `/esxi_datastore_01`
- Export policy: `esxi_nfs_policy`
- Client match: `192.168.1.0/24`
- Datastore: `netapp_nfs_ds01`

## Required Flags
- `PROVIDER_MODE=local-lab-readwrite`
- `NETAPP_NFS_SETUP_APPLY=true`
- `NETAPP_NFS_SETUP_CONFIRM="APPLY NETAPP NFS SETUP"`
- `NETAPP_NFS_SETUP_ALLOW_STORAGE_CREATE=true`

## Blockers
- NetApp ONTAP cluster is not live-configured yet; NFS setup is blocked by prior cluster setup.
- NetApp API access fields are missing: NETAPP_API_USERNAME, NETAPP_API_PASSWORD.
- NETAPP_NFS_SETUP_APPLY=true is required.
- NETAPP_NFS_SETUP_CONFIRM="APPLY NETAPP NFS SETUP" is required.
- NETAPP_NFS_SETUP_ALLOW_STORAGE_CREATE=true is required.

## Safety
- NFS only. iSCSI is not used by this workflow.
- Secrets are represented only as configured/missing/redacted state.
