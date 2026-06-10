# Lab Builder App Atlas

Date: 2026-06-09

Scope:
- Legacy app target: `/home/administrator/lab-builder`.
- Local checkout status: present, dirty, and behind GitHub `main`.
- Source of truth used for this atlas: GitHub repository `stevehogeveen/lab-builder` at `main`, commit `c356ca430fea63f578fa8b9968784de57de64319`.
- No files were modified under `/home/administrator/lab-builder`.
- No hardware workflows were run.
- No secrets, tokens, passwords, or credential values were printed or copied.
- Historical artifacts and local runtime files were treated as historical evidence only.

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

The old Lab Builder app has a stronger operator workflow model than the current app. Its best ideas are kit-centered setup, module manifests, stage plugins, preview/review/execute gates, background job progress, live job UI, run bundles, history, and debug bundles. It is weaker on explicit runtime provenance, stale-vs-current semantics, typed frontend architecture, and provider safety boundaries. The right synthesis is to steal the workflow shape and process management, not the old app's monolithic implementation or credential/config persistence patterns.

## Source Selection

The local `/home/administrator/lab-builder` directory exists, but it is not the right source of truth for this run:
- It is on a non-main branch.
- It has many modified and untracked files.
- Its local HEAD is older than GitHub `main`.

Per the user instruction, GitHub `main` was used for stale/missing legacy app inspection. The local checkout was not modified.

## Repo Shape

Remote top-level structure:
- `README.md`: primary operator and developer orientation.
- `docs/`: HOWTO, automation principles, UX principles, ESXi operations, debugging, code maps, module notes, and ONTAP references.
- `app/main.py`: large central FastAPI/Jinja application.
- `app/core/`: config, database, jobs, models, policies, module registry, secrets, and stage registry.
- `app/modules/`: feature modules for Cisco, configs, ESXi config, ESXi install, execution, iLO, NetApp, OVF templates, QNAP, storage, and Windows.
- `app/stages/`: stage plugins and runtime adapters for iLO, storage, ESXi, NetApp, and Windows.
- `templates/`: Jinja page partials, sidebar, components, and app shell.
- `static/`: CSS and JavaScript for shell behavior, dashboards, live jobs, and interaction helpers.
- `scripts/`: start, health check, ISO build, backup/restore, release/audit, UI audit, duplicate finder, and deployment helpers.
- `config/kits/`: ignored per-kit local configuration.
- `artifacts/`: generated runs, history, reports, debug bundles, exports, generated media, and screenshots.

## README And Docs

The old README frames the app as an offline/controlled lab provisioning tool:
- A kit is the central unit of setup.
- Global, site, subnet, included systems, and credential references are saved before execution.
- Setup modules collect intent and readiness.
- Run Center previews, reviews, confirms, executes, and records artifacts.
- Artifacts are grouped under local run/history/export/generated directories.

Important docs:
- `docs/HOWTO.md`: end-to-end operator flow from install/start through kit setup, Run Center preview/confirmation, job monitor, and artifact review.
- `docs/automation-principles.md`: durable workflow principle: discover, compare, safely correct when provable, explain when not safe.
- `docs/ux-product-principles.md`: status visibility, task-list navigation, in-place feedback, useful empty states, command palette, compact density, and accessibility.
- `docs/esxi-operations.md`: ESXi operational guidance.
- `docs/debugging.md`: debugging and failure bundle concepts.

The docs are practical and product-oriented. Their best contribution is the workflow language: operators should always see current kit state, blockers, next action, preview, confirmation, live progress, and evidence.

## Architecture

Technology:
- Python FastAPI.
- Server-rendered Jinja templates.
- HTMX-like partial replacement patterns.
- Static CSS/JavaScript for interaction.
- SQLite/local files for runtime state.

Main architectural pieces:
- `app/main.py`: application composition, kit config functions, run summary builders, report/history functions, execution handlers, and many route handlers.
- `app/core/registry.py`: module manifest discovery, environment-based module enable/disable, route loading, and module navigation.
- `app/core/stage_registry.py`: simple `StagePlugin` protocol and `StageRegistry`.
- `app/core/jobs.py`: `JobStepRunner` that writes status, current stage, progress, logs, and trace events.
- `app/modules/*/manifest.yml`: feature metadata for title, description, routes, navigation, and capabilities.
- `app/modules/*/routes.py` and `service.py`: module-specific pages and behavior.
- `app/stages/*/plugin.py`: iLO, storage, ESXi, NetApp, and Windows stage adapters.

