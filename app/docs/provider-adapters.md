# Provider Adapters

Provider adapters isolate infrastructure-specific behavior from API routes and
workflow lifecycle code.

## Current MVP Adapters

- vSphere: mocked implementation for plan and execute.
- NetBox/Nautobot source of truth: mocked catalog validation.
- AWX/Ansible: mocked health only.
- Terraform/OpenTofu: mocked health only.
- HPE iLO/Redfish: local configuration preview plus explicit GET-only probe.
- Cisco console: dynamic local serial discovery plus explicit read-only probe.
- Cisco Ansible SSH: management-IP readiness gated by `CISCO_MGMT_CONFIGURED`
  plus explicit read-only show-command probe.
- ESXi: local target preview gated by `ESXI_CONFIGURED` plus explicit HTTPS/TCP
  read-only probe.
- NetApp ONTAP (`netapp-ontap`): setup/status preview only, with planned target addressing,
  bootstrap/API/upgrade readiness placeholders, cluster/SVM/LIF intent, and
  disabled dangerous actions.
- network switch: mocked health only.

`PROVIDER_MODE=mock` remains the default. In mock mode, provider status may
inspect local serial device paths for Cisco console candidates, but no network
or serial probe is run automatically.

The backend resolves default adapters through `app.providers.registry`. The
current registry accepts `PROVIDER_MODE=mock` for workflow lifecycle execution.
Provider status also supports `PROVIDER_MODE=local-readonly` so an operator can
manually run guarded read-only iLO, Cisco, and ESXi probes from a local lab
machine.
Unsupported modes raise a provider registry error.

## Local Read-Only Preview Mode

Optional local lab settings must be placed in `.env.local.real-lab` at the
repository root. This file is ignored by Git and must not be committed. Provider
status responses expose local provider values only as configured/missing flags.
Probe results redact configured endpoints, users, passwords, tokens, cookies,
and other sensitive fields before caching or returning them.

ESXi and Cisco management targets distinguish planned addressing from a
configured, reachable management network:

- `ESXI_CONFIGURED=false` means `ESXI_TEST_HOST` may be a planned management IP,
  but ESXi HTTPS/SSH probes are skipped and the status is reported as
  `planned-target` or `not-configured`.
- `CISCO_MGMT_CONFIGURED=false` means `CISCO_TARGET_IP` may be a planned
  management IP, but Cisco SSH/Ansible probes are skipped and the status is
  reported as `awaiting-bootstrap`.
- Cisco console discovery remains active regardless of
  `CISCO_MGMT_CONFIGURED`; if no serial device is found the console status
  reports `missing-console` with cable, USB path, and permissions guidance.

Supported local variables:

- `ILO_TEST_HOST`
- `ILO_TEST_USERNAME`
- `ILO_TEST_PASSWORD`
- `ILO_TEST_VERIFY_TLS` (`true` by default; set `false` for lab self-signed TLS)
- `ILO_TEST_TIMEOUT_SECONDS` (`3.0` by default)
- `ESXI_CONFIGURED` (`false` by default; set `true` only after ESXi management
  networking is configured)
- `ESXI_TEST_HOST`
- `ESXI_TEST_USERNAME`
- `ESXI_TEST_PASSWORD`
- `ESXI_TEST_VERIFY_TLS` (`true` by default; set `false` for lab self-signed TLS)
- `ESXI_TEST_TIMEOUT_SECONDS` (`3.0` by default)
- `CISCO_CONSOLE_PORT`
- `CISCO_CONSOLE_BAUD` (`9600` by default)
- `CISCO_CONSOLE_TIMEOUT_SECONDS` (`2.0` by default)
- `CISCO_MGMT_CONFIGURED` (`false` by default; set `true` only after console
  bootstrap has configured Cisco management IP/SSH)
- `CISCO_TARGET_IP`
- `CISCO_TEST_USERNAME`
- `CISCO_TEST_PASSWORD`
- `CISCO_ENABLE_PASSWORD`
- `ANSIBLE_CISCO_NETWORK_OS` (`cisco.ios.ios` by default)
- `ANSIBLE_CISCO_CONNECTION` (`ansible.netcommon.network_cli` by default)
- `LAB_CLOSED_LOOP_ACK` (`YES` required for real lab probes)
- `LAB_READONLY_ACK` (`YES` required for real lab probes)
- `LAB_DESTRUCTIVE_ACK` (`REBUILD_LAB` required before future destructive plans can apply)

If `CISCO_CONSOLE_PORT` is not set, the backend dynamically discovers
candidates from:

- `/dev/serial/by-id/*`
- `/dev/ttyUSB*`
- `/dev/ttyACM*`

Discovery prefers stable `/dev/serial/by-id/*` paths. If exactly one stable
candidate exists, it is marked as the recommended default. Multiple candidates
return `needs-selection`, and no candidates return `missing-console`.
Discovery does not open serial ports, send commands, or require the user to run
`ls /dev/serial/by-id` manually.

