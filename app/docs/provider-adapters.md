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
- NetApp ONTAP: mocked health only.
- network switch: mocked health only.

`PROVIDER_MODE=mock` remains the default. In mock mode, provider status may
inspect local serial device paths for Cisco console candidates, but no network
or serial probe is run automatically.

The backend resolves default adapters through `app.providers.registry`. The
current registry accepts `PROVIDER_MODE=mock` for workflow lifecycle execution.
Provider status also supports `PROVIDER_MODE=local-readonly` so an operator can
manually run guarded read-only iLO and Cisco probes from a local lab machine.
Unsupported modes raise a provider registry error.

## Local Read-Only Preview Mode

Optional local lab settings may be placed in `.env.local.providers` at the
repository root. This file is ignored by Git and must not be committed.

Supported local variables:

- `ILO_TEST_HOST`
- `ILO_TEST_USERNAME`
- `ILO_TEST_PASSWORD`
- `ILO_TEST_VERIFY_TLS` (`true` by default; set `false` for lab self-signed TLS)
- `ILO_TEST_TIMEOUT_SECONDS` (`3.0` by default)
- `CISCO_CONSOLE_PORT`
- `CISCO_CONSOLE_BAUD` (`9600` by default)
- `CISCO_CONSOLE_TIMEOUT_SECONDS` (`2.0` by default)

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
console prompts for login, password, enable, or appears to be in config mode,
the probe reports a blocked state instead of guessing credentials.

## Optional Provider Smoke

Manual local smoke:

```bash
source .env.local.providers
PROVIDER_MODE=local-readonly make provider-smoke
```

The smoke command dynamically discovers Cisco console candidates, skips probes
when local config or hardware is absent, and exits successfully for missing lab
hardware. It redacts sensitive values and must not be used with production
infrastructure credentials.

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
