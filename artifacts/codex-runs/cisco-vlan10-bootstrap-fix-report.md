# Cisco VLAN 10 Bootstrap Fix Report

## Summary

- Checked at: `2026-06-07T12:55:44.526936+00:00`
- Provider mode: `local-lab-readwrite`
- Overall status: `completed`
- Management VLAN: `10`
- Management interface: `Vlan10`
- Management IP: `192.168.1.204`
- Management prefix: `/24`
- Bootstrap apply status: `not-attempted`
- Serial writes attempted: `False`
- Failure classification: `passed`

## Commands Sent

- none

## Planned Commands

- `terminal length 0`
- `configure terminal`
- `hostname lab-cisco-switch`
- `ip domain-name lab.local`
- `lldp run`
- `no ip http server`
- `no ip http secure-server`
- `vlan 10`
- ` name LAB-MGMT`
- `interface Vlan10`
- ` ip address 192.168.1.204 255.255.255.0`
- ` no shutdown`
- ` exit`
- `interface range Gi1/0/1,Gi1/0/2,Gi1/0/3,Gi1/0/4,Gi1/0/5,Gi1/0/6,Gi1/0/7,Gi1/0/8,Gi1/0/9,Gi1/0/10,Gi1/0/11,Gi1/0/12,Gi1/0/13,Gi1/0/14,Gi1/0/15,Gi1/0/16,Gi1/0/17,Gi1/0/18,Gi1/0/19,Gi1/0/20,Gi1/0/21,Gi1/0/22`
- ` switchport mode access`
- ` switchport access vlan 10`
- ` no shutdown`
- ` exit`
- `username REDACTED privilege 15 secret <redacted>`
- `crypto key generate rsa modulus 2048`
- `ip ssh version 2`
- `ip scp server enable`
- `line console 0`
- ` login local`
- ` exit`
- `line vty 0 31`
- ` login local`
- ` transport input ssh`
- ` exit`
- `end`
- `write memory`

## Switch Validation

- Vlan10 configured: `True`
- Vlan10 IP: `192.168.1.204`
- Vlan10 line state: `up`
- Vlan10 protocol state: `up`
- Always-access lab ports: `['Gi1/0/1']`
- Access port source: `always-access-plus-detected-show-interfaces-status`
- Configured/detected lab ports: `['Gi1/0/1', 'Gi1/0/2', 'Gi1/0/3', 'Gi1/0/4', 'Gi1/0/5', 'Gi1/0/6', 'Gi1/0/7', 'Gi1/0/8', 'Gi1/0/9', 'Gi1/0/10', 'Gi1/0/11', 'Gi1/0/12', 'Gi1/0/13', 'Gi1/0/14', 'Gi1/0/15', 'Gi1/0/16', 'Gi1/0/17', 'Gi1/0/18', 'Gi1/0/19', 'Gi1/0/20', 'Gi1/0/21', 'Gi1/0/22']`
- Ports assigned to VLAN 10: `['Gi1/0/1', 'Gi1/0/2', 'Gi1/0/3']`
- All configured/detected ports assigned to VLAN 10: `False`

## Ubuntu Route To Cisco

- Route status: `ready`
- Route: `192.168.1.204 dev enx607d09047834 src 192.168.1.30 uid 1000 cache`
- Interface: `enx607d09047834`
- Source IP: `192.168.1.30`

## Network Reachability

- Ping: `ok`
- SSH TCP/22 reachable: `True`
- SCP TCP/22 readiness: `True`

## Failure Classification Guide

- `config`: expected VLAN 10, SVI, local admin, SSH/SCP, or line login config was not confirmed.
- `config` also includes `interface Vlan10` using an IP other than `192.168.1.204`.
- `svi_down`: `interface Vlan10` exists but line/protocol is not up/up.
- `port_down`: no selected/detected access port is confirmed in VLAN 10.
- `host_routing`: switch-side validation looks usable, but Ubuntu cannot route/reach `192.168.1.204`.
- `passed`: switch-side validation and Ubuntu reachability passed.

## Blockers

- none

## Safety

- Local admin secret values are redacted.
- Raw console output and raw running-config are not saved.
- `write memory` is only sent by the guarded apply path.
