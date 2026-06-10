# Dual-App Merge Plan

Date: 2026-06-09

Scope:
- Current app: `/home/administrator/infra-config-portal`.
- Legacy reference: GitHub `stevehogeveen/lab-builder` at `main`, commit `c356ca430fea63f578fa8b9968784de57de64319`.
- No hardware workflows were run.
- No `/home/administrator/lab-builder` files were modified.
- Mock/test/historical state was not treated as current real lab state.

Applied skills:
- `lab-builder-real-runtime`
- `lab-builder-ux`
- `lab-builder-hardware-run`
- `lab-builder-report-remediation`
- `lab-builder-toolchain`
- `lab-builder-dual-app-architecture`
- `lab-builder-product-craft`
- `lab-builder-skill-steward`

## Merge Strategy

Use `infra-config-portal` as the base. It has the safer architecture and the right long-term technology stack. Adopt the old app's workflow model and operator UX ideas through rewrites, not by copying server-rendered code.

Guiding rules:
- Preserve mock-safe defaults and explicit real-lab gates.
- Never treat old artifacts as current lab state.
- Keep secrets and credentials outside reports, UI summaries, and committed files.
- Prefer shared typed services over duplicated provider page logic.
- Move operators from profile -> setup -> run -> report without forcing them through raw artifacts.

## Capability Decisions

| Capability | Decision | Why | Target Form |
| --- | --- | --- | --- |
| React app shell | Keep current implementation | Better long-term frontend base and typed API fit. | Split into page/component modules and refine navigation. |
| Old Jinja shell | Discard implementation, adopt ideas | Useful patterns but not the desired stack. | React sidebar context card, quick jump, issue drawer, compact view. |
| Sidebar kit/profile context | Adopt from lab-builder | Operators need active profile, readiness, and blockers always visible. | Shared `ActiveProfileContext` and sidebar summary component. |
| Module manifests | Adopt from lab-builder, rewrite | Cleaner capability/nav ownership. | Typed backend module/action manifest plus generated frontend types. |
| Stage registry | Adopt from lab-builder, rewrite | Needed for hardware workflow composition. | `HardwareStageRegistry` with discover/plan/apply/verify/report. |
| Current provider status/source model | Keep current implementation | Strong safety and stale/current semantics. | Shared runtime state service consumed by providers, reports, actions, runs. |
| Current action policy | Keep current implementation | Strongest write-gate and category model. | Policy layer under Action Catalog and workflow engine. |
| Control Center action catalog | Merge both | Current catalog is strong; old Run Center gives process ceremony. | Canonical Action Catalog feeding Control Center, Lab Setup, Run Center, Reports. |
| Old Run Center execution ceremony | Adopt, rewrite | Preview/review/confirm/run/live progress is exactly the operator model needed. | DB-backed run records, stage timeline, policy gates, live polling/WebSocket. |
| Current Run Center UI | Rewrite | Current page is a shell, not the canonical engine yet. | Run builder, review, approval gate, live stage monitor, run archive. |
| Report Center issues | Keep current implementation | Best stale/current and remediation model. | Extend to link issues to run/stage/evidence records. |
| Old run bundles/history/debug bundles | Adopt | Current app lacks a cohesive run archive. | Redacted run bundles generated from workflow engine. |
| Lab Profiles | Merge both | Current is safer; old has better kit-centered product framing. | Lab Profile as non-secret profile plus run grouping/context. |
| Provider scripts | Keep current, wrap | Existing scripts produce useful redacted artifacts. | Stage runners call or wrap scripts through policy-aware adapters. |
| Make targets | Keep current | Clear explicit operator commands. | Keep as manual/recheck commands and workflow runner entrypoints. |
| Old monolithic `app/main.py` | Discard | It is too concentrated and not portable to current architecture. | Recreate only concepts in current backend services. |
| Old credential/config kit persistence | Discard | Blends sensitive/local runtime concerns too much. | Preserve current secret-safe profile boundaries. |
| Old NetApp planning depth | Adopt selectively | Strong domain model. | Add typed NetApp plan/profile/defaults without direct ONTAP apply. |
| Old Cisco operator findings/diff | Adopt selectively | Strong operational clarity. | Add console-first Cisco findings, config diff, port map, backup evidence. |
| Old automation principles | Adopt | Good hardware safety language. | Add to docs and enforce in stage engine/report issue contracts. |
| Old health-check script | Adopt selectively | Useful local developer command. | Add or extend current root Make target only if not duplicative. |
| Skills | Mostly keep | Existing skills cover most recurring risks. | Track candidates; create after repeated implementation evidence. |

## Keep Current Implementation

Keep without major conceptual change:
- Provider mode settings.
- `ProviderStatus` provenance fields.
- `status_source.py` freshness/current-state rules.
- `report_center.py` issue normalization.
- `LabActionPolicy` category gates.
- Redaction conventions.
- Lab Profile non-secret storage.
- Build Verification source classification.
- Firmware compliance/waiver/package model.
- Root Make targets as explicit operator/recheck commands.
- Backend pytest style and safety tests.

Reason:
- These pieces prevent the main failure modes: mock-as-real, stale-as-current, and accidental hardware write.

## Adopt From Lab Builder

