# iLO Local-Readonly Smoke Report

Checked at: 2026-06-05T15:39:25Z

## Scope

- Provider mode: `local-readonly`
- Provider filter: `ilo-redfish`
- Real lab env file: present, mode `0o600`
- Destructive mode: disabled
- Write/apply actions: not attempted
- Cisco and ESXi probes: not attempted

## Commands Run

```bash
sed -n '1,220p' Makefile
sed -n '1,220p' app/Makefile
sed -n '1,320p' app/backend/scripts/provider_smoke.py
sed -n '1,240p' app/backend/app/core/config.py
rg -n "provider-smoke|local-readonly|LAB_CLOSED_LOOP_ACK|LAB_READONLY_ACK|ILO_TEST|Redfish|iLO" README.md app/README.md app/docs/provider-adapters.md app/docs/security.md
cd app/backend && PROVIDER_MODE=mock .venv/bin/pytest -q tests/test_provider_status_adapters.py
PROVIDER_MODE=local-readonly PROVIDER_SMOKE_PROVIDERS=ilo-redfish make provider-smoke
```

## Gate Status

- `LAB_CLOSED_LOOP_ACK`: present
- `LAB_READONLY_ACK`: present
- `ILO_TEST_HOST`: present
- `ILO_TEST_USERNAME`: present
- `ILO_TEST_PASSWORD`: present
- `ILO_TEST_VERIFY_TLS`: configured as `false`
- iLO safe action: enabled
- Missing iLO config fields: none

## Result

Status: fail from this Codex execution environment.

- Target configured: yes
- TCP 443 reachable: no
- TCP preflight errors: `PermissionError` on all 3 attempts
- HTTPS/Redfish response: no successful response
- Redfish paths attempted: `/redfish/v1/`, `/redfish/v1`, `/`, `/xmldata?item=All`
- Redfish classifications: `network_unreachable`
- Authentication result: not exercised; connection failed before auth could be verified
- TLS verification: disabled for this lab run. This run does not prove whether verification must stay disabled because the target was not reachable from the sandbox.

Generated sanitized smoke artifacts:

- `artifacts/real-lab/provider-smoke-20260605T153925Z.json`
- `artifacts/real-lab/provider-smoke-20260605T153925Z.md`

## Code Changes

Added `PROVIDER_SMOKE_PROVIDERS` filtering to `app/backend/scripts/provider_smoke.py` so the existing `make provider-smoke` path can run only `ilo-redfish` without probing Cisco or ESXi. Updated docs and focused tests.

## Next Action

Run the same command from a shell with normal access to the lab network:

```bash
PROVIDER_MODE=local-readonly PROVIDER_SMOKE_PROVIDERS=ilo-redfish make provider-smoke
```

If TCP 443 succeeds there, review Redfish endpoint classification and auth results from the generated sanitized report before enabling any write/apply lane.
