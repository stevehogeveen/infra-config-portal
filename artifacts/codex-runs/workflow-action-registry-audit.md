# Workflow Action Registry Audit

Date: 2026-06-09

Scope: `/home/administrator/infra-config-portal` only. `/home/administrator/lab-builder`
was not modified. No hardware workflow was run.

## Skills Used

- `lab-builder-skill-steward`
- `lab-builder-real-runtime`
- `lab-builder-ux`
- `lab-builder-product-craft`
- `lab-builder-hardware-run`
- `lab-builder-report-remediation`
- `lab-builder-toolchain`
- `lab-builder-dual-app-architecture`

## Source Inputs

- `Makefile`
- `app/Makefile`
- `app/backend/scripts`
- `app/backend/app/services`
- `app/backend/app/api/routes.py`
- `app/backend/app/schemas.py`
- `app/frontend/src/App.tsx`
- `app/docs/*`
- `artifacts/codex-runs/*`
- `artifacts/codex-runs/infra-config-portal-app-atlas.md`
- `artifacts/codex-runs/lab-builder-app-atlas.md`
- `artifacts/codex-runs/dual-app-synthesis-report.md`
- `artifacts/codex-runs/lab-builder-skills-dual-app-final-report.md`

## Current Actions By Provider And Stage

| Stage | Current action sources |
| --- | --- |
| Lab Profile | `/api/v1/lab/profiles`, Control Center lab-profile section, Build Verification lab IP profile reports, `make provider-lab-build-verification-live`. |
| Firmware | `make provider-lab-firmware-inventory`, `make provider-lab-firmware-cisco-inventory`, `make provider-lab-firmware-compliance`, scoped compliance targets, waiver check target, `/api/v1/lab/firmware-*`, Firmware page. |
| Cisco | Shared serial discovery target, Cisco console recovery target, privilege target, VLAN10 bootstrap fix/apply targets, console/ethernet readiness target, Cisco firmware inventory target, Cisco setup/bootstrap routes, Control Center Cisco actions, Run Center Cisco choice. |
| HPE / iLO | iLO reachability/auth/inventory/readiness targets, firmware inventory target, iLO setup/readiness/compare/report/apply routes, Control Center iLO actions, provider status actions. |
| RAID | HPE storage discovery, RAID discovery, plan, debug, apply, pending, reset, validate-after-reset targets, HPE RAID routes, HPE RAID panel buttons, Control Center RAID actions. |
| ESXi | install readiness, media URL, insert/eject virtual media, one-time boot, reset installer boot, detect installer targets, ESXi readiness route, Run Center and Control Center ESXi actions. |
| NetApp | serial console discovery, console autodiscovery/discovery/read-state, live-state, validate-setup, NFS/vCenter readiness, netapp-real-readiness target, NetApp routes, Run Center NetApp buttons, Control Center NetApp actions. |
| Build Verification | live status/current state, build verification live/full targets, toolchain check target, full rebuild summary target, `/api/v1/lab/build-verification`, `/api/v1/lab/full-rebuild-summary`, Verification page. |
| Reports | `/api/v1/reports/issues`, `/api/v1/reports/summary`, provider artifacts endpoints, request/run artifact endpoints, Reports page, many historical markdown/json artifacts under `artifacts/codex-runs/`. |

## Duplicate Actions

- Firmware inventory appears as generic HPE/iLO inventory, Cisco-specific firmware inventory, Firmware page inventory, and Control Center actions.
- Cisco console discovery overlaps `provider-lab-serial-console-discovery`, `cisco.discover-console`, and Prompt Readiness.
- NetApp console discovery appears as shared serial discovery plus NetApp console autodiscovery/discovery aliases.
- ESXi virtual media and one-time boot appear under both iLO control and ESXi install workflow concerns.
- RAID discovery has `provider-lab-hpe-storage-discovery` and `provider-lab-hpe-raid-discovery` aliases.
- Build Verification live/current state overlaps provider live status, report center summaries, and verification report generation.
- Report links are repeated in Control Center section links, Report Center evidence, provider pages, and hard-coded frontend report lists.

## Hard-Coded Frontend Actions

- Run Center had hard-coded stage choices in `buildRunChoices`: iLO, storage/RAID, ESXi, Cisco, NetApp, verification.
- Run Center had direct NetApp buttons for console discovery, console read-state, live-state, setup validation, and refresh.
- Control Center rendered its own Action Catalog table from `GET /api/v1/control/actions`.
- Firmware page filtered firmware actions from the Control Center catalog.
- Provider detail pages still render provider `safe_actions` and `disabled_actions` from provider status rather than the workflow registry.
- Request lifecycle buttons remain request-specific and are intentionally outside the hardware workflow registry.

## Make Targets Without UI Actions

- `provider-lab-refresh-live-state`
- `provider-lab-build-verification-live`
- `provider-lab-firmware-compliance-scope-cisco`
- `provider-lab-firmware-compliance-scope-hpe`
- `provider-lab-firmware-compliance-scope-full`
- app-local `provider-lab-hpe-raid-debug`
- app-local `provider-lab-hpe-raid-pending` before registry linkage
- app-local `provider-lab-server-reset-for-raid` before explicit reset action mapping
- `provider-lab-esxi-eject-virtual-media`
- `provider-lab-full-rebuild-summary`
- `provider-lab-full-rebuild`
- app lifecycle targets such as `app-start`, `app-stop`, `app-status`

## UI Buttons Without Registry Backing

- Request lifecycle controls: submit, approve, plan, execute, cancel.
- Lab profile save/activate/edit controls.
- Provider mode save controls.
- Existing provider setup forms for Cisco requirements, iLO setup intent, HPE RAID intent, and NetApp observations.
- NetApp Run Center execution buttons still call provider-specific routes directly, though matching registry actions now exist.
- HPE RAID post-apply refresh/reset controls still live in the RAID setup panel.
- iLO and ESXi setup/detail page buttons still use provider-specific APIs where present.

These are not all defects. Some are app-state edits, request lifecycle controls, or setup forms. The risk is that hardware-like buttons can drift from the shared action definition if they do not resolve to a registry action.

## Reports Not Tied To Actions

Key provider reports now have action mappings in the first registry pass. Remaining report families that are not fully action-owned:

- dual-app synthesis, app atlas, skill inventory, UX audit/design/final reports
- overnight and full-device run logs/patch snapshots
- historical Cisco 4h run detail artifacts
- full rebuild summary/execution reports beyond Build Verification linkage
- old UX, control-center, sidebar, and report-center pass reports
- debugging reports that are evidence-only and not an operator action target

These should stay evidence-only unless they represent an operator stage. Historical files must not create current blockers without a fresh check.

## Main Gaps

- No database-backed run trace table exists for hardware stages yet.
- Existing Report Center issues were source/stage based, not action-id based, before this pass.
- Control Center and Run Center had overlapping action concepts.
- The registry needs to become the source for provider page action buttons over multiple smaller passes.
- Direct POST run support remains intentionally out of scope for this pass.

## Safety Findings

- Providers remain mock-first by default.
- The new registry is GET-only and exposes commands/API endpoints as copyable guidance.
- Historical artifacts are classified as evidence. They are not treated as live state.
- No real infrastructure call or destructive workflow was run during the audit.