Adopt as product behavior, with current-app rewrites:
- Module manifests for title, description, navigation, capabilities, routes, and action/stage metadata.
- Stage registry and enabled-stage filtering.
- Run Center preview/review/confirm `EXECUTE` ceremony.
- Background job status: current stage, progress percent, completed/total, logs, trace events.
- Live job stream or polling model.
- Run bundles, history, and latest failure debug bundle.
- Sidebar profile/kit card, readiness meter, blocker count, quick jump, issue drawer, compact view.
- Setup task-list rows with status dots and whole-row navigation.
- Automation principle: discover, compare, correct only when provably safe, otherwise explain and block.

Reason:
- These are operator workflow improvements and do not require adopting unsafe or stale implementation details.

## Merge Both

Merge:
- Lab Profiles and kit context.
- Control Center and Run Center.
- Report Center issues and old run bundles.
- Current provider readiness endpoints and old stage plugins.
- Current Build Verification and old readiness meter.
- Current firmware compliance and old upgrade helper/activity framing.
- Current Cisco safety gates and old Cisco config diff/operator findings.
- Current NetApp planned/current separation and old NetApp profile/adaptive discovery depth.

Merged target:
- One source of truth for action/stage definitions.
- One runtime state model for provider observations.
- One run model for stage execution and evidence.
- One report model for issues, evidence, and recheck commands.

## Discard

Discard:
- Copying old Jinja templates directly.
- Copying old `app/main.py` structure.
- Any old app path that blends desired state, current state, runtime state, and credential values in one local config object.
- Any old real execution behavior that bypasses current provider modes or action policy.
- Raw artifact browsing as the primary operator UX.
- UI pages that rely on explanatory text instead of clear state, next action, and evidence.

## Rewrite

Rewrite as current-app code:
- Module manifest loader.
- Hardware stage registry.
- Workflow run engine.
- Run Center.
- Lab Setup list/detail.
- Sidebar active profile/readiness block.
- Issue drawer and quick jump.
- Run bundle writer.
- Debug bundle writer.
- Cisco diff/operator findings.
- NetApp plan/profile details.

Rewrite principles:
- Pydantic contracts first.
- API route layer thin.
- Services own business rules.
- Provider adapters own external calls.
- Every real-lab observation has source metadata.
- Every write-like stage checks action policy.
- Every artifact is redacted by construction.

## Turn Into Shared Components

Frontend shared components:
- `StatusBadge`
- `SourceMetadataBadge`
- `FreshnessPill`
- `IssueCard`
- `EvidenceDrawer`
- `RecheckCommand`
- `ActionPlanPanel`
- `ActionButtonWithPolicy`
- `StageTimeline`
- `RunProgress`
- `LabSetupRow`
- `LabSetupDetail`
- `ProfileContextCard`
- `ToolchainReadinessList`
- `ReportLinkList`
- `CurrentDesiredDiff`

Backend shared services:
- `action_catalog`
- `hardware_stage_registry`
- `hardware_run_service`
- `runtime_state_service`
- `evidence_artifact_service`
- `run_bundle_service`
- `issue_service`
- `toolchain_readiness_service`
- `profile_context_service`

Shared contracts:
- `ActionDefinition`
- `StageDefinition`
- `HardwareRunRead`
- `HardwareStageRunRead`
- `RuntimeObservationRead`
- `IssueRead`
- `EvidenceArtifactRead`
- `ToolchainRequirementRead`

## Turn Into Skills

Do not create new skills during this run.

Candidate skill topics to revisit after implementation:
- `lab-builder-state-model`: if repeated work changes source type, freshness, run observations, or runtime migrations.
- `lab-builder-action-catalog`: if multiple runs modify action definitions, stage registry, and Control Center semantics.
- `lab-builder-test-strategy`: if workflow engine and frontend state tests become recurring.
- `lab-builder-netapp-ontap`: if NetApp implementation deepens beyond readiness/preview.
- `lab-builder-esxi-kickstart`: if ESXi ISO/kickstart/virtual-media execution becomes active work.
- `lab-builder-cisco-network`: if Cisco console/SSH/VLAN/bootstrap workflows repeat.
- `lab-builder-firmware-upgrades`: if firmware upgrade plans become executable.
- `lab-builder-visual-design-system`: if shared UI components and screenshot validation need stricter reusable rules.

## Proposed Implementation Runs

### Run 1: Workflow Substrate

Goal:
- Add the durable hardware run model and stage engine without enabling hardware writes.

Deliverables:
- Backend models for hardware run, stage run, observation, evidence.
- Stage registry contract.
- Action policy integration.
- Run bundle writer.
- Tests for source metadata, stale classification, policy denial, and redaction.

### Run 2: Lab Setup And Run Center UI

Goal:
- Make the app easier to use without changing hardware behavior.

Deliverables:
- Split `App.tsx`.
- Lab Setup list/detail.
- Sidebar profile/readiness block.
- Issue drawer.
- Run Center review/progress/archive backed by placeholder or read-only stage data.
- Screenshot validation.

### Run 3: Provider Workflow Consolidation

Goal:
- Move Cisco, iLO, RAID, ESXi, NetApp, Firmware, and Build Verification into the same action/stage/report model.

Deliverables:
- Action/stage manifests per provider.
- Existing scripts wrapped as stage runners where appropriate.
- Reports linked to run/stage evidence.
- Provider-specific tests.
- Updated docs/runbooks.

## Merge Plan Conclusion

The winning product is not a direct merge of files. It is a conceptual merge:
- Current app as the safe control plane.
- Old app as the workflow and operator-experience reference.
- A new shared hardware workflow engine as the bridge.
