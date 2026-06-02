# 020 - Provider Status Real Adapter Preview With Dynamic Discovery

## Goal

Build the first provider status preview pages and read-only adapter probes for HPE iLO / Redfish and Cisco console.

The UI should show what real provider pages will look like, while keeping all dangerous actions disabled.

Important: Cisco console path discovery must be dynamic. The user should not need to manually run `ls /dev/serial/by-id` and edit `.env.local.providers` just to see candidates.

## User Test Lab

Local-only test settings may exist in `.env.local.providers`.

This file is local only and must never be committed.

Expected optional variables:

- `ILO_TEST_HOST`
- `ILO_TEST_USERNAME`
- `ILO_TEST_PASSWORD`
- `CISCO_CONSOLE_PORT`
- `CISCO_CONSOLE_BAUD`

If `CISCO_CONSOLE_PORT` is missing, dynamically discover console candidates.

Do not print passwords.
Do not write passwords to logs.
Do not include credentials in screenshots.
Do not commit `.env.local.providers`.

## Dynamic Cisco Console Discovery

Add backend support to discover serial console candidates dynamically.

Discovery should inspect:

- `/dev/serial/by-id/*`
- `/dev/ttyUSB*`
- `/dev/ttyACM*`

Rules:

1. Prefer stable `/dev/serial/by-id/*` paths.
2. Include `/dev/ttyUSB*` and `/dev/ttyACM*` as fallback candidates.
3. Return all candidates with path, stable_path boolean, exists boolean, readable/writable status if safely checkable, detected label/name if derivable from symlink, and recommendation.
4. If exactly one stable candidate exists, mark it as the recommended default.
5. If multiple candidates exist, do not guess. Return a blocked/needs-selection status.
6. If no candidates exist, return missing-console status with helpful instructions.
7. Do not open the serial port during candidate discovery unless explicitly doing a read-only probe.
8. Do not send serial commands during candidate discovery.

Provider Status UI should show detected console candidates, recommended console path if exactly one is safe, env override status, selected/effective console path, missing/multiple candidate blocker, and safe next action.

## iLO Local Configuration

iLO configuration should be local and explicit.

If `ILO_TEST_HOST`, `ILO_TEST_USERNAME`, or `ILO_TEST_PASSWORD` are missing:

- show missing configuration status
- do not attempt a probe

If present:

- allow explicit read-only probe
- do not run probe automatically on page load
- redact password in all logs/responses/UI

## Safety

Read-only discovery only.

Do not perform firmware updates, BIOS changes, boot order changes, virtual media mounting, power actions, iLO user changes, Cisco configuration changes, Cisco write memory, Cisco reload, Cisco erase startup-config, Cisco copy commands, Cisco conf t, or any destructive/persistent action.

Allowed Cisco console operations:

- discover candidate serial paths
- open selected serial port only when user explicitly triggers read-only probe
- detect prompt
- send newline
- run safe show commands only if prompt allows it without changing state:
  - show version
  - show inventory
  - show interfaces status
  - show ip interface brief
  - show vlan brief
- avoid enable/config mode unless already at privileged prompt
- never send `conf t`

If Cisco requires login/password/enable and credentials are not safely configured, show blocked state with instructions. Do not guess credentials.

Allowed iLO/Redfish operations:

- GET service root
- GET manager information
- GET system information
- GET chassis information
- GET power/thermal summary if safe
- GET firmware/inventory summary if safe and read-only

## Provider Modes

Keep default mode mock.

Add a separate explicit local read-only mode if needed, such as `PROVIDER_MODE=local-readonly`.

Real probes must never run automatically on page load.

Provider status should show mock provider status, local config detected/missing, dynamic Cisco console candidates, last probe result, last probe time, blocked reasons, warnings, and safe next action.

## Backend Work

Add or improve provider contracts for provider name, type, mode, status, capabilities, read-only probe, blocked/dangerous actions, warnings, and last result.

Add Cisco console discovery service:

- dynamic candidate discovery
- stable path preference
- env override support
- missing/multiple candidate blockers
- no command execution during discovery
- redaction of sensitive values

Add iLO read-only adapter:

- use Redfish HTTP requests only for explicit probe
- TLS verification should be configurable for lab/self-signed systems
- timeouts must be short
- errors must be normalized
- secrets must be redacted

## Frontend Work

Improve Provider Status UI with separate cards/pages for:

- HPE iLO / Redfish
- Cisco Console
- vSphere mock
- NetApp mock
- Switch mock
- Terraform/OpenTofu mock
- AWX mock

For Cisco, show discovered serial console candidates, recommended candidate, selected/effective path, missing/multiple candidate blocker, safe read-only probe button if a single selected path is available, dangerous disabled actions, and warnings/blockers.

For iLO, show configuration status without exposing secrets, host and username if configured, password configured yes/no only, safe read-only probe button, dangerous disabled actions, last probe result, warnings/blockers, and raw result disclosure with redaction.

The user wants to see what these provider pages will look like.

## Tests

Add tests for:

- Cisco candidate discovery with one stable candidate
- Cisco candidate discovery with multiple candidates
- Cisco candidate discovery with no candidates
- Cisco env override path
- Cisco discovery does not open serial or send commands
- iLO missing config returns blocked/missing-config
- iLO redacts secrets
- dangerous actions are not exposed as runnable
- local-readonly mode does not run probes automatically
- provider status response shape

Do not require real iLO or Cisco hardware for normal tests. Hardware tests must be optional/manual.

## Manual Test Commands

Add documentation for optional manual tests.

Example:

`source .env.local.providers && PROVIDER_MODE=local-readonly make provider-smoke`

If a provider smoke target is added, it must skip gracefully when local config is missing, never fail normal CI just because hardware is absent, never print credentials, and dynamically discover Cisco console candidates.

## Documentation

Update docs with mock mode, local-readonly mode, dynamic Cisco console discovery, safe probe boundaries, optional iLO variables, what not to commit, and optional provider smoke tests.

## Quality Gates

Run:

- make smoke
- make test
- make lint

If frontend changes, ensure build passes.

## Acceptance Criteria

- Provider Status UI shows iLO and Cisco pages/cards with realistic adapter status.
- Cisco console candidates are dynamically discovered.
- User does not need to edit `.env.local.providers` for Cisco candidate discovery.
- Real probes are explicit, read-only, and never automatic.
- Secrets are never committed or printed.
- Normal tests pass without hardware.
- Optional local probes are documented.
- No destructive provider actions are added.