Strength:
- The module/stage registry ideas are clean and reusable.
- The app has a strong process model around preview, review, confirmation, execution, job monitor, and run history.

Weakness:
- Too much lives in `app/main.py`.
- Server-rendered templates are not the desired direction for `infra-config-portal`.
- Runtime state and safety metadata are less formal than in the current app.

## Module Registry

`app/core/registry.py` is one of the best pieces to reuse:
- It discovers `manifest.yml` files under `app/modules/`.
- It supports `LAB_BUILDER_DISABLED_MODULES` and `LAB_BUILDER_ENABLED_MODULES`.
- It loads module routes dynamically.
- It exposes module navigation metadata.
- It defines a `ModuleService` protocol with `discover`, `plan`, `validate`, `preview`, `apply`, `status`, and `repair`.

Product value:
- Navigation and capability metadata live close to the module.
- A new provider can be added without editing one giant navigation table.
- Setup, Action Catalog, Reports, and Run Center can all consume the same manifest.

Synthesis:
- Adopt the manifest idea.
- Rewrite it into typed Python/Pydantic plus TypeScript contracts for the current app.

## Stage Registry

`app/core/stage_registry.py` defines:
- A `StagePlugin` protocol: `enabled`, `plan`, `validate`, `execute`.
- A `CallableStagePlugin` dataclass.
- A `StageRegistry` that returns all or enabled stages.

Stage plugins exist for:
- iLO
- Storage
- ESXi
- NetApp
- Windows

Product value:
- Multi-stage hardware runs become composable.
- Enabled stages can be derived from kit/profile state.
- Run Center can show preview, validation, and execution stages consistently.

Synthesis:
- Adopt the concept.
- Rewrite the contract to match `infra-config-portal` safety model: `discover`, `plan`, `apply`, `verify`, `report`, plus `source_type`, `freshness`, action policy, audit logging, evidence links, and recheck commands.

## Process Management

Old app process model:
- `prepare_execute_handler` builds preview and validates selected scope.
- `execute_scope_handler` blocks if real launch is unavailable.
- It requires a confirmation checkbox.
- It requires the exact phrase `EXECUTE`.
- It starts a background thread for the selected scope.
- `JobStepRunner` updates job state, current stage, completed steps, total steps, progress percentage, logs, and trace events.
- WebSocket `/ws/job/{kit_name}` streams job updates.
- Run bundles and debug bundles are written for later inspection.

This is stronger than the current app's report-only script model. It should be adopted in spirit, but rewritten with the current app's database, API, and policy model.

## UI Patterns

Strong UI patterns in the old app:
- Kit context card in the sidebar.
- Readiness meter and blocker count.
- Sidebar utility controls: quick jump, open issues, compact view.
- Setup Modules section with status dots for each workflow.
- Run Center snapshot: mode, current step, progress, completed count, next action.
- Live job card with progress bar and stage checklist.
- Stage detail drawers with confirmed checks.
- Reports page groups latest run bundles, older runs, and matching files.
- Command palette built from visible sidebar navigation.
- Issue drawer available globally.
- Dense operator layout that prioritizes scanning over marketing.

Weak UI patterns:
- Some pages are extremely dense.
- Several cards nest details inside other cards.
- Jinja templates are harder to evolve than the current React shell.
- The visual system is useful but not a direct copy target.

Synthesis:
- Keep current React shell.
- Adopt kit/profile context, readiness meter, global issue drawer, quick jump, compact density, and stage checklist patterns.
- Implement as shared React components rather than copied Jinja.

## Lab Profiles And Kits

Old app model:
- A kit is the central configuration unit.
- Kit files live under `config/kits/`.
- Current kit state drives the sidebar, setup pages, run center, and reports.
- Setup pages collect global, site, subnet, included systems, credentials, iLO, storage, ESXi, Windows, NetApp, Cisco, and optional module settings.

Strength:
- Operators understand "one kit at a time".
- Readiness and blockers are attached to a named setup context.
- Run history can be grouped by kit.

Weakness:
- Kit configuration can blend desired state, local runtime details, and credential references too tightly.
- Current app's local non-secret Lab Profile model is safer.

Synthesis:
- Merge the ideas: use current Lab Profiles as the safe, non-secret profile substrate; borrow the old app's kit-centered context card, readiness meter, and history grouping.

## Operational Mode Handling

Old app has:
- Preview and real execution paths.
- Blocking when real launch is unavailable.
- Confirmation checkbox and exact `EXECUTE`.
- Run Center messaging that distinguishes preview and real execution.

