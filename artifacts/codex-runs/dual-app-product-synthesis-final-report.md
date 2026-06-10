# Dual-App Product Synthesis Final Report

Date: 2026-06-09

Scope:
- Current app: `/home/administrator/infra-config-portal`.
- Legacy reference: GitHub `stevehogeveen/lab-builder` at `main`, commit `c356ca430fea63f578fa8b9968784de57de64319`.
- No files were modified in `/home/administrator/lab-builder`.
- No hardware workflows were run.
- No secrets, tokens, passwords, or credential values were printed or copied.
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

## Bottom Line

Use `infra-config-portal` as the product base. It is safer, better typed, and already has the right runtime/reporting principles. Use old `lab-builder` as a workflow and product reference. Its best ideas are the kit-centered setup flow, stage registry, Run Center execution ceremony, live job progress, run bundles, history, and dense operator navigation.

The first product move should be a workflow substrate: shared Action Catalog plus stage/run records that preserve current app safety semantics. After that, refactor the UI into Lab Setup list/detail, Control Center, Run Center, and Reports & Issues around the same data.

## Top 10 Things To Steal From Lab Builder

1. Module manifests for navigation, capabilities, routes, and setup ownership.
2. Stage registry with enabled-stage filtering.
3. Run Center preview/review/confirm/execute ceremony.
4. Exact confirmation phrase and checkbox before real execution.
5. Background job progress with current stage, logs, trace events, and progress percent.
6. Run bundles, older run history, related reports, and latest failure debug bundle.
7. Sidebar kit/profile card with readiness meter and blocker count.
8. Quick jump, global open issues drawer, and compact density toggle.
9. Task-list setup navigation with status dots and whole-row navigation.
10. Rich Cisco and NetApp operator detail: config diffs, findings, adaptive discovery, protocol/profile planning, and upgrade activity.

## Top 10 Things Current App Does Better

1. Explicit `source_type`, `freshness`, `checked_at`, `is_current`, and `recheck_command` semantics.
2. Strong handling of mock/test/historical/stale evidence so it does not become current real lab state.
3. Provider action policy with categories and write gates.
4. Safer non-secret Lab Profile model.
5. Typed FastAPI/Pydantic contracts and React/TypeScript frontend.
6. Report Center issue normalization with severity, status, evidence, fix location, and recheck commands.
7. Control Center action catalog with current/desired/diff and manual command posture.
8. Provider adapter boundaries and redaction rules.
9. Broader backend tests for providers, reports, firmware, NetApp, Cisco, iLO, RAID, ESXi, profiles, and lifecycle behavior.
10. Root Make targets that expose explicit operator commands without hiding hardware workflows behind ambient UI behavior.

## Top 10 Product Cleanup Moves

1. Create a first-class Lab Setup list/detail workflow for Cisco, iLO, RAID, ESXi, NetApp, Firmware, Build Verification, and Toolchain.
2. Split `app/frontend/src/App.tsx` into feature pages and shared components.
3. Make one Action Catalog feed Lab Setup, Control Center, Run Center, and Reports.
4. Add durable hardware run and stage-run records instead of relying on report files as a shadow database.
5. Make Reports & Issues issue-first, with raw JSON and historical artifacts collapsed.
6. Add active profile/readiness/blocker context to the sidebar.
7. Normalize page states: current blocker, stale check, not checked, warning, ready, unavailable.
8. Turn Build Verification into the product-wide readiness summary.
9. Group provider scripts behind stage runners so commands remain explicit but product state is unified.
10. Keep Control Center as the expert console and stop making it carry the guided setup flow alone.

## Next 3 Big Implementation Runs

### 1. Workflow Substrate

Goal:
- Add the safe shared backend layer that future UI and provider work can build on.

Deliver:
- `HardwareRun`, `HardwareStageRun`, `RuntimeObservation`, `EvidenceArtifact`, and `Issue` contracts.
- Stage registry with discover/plan/apply/verify/report semantics.
- Action policy integration.
- Redacted run bundle writer.
- Tests for source freshness, stale/historical classification, policy denial, run state transitions, and redaction.

### 2. Lab Setup And Run Center UI Refactor

Goal:
- Make the app easier to scan and operate without changing hardware behavior.

Deliver:
- Split frontend feature modules.
- Lab Setup list/detail.
- Sidebar active profile card.
- Issue drawer.
- Run Center preview/review/progress/archive backed by the new substrate or safe placeholders.
- Screenshot validation for the changed pages.

### 3. Provider Workflow Consolidation

Goal:
- Bring Cisco, iLO, RAID, ESXi, NetApp, Firmware, and Build Verification under one action/stage/report model.

Deliver:
- Provider action/stage manifests.
- Existing scripts wrapped as policy-aware runners where appropriate.
- Reports linked to run/stage/evidence.
- Device-specific tests.
- Updated operator docs and Make command mapping.

## Recommended Skill Updates

Do not create new skills now.

Revisit after implementation:
- `lab-builder-state-model`: likely valuable once the runtime/run contracts exist.
- `lab-builder-action-catalog`: likely valuable once Action Catalog and stage manifests are implemented.
- `lab-builder-test-strategy`: useful after workflow-engine and frontend state tests start repeating.
- Provider-specific skills for NetApp, ESXi, Cisco, and Firmware only after those workflows move beyond readiness/preview.

Update existing skills later with concrete contracts:
- Add final run/stage/evidence model names to `lab-builder-real-runtime`.
- Add final stage contract to `lab-builder-hardware-run`.
- Add final issue/run/evidence linkage to `lab-builder-report-remediation`.
- Add final Lab Setup and Run Center component rules to `lab-builder-ux`.
- Add final tool requirement schema to `lab-builder-toolchain`.

## What To Do First

Start with the workflow substrate, not another provider page. The current app already has enough provider-specific surfaces. The missing product layer is a durable, safe run/stage/evidence model that every page can share.

First concrete implementation target:
- Add a DB/API-backed hardware run model and stage registry in preview/read-only mode.
- Connect one low-risk source, such as Build Verification or Toolchain readiness, to prove the model.
- Then connect one provider readiness workflow, such as Cisco console discovery or iLO reachability, without enabling hardware writes.

This gives the app a spine before more provider depth is added.

## Final Product Direction

The synthesized product should be:
- Profile-aware.
- Source-explicit.
- Issue-driven.
- Stage-based.
- Report-backed.
- Safe by default.
- Expert-capable without making the guided path dense.

The old app shows how the workflow should feel. The current app shows how it should be made safe.
