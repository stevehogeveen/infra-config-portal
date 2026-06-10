# Lab Validation Page Audit

Generated: 2026-06-09

## Scope

- Repository: `/home/administrator/infra-config-portal`
- Reference inspected read-only: `/home/administrator/lab-builder`
- Skills applied: `lab-builder-skill-steward`, `lab-builder-real-runtime`, `lab-builder-ux`, `lab-builder-product-craft`, `lab-builder-hardware-run`, `lab-builder-report-remediation`, `lab-builder-toolchain`, `lab-builder-dual-app-architecture`
- Safety: no hardware workflow was run, no credentials were printed, and historical artifacts are treated as evidence only.

## Existing Proof Surfaces

- Build Verification: `/verification` and `GET /api/v1/lab/build-verification` expose product certification status, redacted findings, current-state warnings, and supporting evidence. This is the strongest proof source, but it is certification-oriented rather than handoff-oriented.
- Reports / Issues: `/reports` and `GET /api/v1/reports/issues` normalize blockers, warnings, source reports, evidence artifacts, source type, freshness, and linked workflow actions. It is the best place to keep issue details and evidence drawers.
- Run Center: `/run-center` shows staged workflow readiness and registry actions for lab profile, firmware, Cisco, iLO, RAID, ESXi, NetApp, Build Verification, and Reports. It is useful for next actions, but not compact enough for handoff.
- Control Center: `/control-center` exposes the registry-backed action catalog, availability, required gates, reports, and copyable commands. It is useful for operators who know which workflow to run, but it does not answer "what is set up across the lab?" in one place.
- Workflow registry: `app/backend/app/services/workflow_registry.py` links stages, actions, reports, current availability, last report traces, source type, freshness, and run endpoints. This should feed linked workflow actions on the validation page.
- NetApp artifacts: existing reports such as `netapp-console-autodiscovery-report.md`, `netapp-console-state-report.md`, `netapp-console-login-state-report.md`, `netapp-live-state-report.md`, and `netapp-nfs-vcenter-readiness-report.md` provide proof, but should remain collapsed support rather than main-page clutter.

## Missing Login Information

- There is no single place that shows operator login targets beside setup state.
- iLO should show `https://192.168.1.201` and credential state by field name only when missing.
- ESXi should show `https://192.168.1.203` when configured or planned, with `ESXI_TEST_USERNAME` / `ESXI_TEST_PASSWORD` field names only when missing.
- Cisco should show `ssh admin@192.168.1.204` when management is ready, and otherwise keep console-first proof visible.
- NetApp cluster should show `https://192.168.1.220` only as the planned/configured cluster management target, not as live state until ONTAP is configured.
- vCenter should show `VCENTER_HOST` / `GOVC_URL` as the configured target when present, with field names only when credentials are missing.
- NetApp NFS datastore should show datastore name `netapp_nfs_ds01` as planned until the datastore mount has proof.

## Unclear Setup State

- Historical report links can make a stage look evidenced, but the current UI requires the operator to inspect each page to understand whether evidence is fresh, live cached, historical, or not checked.
- NetApp planned intent and current live state are separated in backend services, but the handoff story is split between console readiness, live state, readiness comparison, and NFS/vCenter readiness.
- vCenter-to-NetApp storage is present as NetApp NFS/vCenter readiness, but not as a first-class stage/lane in the registry or a cross-component validation item.
- Build Verification reports blockers and warnings but does not directly show where the operator should log in to validate each component.
- Control Center makes write-capable future actions visible, but the handoff page needs to keep future apply placeholders clearly disabled and off the primary path.

## Reports To Summarize

- Lab profile: `lab-ip-profile-update-report.md`, `lab-ip-profile-hardening-report.md`
- Firmware: `firmware-compliance-report.md`, `firmware-compliance-summary-redacted.json`, `toolchain-availability-report.md`
- Cisco: `serial-console-discovery-report.md`, `cisco-console-ethernet-readiness-report.md`, `cisco-bootstrap-apply-report.md`
- iLO/HPE: `ilo-real-run-report.md`, `ilo-local-readonly-smoke-report.md`, `hpe-raid-plan-report.md`, `hpe-raid-pending-report.md`
- ESXi: `esxi-install-readiness-report.md`, `esxi-installer-boot-report.md`
- NetApp: `netapp-console-autodiscovery-report.md`, `netapp-console-state-report.md`, `netapp-console-login-state-report.md`, `netapp-live-state-report.md`, `netapp-setup-plan-report.md`
- vCenter-NetApp storage: `vcenter-netapp-readiness-report.md`, `vcenter-netapp-datastore-plan-report.md`
- Build Verification: `build-verification-report.md`, `build-verification-summary-redacted.json`, `build-verification-evidence-report.md`
- Report Center: current issues and source summaries from `GET /api/v1/reports/issues`

## What Should Move Into Proof/Evidence Drawers

- Raw redacted Build Verification payload.
- Report artifact path lists.
- Workflow registry trace details.
- Full blocker details after the first actionable line.
- NetApp console probe candidates, attempts, and raw prompt labels.
- Connectivity check matrices and command previews.
- Historical artifacts with stale/historical labels.
- Raw JSON and report links that support a row but are not the row's main status.

## Target Handoff Shape

- A single `Lab Validation / Handoff` page should show component, status, setup summary, login/proof, and next action in a table.
- Selecting a row should open a detail panel with current state, desired state, proof points, collapsed evidence, login hints, recheck command, and linked workflow action.
- Red should only represent a current live blocker. Partial, warning, historical, and not-checked states should not be rendered as red current failures.
- vCenter-NetApp should be a first-class validation item and registry lane, blocked by NetApp `cluster_setup_wizard` / ONTAP/NFS not configured until prior stages complete.