Current app has:
- More explicit provider modes and source metadata.
- More formal action policy categories and write gates.

Synthesis:
- Keep current app's provider modes, action categories, source metadata, and stale/historical classification.
- Adopt old app's preview/review/confirm/run operator ceremony.

## Scripts And Make Targets

Old app scripts include:
- `scripts/start-app`: runs uvicorn against `app.main:app`.
- `scripts/health-check`: reports git status, workspace size, large files, Python compile, and pytest.
- ESXi ISO build helpers.
- Backup/restore helpers.
- Release/audit tools.
- UI and layout audit tools.
- ONTAP catalog helpers.

The script set is useful but not as safety-framed as the current repo's root Make targets. The health-check idea is worth adopting as a developer convenience, while hardware workflows should remain behind the current repo's explicit provider commands and policy gates.

## Device Workflow Ideas

### iLO

Old app has a stage plugin and setup page pattern that feeds Run Center execution. It treats iLO as a first-class stage in a kit workflow. Current app has safer provider status, redaction, and readiness primitives. Merge them by making iLO a first-class stage in the future workflow engine.

### Storage / RAID

Old app's automation principles are especially strong for storage:
- Discover current state.
- Compare approved intent with live hardware.
- Remap only when hardware identity still matches.
- Block if selected drives or controller identity changed.
- Write structured diagnostic logs.

Current app should use these rules for the HPE RAID run engine and keep its explicit destructive gate.

### ESXi

Old app has richer run sequencing around ISO generation, virtual media, boot, and management validation. Current app has safer readiness surfaces and media inventory. Merge into an ESXi stage workflow with preview, generated ISO evidence, virtual media validation, and management reachability verification.

### NetApp

Old app has rich NetApp product depth:
- Protocol profiles.
- Cluster/SVM/node/port defaults.
- Adaptive discovery.
- VMware plan generation.
- Bootstrap checklists.
- Upgrade activity records.
- Live ONTAP version reads.

Current app is safer because planned and current discovered state are separated and ONTAP apply is not ambient. Borrow the planning and discovery depth, not direct mutation paths.

### Cisco

Old app has a strong Cisco module:
- Console discovery.
- SSH/serial modes.
- Config rendering and diffs.
- Operator findings.
- Port maps, VLANs, bootstrap inference, and running-config backup.

Current app already has safer console-first readiness. Borrow the richer operator findings and diff model, but keep the current apply gates.

### Firmware / Upgrades

Old app's upgrade helper and activity records give useful product shape. Current app has stronger compliance, waiver, and package surfaces. Merge into a Firmware / Upgrades area with baseline, inventory, waivers, package readiness, upgrade plan, staged execution, and rollback notes.

## Reports And History

Old app report ideas:
- Latest run bundles.
- Older run bundles.
- Related reports.
- Downloadable run summaries.
- Debug bundle for latest failure.
- Report search by name/folder/type.

Current app report ideas:
- Normalized issue cards.
- Source metadata and freshness.
- Recheck commands.
- Page badges and severity classification.

Synthesis:
- Merge both.
- The final app should have issue-first Reports & Issues plus a run bundle/history archive behind it.

## Cleaner Than Current App

Old app is cleaner in these areas:
- Module capability metadata.
- Stage registry contract.
- Run Center process ceremony.
- Live job status and progress model.
- Kit-centered readiness and blocker context.
- Run bundle/history/debug bundle concept.
- Task-list navigation for setup modules.
- Device-specific detail in NetApp and Cisco modules.

## Weaker Than Current App

Old app is weaker in these areas:
- Explicit source type/freshness/current-state model.
- Stale/historical/test fixture classification.
- Provider action policy and category gates.
- Typed React frontend.
- Pydantic API contracts across the product.
- Secret-safe separation of local profile state.
- Report issue normalization.
- Testable provider adapter boundary.
- Default mock/safe behavior in the current repo's style.

## Stage 2 Conclusions

Steal:
- Module manifests.
- Stage registry.
- Preview/review/execute gates.
- Background job progress.
- WebSocket/polling live job UI.
- Run bundles, history, and debug bundles.
- Kit/profile context in the sidebar.
- Readiness meter and open issue drawer.
- NetApp and Cisco planning depth.
- Automation principles around discover/compare/correct/block/report.

Do not steal:
- Monolithic `app/main.py`.
- Direct Jinja implementation.
- Blending desired state, runtime state, and credential references in kit files.
- Any behavior that treats historical output as current state.
- Any real execution path without current app policy gates.
