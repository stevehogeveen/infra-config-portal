# Lab IP Profile Hardening Report

- Checked at: `2026-06-07T01:16:49.658689+00:00`
- Classification: `passed`
- Status: `ready`
- Provider mode: `local-lab-readwrite`

## Current Profile

- Lab subnet: `192.168.1.0/24`
- iLO: `192.168.1.201`
- Server embedded NIC: `192.168.1.202`
- ESXi management: `192.168.1.203`
- Cisco management: `192.168.1.204`
- Ansible/control host: `192.168.1.205`

## Stale Detection

- No active Build Verification input contains `10.10.8.x`.
- Stale report evidence: `artifacts/codex-runs/overnight-lab-builder-final-report.md` should be regenerated.

## Next Action

- Active lab IP profile matches 192.168.1.0/24 with devices at 192.168.1.200+.
