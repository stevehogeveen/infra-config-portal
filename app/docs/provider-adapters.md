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

`GET /api/v1/providers/ilo-redfish/setup-apply-plan` builds the only current
iLO live-write plan. It is limited to an idempotent Redfish
`ManagerNetworkProtocol.HostName` update discovered from
`/redfish/v1/Managers`. It does not run on page load and does not send PATCH.
The plan reports required gates, blocked actions, and the exact confirmation
phrase.

`POST /api/v1/providers/ilo-redfish/setup-apply` can send a real Redfish PATCH
only when all of these are true:

- saved iLO setup intent contains `network.hostname`
- `PROVIDER_MODE=local-readonly`
- `LAB_CLOSED_LOOP_ACK=YES`
- `LAB_READONLY_ACK=YES`
- `ILO_SETUP_APPLY_ENABLED=true`
- `LAB_APPLY_ACK=YES`
- `LAB_TARGET_ACK` exactly matches the configured `ILO_TEST_HOST`
- request body contains `confirmation_phrase=APPLY ILO HOSTNAME SETUP`

The apply path does GET-before, PATCH, then GET-after readback verification.
It redacts the configured target, credentials, and desired hostname from the
recorded result. It blocks iLO IP, subnet/prefix, gateway, VLAN, user, SNMP,
NTP, DNS, firmware, virtual media, boot, power, and reset actions.

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
- HostName Apply: exposes a backend-only guarded Redfish PATCH lane for
  `ManagerNetworkProtocol.HostName`. It requires saved hostname intent,
  local-lab acknowledgement gates, target acknowledgement, and an exact
  confirmation phrase. It verifies by readback and redacts the desired value.
- Safety: lists disabled dangerous actions and keeps flash, power, virtual
  media, boot, BIOS, user, IP/subnet/gateway/VLAN, SNMP, NTP, and DNS/domain
  changes unavailable.

Except for the explicit HostName apply lane, every iLO endpoint and UI section
keeps `apply_enabled=false` and is limited to local persistence, cached
discovery, mock data, or explicitly requested read-only discovery. Dangerous
actions are absent or disabled by design.

Testing remains mock-first. Normal backend and frontend checks should run with
`PROVIDER_MODE=mock`. Optional `PROVIDER_MODE=local-readonly` smoke checks are
GET-only discovery checks for a local lab and require the explicit lab
acknowledgement variables described below. The HostName apply lane is a
separate guarded local-lab write path and must not be used for production
infrastructure.

Operator screenshots may be saved locally under ignored paths such as
`artifacts/debug/` or `artifacts/screenshots/`. Screenshots, generated
artifacts, local reports, media, and real-lab files must not be committed.

## Local Read-Only Preview Mode

Optional local lab settings must be placed in `.env.local.real-lab` at the
repository root. This file is ignored by Git and must not be committed. Provider
status responses expose local provider values only as configured/missing flags.
Probe results redact configured endpoints, users, passwords, tokens, cookies,
and other sensitive fields before caching or returning them.

For a local iLO at `192.168.1.202`, use the setup helper or create a private
`.env.local.real-lab` with `ILO_TEST_HOST=192.168.1.202`,
`PROVIDER_MODE=local-readonly`, `LAB_CLOSED_LOOP_ACK=YES`, and
`LAB_READONLY_ACK=YES`. Then run:

```bash
PROVIDER_MODE=local-readonly make provider-smoke
```

That command runs explicit GET-only iLO endpoint detection and inventory
discovery through the guarded provider-smoke path. Normal tests still run with
`PROVIDER_MODE=mock` and do not contact `192.168.1.202`.

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
- `ILO_SETUP_APPLY_ENABLED` (`true` required for guarded iLO HostName apply)
- `LAB_APPLY_ACK` (`YES` required for guarded apply paths)
- `LAB_TARGET_ACK` (must match the configured target for guarded apply paths)
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
message explains that a web endpoint responded but Redfish was not found, then
asks the operator to verify the configured address, older or legacy iLO
generation, Redfish support, and whether the responding portal is actually iLO.
Both states remain read-only and do not enable any setting change. The redacted
readiness and report-preview payloads may include diagnostic hints for these
checks, but they do not include response bodies, credentials, auth headers, or
raw inventory values.

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
- serve `GET /api/v1/providers/netapp-ontap/artifacts` as mock-only,
  non-downloadable metadata without writing report files
- contribute provider-scoped metadata to `GET /api/v1/providers/artifacts`
- serve `GET /api/v1/providers/netapp-ontap/upgrade-readiness` as an offline
  media-readiness preview using sanitized media inventory metadata only
- serve `GET /api/v1/providers/netapp-ontap/console-readiness` as manual
  console/bootstrap guidance without opening serial ports or sending commands
- serve `GET` and `PUT /api/v1/providers/netapp-ontap/observations` as
  process-local, mock-only operator readiness notes that are bounded, redacted,
  reject secret-shaped note text, and are never sent to NetApp
- serve `GET /api/v1/providers/netapp-ontap/readiness-comparison` as a
  planned-vs-observed comparison of local target intent and manual observations
  only, without live discovery; missing required manual checks remain unknown
  or blocking, optional Controller B console observation is a warning, and
  console readiness reports required and optional observation counts separately

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
