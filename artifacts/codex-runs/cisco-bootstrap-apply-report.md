# Cisco Bootstrap Apply Report

## Apply Run

- Checked at: `2026-06-07T11:47:20.408364+00:00`
- Provider mode: `local-lab-readwrite`
- Management IP requested: `192.168.1.204`
- Console adapter: `/dev/serial/by-id/usb-Prolific_Technology_Inc._USB-Serial_Controller_D-if00-port0`
- Selected baud: `9600`
- Privileged exec reached: `True`
- Privilege level readback: `15`
- Bootstrap apply status: `completed`
- Serial writes attempted: `True`
- `write memory` sent: `True`
- Reload attempted: `False`

## Commands Sent

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
- `interface range Gi1/0/2,Gi1/0/3,Gi1/0/4,Gi1/0/5,Gi1/0/6,Gi1/0/7,Gi1/0/8,Gi1/0/9,Gi1/0/10,Gi1/0/11,Gi1/0/12,Gi1/0/13,Gi1/0/14,Gi1/0/15,Gi1/0/16,Gi1/0/17,Gi1/0/18,Gi1/0/19,Gi1/0/20,Gi1/0/21,Gi1/0/22`
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

## Follow-Up Validation

- Checked at: `2026-06-07T11:53:57.930892+00:00`
- Follow-up mode: read-only validation, no apply
- Overall validation status: `completed`
- Vlan10 configured: `True`
- Vlan10 IP: `192.168.1.204`
- Vlan10 line state: `up`
- Vlan10 protocol state: `up`
- Ports assigned to VLAN 10: `Gi1/0/2`, `Gi1/0/3`, `Gi1/0/4`
- Host route interface: `wlp0s20f3`
- Host route source IP: `192.168.1.19`
- Ping/SSH/SCP from Ubuntu: `failed`
- Failure classification: `host_routing`

## Safety

- No secrets were printed in this report.
- Raw console logs and raw running-config were not saved.
- Mock results were not used as substitutes for live-lab evidence.
