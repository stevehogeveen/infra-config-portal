# Lab IP Profile Hardening Report

- Checked at: `2026-06-10T15:39:22.887875+00:00`
- Classification: `stale_config`
- Status: `blocked`
- Source: `test_fixture`
- Freshness: `unknown`

## Current Profile

- Lab subnet: `192.168.1.0/24`
- iLO: `192.168.1.201`
- Server embedded NIC: `192.168.1.202`
- ESXi management: `192.168.1.203`
- Cisco management: `192.168.1.204`
- Ansible/control host: `192.168.1.205`
- NetApp Controller A SP: `192.168.1.210`
- NetApp Controller B SP: `192.168.1.211`
- NetApp cluster management: `192.168.1.220`
- NetApp Node A management/e0M: `192.168.1.221`
- NetApp Node B management/e0M: `192.168.1.222`
- NetApp SVM management: `192.168.1.223`
- NetApp NFS LIFs: `192.168.1.230,192.168.1.231`
- NetApp iSCSI LIFs: `192.168.1.240,192.168.1.241,192.168.1.242,192.168.1.243`

## Stale Detection

- Active field `netapp_cluster_mgmt` contains stale `10.10.8.45`.
- Active field `netapp_cluster_mgmt_ip_env` contains stale `10.10.8.45`.
- Stale report evidence: `artifacts/codex-runs/overnight-lab-builder-final-report.md` should be regenerated.

## Next Action

- Update provider environment inputs to match `Runtime environment` or remove out-of-scope overrides before certification.