`local-readonly` probes never run on page load. They run only from an explicit
Provider Status action.

## Read-Only Probe Boundaries

iLO / Redfish probes may only issue GET requests for:

- service root
- manager summary
- system summary
- chassis summary
- power and thermal summaries when linked by Redfish
- firmware inventory summary when linked by Redfish

The adapter uses short timeouts, configurable TLS verification, HTTP basic auth,
and response/error redaction. Passwords are never returned in API responses.

Cisco console probes may only:

- open the selected serial port after explicit operator action
- send a newline to detect the prompt
- run these safe show commands when already at an exec prompt:
  - `show version`
  - `show inventory`
  - `show interfaces status`
  - `show ip interface brief`
  - `show vlan brief`

The Cisco adapter never sends `enable`, `conf t`, `write memory`, `reload`,
`erase startup-config`, `copy`, or persistent configuration commands. If the
console prompts for login, password, setup wizard input, enable, or appears to
be in config mode, the probe reports a blocked state instead of guessing
credentials. Console probe responses summarize prompt state and command output
byte counts; raw prompt text and raw show-command output are not cached or
returned.

Cisco Ansible probes may only:

- check TCP reachability to SSH
- run `ansible --version`
- parse a generated temporary inventory with `ansible-inventory --graph`
- run fixed read-only `cisco.ios.ios_command` show commands:
  - `show version`
  - `show inventory`
  - `show interfaces status`
  - `show ip interface brief`
  - `show vlan brief`

The generated inventory is local, temporary, mode `0600`, and deleted after the
probe. The adapter never accepts arbitrary Ansible variables or free-form
commands from the UI. Show-command subprocess results keep return codes and
output byte counts only; raw device output is not cached or returned.

ESXi probes may only:

- check TCP reachability to HTTPS and SSH
- issue HTTPS GET requests for `/`, `/ui/`, and `/sdk/vimServiceVersions.xml`
- summarize VIM service versions when that XML is reachable
- report local `govc`, PowerCLI, and pyVmomi availability

The ESXi adapter does not reinstall, reboot, change networking, add/remove
datastores, create/delete VMs, deploy OVFs, power VMs, change firewall settings,
or run host configuration commands.

NetApp setup preview may only:

- display planned Controller SP, cluster management, node management, SVM
  management, and iSCSI LIF addresses
- report `NETAPP_CONFIGURED` as a presence flag
- show console/bootstrap, ONTAP API, and upgrade readiness placeholders
- show cluster/SVM/LIF intent and artifact/report placeholders
- serve `GET /api/v1/providers/netapp-ontap/plan-preview` from local planned
  values only, for future Run Center and artifact/report handoff

While `NETAPP_CONFIGURED=false`, ONTAP API readiness is disabled and no probe is
available. The adapter does not configure ONTAP, create clusters, change IPs,
create SVMs, create LIFs, create volumes, upload images, upgrade ONTAP, reboot
controllers, wipe disks, or apply changes.

## Optional Provider Smoke

Manual local smoke:

```bash
PROVIDER_MODE=local-readonly make provider-smoke
```

The backend loads local provider values from `.env.local.real-lab`, but ignores
`PROVIDER_MODE` from that file so default app and test startup remains mock.
Plain `make provider-smoke` runs in mock mode and skips probes. With explicit
`PROVIDER_MODE=local-readonly`, the smoke command dynamically discovers Cisco
console candidates, performs configured read-only probes, skips ESXi/Cisco
management network checks while their configured flags are false, skips probes
when local config or hardware is absent, and exits successfully for missing lab
hardware. It writes sanitized JSON and Markdown reports under ignored
`artifacts/real-lab/`, redacts sensitive values, and must not be used with
production infrastructure credentials.

## Interface Expectations

Real adapters should implement small interfaces:

- `health()`
- `probe()` for explicit read-only checks
- `plan_*()`
- `execute_*()`

The workflow service should not know vendor API details. It should receive a
plan and result object from adapters and persist them.

Workflow lifecycle code depends on adapter protocols and accepts injected
adapters for tests. Default local execution uses the mock registry.

## Real Adapter Requirements

A real provider adapter must:

- default to disabled or dry-run mode
- require explicit configuration
- use credential references only
- never log secret values
- support dry-run or plan before execution
- expose provider task identifiers where available
- convert vendor errors into structured application errors
- record audit events through workflow services

## Source Of Truth

Source-of-truth adapters validate whether requested values exist and are allowed.
For example, a VM deployment request should validate:

- environment exists
- site exists
- cluster belongs to site
- template exists
- network/VLAN exists
- datastore or storage tier exists

The MVP uses in-memory mock catalog data. Future NetBox or Nautobot adapters
should replace that mock without changing API routes.
