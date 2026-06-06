# Lab IP Profile Hardening Report

- Checked at: `2026-06-06T18:52:38.681419+00:00`
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

## Stale Detection

- Active field `esxi_management` contains stale `10.10.8.203`.
- Active field `cisco_management` contains stale `10.10.8.112`.
- Active field `ansible_cisco_inventory_target` contains stale `10.10.8.112`.
- Stale report evidence: `artifacts/codex-runs/overnight-lab-builder-final-report.md` should be regenerated.

## Next Action

- Update active lab inputs to 192.168.1.201-.205 and remove stale 10.10.8.x values before certification.
