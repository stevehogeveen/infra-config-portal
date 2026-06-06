# Security

## Safety Posture

This project starts in mock-only mode. It must not perform real production or
lab infrastructure actions until a future adapter is explicitly configured,
reviewed, and tested.

## Secrets

- Do not store plaintext secrets.
- Do not commit credentials, tokens, private keys, real hostnames, IPs, or
  customer data.
- `ProviderCredentialRef` records are references only. They may identify a
  secret manager path or external credential ID, but not the secret value.
- Future secret retrieval should go through a dedicated secret provider service
  with audit logging.

## Provider Execution Controls

All provider adapters default to mock mode. A future real adapter must require:

- explicit provider mode configuration
- named credential reference
- dry-run or plan output
- approval before execution for production-like environments
- audit logging around each status transition and provider task ID

`PROVIDER_MODE=local-readonly` is reserved for explicit local iLO/Redfish,
Cisco console, Cisco Ansible SSH, and ESXi preview probes. It must not run
automatically on page load and requires `LAB_CLOSED_LOOP_ACK=YES` plus
`LAB_READONLY_ACK=YES` for real lab probes.

Allowed local-readonly behavior:

- dynamic Cisco console candidate discovery without opening serial ports
- explicit Cisco console read-only probe with newline and safe `show` commands
- explicit iLO/Redfish GET-only inventory/status probe
- explicit Cisco Ansible SSH reachability, temporary inventory parse, and fixed
  safe `show` commands
- explicit ESXi HTTPS GET and TCP reachability checks

`PROVIDER_MODE=local-lab-readwrite` is separate from both `mock` and `local-readonly`.
It is for isolated lab equipment only and requires all of:

- `LAB_ENVIRONMENT=isolated-real-lab`
- `LAB_ACKNOWLEDGE_REAL_HARDWARE=true`
- `LAB_ACKNOWLEDGE_DEVICE_RECONFIGURATION=true`
- `LAB_ACKNOWLEDGE_DATA_LOSS_RISK=true`
- `LAB_ACKNOWLEDGE_LAB_ONLY=true`

Allowed local-lab-readwrite behavior is category-gated by
`app.providers.action_policy`: readonly discovery, app-side state updates,
network/storage/BIOS/boot/virtual-media/OS-install/VM-deploy workflows, and
only explicit allowlisted workflow steps. Power actions require
`LAB_ALLOW_POWER_ACTIONS=true`; firmware updates require
`LAB_ALLOW_FIRMWARE_UPDATES=true`; factory reset requires
`LAB_ALLOW_FACTORY_RESET=true`.

Blocked behavior includes power actions, firmware updates, virtual media
mounts, iLO account changes, switch configuration changes, `conf t`, `write
memory`, `reload`, `erase startup-config`, `copy`, arbitrary Ansible variables,
ESXi reinstall/reboot/network/datastore/VM/power operations,
Terraform/OpenTofu apply, AWX launches, and any production-like provider action.

## Input Safety

The UI and API should collect structured fields only. They must not accept:

- arbitrary scripts
- arbitrary Ansible variables
- raw Terraform files
- unvalidated provider payloads
- free-form command lines

Provider-specific options should be modeled as typed fields with allow-lists,
range validation, and source-of-truth checks.

## Approval Gates

Production-impacting workflows must not bypass approval. The MVP requires
approval for every VM deployment so the gate is exercised from day one.

## Audit Events

Every important action records an audit event, including:

- request creation
- submit
- validation start and pass/fail
- approval
- plan creation
- execution start
- completion
- failure
- cancellation

Audit events should be treated as immutable application history.
