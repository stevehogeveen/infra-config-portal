# Lab IP Profile Update

- Checked at: `2026-06-06T18:52:38.681419+00:00`
- Status: `blocked`
- Provider mode: `mock`

## Expected Profile

- subnet: `192.168.1.0/24`
- ilo: `192.168.1.201`
- server_embedded_nic: `192.168.1.202`
- esxi_management: `192.168.1.203`
- cisco_management: `192.168.1.204`
- ansible_control_host: `192.168.1.205`

## Configured Values

- subnet: `192.168.1.0/24`
- ilo: `192.168.1.201`
- server_embedded_nic: `192.168.1.202`
- esxi_management: `10.10.8.203`
- cisco_management: `10.10.8.112`
- ansible_cisco_inventory_target: `10.10.8.112`
- ansible_control_host: `192.168.1.205`
- cisco_target_ip_env: `192.168.1.204`
- ansible_cisco_host_env: `192.168.1.204`

## Stale Assumptions

- `esxi_management` still contains stale `10.10.8.203`
- `cisco_management` still contains stale `10.10.8.112`
- `ansible_cisco_inventory_target` still contains stale `10.10.8.112`

## Stale Report Evidence

- `artifacts/codex-runs/overnight-lab-builder-final-report.md` contains stale `10.10.8.x` evidence. Regenerate this report after confirming the 192.168.1.0/24 lab profile.

## Mismatches

- `esxi_management` expected `192.168.1.203`, configured `10.10.8.203`
- `cisco_management` expected `192.168.1.204`, configured `10.10.8.112`

## Ansible Role

- Cisco first contact/bootstrap remains console.
- Ansible starts after Cisco management SSH is configured at `192.168.1.204`.
- Ansible is for show commands, backup, validation, drift checks, and future repeatable config.
- Ansible is not the initial Cisco bootstrap path.

## Reports

- Build verification report: `artifacts/codex-runs/build-verification-report.md`
- Build verification summary: `artifacts/codex-runs/build-verification-summary-redacted.json`