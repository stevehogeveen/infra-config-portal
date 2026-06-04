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
- NetApp ONTAP: mocked health only.
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

The iLO Provider Status panel also uses
`GET /api/v1/providers/ilo-redfish/readiness-summary` for a read-only summary
of connection readiness, cached GET-only endpoint detection, cached Redfish
discovery, desired setup sections, firmware/media readiness, report
placeholders, and disabled dangerous actions.
This endpoint does not run discovery or contact iLO. It only normalizes local
configuration presence flags, cached probe results, endpoint classification,
media metadata, and the plan-only upgrade decision model.

`GET /api/v1/providers/ilo-redfish/setup-plan-preview` builds a plan-only setup
preview from that readiness summary. It includes network, users, SNMP, NTP/time,
DNS/domain, firmware readiness handoff, and report/artifact placeholder
sections. The preview does not call iLO, does not collect media or artifacts,
does not apply settings, and keeps all dangerous actions disabled.

`GET` and `PUT /api/v1/providers/ilo-redfish/setup-intent` store desired iLO
setup intent locally for preview only. Intent covers network labels, desired
local usernames as labels, role intent, SNMP enabled state and reference labels,
NTP/time placeholders, DNS/domain placeholders, and notes. It must not contain
passwords, tokens, SNMP secrets, private keys, or real credential values. Saved
intent feeds setup-plan-preview section status as missing intent, planned,
blocked, warning, or already discovered when cached discovery can support that
classification. Saving intent never applies settings and never contacts iLO.

`GET /api/v1/providers/ilo-redfish/setup-compare` returns a read-only compare
report between saved setup intent and cached readiness/discovery only. Unknown
discovered values are reported as `discovered_unknown` and are not treated as
mismatches. Potentially sensitive desired values such as management addressing,
DNS, SNMP destinations, and user labels are represented as configured/missing
rather than echoed raw. Every compare section and row has `apply_enabled=false`.

`GET /api/v1/providers/ilo-redfish/report-preview` generates a redacted report
preview from readiness summary, desired setup intent, setup compare, setup plan
preview, destructive rebuild handoff preview, firmware readiness, media
inventory metadata, disabled actions, blockers, and warnings. It does not run
provider discovery or collect artifacts. The report represents host
credentials, management addressing, SNMP labels, local media paths, serial
values, and other sensitive data as configured, missing, counts, or placeholder
names only. The report has `apply_enabled=false`.

`GET /api/v1/providers/ilo-redfish/destructive-rebuild-preview` returns a
blocked future workflow handoff for a full destructive server rebuild. It
describes the future scope, including drive wipe, existing RAID/logical drive
deletion, new RAID/logical drive creation, boot/install media preparation, ESXi
install, and logs/reports/artifacts. It also lists prerequisites such as
verified iLO identity, discovered model, serial presence, iLO generation,
firmware knowledge, drive inventory, RAID plan, ESXi install media, final
dry-run plan, destructive confirmation, and a dedicated rebuild workflow. This
endpoint does not run discovery, does not call storage or ESXi systems, and does
not expose a destructive action. It always returns
`status=blocked_out_of_scope`, `destructive_enabled=false`, and
`apply_enabled=false` until a separate guarded bare-metal rebuild workflow owns
that lifecycle.

## iLO Plan-Only Workflow Checkpoint

The current iLO Provider Status workflow is a read-only, plan-only operator
surface. It is organized around these sections:

- Overview / Readiness: summarizes connection configuration flags, cached
  GET-only endpoint classification, Redfish root status, legacy endpoint
  status, web endpoint status, Redfish discovery availability, last probe
  status, model/generation, firmware, media inventory mode, upgrade decision,
  blockers, removable warnings, and the next safe action. It does not probe iLO
  on page load.
- Desired Intent: stores intended setup values locally for preview only. The
  form accepts network, users, SNMP, NTP/time, DNS/domain, and notes intent,
  but no passwords, tokens, SNMP secrets, or credential values. Saving intent
  does not call providers or apply settings.
- Compare: compares saved intent with cached readiness/discovery only. Unknown
  discovered values remain explicit as unknown and are not treated as
  mismatches. Sensitive desired values are represented as configured or missing.
- Plan Preview: builds plan-only setup sections for network, users, SNMP,
  NTP/time, DNS/domain, firmware readiness handoff, and report/artifact
  placeholders. It also shows a blocked Full Destructive Rebuild handoff section
  so operators can see that wipe, RAID, and ESXi installation belong to a future
  dedicated workflow. All section actions remain disabled.
- Firmware Readiness: shows readiness and handoff context only. It does not
  upload, flash, stage, or mount firmware or media.
- Report Preview: generates a redacted preview combining readiness, intent,
  compare, plan preview, destructive rebuild handoff, firmware/media summaries,
  disabled dangerous actions, blockers, warnings, provider mode, and timestamp.
  The UI action is Generate Preview or Refresh Preview, never Apply or Run.
- Destructive Rebuild: previews future full rebuild requirements and blockers.
  The page may show the future confirmation phrase `DESTROY AND REBUILD`, but it
  does not expose a clickable destructive execution button and does not run wipe,
  RAID, virtual media, boot order, BIOS, power, or ESXi install actions.
- Safety: lists disabled dangerous actions and keeps apply, flash, power,
  virtual media, boot, BIOS, user, network, SNMP, NTP, and DNS/domain changes
  unavailable.

The workflow has no apply path. Every endpoint and UI section keeps
`apply_enabled=false` and is limited to local persistence, cached discovery,
mock data, or explicitly requested read-only discovery. Dangerous actions are
absent or disabled by design.

Testing remains mock-first. Normal backend and frontend checks should run with
`PROVIDER_MODE=mock`. Optional `PROVIDER_MODE=local-readonly` smoke checks are
GET-only discovery checks for a local lab and require the explicit lab
acknowledgement variables described below; they must not be used for writes or
production infrastructure.

Operator screenshots may be saved locally under ignored paths such as
`artifacts/debug/` or `artifacts/screenshots/`. Screenshots, generated
artifacts, local reports, media, and real-lab files must not be committed.

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

- endpoint detection paths:
  - `/redfish/v1/`
  - `/redfish/v1`
  - `/`
  - `/xmldata?item=All`
- service root
- manager summary
- system summary
- chassis summary
- power and thermal summaries when linked by Redfish
- firmware inventory summary when linked by Redfish

The adapter uses short timeouts, configurable TLS verification, HTTP basic auth,
and response/error redaction. Passwords are never returned in API responses.
The endpoint detection matrix records only path, HTTP status code, content
type, sanitized error class, and classification. It does not return response
bodies, credentials, auth headers, cookies, or raw device inventory values.

iLO endpoint classifications include:

- `redfish_available`
- `redfish_http_error`
- `legacy_available`
- `legacy_available_redfish_not_found`
- `web_available_redfish_not_found`
- `endpoint_not_found_or_wrong_target`
- `auth_failed`
- `tls_failed`
- `network_unreachable`
- `not_checked`
- `unknown_endpoint_state`

When `/redfish/v1/` returns 404 and `/xmldata?item=All` returns 200, the
operator message is: "Legacy iLO endpoint is available, but Redfish root was not
found." When `/redfish/v1/` returns 404 and `/` returns 200, the operator
message is: "iLO web endpoint is reachable, but Redfish root was not found."
Both states remain read-only and do not enable any setting change.

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
