# Lab Profile Topology Rules Audit

- Generated: 2026-06-10
- Scope: `/home/administrator/infra-config-portal`
- Skills used: lab-builder-skill-steward, lab-builder-real-runtime, lab-builder-ux, lab-builder-product-craft, lab-builder-hardware-run, lab-builder-report-remediation, lab-builder-toolchain, lab-builder-dual-app-architecture
- Hardware workflows run: none
- Secrets printed: none

## Summary

The app already has a saved profile store under `.local/lab-profiles.json`, and `.local/` is ignored by Git. The existing model is flat: `global_settings` plus `address_plan`. Prefix handling exists, but it treats `/25` through `/29` as a generic compact mode and treats `/24` or larger as NetApp-capable. It does not expose a first-class topology type, feature flags, not-in-scope stages, or one active resolved profile context for all consumers.

## Current Assumptions Found

### `.200+` high-address layout

- `app/backend/app/core/config.py` defines fixed runtime defaults for the 192.168.1.0/24 lab: iLO `.201`, server NIC `.202`, ESXi `.203`, Cisco `.204`, Ansible/control `.205`, NetApp `.210/.211/.220+`, NFS `.230/.231`, and iSCSI `.240-.243`.
- `app/backend/app/services/lab_profiles.py` has `LAB_BUILDER_CORE_OFFSETS` and `LAB_BUILDER_NETAPP_OFFSETS`; these are only keyed by prefix support, not by explicit topology.
- `app/backend/app/services/build_verification.py` rebuilds expected lab IPs directly from constants/settings and an optional saved profile. It does not consume a reusable resolved topology context.
- `app/backend/app/services/lab_validation.py` rebuilds a runtime address plan directly from settings and constants, then compares saved profile subnet as a warning.
- `app/backend/app/services/control_actions.py` compares section desired state to hardcoded known lab constants instead of the selected topology rules.
- `app/frontend/src/App.tsx` mirrors backend derivation with hardcoded `labBuilderCoreOffsets`, `compactCoreOffsets`, and NetApp offsets.
- `scripts/setup-real-lab-env.sh` prompts only for the 192.168.1.0/24 high-address layout and always writes NetApp/vCenter prompts.
- `app/.env.example` documents stale NetApp `.206-.215` comments that disagree with current high-address `.210/.220+` defaults.

### NetApp expected for all labs

- `app/backend/app/services/workflow_registry.py` always includes the NetApp stage and makes Build Verification depend on `netapp`.
- `app/backend/app/services/lab_validation.py` always adds NetApp console, ONTAP, upgrade, NFS, and vCenter-NetApp validation items.
- `app/backend/app/services/build_verification.py` always adds NetApp REST, SSH, console, and NFS/vCenter protocol checks.
- `app/backend/app/services/netapp_setup_intent.py` and `app/backend/app/services/netapp_upgrade_center.py` always build NetApp setup/upgrade payloads from settings.
- `app/backend/app/services/vcenter_netapp_readiness.py` treats NetApp state as a prerequisite rather than first checking whether NetApp is in scope for the active profile.
- `app/frontend/src/App.tsx` shows NetApp in profile summaries, control summaries, firmware lists, and normal validation paths even when the subnet profile disables NetApp.

### vCenter expected for all labs

- `app/backend/app/services/lab_validation.py` always includes a vCenter item and vCenter-NetApp datastore item.
- `app/backend/app/services/vcenter_netapp_readiness.py` returns `not_configured_yet` or `blocked_by_prior_stage` for missing vCenter/govc even when vCenter should be outside the active topology.
- `app/backend/app/services/build_verification.py` includes NetApp NFS/vCenter readiness in protocol certification regardless of active profile feature scope.
- `scripts/setup-real-lab-env.sh` always prompts for vCenter readiness and host after NetApp prompts.

### Subnet size ignored or too loosely mapped

- Current `/25` through `/29` profiles all share one compact layout. The compact offsets do not match the requested `/26` layout.
- `/29` remains available in UI/API options, but the requested compact `+11` iLO offset cannot fit inside `/29`.
- Existing validation fills or clears fields but does not consistently reject out-of-subnet overrides or duplicate IP overrides.
- NetApp support is inferred from prefix `<= /24`; vCenter support is not profile-controlled.

### Active profile values not driving defaults everywhere

- Dashboard and the profile editor display the active profile, but Build Verification, Lab Validation, vCenter-NetApp readiness, and several control diffs still use settings/constants as the effective default.
- Control Access reads active profile desired addresses, but Control Center state comparisons still use a hardcoded known lab profile.
- NetApp setup/upgrade services use environment/settings directly rather than the active profile’s resolved NetApp feature state and derived targets.
- Workflow registry action defaults and stage dependencies are not profile-aware.
- Reports currently treat mismatches as stale config but do not include a single reusable list of exact fields, expected active-profile values, and runtime/env current values.

## Required Implementation Direction

- Add a topology derivation service with explicit `high_address_lab`, `compact_edge_lab`, and `custom` topologies.
- Keep `address_plan` for compatibility, but add `profile_topology`, `subnet_cidr`, `devices`, `features`, resolved context, not-in-scope stages, mismatch warnings, and fix guidance.
- Make `/24` default to high-address layout and `/26` default to compact offset layout.
- Mark NetApp and vCenter as `not_in_scope` for compact `/26` defaults instead of `not_configured_yet`.
- Use one active profile context in Build Verification, Lab Validation, Control Center, workflow registry, NetApp setup/upgrade, and vCenter-NetApp readiness.
- Keep saved profiles under ignored local state and keep `.env.local.real-lab` as bootstrap/secrets/emergency override only.
