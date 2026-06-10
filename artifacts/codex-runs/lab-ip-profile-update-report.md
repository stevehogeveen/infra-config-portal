# Lab IP Profile Update

- Checked at: `2026-06-10T21:52:14.333870+00:00`
- Status: `blocked`
- Source: `test_fixture`
- Freshness: `unknown`

## Expected Profile

- subnet: `192.168.1.0/24`
- ilo: `192.168.1.201`
- server_embedded_nic: `192.168.1.202`
- esxi_management: `192.168.1.203`
- cisco_management: `192.168.1.204`
- ansible_control_host: `192.168.1.205`
- netapp_controller_a_sp: `192.168.1.210`
- netapp_controller_b_sp: `192.168.1.211`
- netapp_cluster_mgmt: `192.168.1.220`
- netapp_node_a_mgmt: `192.168.1.221`
- netapp_node_b_mgmt: `192.168.1.222`
- netapp_svm_mgmt: `192.168.1.223`
- netapp_nfs_lifs: `192.168.1.230,192.168.1.231`
- netapp_iscsi_lifs: `192.168.1.240,192.168.1.241,192.168.1.242,192.168.1.243`

## Configured Values

- subnet: `192.168.1.0/24`
- ilo: `192.168.1.201`
- server_embedded_nic: `192.168.1.202`
- esxi_management: `192.168.1.203`
- cisco_management: `192.168.1.204`
- ansible_cisco_inventory_target: `192.168.1.204`
- ansible_control_host: `192.168.1.205`
- netapp_controller_a_sp: `192.168.1.210`
- netapp_controller_b_sp: `192.168.1.211`
- netapp_cluster_mgmt: `10.10.8.45`
- netapp_node_a_mgmt: `192.168.1.221`
- netapp_node_b_mgmt: `192.168.1.222`
- netapp_svm_mgmt: `192.168.1.223`
- netapp_nfs_lifs: `192.168.1.230,192.168.1.231`
- netapp_iscsi_lifs: `192.168.1.240,192.168.1.241,192.168.1.242,192.168.1.243`
- runtime_subnet_default: `192.168.1.0/24`
- runtime_provider_mode: `mock`
- cisco_target_ip_env: `192.168.1.204`
- ansible_cisco_host_env: `192.168.1.204`
- netapp_controller_a_sp_env: `192.168.1.210`
- netapp_controller_b_sp_env: `192.168.1.211`
- netapp_cluster_mgmt_ip_env: `10.10.8.45`
- netapp_node_a_mgmt_ip_env: `192.168.1.221`
- netapp_node_b_mgmt_ip_env: `192.168.1.222`
- netapp_svm_mgmt_ip_env: `192.168.1.223`
- netapp_nfs_lifs_env: `192.168.1.230,192.168.1.231`
- netapp_iscsi_lifs_env: `192.168.1.240,192.168.1.241,192.168.1.242,192.168.1.243`

## Stale Assumptions

- `netapp_cluster_mgmt` still contains stale `10.10.8.45`
- `netapp_cluster_mgmt_ip_env` still contains stale `10.10.8.45`

## Stale Report Evidence

- `artifacts/codex-runs/overnight-lab-builder-final-report.md` contains stale `10.10.8.x` evidence. Regenerate this report after confirming the 192.168.1.0/24 lab profile.

## Mismatches

- `netapp_cluster_mgmt` expected `192.168.1.220`, configured `10.10.8.45`

## Ansible Role

- Cisco first contact/bootstrap remains console.
- Ansible starts after Cisco management SSH is configured at `192.168.1.204`.
- Ansible is for show commands, backup, validation, drift checks, and future repeatable config.
- Ansible is not the initial Cisco bootstrap path.

## Reports

- Build verification report: `artifacts/codex-runs/build-verification-report.md`
- Build verification summary: `artifacts/codex-runs/build-verification-summary-redacted.json`