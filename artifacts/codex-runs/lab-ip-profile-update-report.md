# Lab IP Profile Update

- Checked at: `2026-06-08T14:47:17.555667+00:00`
- Status: `blocked`
- Provider mode: `mock`

## Expected Profile

- subnet: `192.168.1.0/24`
- ilo: `192.168.1.201`
- server_embedded_nic: `192.168.1.202`
- esxi_management: `192.168.1.203`
- cisco_management: `192.168.1.204`
- ansible_control_host: `192.168.1.205`
- netapp_controller_a_sp: `192.168.1.206`
- netapp_controller_b_sp: `192.168.1.207`
- netapp_cluster_mgmt: `192.168.1.208`
- netapp_node_a_mgmt: `192.168.1.209`
- netapp_node_b_mgmt: `192.168.1.210`
- netapp_svm_mgmt: `192.168.1.211`
- netapp_iscsi_lifs: `192.168.1.212,192.168.1.213,192.168.1.214,192.168.1.215`

## Configured Values

- subnet: `192.168.1.0/24`
- ilo: `192.168.1.201`
- server_embedded_nic: `192.168.1.202`
- esxi_management: `192.168.1.203`
- cisco_management: `192.168.1.204`
- ansible_cisco_inventory_target: `192.168.1.204`
- ansible_control_host: `192.168.1.205`
- cisco_target_ip_env: `192.168.1.204`
- ansible_cisco_host_env: `192.168.1.204`
- netapp_controller_a_sp: `192.168.1.206`
- netapp_controller_b_sp: `192.168.1.207`
- netapp_cluster_mgmt: `192.168.1.208`
- netapp_node_a_mgmt: `192.168.1.209`
- netapp_node_b_mgmt: `192.168.1.210`
- netapp_svm_mgmt: `192.168.1.211`
- netapp_iscsi_lifs: `192.168.1.212,192.168.1.213,192.168.1.214,192.168.1.215`
- netapp_cluster_mgmt_ip_env: `10.10.8.45`

## Stale Assumptions

- `netapp_cluster_mgmt_ip_env` still contains stale `10.10.8.45`

## Stale Report Evidence

- `artifacts/codex-runs/overnight-lab-builder-final-report.md` contains stale `10.10.8.x` evidence. Regenerate this report after confirming the 192.168.1.0/24 lab profile.

## Mismatches

- No lab IP profile mismatches.

## Ansible Role

- Cisco first contact/bootstrap remains console.
- Ansible starts after Cisco management SSH is configured at `192.168.1.204`.
- Ansible is for show commands, backup, validation, drift checks, and future repeatable config.
- Ansible is not the initial Cisco bootstrap path.

## Reports

- Build verification report: `artifacts/codex-runs/build-verification-report.md`
- Build verification summary: `artifacts/codex-runs/build-verification-summary-redacted.json`