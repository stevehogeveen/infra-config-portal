# ESXi Management Readdress Report

Date: 2026-06-07T13:22:05Z
Mode: `local-lab-readwrite`
Status: complete

## Intended Lab Profile

- iLO: `192.168.1.201`
- Server embedded NIC / temporary host address: `192.168.1.202`
- ESXi management: `192.168.1.203`
- Cisco management: `192.168.1.204`
- Ansible/control host: `192.168.1.205`

## Old Lab-Builder Lesson Applied

The older lab-builder flow treated a rebuild as a staged workflow: discover the
live state first, compare it to the intended profile, make the smallest safe
correction, then validate from the operator-facing endpoint.

That pattern avoided an unnecessary reinstall here. ESXi was already installed
and healthy, but it was still using the old management address.

## Before

- `192.168.1.202` responded to ping.
- `192.168.1.202` accepted HTTPS on port `443`.
- `192.168.1.202` accepted SSH on port `22`.
- `192.168.1.202` accepted ESXi service traffic on port `902`.
- `192.168.1.202` exposed `/sdk/vimServiceVersions.xml`.
- `192.168.1.203` did not respond before the change.
- SSH readback from the live host showed `vmk0` configured as
  `192.168.1.202/24` with gateway `192.168.1.1`.

## Change Applied

The ESXi management VMkernel interface was moved to the corrected lab address:

- Interface: `vmk0`
- Address: `192.168.1.203`
- Netmask: `255.255.255.0`
- Gateway: `192.168.1.1`

No ESXi reinstall, reboot, datastore change, VM operation, or firewall change
was performed.

## After

- `192.168.1.203` responded to ping.
- `192.168.1.203` accepted SSH on port `22`.
- `192.168.1.203` accepted HTTPS on port `443`.
- `192.168.1.203` accepted ESXi service traffic on port `902`.
- `192.168.1.202` no longer responded to ping.
- SSH readback from `192.168.1.203` confirmed:
  - Product: `VMware ESXi 8.0.3 build-24859861`
  - Hostname: `HomeEsxi.`
  - `vmk0`: `192.168.1.203/24`, static, gateway `192.168.1.1`

## App Validation

- `.env.local.real-lab` was updated locally so ESXi is marked configured and
  points at the corrected target. Secrets were not printed or saved in this
  report.
- Backend config loading now treats an isolated real-lab `.env.local.real-lab`
  file as authoritative for real-lab values while still allowing the launch
  command to control `PROVIDER_MODE`.
- Provider status now reports `esxi-readonly` as `ready`.
- The ESXi read-only provider probe completed with status `ok`.
- HTTPS reachability: reachable on port `443`.
- SSH reachability: reachable on port `22`.
- Vim service versions: available, including `8.0.3.0`.
- Tool availability:
  - `govc`: unavailable
  - PowerCLI: unavailable
  - pyVmomi: unavailable

## ESXi Install Readiness

`artifacts/codex-runs/esxi-install-readiness-report.md` was refreshed after the
address correction.

- Inventory: `ProLiant DL360 Gen10`
- Power state: `On`
- Virtual media support: available
- ISO-capable virtual media: available
- One-time boot support: available
- BIOS settings discovery: available
- ESXi ISO candidates: found
- Status: `ready`

## Remaining Gaps

- The app has not removed or re-added this ESXi host in vCenter because no
  vCenter/govc target is configured in this workflow.
- `govc`, PowerCLI, and pyVmomi are not currently available to the backend.
- Automated ESXi reinstall was not run because the installed host was healthy
  and only needed the management IP corrected.
