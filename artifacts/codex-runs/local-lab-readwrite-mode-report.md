# local-lab-readwrite Mode Report

Date: 2026-06-05

## Summary

Added `PROVIDER_MODE=local-lab-readwrite` as the explicit mode for isolated real
lab equipment. `mock` remains the default and cannot contact real devices.
`local-readonly` remains strictly read-only. Production-like or unknown provider
modes remain blocked by the provider registry.

Secrets and configured device targets are still redacted from provider status,
probe results, and smoke reports. `.env.local.real-lab` values are loaded
privately and `PROVIDER_MODE` from that file is ignored by app startup.

## Required Acknowledgements

`local-lab-readwrite` requires all of these private `.env.local.real-lab` flags:

- `LAB_ENVIRONMENT=isolated-real-lab`
- `LAB_ACKNOWLEDGE_REAL_HARDWARE=true`
- `LAB_ACKNOWLEDGE_DEVICE_RECONFIGURATION=true`
- `LAB_ACKNOWLEDGE_DATA_LOSS_RISK=true`
- `LAB_ACKNOWLEDGE_LAB_ONLY=true`

The report and smoke tooling show only present/enabled/disabled status, not
secret values.

## Action Policy

Added a central action policy in `app/backend/app/providers/action_policy.py`.
Actions are classified into:

- `readonly`
- `app_state_write`
- `network_config`
- `storage_config`
- `bios_config`
- `boot_config`
- `virtual_media`
- `os_install`
- `vm_deploy`
- `power_action`
- `firmware_update`
- `factory_reset`

`local-lab-readwrite` allows only explicit allowlisted workflow action IDs.
Power actions additionally require `LAB_ALLOW_POWER_ACTIONS=true`. Firmware
updates require `LAB_ALLOW_FIRMWARE_UPDATES=true`. Factory reset requires
`LAB_ALLOW_FACTORY_RESET=true`.

## iLO Workflow Targets

Added root/app Make targets:

- `provider-smoke-ilo-readonly`
- `provider-lab-ilo-inventory`
- `provider-lab-ilo-readiness`

The older local-lab iLO target names remain as aliases and now use
`local-lab-readwrite`.

## Verification

Commands run:

- `cd app/backend && PROVIDER_MODE=mock .venv/bin/pytest -q tests/test_provider_status_adapters.py tests/test_provider_registry.py`
- `make -C app backend-test`
- `make lint`

Results:

- Focused provider tests: `95 passed`
- Backend suite: `188 passed`
- Lint/build: passed; backend ruff was skipped because it is not installed in
  `app/backend/.venv`; frontend build passed.

No real firmware updates, factory resets, power actions, or real provider apply
commands were run during verification.
