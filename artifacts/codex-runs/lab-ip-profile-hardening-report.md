# Lab IP Profile Hardening Report

- Checked at: `2026-06-08T14:47:17.555667+00:00`
- Classification: `stale_config`
- Status: `blocked`
- Provider mode: `mock`

## Current Profile

- Lab subnet: `192.168.1.0/24`
- iLO: `192.168.1.201`
- Server embedded NIC: `192.168.1.202`
- ESXi management: `192.168.1.203`
- Cisco management: `192.168.1.204`
- Ansible/control host: `192.168.1.205`
- NetApp Controller A SP: `192.168.1.206`
- NetApp Controller B SP: `192.168.1.207`
- NetApp cluster management: `192.168.1.208`
- NetApp Node A management/e0M: `192.168.1.209`
- NetApp Node B management/e0M: `192.168.1.210`
- NetApp SVM management: `192.168.1.211`
- NetApp iSCSI LIFs: `192.168.1.212,192.168.1.213,192.168.1.214,192.168.1.215`

## Stale Detection

- Active field `netapp_cluster_mgmt_ip_env` contains stale `10.10.8.45`.
- Stale report evidence: `artifacts/codex-runs/overnight-lab-builder-final-report.md` should be regenerated.

## Next Action

- Update provider environment inputs to match `Runtime environment` and remove stale 10.10.8.x values before certification.
