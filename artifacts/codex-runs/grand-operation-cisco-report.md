# Grand Operation Cisco Report

- Generated at: `2026-06-10T22:47:34.018362+00:00`
- Scope: real-lab Cisco switch Stage 3.
- Credentials: configured locally and redacted; no secret values are stored in this report.

## Status

- Overall status: `ready`
- Console: discovered on Prolific USB serial at 9600 baud.
- Privileged exec: confirmed earlier in Cisco console workflow artifacts.
- Management IP: `192.168.1.204` on `Vlan10`, line/protocol `up/up`.
- Host reachability: ping passed; TCP/22 passed.
- SSH login: `ready`; privileged prompt `True`.
- SCP probe: `ready`; upload succeeded and cleanup removed `flash:/codex_scp_probe.txt`.
- IOS XE version: `17.15.05`; model hint: `C9300-24T`.
- Firmware upgrade: not performed because the switch is already running `17.15.05`, matching the local `cat9k_iosxe.17.15.05.SPA.bin` image.

## Configured Or Validated

- Hostname: present in running config summary.
- VLAN 10: present and active.
- VLAN 10 access ports seen: `['Gi1/0/1,', 'Gi1/0/10,', 'Gi1/0/11,', 'Gi1/0/12,', 'Gi1/0/13,', 'Gi1/0/14,', 'Gi1/0/15,', 'Gi1/0/16,', 'Gi1/0/17,', 'Gi1/0/18,', 'Gi1/0/19,', 'Gi1/0/2,', 'Gi1/0/20,', 'Gi1/0/21,', 'Gi1/0/22', 'Gi1/0/3,', 'Gi1/0/4,', 'Gi1/0/5,', 'Gi1/0/6,', 'Gi1/0/7,', 'Gi1/0/8,', 'Gi1/0/9,']`.
- SSH: enabled as version 2.0.
- SSH host key: generated and bound with label `LAB-SSH-HOSTKEY`.
- SCP: `ip scp server enable` present; real SCP upload/delete probe passed.
- VTY: `login local` and `transport input ssh` validated.
- Legacy management: HTTP and HTTPS disabled; Telnet not allowed on VTY.
- SNMP: absent, matching active profile `enable_snmp=false`.
- IPv6: unicast routing not present, matching active profile `disable_ipv6=true`.
- Startup config: saved after SSH host-key remediation.

## Active Profile Notes

- Active profile enables DNS but has no DNS servers; no Cisco DNS servers were required.
- Active profile enables NTP but has no NTP servers; no Cisco NTP servers were required.
- Active profile has no MTU value; Cisco management MTU was inspected only.

## Fixes Made During Stage

- Fixed app media/toolchain issues earlier in the run that surfaced while preparing this stage.
- Fixed Cisco bootstrap access-port configuration to send per-interface commands instead of a long interface range.
- Fixed Cisco bootstrap SSH host-key creation to use a labeled 2048-bit RSA key and bind `ip ssh rsa keypair-name`.
- Fixed Cisco failure classification so ping-ready/TCP-22-refused states report `ssh_service` instead of `host_routing`.
- Terminated one stuck serial bootstrap process after it exceeded normal waits, then completed SSH remediation with a narrower bounded console sequence.

## Artifacts

- `artifacts/codex-runs/cisco-ssh-validation-redacted.json`
- `artifacts/codex-runs/cisco-scp-validation-redacted.json`
- `artifacts/codex-runs/cisco-service-policy-validation-redacted.json`
- `artifacts/codex-runs/cisco-ssh-hostkey-remediation-redacted.json`
- `artifacts/codex-runs/cisco-4h-lab-run-details-redacted.json`
- `artifacts/codex-runs/cisco-scp-validation-report.md`
- `artifacts/codex-runs/cisco-ssh-validation-report.md`
- `artifacts/codex-runs/cisco-service-policy-validation-report.md`
- `artifacts/codex-runs/cisco-ssh-hostkey-remediation-report.md`

## Remaining Cisco Blockers

- none

## Next Action

- Continue to Stage 4 HPE iLO/server inventory using `192.168.1.201`.
