# Unified Report Center Audit

Date: 2026-06-08

Scope: `/home/administrator/infra-config-portal`

Safety posture: audit-only. No destructive hardware workflow was run. No live
provider action was executed. Secret values and real target values are not
included.

## Report Sources

| Source | Backend source | API / action | Primary artifacts |
| --- | --- | --- | --- |
| Build Verification / Certification | `app/backend/app/services/build_verification.py` | `GET /api/v1/lab/build-verification`, `make provider-lab-build-verification` | `artifacts/codex-runs/build-verification-report.md`, `artifacts/codex-runs/build-verification-summary-redacted.json`, `artifacts/codex-runs/build-verification-classification-report.md`, `artifacts/codex-runs/failure-case-hardening-report.md` |
| Lab IP Profile | `app/backend/app/services/build_verification.py`, `app/backend/app/services/lab_profiles.py`, `app/backend/app/services/control_actions.py` | Build Verification payload, Control Center lab-profile section, Settings / Lab Profile | `artifacts/codex-runs/lab-ip-profile-update-report.md`, `artifacts/codex-runs/lab-ip-profile-hardening-report.md`, `artifacts/codex-runs/netapp-lab-profile-plan-report.md` |
| Toolchain Availability | `app/backend/app/services/build_verification.py` | Build Verification payload, Settings / Toolchain | `artifacts/codex-runs/toolchain-availability-report.md` |
| Firmware Compliance | `app/backend/app/services/firmware_compliance.py` | `GET /api/v1/lab/firmware-compliance`, firmware control actions | `artifacts/codex-runs/firmware-compliance-report.md`, `artifacts/codex-runs/firmware-compliance-summary-redacted.json`, `artifacts/codex-runs/firmware-inventory-report.md`, `artifacts/codex-runs/firmware-waiver-report.md`, `artifacts/codex-runs/firmware-compliance-gate-final-report.md` |
| Cisco Readiness / Bootstrap | `app/backend/app/services/cisco_setup_readiness.py`, `cisco_setup_wizard_plan.py`, `cisco_console_bootstrap.py`, control catalog | `GET /api/v1/providers/cisco/setup-readiness`, `GET /api/v1/providers/cisco/setup-wizard-plan`, `GET /api/v1/providers/cisco/console-bootstrap/plan`, Cisco control actions | `artifacts/codex-runs/cisco-4h-lab-run-details-redacted.json`, `artifacts/codex-runs/cisco-4h-lab-run-report.md`, `artifacts/codex-runs/cisco-console-discovery-report.md`, `artifacts/codex-runs/cisco-console-ethernet-readiness-report.md`, `artifacts/codex-runs/cisco-bootstrap-apply-report.md`, `artifacts/codex-runs/cisco-firmware-inventory-report.md` |
| HPE / iLO Readiness | `app/backend/app/services/ilo_readiness.py`, `upgrade_decision.py`, iLO provider status | `GET /api/v1/providers/ilo-redfish/readiness-summary`, `GET /api/v1/providers/ilo-redfish/report-preview`, `GET /api/v1/providers/ilo-redfish/upgrade-readiness`, Provider Status | `artifacts/codex-runs/ilo-local-readonly-smoke-report.md`, `artifacts/codex-runs/ilo-local-lab-test-report.md`, `artifacts/real-lab/ilo-reachability-*.json`, `artifacts/real-lab/ilo-reachability-*.md` |
| HPE RAID | `app/backend/app/services/hpe_raid.py` | `GET /api/v1/providers/ilo-redfish/hpe-storage-discovery`, `GET /api/v1/providers/ilo-redfish/hpe-raid-plan-preview`, `GET /api/v1/providers/ilo-redfish/hpe-raid-pending`, reset/apply plan endpoints | `artifacts/codex-runs/hpe-raid-discovery-report.md`, `hpe-raid-plan-report.md`, `hpe-raid-apply-report.md`, `hpe-raid-pending-report.md`, `hpe-raid-reset-report.md`, `hpe-raid-after-reset-validation-report.md`, `hpe-smartstorage-current.json`, `hpe-smartstorage-settings.json` |
| ESXi Readiness / Boot / Rebuild | `app/backend/app/services/esxi_install_readiness.py`, `esxi_boot_workflow.py`, control catalog | `GET /api/v1/providers/ilo-redfish/esxi-install-readiness`, ESXi control actions | `artifacts/codex-runs/esxi-install-readiness-report.md`, `esxi-media-url-report.md`, `esxi-virtual-media-report.md`, `esxi-one-time-boot-report.md`, `esxi-installer-boot-report.md`, `esxi-full-rebuild-boot-report.md`, `esxi-management-readiness-report.md` |
| NetApp Console / Readiness | `app/backend/app/services/netapp_console_readiness.py`, `netapp_readiness_comparison.py`, `netapp_real_lab.py`, `netapp_state.py`, `netapp_upgrade_readiness.py`, `providers/netapp.py` | `GET /api/v1/providers/netapp-ontap/plan-preview`, console/read-state/live-state/readiness endpoints | `artifacts/codex-runs/netapp-console-autodiscovery-report.md`, `netapp-console-autodiscovery-redacted.json`, `netapp-console-state-report.md`, `netapp-console-state-redacted.json`, `netapp-live-state-report.md`, `netapp-console-last-known-good-redacted.json`, `netapp-state-automanagement-report.md`, `netapp-nfs-vcenter-readiness-report.md`, `netapp-nfs-vcenter-readiness-redacted.json` |
| Serial Console Discovery | `app/backend/app/services/serial_console_discovery.py`, Cisco/NetApp console services | Cisco and NetApp console discovery/readiness endpoints | `artifacts/codex-runs/serial-console-discovery-report.md`, `serial-console-discovery-redacted.json`, `serial-console-autodiscovery-final-report.md` |
| Control Catalog / Run Center | `app/backend/app/services/control_actions.py` | `GET /api/v1/control/actions` | every action-level `last_report` plus report paths embedded in section definitions |
| Workflow Artifacts | `app/backend/app/services/artifacts.py` | request/workflow artifact endpoints | database-backed mock artifact metadata shown in request and workflow detail pages |

