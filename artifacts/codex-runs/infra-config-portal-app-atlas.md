# Infra Config Portal App Atlas

Date: 2026-06-09

Scope:
- Primary repo: `/home/administrator/infra-config-portal`.
- No hardware workflows were run.
- No secrets, tokens, passwords, or credential values were printed or copied.
- Mock/test state and historical artifacts were treated as evidence only, not current real lab state.
- The worktree was already dirty before this inspection; this report does not classify unrelated changes as mine.

Applied skills:
- `lab-builder-real-runtime`
- `lab-builder-ux`
- `lab-builder-hardware-run`
- `lab-builder-report-remediation`
- `lab-builder-toolchain`
- `lab-builder-dual-app-architecture`
- `lab-builder-product-craft`
- `lab-builder-skill-steward`

## Executive Snapshot

`infra-config-portal` is already a safer control-plane implementation than the old app. Its strongest assets are runtime provenance, explicit provider modes, report normalization, a policy-backed Control Center, and a broad set of safe real-lab readiness entrypoints. The main product problem is not missing capability; it is that capability is spread across many routes, scripts, reports, and a very large frontend file. The app needs an operator-facing information architecture that turns the existing safe primitives into a coherent Lab Setup, Control Center, Run Center, and Reports workflow.

## Repo Shape

Top-level structure:
- `.codex/`: project automation, skills, task queue, and run history.
- `AGENTS.md`: safety and execution rules for Codex work in this repo.
- `Makefile`: root entrypoint for tests, lint, app lifecycle, Codex tasks, provider readiness, real-lab probes, firmware, build verification, and full rebuild report commands.
- `app/`: current implementation.
- `reference/`: target behavior reference from old Lab Builder.
- `scripts/`: Codex wrapper helpers and local real-lab setup helper.
- `artifacts/`: generated local reports and run evidence.

Application structure:
- `app/backend/`: FastAPI, SQLAlchemy, Pydantic, provider adapters, services, scripts, and tests.
- `app/frontend/`: React, TypeScript, Vite, CSS, API client, and typed contracts.
- `app/docs/`: workflow and operator documentation.
- `app/Makefile`: app-local testing and provider workflow commands.

## Project Instructions And Skills

`AGENTS.md` is strict and useful. It correctly defines:
- This app as a mock-first control plane, not the automation engine itself.
- Real providers disabled by default unless explicitly configured.
- No hardware calls during automated Codex work.
- Explicit separation of API routes, schemas, domain models, workflow state, provider adapters, audit/event logging, and frontend UI.
- Root-level command usage from `/home/administrator/infra-config-portal`.
- UI screenshot expectations for visible UI changes.

`.codex/skills/` contains the active Lab Builder skill set:
- `lab-builder-real-runtime`
- `lab-builder-ux`
- `lab-builder-hardware-run`
- `lab-builder-report-remediation`
- `lab-builder-toolchain`
- `lab-builder-dual-app-architecture`
- `lab-builder-product-craft`
- `lab-builder-skill-steward`

The skills are well aligned with the repo's current safety risks. They should remain the default guidance for future runs.

## Makefiles And Commands

Root commands cover:
- General checks: `make test`, `make lint`.
- App lifecycle: `make app-start`, `make app-stop`, `make app-status`, `make app-logs`.
- Codex wrappers: `make codex-task`, `make codex-next`.
- Provider checks: `provider-smoke`, `provider-lab-live-status`, iLO reachability/auth/inventory/readiness, Cisco console/bootstrap/readiness, NetApp readiness/state/validation, HPE RAID discovery/plan/apply/reset/validate, ESXi readiness/media/boot/detect.
- Firmware: inventory, compliance, package/waiver checks, upgrade planning.
- Build Verification and full rebuild summaries.
- Toolchain and serial console readiness.

Important behavior:
- Tests force safe mock defaults.
- Real-lab commands are explicit command targets, not ambient app behavior.
- Current default mode in the root make context is oriented toward local lab operation, but repo guidance still requires mock-safe automated behavior and explicit write gates.

## Backend Architecture

