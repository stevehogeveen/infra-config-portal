# 042 - Stabilize Real Lab Provider Preview

## Goal

Stabilize the current uncommitted provider preview work for:

- iLO / Redfish
- Cisco Console
- Cisco Ansible
- ESXi read-only

Preserve useful work, but make the repo safe and green again.

## Current Situation

There are uncommitted changes from a real-lab run.

Important files include:

- `app/backend/app/providers/cisco_console.py`
- `app/backend/app/providers/ilo_redfish.py`
- `app/backend/app/providers/cisco_ansible.py`
- `app/backend/app/providers/esxi_readonly.py`
- `app/backend/app/providers/lab_safety.py`
- `app/backend/app/providers/registry.py`
- `app/backend/app/api/routes.py`
- `app/backend/app/core/config.py`
- `app/backend/scripts/provider_smoke.py`
- `app/frontend/src/App.tsx`
- docs and tests

The previous failures were mostly caused by `PROVIDER_MODE=local-readonly` leaking into normal tests.

## Required Outcome

Normal app tests must always run in mock mode unless they are explicitly provider smoke / real-lab tests.

Fix the provider mode isolation so these pass even if the shell had `.env.local.real-lab` sourced earlier:

- `PROVIDER_MODE=mock make smoke`
- `PROVIDER_MODE=mock make test`
- `PROVIDER_MODE=mock make lint`

Also make sure these are safe:

- `make provider-smoke || true`
- `PROVIDER_MODE=local-readonly make provider-smoke || true`

## Safety Rules

Do not perform destructive or persistent real infrastructure actions.

Do not call real:

- iLO destructive actions
- Redfish destructive actions
- Cisco config mode
- Cisco write memory
- Cisco reload
- Cisco copy/erase
- ESXi changes
- vCenter changes
- NetApp changes
- switch config changes
- firmware upgrades
- virtual media mounting
- power actions
- Terraform/OpenTofu apply
- AWX job launches

Read-only local provider probes must remain explicit and opt-in.

Do not commit:

- `.env.local.real-lab`
- `.env.local.providers`
- passwords
- tokens
- private keys
- raw running-config with secrets
- generated real-lab artifacts

## Fix Requirements

1. Make normal Makefile targets force `PROVIDER_MODE=mock`:
   - root `make smoke`
   - root `make backend-smoke`
   - root `make test`
   - app `make backend-test`
   - any pytest command used by normal test targets

2. Keep `make provider-smoke` flexible:
   - default to `PROVIDER_MODE=mock` if no mode is set
   - allow `PROVIDER_MODE=local-readonly make provider-smoke`
   - skip gracefully when hardware/config is missing
   - never print passwords

3. Real-lab runner must:
   - use local-readonly only for provider smoke/probe steps
   - run normal quality gates with `PROVIDER_MODE=mock`
   - treat network unreachable as a lab preflight blocker, not a unit-test failure
   - write blocker reports under `artifacts/real-lab/`
   - not commit generated artifacts

4. Provider registry must:
   - support mock mode for normal app/test flow
   - support local-readonly provider status/probes where implemented
   - never break VM lifecycle APIs just because local-readonly env vars are present
   - normalize provider errors instead of crashing normal API routes

5. Provider Status UI must:
   - show iLO, Cisco Console, Cisco Ansible, and ESXi preview cards
   - show missing config and blockers clearly
   - show dangerous actions disabled
   - not expose secrets

6. Tests:
   - update or add tests for provider mode isolation
   - normal tests should not require real hardware
   - local-readonly tests must mock hardware or skip safely

## Commands To Run

Run:

- `PROVIDER_MODE=mock make smoke`
- `PROVIDER_MODE=mock make test`
- `PROVIDER_MODE=mock make lint`
- `make provider-smoke || true`
- `PROVIDER_MODE=local-readonly make provider-smoke || true`
- `git diff --check`

## Acceptance Criteria

- Normal mock tests pass.
- Provider smoke does not break normal CI/test flow.
- Uncommitted provider work is either stabilized or reduced safely.
- No real destructive actions are added.
- No secrets are printed or committed.
- Final summary says whether the changes are safe to commit.
