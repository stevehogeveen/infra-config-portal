# vCenter-NetApp Datastore Plan Report

- Generated at: `2026-06-09T23:20:11.599603+00:00`
- Apply enabled: `False`
- Plan type: `preview_only`

## Planned NFS
- Volume: `esxi_datastore_01`
- Export policy: `esxi_nfs_policy`
- Mount path: `/esxi_datastore_01`
- Datastore: `netapp_nfs_ds01`
- NFS LIFs: `192.168.1.230, 192.168.1.231`

## Command Preview
- govc: `govc datastore.create -type nfs -name netapp_nfs_ds01 -remote-host 192.168.1.230 -remote-path /esxi_datastore_01`
- ESXi fallback: `esxcli storage nfs add -H 192.168.1.230 -s /esxi_datastore_01 -v netapp_nfs_ds01`

## Safety
- This is not runnable apply logic.
- Future apply must require fresh discovery, approval, audit logging, and explicit write gates.