Core files:
- `app/backend/app/api/routes.py`: large API surface for VM request lifecycle, provider status, Control Center, Reports, Lab Profiles, Cisco, iLO, RAID, ESXi, NetApp, Firmware, Build Verification, and media inventory.
- `app/backend/app/models.py`: SQLAlchemy models for users, environments, requests, workflow runs, approvals, audit events, provider runtime state, iLO intent, and HPE RAID intent.
- `app/backend/app/schemas.py`: typed API contracts for the same surfaces.
- `app/backend/app/providers/`: provider status contracts, provider registry, action policy, redaction, iLO, Cisco, ESXi, NetApp, and mock providers.
- `app/backend/app/services/`: report center, source metadata, lab profiles, control actions, firmware compliance, build verification, NetApp setup, Cisco setup, iLO setup, ESXi install, HPE RAID workflow, and other orchestration services.
- `app/backend/app/scripts/`: command-oriented workflow helpers that emit redacted artifacts.

The backend already has the right conceptual pieces for a control plane:
- Provider adapters are separated from request lifecycle code.
- Provider statuses expose provenance and operator visibility fields.
- Write-like actions are policy-gated.
- Reports classify current, stale, historical, and not-checked evidence differently.
- Lab profile state is local and non-secret.

The main backend weakness is fragmentation: device workflows exist as API endpoints, service functions, scripts, reports, and Control Center action definitions, but there is no single hardware workflow engine or stage-run database model tying them together.

## Runtime And State Model

Strong current patterns:
- `ProviderStatus` includes `source_type`, `checked_at`, `freshness`, `is_current`, `is_operator_visible`, `recheck_command`, evidence artifacts, blockers, warnings, safe actions, disabled actions, and last probe metadata.
- `status_source.py` centralizes source metadata and current/stale decisions.
- `report_center.py` downgrades stale, historical, test-fixture, and not-checked information so old artifacts do not become current critical blockers.
- `ProviderRuntimeState` stores provider identity, role, configured/discovered state, source, last successful probe time, report path, confidence, blockers, and JSON payload.

Gaps:
- Provider runtime state is not yet the canonical source for every workflow.
- Historical report artifacts still carry too much product weight.
- Current-state pages can feel like a collection of report readers instead of a live state model with recheck actions.
- There is no durable per-stage run model for hardware workflows.

Recommendation:
- Keep the current source metadata model.
- Promote it into a unified `RuntimeState`/`HardwareRun` substrate before adding more provider-specific apply lanes.

## Backend API Surface

Current major API groups:
- Request lifecycle: create/list/read/update/submit/approve/reject/plan/cancel/execute.
- Workflow runs and artifacts.
- Audit events.
- Provider status and provider probes.
- Provider mode settings.
- Control Center action catalog, plan, run placeholder, and access config.
- Firmware inventory, compliance, waivers, package checks, and upgrade plans.
- Full rebuild summary and Build Verification.
- Reports and issue summaries.
- Lab Profiles CRUD and activation.
- Cisco setup readiness, wizard plan, bootstrap requirements, console bootstrap plan/apply, prompt readiness.
- iLO upgrade/readiness/destructive rebuild preview/setup intent/compare/report/apply plan/apply.
- HPE RAID discovery, intent, plan, apply, pending, reset, validation.
- ESXi install readiness.
- NetApp plan, console readiness/discovery/state, live state, setup validation, NFS/vCenter readiness, observations, comparison, upgrade readiness, artifacts.
- Catalog and media inventory.

This breadth is useful, but it needs a stronger navigation model. The operator should not have to understand the route map to understand the lab.

## Provider And Action Policy

Provider modes:
- `mock`
- `local-readonly`
- `local-lab-readwrite`

`LabActionPolicy` is one of the best current pieces:
- It classifies actions by category, including read-only, app state writes, network/storage/BIOS/boot/virtual-media/OS-install/VM-deploy/power/firmware/factory operations.
- It requires explicit acknowledgements for risky categories.
- It allows controlled read-only and app-state operations before allowing hardware writes.
- It can deny direct execution and return a user-facing reason.

This should become the policy layer under the future workflow engine and Action Catalog.

## Control Center

Current Control Center strengths:
- Backend `control_actions.py` defines a broad `ControlActionCatalog`.
- Actions include current state, desired state, diffs, provider diagnostics, report links, last results, safety posture, and manual commands.
- Sections exist for Lab Profile, Cisco, iLO, RAID, ESXi, NetApp, Firmware/Upgrade, Verification, and Reports.
- Direct action execution is intentionally disabled or placeholder-backed; the response returns manual command guidance instead of silently running hardware workflows.