## Current UI Clutter Problems

- `ReportsPage` is a link directory. It groups report paths and provider
  artifact placeholders, but it does not tell the operator what is broken,
  which finding is current, or what to fix next.
- `BuildVerificationPage` has a strong classification payload, but the current
  UI keeps the issue model local to that page. A stale lab profile issue,
  protocol issue, or toolchain issue does not become a shared issue visible from
  Dashboard, Firmware, Run Center, or Settings.
- `FirmwarePage` shows compliance details and action catalog metadata but its
  blocked components are not normalized into the same issue list as Build
  Verification and provider readiness.
- `RunCenter` repeats provider blockers and NetApp report paths inside its
  stage cards. The operator sees local blocker snippets but not a single
  remediation queue.
- `ControlCenterPage` repeats report links per section under collapsible
  details and also shows action blockers. It has useful staged metadata but
  does not provide page-level issue counts.
- `SettingsPage` repeats Build Verification credential/toolchain/lab-profile
  facts. Stale profile findings and missing toolchain packages remain local
  status rows instead of shared issues.
- NetApp preview surfaces many artifact/report paths as visible report-like
  rows. Those links should move to collapsed evidence under a unified issue.
- Workflow/request detail pages correctly show per-run artifacts, but top-level
  navigation does not distinguish real blockers from historical evidence.

## Duplicated Status Rows

- Build Verification, Settings / Credentials, and Control Center all expose
  credential status rows.
- Build Verification, Settings / Toolchain, and Reports all expose toolchain
  report state.
- FirmwarePage and Control Center both expose firmware compliance and upgrade
  action state.
- Run Center, Control Center, and Provider Status sections all expose Cisco,
  iLO, RAID, ESXi, and NetApp blockers independently.
- NetApp Run Center and NetApp Provider Status duplicate console discovery,
  live-state, NFS/vCenter, readiness comparison, and artifact placeholders.
- ReportsPage duplicates `last_report` links already shown under individual
  Control Center sections.

## Needs Attention Without Clear Next Action

- Sidebar/top-level navigation has no issue badge, so `Needs attention` is only
  visible after opening a page and scanning sections.
- `StatusBadge` maps `blocked` and `failed` to `Needs attention`, but a red
  failure and a calm "not configured yet" state can look too similar when the
  status is only a small label.
- Run Center stage cards show provider blockers but do not link directly to a
  filtered remediation view.
- Control Center action blockers explain why an action is blocked, but the page
  does not show a consolidated "top fix" across all sections.
- ReportsPage shows paths as the main content even when the operator needs a
  next action first and evidence second.
- Missing optional reports are currently easy to confuse with failed reports.
  Missing optional evidence should become `not_configured_yet` or `not_run`, not
  a red failure.

## Failures That Should Be Red

- Build Verification classifications `hard_fail` and active `stale_config`.
- Firmware Compliance components with status `blocked`.
- ESXi install readiness blockers such as missing RAID validation, virtual
  media support, one-time boot support, or ESXi ISO readiness.
- RAID plan/apply/pending/validation failures that indicate saved intent cannot
  be validated or a live layout mismatch exists.
- Cisco readiness blockers that require operator action before bootstrap or
  management verification can proceed.
- iLO readiness blockers that prevent GET-only inventory/readiness from being
  trusted.
- NetApp stale legacy configured flags or live-state blockers when they affect
  active configuration.
- Required toolchain packages missing for the active stage.

## Calm / Neutral States

- `not_configured_yet` should be neutral or blue, not red.
- Optional missing report artifacts should be evidence status only.
- NetApp planned targets that are not discovered yet should be neutral unless a
  workflow explicitly requires live validation.
- Historical artifacts with stale values should be marked historical evidence,
  not current blockers, unless an active config value still depends on them.

## Recommended First Unified Model

- Normalize every source into issue rows with `severity`, `classification`,
  `status`, `next_action`, `source_report`, `evidence_artifacts`, and
  `linked_page`.
- Keep artifact paths under collapsed Evidence by default.
- Use page-level badges for Dashboard, Run Center, Control Center, Firmware,
  Build Verification, Reports, and Settings.
- Use red for critical blockers, yellow for review, neutral for
  `not_configured_yet`, and green for passed state, always with labels.
