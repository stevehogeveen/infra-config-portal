# local-lab Provider Mode Design

Checked at: 2026-06-05T15:50:14Z

## Goal

Add `PROVIDER_MODE=local-lab` as a separate real-lab mode without weakening
`mock`, `local-readonly`, or future production safety.

## Modes

- `mock`: default. Real targets are not contacted.
- `local-readonly`: existing explicit read-only probe mode. It still requires
  `LAB_CLOSED_LOOP_ACK=YES` and `LAB_READONLY_ACK=YES`.
- `local-lab`: new iLO-only real-lab mode. It can contact the configured iLO
  only after the new acknowledgement policy is satisfied.

Provider status accepts `local-lab`, but VM lifecycle execution remains
mock-backed only. `local-lab` does not enable vSphere, storage, Cisco, ESXi, or
NetApp execution.

## Required local-lab Flags

Read from `.env.local.real-lab` and reported only as statuses:

- `LAB_ENVIRONMENT=real-lab`
- `LAB_ACKNOWLEDGE_REAL_HARDWARE=true`
- `LAB_ALLOW_READONLY=true`
- `LAB_ALLOW_SAFE_WRITES=true`

Dangerous flags default to disabled and do not enable actions yet:

- `LAB_ALLOW_POWER_ACTIONS=false`
- `LAB_ALLOW_FIRMWARE_UPDATES=false`
- `LAB_ALLOW_VIRTUAL_MEDIA=false`
- `LAB_ALLOW_NETWORK_CHANGES=false`
- `LAB_ALLOW_FACTORY_RESET=false`

## Current local-lab Allowlist

Allowed for iLO:

- HTTPS/Redfish connection checks
- Redfish authentication checks through GET-only requests
- GET-only read-only inventory
- sanitized local probe-result recording
- preview/plan generation

No iLO device-side write is allowlisted in this implementation.

## Blocked Actions

Always blocked for now:

- firmware update
- power on/off/reset
- virtual media mount/eject
- boot order change
- BIOS change
- user/password change
- iLO network change
- factory reset
- any iLO POST/PATCH/PUT/DELETE

The previous HostName PATCH lane is now blocked in both `local-readonly` and
`local-lab` until a future task adds a tested device-write allowlist entry.

## Implementation Notes

- Added central policy helper: `app/backend/app/providers/action_policy.py`
- Added `local-lab` settings in `app/backend/app/core/config.py`
- Updated iLO provider health/probe gates in `app/backend/app/providers/ilo_redfish.py`
- Updated provider status registry to accept `local-lab`
- Added iLO-only Make targets:
  - `make provider-smoke-ilo-readonly`
  - `make provider-smoke-ilo-local-lab`
  - `make provider-inventory-ilo-local-lab`

## Tests

Covered:

- `mock` iLO probe does not instantiate an HTTP client
- `local-readonly` blocks iLO writes
- `local-lab` requires acknowledgement flags
- `local-lab` allows iLO GET-only inventory with a fake Redfish client
- dangerous iLO actions remain disabled
- local-lab result redaction excludes target, username, and password

Verification:

- `make test`: passed, `185 passed`
- `make lint`: passed; backend `ruff` skipped because it is not installed