Current Control Center weaknesses:
- It duplicates workflow knowledge already present in scripts and provider services.
- Some actions are really workflow stages and should be backed by a durable run engine.
- The UI is powerful but dense; the novice path should be Lab Setup list/detail, while Control Center should become the expert console.

Recommendation:
- Keep Control Center as the expert action catalog.
- Move canonical action/stage metadata into a shared service consumed by Lab Setup, Run Center, Reports, and Control Center.

## Frontend Architecture

Current frontend files:
- `app/frontend/src/App.tsx`: the main app shell, routing, pages, and many components in one very large file.
- `app/frontend/src/api.ts`: API client.
- `app/frontend/src/types.ts`: frontend data contracts.
- `app/frontend/src/styles.css`: app styling and responsive shell.

Routes:
- `/dashboard`
- `/run-center`
- `/control-center`
- `/firmware`
- `/verification`
- `/reports`
- `/settings`
- `/requests`
- `/requests/new`
- `/requests/:id`
- `/workflow-runs/:id`
- `/lab-profiles`
- `/audit-events`
- `/media`
- redirects from `/artifacts` to `/reports` and `/providers` to `/verification`

Major pages and components:
- Dashboard
- Run Center
- Control Center
- Firmware
- Build Verification
- Reports
- Settings
- Request list/new/detail
- Workflow run detail
- Audit events
- Media inventory
- Lab Profiles
- Provider detail blocks and many device-specific panels

Strengths:
- React/Vite is a better long-term shell than the old app's Jinja/HTMX templates.
- The sidebar already groups major surfaces.
- Provider status, profiles, reports, and Control Center are integrated.
- The UI shows safety language and blocked/current/stale distinctions.

Weaknesses:
- `App.tsx` is too large and slows future product work.
- Several pages mix overview, details, raw evidence, controls, and education in one surface.
- Reports, Control Center, Verification, and Run Center overlap conceptually.
- There is not yet a crisp Lab Setup list/detail workflow across Cisco, iLO, RAID, ESXi, NetApp, and Firmware.

## Reports And Artifacts

Current report model:
- `report_center.py` collects evidence from Build Verification, Firmware, Cisco, iLO, RAID, ESXi, NetApp, Serial, Toolchain, and Lab Profile sources.
- Issue cards include source metadata, severity, status, recheck commands, fix locations, and evidence links.
- Stale/historical/test fixture sources are not treated as current blockers.
- Page badges summarize issue state across the app.

Artifact patterns:
- Provider scripts write redacted JSON/Markdown under local artifact paths.
- Build Verification and full rebuild summaries are report-first.
- Reports expose recheck commands rather than pretending an old run is live state.

Gaps:
- Reports are still file-path driven.
- Run history is not yet a first-class model.
- A failed or blocked run does not yet become a durable operator story with stage timeline, logs, issue cards, and debug bundle in one place.

## Docs

Important docs:
- `README.md`: real-lab operator surface, provider modes, app lifecycle, Control Center, Firmware, Build Verification, and report guidance.
- `app/docs/workflows.md`: Control Center behavior, direct run placeholder, access config storage, Run Center skeleton, media inventory, full rebuild split.
- `reference/lab-builder-reference.md`: target behavior reference from old Lab Builder.

Docs are strong on safety posture. They need to catch up after the product architecture is consolidated so there is one operator mental model.

## Tests

Current backend tests cover:
- VM request validation and lifecycle.
- Provider status shape and provider adapters.
- Source type and freshness behavior.
- Report Center issue classification.
- Lab profile behavior.
- Cisco setup/bootstrap/prompt readiness.
- iLO readiness, redaction, setup planning, and GET-only adapter behavior.
- HPE RAID discovery/plan/apply/reset/validate paths.
- ESXi readiness and boot planning.
- NetApp setup/readiness/state behavior.
- Firmware compliance and upgrade decisions.
- Build Verification and full rebuild summaries.
- Media inventory and serial console discovery.

Frontend test coverage appears to rely mainly on `npm run build`; no dedicated frontend unit or E2E suite was identified during this pass.

## Workflow Atlas

### Cisco

Current implementation:
- Console-first readiness and discovery.
- Bootstrap requirements stored locally.
- Prompt readiness and privilege checks.
- Console bootstrap plan/apply endpoints.
- Cisco Ansible provider surface exists after management reachability.
- Firmware inventory and validation hooks.

