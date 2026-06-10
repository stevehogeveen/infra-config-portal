# NetApp Setup Preview Report

- Checked at: `2026-06-10T00:36:28.423477+00:00`
- Status: `blocked`
- Detected state: `cluster_setup_wizard`
- Apply enabled: `False`
- Apply command: `NETAPP_SETUP_APPLY=true NETAPP_SETUP_CONFIRM="APPLY NETAPP CLUSTER SETUP" NETAPP_SETUP_ALLOW_CLUSTER_CREATE=true PROVIDER_MODE=local-lab-readwrite make provider-lab-netapp-setup-apply`

## Setup Intent
- cluster_name: `None`
- node_a_name: `None`
- node_b_name: `None`
- cluster_mgmt_ip: `192.168.1.220`
- node_a_mgmt_ip: `192.168.1.221`
- node_b_mgmt_ip: `192.168.1.222`
- svm_name: `None`
- svm_mgmt_ip: `192.168.1.223`
- nfs_lifs: `['192.168.1.230', '192.168.1.231']`
- nfs_volume: `esxi_datastore_01`
- nfs_mount_path: `/esxi_datastore_01`
- export_policy: `esxi_nfs_policy`
- export_client_match: `192.168.1.0/24`
- dns_servers: `[]`
- ntp_servers: `[]`
- search_domains: `[]`
- admin_access_source: `None`
- admin_access_configured: `False`
- admin_access_redacted: `True`

## Remediation Items
- `cluster_name`: set `.env.local.real-lab: NETAPP_CLUSTER_NAME` suggested `lab-ontap-cluster-01`; recheck `make provider-lab-netapp-setup-preview`
- `node_a_name`: set `.env.local.real-lab: NETAPP_NODE_A_NAME` suggested `netapp-a`; recheck `make provider-lab-netapp-setup-preview`
- `node_b_name`: set `.env.local.real-lab: NETAPP_NODE_B_NAME` suggested `netapp-b`; recheck `make provider-lab-netapp-setup-preview`
- `svm_name`: set `.env.local.real-lab: NETAPP_SVM_NAME` suggested `svm_esxi_nfs`; recheck `make provider-lab-netapp-setup-preview`
- `dns_servers`: set `.env.local.real-lab: NETAPP_DNS_SERVERS`; recheck `make provider-lab-netapp-setup-preview`
- `ntp_servers`: set `.env.local.real-lab: NETAPP_NTP_SERVERS`; recheck `make provider-lab-netapp-setup-preview`
- `search_domains`: set `.env.local.real-lab: NETAPP_SEARCH_DOMAINS`; recheck `make provider-lab-netapp-setup-preview`
- `admin_access_source`: set `.env.local.real-lab: NETAPP_ADMIN_ACCESS_SOURCE` suggested `.env.local.real-lab NetApp admin access reference`; recheck `make provider-lab-netapp-setup-preview`

## Address Conflict Scan
- Status: `not_checked` free=`False`

## Exact Changes
- cluster: Create or join cluster -> `None`
- cluster_mgmt: Assign cluster management IP -> `192.168.1.220`
- node_a: Assign node A name and management IP -> `missing / 192.168.1.221`
- node_b: Assign node B name and management IP -> `missing / 192.168.1.222`
- svm: Create SVM and management LIF -> `missing / 192.168.1.223`
- nfs: Create NFS LIFs -> `192.168.1.230, 192.168.1.231`
- nfs: Create datastore volume/export -> `esxi_datastore_01 at /esxi_datastore_01`
- services: Configure DNS, NTP, and search domains -> `operator-provided values required`

## Blockers
- Required NetApp setup intent fields are missing.

## Safety
- Preview only; no NetApp setup/apply/upgrade command was run.
- Secrets are represented only as configured/missing/redacted state.
