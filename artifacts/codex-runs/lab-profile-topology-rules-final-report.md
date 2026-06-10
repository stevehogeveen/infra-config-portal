# Lab Profile Topology Rules Final Report

Checked at: 2026-06-10

## Summary

Implemented active Lab Profile topology rules across backend context, validation,
control surfaces, workflow defaults, NetApp/vCenter readiness, setup script
comments, docs, tests, and frontend profile UI.

The active profile now exposes:

- `profile_topology`: `high_address_lab`, `compact_edge_lab`, or `custom`
- `subnet_cidr`, gateway, DNS/NTP, VLAN, MTU
- resolved device/address plan
- feature flags for NetApp, vCenter, firmware gate, build verification, storage
  protocol, IPv6, SNMP, NTP, and DNS
- disabled/not-in-scope feature state
- runtime/env mismatch warnings with exact env field, active profile expected
  value, and remediation guidance

## Topology Behavior

- `/24` high-address profiles derive iLO `.201`, server NIC `.202`, ESXi `.203`,
  Cisco `.204`, control host `.205`, NetApp SP `.210/.211`, NetApp management
  `.220-.223`, NFS `.230/.231`, and iSCSI `.240-.243`.
- `/26` compact profiles derive gateway `+1`, switch `+2/+3`, reserved `+4-+6`,
  UPS `+7`, backup storage `+8`, utility VM `+9`, ESXi `+10`, and iLO `+11`.
- `/26` compact profiles disable NetApp and vCenter by default. Those rows are
  `not_in_scope`, not blockers.
- Custom overrides are validated inside the active subnet, reject
  network/broadcast addresses, and reject duplicate IPs.

## Integration Points Updated

- Backend topology/model/context:
  - `app/backend/app/services/lab_topology.py`
  - `app/backend/app/services/lab_profiles.py`
  - `app/backend/app/schemas.py`
  - `app/backend/app/api/routes.py`
- Runtime/report behavior:
  - `app/backend/app/services/build_verification.py`
  - `app/backend/app/services/lab_validation.py`
  - `app/backend/app/services/vcenter_netapp_readiness.py`
  - `app/backend/app/services/netapp_real_lab.py`
  - `app/backend/app/services/netapp_setup_intent.py`
  - `app/backend/app/services/netapp_upgrade_center.py`
  - `app/backend/app/services/workflow_registry.py`
  - `app/backend/app/services/control_actions.py`
- Frontend:
  - `app/frontend/src/App.tsx`
  - `app/frontend/src/types.ts`
  - `app/frontend/tests/safe-action-runner.spec.ts`
- Script/docs:
  - `scripts/setup-real-lab-env.sh`
  - `app/.env.example`
  - `README.md`
  - `app/docs/workflows.md`
  - `app/docs/lab-profile-examples.md`
- Tests:
  - `app/backend/tests/test_lab_topology.py`
  - `app/backend/tests/test_api.py`
  - `app/backend/tests/test_build_verification.py`
  - `app/backend/tests/test_lab_validation.py`
  - `app/backend/tests/test_provider_registry.py`
  - `app/backend/tests/test_workflow_registry.py`
  - `app/backend/tests/conftest.py`

## Screenshots

- `artifacts/screenshots/profile-topology-dashboard.png`
- `artifacts/screenshots/profile-topology-24-high-address.png`
- `artifacts/screenshots/profile-topology-26-compact.png`
- `artifacts/screenshots/profile-topology-validation-not-in-scope.png`
- `artifacts/screenshots/profile-topology-netapp-disabled-26.png`

Screenshots were captured from the running local app using non-secret local
demo profiles. Saved demo profiles remain local ignored state and were not
committed.

## Validation

- `make lint` passed.
- `make test` passed:
  - backend: `360 passed`
  - frontend production build completed through the root target.
- Additional focused checks passed during development:
  - topology/API/Build Verification/Lab Validation/workflow registry focused
    pytest subset: `16 passed`
  - frontend build: `npm run build`
  - backend syntax: `python3 -m py_compile ...`
  - setup script syntax: `bash -n scripts/setup-real-lab-env.sh`

## Safety Notes

- No hardware workflows were run.
- No real provider writes were performed.
- No secrets were printed in reports or terminal output.
- `.env.local.real-lab` remains bootstrap/secrets/emergency override state.
- Saved lab profiles are local-only and ignored by Git.
- Reports/artifacts remain evidence only and are not used as configuration
  source.

## Skill Review

- `lab-builder-real-runtime`: active profile now drives defaults and mismatch
  warnings without using historical artifacts as current blockers.
- `lab-builder-ux` and `lab-builder-product-craft`: Dashboard/Profile/Control
  surfaces now show topology, derived IPs, enabled features, and
  disabled/not-in-scope features.
- `lab-builder-hardware-run`: hardware sequencing stays profile-scoped and
  compact labs keep NetApp/vCenter out of normal validation.
- `lab-builder-report-remediation`: stale env values include exact field,
  expected value, and fix guidance.
- `lab-builder-toolchain`: firmware and workflow defaults hide or mark
  irrelevant devices when out of scope.
- `lab-builder-dual-app-architecture`: behavior follows Lab Builder profile
  intent as the portal source of defaults.