Product read:
- The safety posture is good: console discovery and prompt readiness come before write-like bootstrap.
- The workflow needs clearer operator staging: Discover Console -> Confirm Access -> Bootstrap Preview -> Apply Gate -> Validate SSH/SCP -> Save/Reload if required -> Report.

### iLO / HPE

Current implementation:
- Reachability, auth, inventory, readiness, upgrade readiness, destructive rebuild preview.
- Setup intent, compare report, setup report preview, apply plan, and apply endpoint.
- Provider adapters support redacted status and GET-only diagnostics.

Product read:
- The app has a strong iLO safety model and redaction story.
- The UI should separate read-only diagnosis from guarded setup apply even more visibly.

### RAID

Current implementation:
- HPE storage discovery.
- RAID intent persistence.
- Plan preview, apply plan, apply, pending check, reset plan, server reset, post-reset validation.
- Destructive behavior is policy-gated.

Product read:
- The staged RAID workflow is credible.
- It needs to be represented as a first-class run with stage timeline and explicit reboot/pending state, not just endpoint/report surfaces.

### ESXi

Current implementation:
- Install readiness.
- Media inventory and ISO path checks.
- Virtual media and one-time boot actions represented in Control Center and scripts.
- Readiness links to iLO state and lab profile.

Product read:
- Good foundation, but ESXi currently reads more like a set of checks than a full install run.
- The target model should be: media readiness -> kickstart/ISO generation -> virtual media insert -> boot override -> power action -> management validation -> report.

### NetApp

Current implementation:
- Plan preview.
- Console readiness and autodiscovery.
- Console state and live state.
- Setup validation.
- NFS/vCenter readiness.
- Observations and readiness comparison.
- Upgrade readiness.
- Artifacts list.

Product read:
- Current app has the right safety boundary: planned intent and current discovered state are separate.
- It should borrow richer NetApp planning detail from old Lab Builder, but keep this repo's no-apply-by-default posture.

### Firmware

Current implementation:
- Inventory, compliance, waivers, packages, upgrade plan, and upgrade placeholders.
- Firmware appears in Control Center, Reports, Build Verification, and Make targets.

Product read:
- Firmware is close to becoming a standalone product area.
- It needs baseline management, package inventory, waivers, upgrade run planning, and rollback notes as one workflow.

### Build Verification

Current implementation:
- Report-first certification surface.
- Toolchain, lab profile, provider, firmware, and workflow readiness inputs.
- Classifications separate blockers, warnings, stale evidence, and missing checks.

Product read:
- This is one of the clearest current product surfaces.
- It should become the readiness summary that drives the sidebar and Lab Setup list.

### Reports

Current implementation:
- Unified issue collection with source metadata, severity, status, recheck commands, fix locations, and evidence links.
- Page badges and summary endpoints.

Product read:
- Keep the report center contract.
- Move raw JSON and historical files behind collapsed evidence drawers.
- Promote actionable issue cards and recheck commands.

### Lab Profiles

Current implementation:
- Local profile CRUD and activation.
- Address planning and subnet generation.
- Provider targeting context.
- Non-secret local state.

Product read:
- This is better and safer than old kit configs.
- It should become Settings / Lab Profile and provide the context banner across the app.

### Control Center

Current implementation:
- Broad action catalog with manual command guidance and policy state.
- Strong expert surface.

Product read:
- Keep it, but stop making it the only place an operator can understand the workflow.
- Use Lab Setup list/detail for guided work, Control Center for expert action lookup, and Reports for evidence/issues.

## Product Risks

Main risks:
- The app can feel more complex than the hardware workflows themselves because all details are surfaced at once.
- `App.tsx` concentration makes UI changes risky.
- Without a workflow engine, every provider grows its own mini run model.
- Report artifacts can become a shadow database if not folded into a real run/history model.
- Current app has many safe controls, but the user journey from blocked state to next action is inconsistent across pages.

## Stage 1 Conclusions

Keep:
- Runtime source metadata and freshness rules.
- Provider action policy.
- Report Center issue normalization.
- Lab Profile non-secret local model.
- Control Center action catalog.
- Explicit Make targets and redacted artifacts.

Change:
- Build a first-class Lab Setup list/detail workflow.
- Introduce a durable hardware workflow engine.
- Split frontend pages/components out of `App.tsx`.
- Make Reports the issue/evidence center, not a raw artifact browser.
- Turn Control Center into the expert command catalog backed by the same action/stage metadata used by Run Center.
