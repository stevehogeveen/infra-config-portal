# vCenter-NetApp Readiness Report

- Checked at: `2026-06-09T23:20:11.599603+00:00`
- Status: `blocked_by_prior_stage`
- Source type: `live_probe`
- NetApp stage: `cluster_setup_wizard`
- Apply enabled: `False`

## Targets
- vcenter: `not configured`
- esxi_management: `192.168.1.203`
- netapp_cluster_management: `192.168.1.220`
- netapp_nfs_lif: `192.168.1.230`
- datastore_name: `netapp_nfs_ds01`

## Blockers
- NetApp is still at cluster_setup_wizard; ONTAP, NFS, and datastore readiness are blocked by prior setup.

## Warnings
- Preview only. No ONTAP, vCenter, ESXi, NFS, datastore, or storage write action is run.
- NetApp API credential fields are missing: NETAPP_API_USERNAME, NETAPP_API_PASSWORD.

## Checks
- vcenter_configured: `not_configured` - VCENTER_HOST / GOVC_URL is not configured.
- govc_available: `not_configured` - govc is not installed or not on PATH.
- vcenter_credentials_configured: `not_configured` - vCenter credential fields are missing: VCENTER_USERNAME/GOVC_USERNAME, VCENTER_PASSWORD/GOVC_PASSWORD.
- esxi_management_reachable: `blocked` - TCP 443 check failed with TimeoutError.
- netapp_cluster_management_reachable: `not_checked` - Reachability not checked in this read.
- netapp_nfs_lif_reachable: `not_checked` - Reachability not checked in this read.
- netapp_nfs_planned: `ready` - NetApp NFS volume, export policy, mount path, and datastore name are planned.
- netapp_nfs_exists: `not_checked` - ONTAP API existence checks are not attempted until ONTAP is configured and credentials are present.
- datastore_mounted: `not_checked` - vCenter/ESXi datastore inventory is not checked until vCenter/govc and NetApp NFS are ready.

## Safety
- No datastore, ONTAP, vCenter, ESXi, NFS, or storage write action was run.
