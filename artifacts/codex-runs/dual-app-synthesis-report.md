# Dual-App Synthesis Report

Date: 2026-06-09

Scope:
- Primary implementation target: `/home/administrator/infra-config-portal`
- Read-only reference: `/home/administrator/lab-builder`
- No hardware workflows were run.
- No secrets were printed.
- Historical artifacts were treated as evidence, not current blockers.

Applied skills:
- `lab-builder-skill-steward`
- `lab-builder-dual-app-architecture`
- `lab-builder-product-craft`
- `lab-builder-ux`
- `lab-builder-real-runtime`
- `lab-builder-hardware-run`
- `lab-builder-report-remediation`
- `lab-builder-toolchain`

## Capability Comparison

| Capability | Infra Config Portal | Lab Builder | Better Current Implementation |
| --- | --- | --- | --- |
| Product shell | React sidebar with status badges and active lab context. | Server-rendered sidebar with kit state, readiness meter, Open Issues, Suggestions, module status. | Lab Builder for operator orientation; portal for modern route/app foundation. |
| Dashboard | Calm queue, blockers, last run, next actions. | Mission-control dashboard with readiness percent, recommended next step, build path, blockers, job status. | Lab Builder. |
| Run Center | Guided build, provider sections, queue, selected work, deep NetApp panel. | Live job, progress, checklist, stage details, log drawers, run review, execution mode. | Lab Builder for run execution model; portal for typed API and safety metadata. |
| Control/action catalog | Strong typed action catalog with plan/run placeholders and safety classifications. | Module/stage capability manifests and execution review. | Merge both. |
| Workflow state | Request lifecycle plus workflow runs and audit events. | Kit/job/stage traces with run bundles and history. | Portal for request governance; Lab Builder for hardware job execution. |
| Provider status | Source type, freshness, recheck command, evidence artifacts. | Readiness/precheck state and live job story. | Portal for status correctness. |
| Report center | Central issue/source summaries with page badges and recheck commands. | Reports, histories, debug bundles, run summaries. | Portal for current/historical classification; Lab Builder for run bundle richness. |
| iLO | Adapter, readiness, setup intent, setup apply, HPE storage/RAID integration. | Mature client split, inventory, power, upgrade, runtime verification. | Lab Builder for client depth; portal for gates and typed status. |
| Cisco | Console-first readiness, bootstrap requirements, console plan, Ansible status. | Cisco module routes/service and serial/SSH workflow patterns. | Tie; merge console-first model with portal status contracts. |
| RAID/storage | HPE RAID intent, discovery, plan, apply, reset, validation. | Detailed storage planning, drive identity, safe remap, controller selection. | Lab Builder. |
| ESXi | Install readiness and iLO-backed control actions/scripts. | ISO build, URL verification, virtual media, boot, management reachability. | Lab Builder. |
| NetApp | Strong planned-vs-current, observations, live/cached state, upgrade readiness, apply-disabled posture. | Deep module/service/route split, original snapshots, ONTAP catalog, console/IP workflows. | Merge; portal has better state semantics, Lab Builder has deeper workflow implementation. |
| Firmware/toolchain | Build Verification and Toolchain Readiness contracts. | Upgrade Helper and shared activity tracking. | Merge. |
| UI audit/tooling | Frontend build and screenshots by task. | UI layout/design/code health audit scripts. | Lab Builder. |
| Test structure | Pytest plus React build; typed FastAPI contracts. | Pytest plus code health/layout audit scripts. | Portal for typed API; Lab Builder for product audit tooling. |

## Duplicated Ideas

- Provider readiness, blockers, warnings, and next actions.
- Report/evidence links.
- Run Center stage selection.
- Lab profile/kit address intent.
- Toolchain/upgrade readiness.
- Provider-specific page sections for Cisco, iLO, RAID, ESXi, NetApp, firmware, and reports.
- Command wrappers around staged workflows.
- Product guidance that says evidence must be visible but not dominate main pages.

## What Should Be Merged

- Lab Builder module manifests should become a portal workflow/action capability registry.
- Lab Builder stage plugin and job trace ideas should feed portal Run Center.
- Portal source/freshness/status metadata should wrap all imported hardware state.
- Portal Report Center issue contract should absorb Lab Builder debug/run bundle links.
- Lab Builder UI patterns should inform portal shared components: setup strip, action feedback banner, Open Issues drawer, run checklist, and suggestion center.
- Lab Builder automation principles should become workflow engine rules.

## What Should Be Discarded

