# 043 - Lab Target Configured Flags

## Goal

Fix real-lab provider status and provider-smoke behavior so ESXi and Cisco management IPs can be represented as planned but not configured yet.

Current lab reality:
- iLO is the only configured network target right now.
- iLO host is `ILO_TEST_HOST`, currently expected to be `192.168.1.202`.
- ESXi is not configured yet.
- Cisco management IP / SSH is not configured yet.
- Cisco console should still be dynamically discovered through serial candidates.

## Required Behavior

Add or honor local flags:

- `ESXI_CONFIGURED=false`
- `CISCO_MGMT_CONFIGURED=false`

When `ESXI_CONFIGURED=false`:
- ESXi provider status should say `not-configured` or `planned-target`
- ESXi provider-smoke should skip ESXi network probes
- It should not mark ESXi HTTPS/SSH timeout as a device failure
- UI should show safe next action like “Install/configure ESXi management network before read-only probe.”

When `CISCO_MGMT_CONFIGURED=false`:
- Cisco Ansible provider status should say `not-configured` or `awaiting-bootstrap`
- Cisco SSH/Ansible provider-smoke should skip SSH probes
- It should not mark Cisco SSH timeout as a device failure
- UI should show safe next action like “Use console bootstrap before Ansible SSH.”

Cisco Console:
- keep dynamic serial discovery active regardless of Cisco management configured state
- if no serial device is found, show missing-console with cable/USB/permissions guidance

iLO:
- continue to probe/readiness against `ILO_TEST_HOST`
- keep probes read-only
- do not expose secrets

## Safety

Do not perform destructive actions.
Do not enter Cisco config mode.
Do not configure ESXi.
Do not change iLO.
Do not power cycle.
Do not mount media.
Do not write memory.
Do not call real config-changing tools.

Read-only only.

## Tests

Add/update tests for:
- ESXi configured false skips network probe and returns planned/not-configured status
- Cisco management configured false skips SSH/Ansible probe and returns awaiting-bootstrap status
- Cisco console discovery still runs even when management is not configured
- iLO behavior is unchanged
- normal tests force mock mode and pass

## Docs

Update provider docs and `.env.example` docs with:
- `ESXI_CONFIGURED`
- `CISCO_MGMT_CONFIGURED`
- distinction between planned target and configured/reachable target

## Commands

Run:
- `PROVIDER_MODE=mock make smoke`
- `PROVIDER_MODE=mock make test`
- `PROVIDER_MODE=mock make lint`
- `PROVIDER_MODE=local-readonly make provider-smoke || true`
- `git diff --check`

## Acceptance Criteria

- Unconfigured ESXi/Cisco management are shown as planned/awaiting setup, not failures.
- Provider smoke output is less noisy and more accurate.
- iLO remains the only active read-only network target unless flags are enabled.
- Tests pass.
- No secrets or real-lab artifacts are committed.