- Any pattern that grows a central monolith like legacy `app/main.py`.
- Any UI pattern that puts raw logs, raw JSON, or dense technical details on main pages by default.
- Any artifact list that lacks current/stale/historical/test labeling.
- Any hardware action exposed as a direct button without a workflow object, gate, source, plan, audit event, and report path.
- Any duplicate status wording that competes with the canonical source/freshness contract.

## What Should Become Shared Modules

Backend:
- `workflow_registry`: capability manifest, provider, stage, actions, required gates, commands, and report contracts.
- `status_source`: canonical source/freshness/current-state metadata.
- `issue_contract`: blocker/warning/remediation/evidence schema.
- `artifact_index`: generated and historical report metadata with source/freshness labels.
- `lab_profile`: address intent allocator and validator.
- `run_trace`: job/stage event model, progress, logs, and run bundle metadata.
- `toolchain_readiness`: shared tool detection and fix guidance.

Frontend:
- `AppShell`
- `IssueDrawer`
- `SetupStrip`
- `ActionFeedback`
- `RunChecklist`
- `EvidenceDrawer`
- `ProviderFacts`
- `StatusBadge`
- `SectionSwitch`
- `ReportIssueCard`
- provider feature modules for Cisco, iLO, RAID, ESXi, NetApp, firmware, and verification

## What Should Become A Skill

Created now:
- `lab-builder-skill-steward`
- `lab-builder-dual-app-architecture`
- `lab-builder-product-craft`

Deferred candidates:
- state model
- action catalog
- visual design system
- test strategy
- provider-domain skills for NetApp, ESXi, Cisco, and firmware

These should wait until repeated tasks prove that a new skill would reduce
future mistakes beyond the existing skills.

## Proposed Final Product Architecture

The final product should be the portal, not two apps:
- `infra-config-portal` is the long-term control plane.
- `lab-builder` is the reference implementation for product feel, module/stage patterns, and hardware orchestration ideas.
- Hardware workflows move into the portal behind workflow/action registry entries and source/freshness/report contracts.
- Legacy scripts remain useful as references until replaced by typed services, tests, and run artifacts.

Core layers:
1. App shell and operator navigation.
2. Workflow/action registry.
3. Request/governance lifecycle.
4. Provider adapters and tool adapters.
5. Run engine with trace events.
6. Status source and current-state store.
7. Report Center and artifact index.
8. Lab profile and configuration intent.
9. Audit/event logging.

## Proposed UI And Navigation Architecture

Top-level navigation:
- Dashboard
- Run Center
- Control Center
- Firmware
- Verification
- Reports
- Settings

Supporting routes:
- Requests
- Lab Profiles
- Provider detail modules
- Audit events
- Media inventory

UI rules:
- Dashboard answers: what needs attention now?
- Run Center answers: what are we running, reviewing, or waiting on?
- Control Center answers: what actions exist and why are they allowed or blocked?
- Reports answers: what evidence and remediation exist?
- Settings answers: what local mode/profile/tool readiness is configured?

Provider sections should be list/detail surfaces with one next action, current
source/freshness, blockers, and collapsed evidence.

## Proposed Workflow Engine Architecture

Use a registry-driven workflow model:
- capability manifest
- stage order
- current-state collector
- desired-state builder
- plan builder
- approval policy
- apply executor
- verify executor
- report writer
- rollback notes
- recheck command
- evidence artifacts

Every hardware workflow follows:
1. Discover
2. Plan
3. Apply
4. Verify
5. Report

Direct execution from UI remains disabled unless the workflow explicitly
supports it and all gates are satisfied.

## Proposed Reporting And State Architecture

State:
- `source_type`: live probe, live cached, operator config, historical artifact, mock, test, or not checked.
- `checked_at`
- `freshness`
- `is_current`
- `recheck_command`
- `evidence_artifacts`
- `blockers`
- `warnings`
- `next_safe_action`

Reports:
- Issue cards first.
- Current blockers before warnings.
- Historical evidence below current state.
- Raw payloads collapsed.
- Copyable fix/recheck commands when practical.
- Report links are evidence, not blocker headlines.

Artifacts:
- Indexed by provider, workflow, stage, source type, generated time, freshness, redaction, and downloadability.
- Historical artifacts never create current red blockers without a fresh check.

## Recommended Migration Sequence

1. Extract portal frontend route modules and shared product components.
2. Create a backend workflow/action registry from the existing Control Center definitions.
3. Add a run trace model inspired by Lab Builder jobs.
4. Build a current-state artifact index with source/freshness labels.
5. Port Lab Builder setup strip, action feedback, and issue drawer patterns to the portal.
6. Move one workflow family at a time into registry-backed workflows, starting with NetApp state/readiness or RAID planning.
7. Add code health and UI layout audit scripts to the portal.
8. Keep all provider integrations mock-safe by default and real-lab gated.
