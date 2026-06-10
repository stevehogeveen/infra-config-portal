# Dual-App Capability Comparison

Date: 2026-06-09

Scope:
- Current app: `/home/administrator/infra-config-portal`.
- Legacy app: GitHub `stevehogeveen/lab-builder` at `main`, commit `c356ca430fea63f578fa8b9968784de57de64319`.
- No files were modified in `/home/administrator/lab-builder`.
- No hardware workflows were run.
- Mock/test/historical state was not treated as current real lab state.
- No secrets, tokens, passwords, or credential values were printed or copied.

Applied skills:
- `lab-builder-real-runtime`
- `lab-builder-ux`
- `lab-builder-hardware-run`
- `lab-builder-report-remediation`
- `lab-builder-toolchain`
- `lab-builder-dual-app-architecture`
- `lab-builder-product-craft`
- `lab-builder-skill-steward`

## Summary

The current app has the safer control-plane foundation. The old app has the stronger operator workflow shape. The synthesis should keep the current app's safety, runtime provenance, policy gates, typed API, React shell, and Report Center, then adopt the old app's module manifests, stage registry, Run Center process model, job progress, run bundles, and kit-centered workflow context.

## Capability Matrix

| Area | Current App | Old Lab Builder | Stronger | Synthesis Decision |
| --- | --- | --- | --- | --- |
| App shell/navigation | React sidebar with Dashboard, Run Center, Control Center, Firmware, Verification, Reports, Settings, Requests, Lab Profiles, Audit, Media. | Server-rendered sidebar with kit card, readiness meter, quick jump, open issues, compact view, setup modules, run, reports. | Mixed | Keep current React shell; adopt old kit context, readiness meter, quick jump, issue drawer, and density controls. |
| UX clarity | Strong safety wording and current/stale distinctions, but many pages overlap and `App.tsx` is too large. | Strong task-list setup flow and Run Center story, but dense and template-heavy. | Mixed | Build Lab Setup list/detail as the guided path; keep Control Center as expert surface. |
| Lab profiles | Non-secret local Lab Profiles with address planning and activation. | Kit-centered config with readiness and history grouping. | Current for safety, old for product framing | Merge: Lab Profile becomes the safe profile substrate; kit-style context drives sidebar and run history. |
| Provider mode/runtime state | Explicit provider modes, `source_type`, `freshness`, `checked_at`, `is_current`, recheck commands, historical/test downgrade. | Preview vs real execution gates, but less formal runtime provenance. | Current | Keep current model and extend it into durable hardware runs/stages. |
| Process start/stop tooling | Many explicit Make targets and report-generating scripts; Run Center is not yet a durable process engine. | Preview/review/confirm `EXECUTE`, background jobs, progress, logs, WebSocket, run bundles. | Old for process, current for safety | Adopt old process model, rewritten around current policy, database, and source metadata. |
| Report handling | Normalized issue cards, source metadata, freshness, severity/status, recheck commands, page badges. | Run bundles, history, related reports, debug bundles, searchable file archive. | Mixed | Merge: issue-first Reports & Issues plus run bundle/history archive. |
| Action/control model | Strong `ControlActionCatalog`, action policy, current/desired/diff, manual commands, direct run placeholder. | Run Center scope launch and stage execution; less catalog-oriented. | Current for policy/catalog, old for execution ceremony | Merge: one Action Catalog feeds Lab Setup, Control Center, Run Center, and Reports. |
| Device workflows | Broad safe surfaces for Cisco, iLO, RAID, ESXi, NetApp, Firmware, Build Verification. | Richer operator detail in NetApp, Cisco, staged run center, setup modules. | Mixed | Keep current safe providers; borrow old workflow depth and stage sequence. |
| Tests/lint | Broad pytest coverage across lifecycle, providers, reports, profiles, firmware, build verification, and device readiness. Frontend mostly build-level. | Pytest and health-check script; less formal API/source model coverage. | Current | Keep current backend test posture; add frontend tests and workflow-engine tests. |
| Docs/runbooks | Strong safety docs, provider modes, workflow notes, Lab Builder reference. | Strong HOWTO, automation principles, UX principles, debugging, operator flow. | Mixed | Merge docs into one operator mental model: profile -> setup -> run -> reports/issues -> recheck. |
| Skills/agent instructions | Strong project skills and AGENTS rules. | Older app has no equivalent modern skill set in this repo. | Current | Keep current skills; add candidates only after repeated implementation needs. |

## App Shell And Navigation

Current app:
- Better technical base: React routes, typed API client, responsive shell.
- Top-level navigation already matches desired product areas.
- Weakness: navigation exposes too many parallel concepts before the operator understands the lab state.

Old app:
- Better operator context: kit card, readiness meter, blocker count, quick jump, open issues, compact view.
- Setup modules are task-list oriented and status-coded.
- Weakness: implementation is template-heavy and visually dense.

Decision:
- Keep the current React shell.
- Add a persistent Lab Profile/Kit context block, readiness meter, current blocker count, quick jump, open issue drawer, and compact density toggle.
- Reframe navigation into guided and expert zones:
  - Lab Setup
  - Control Center
  - Run Center
  - Reports & Issues
  - Firmware / Upgrades
  - Settings / Lab Profile

## UX Clarity

Current app strengths:
- Safety posture is explicit.
- Mock/test/historical states are classified.
- Report issues include recheck commands and source metadata.

Current app weaknesses:
- Product concepts overlap: Verification, Reports, Run Center, Control Center, and provider pages can all answer similar questions.
- Many details appear at once.
- `App.tsx` concentration makes UI refinement expensive.

Old app strengths:
- Long setup workflows are represented as task lists.
- Run Center clearly stages preview, confirmation, live progress, and evidence.
- Sidebar keeps readiness visible.

Old app weaknesses:
- Dense pages can overwhelm.
- Some visual components are too card-heavy.

Decision:
- Use Lab Setup list/detail as the main guided workflow.
- Give every detail page one primary next action.
- Move raw JSON and old evidence into collapsed report drawers.
- Show red only for current blockers; stale/historical/test evidence must be warnings/history.

## Lab Profiles

Current app:
- Safer: local profile CRUD, activation, address planning, non-secret profile state.
- Better suited to this repo's safety rules.

Old app:
- Better product framing: everything is attached to a named kit and run history.
- Operators always know which kit they are working on.

Decision:
- Merge.
- Keep current Lab Profile storage and non-secret boundaries.
- Add kit-like context and run grouping:
  - active profile
  - readiness percentage
  - current blockers
  - recent runs
  - source freshness
  - recheck command

## Provider Mode And Runtime State

Current app:
- Strongest model: provider modes, source types, freshness, current/stale/historical/test semantics, recheck commands, and provider status visibility.
- Report Center correctly prevents stale artifacts from becoming current blockers.

Old app:
- Has preview vs real execution modes and launch blocking, but lacks a formal source provenance model.

Decision:
- Keep current runtime model.
- Extend it into:
  - `HardwareRun`
  - `HardwareStageRun`
  - `RuntimeObservation`
  - `EvidenceArtifact`
  - `Issue`
- Every run and issue should preserve source metadata.

## Process Start/Stop Tooling

Current app:
- Many explicit commands and redacted report scripts.
- Safe and inspectable.
- Not yet a cohesive process manager.

Old app:
- Clear Run Center flow.
- Background jobs.
- Progress percent, current stage, logs, trace events.
- WebSocket status and run bundles.

Decision:
- Adopt old Run Center process shape.
- Rewrite with current app primitives:
  - API-created run records.
  - Action policy check before stage start.
  - Worker/job abstraction.
  - Stage timeline.
  - Live log/status stream.
  - Cancel/stop only where safe and meaningful.
  - Redacted run bundle on completion/failure.

## Report Handling

Current app:
- Best issue semantics.
- Issue cards have source metadata, severity, status, recheck command, and evidence.

Old app:
- Best run history UX.
- Bundles group summaries, related reports, debug output, and older runs.

Decision:
- Merge:
  - Reports & Issues defaults to actionable issue cards.
  - Each issue links to run/stage/evidence.
  - Run archive shows latest and older run bundles.
  - Debug bundle is generated for failed runs.
  - Raw files are searchable but secondary.

## Action And Control Model

Current app:
- Strong `ControlActionCatalog`.
- Good current/desired/diff model.
- Manual commands and direct-run placeholder prevent unsafe surprises.

Old app:
- Strong execution ceremony for selected run scopes.

Decision:
- Make Action Catalog canonical.
- Each action should declare:
  - provider/stage
  - category
  - safety policy
  - required source freshness
  - planner
  - runner availability
  - report links
  - recheck command
- Lab Setup should show guided action subsets.
- Control Center should expose the full expert catalog.
- Run Center should execute approved stage plans through the same definitions.

## Device Workflows

Cisco:
- Current: safer console-first readiness and bootstrap gates.
- Old: richer config diff, port map, operator findings, running-config backup.
- Merge: console discovery -> prompt readiness -> access check -> bootstrap preview -> gated apply -> SSH/SCP validation -> save/reload decision -> report.

iLO / HPE:
- Current: stronger redaction, source metadata, setup intent/compare/apply plan.
- Old: better stage integration.
- Merge: make iLO a first-class hardware stage with discover/plan/apply/verify/report.

RAID:
- Current: strong HPE RAID endpoints and destructive policy gates.
- Old: better automation principle language and run progression.
- Merge: identity-based discover/compare/remap/block/report stage with reboot/pending timeline.

ESXi:
- Current: safe readiness/media checks.
- Old: richer install sequence and live job state.
- Merge: ISO/kickstart generation -> serve media -> virtual media insert -> one-time boot -> power action -> management validation -> report.

NetApp:
- Current: safer planned/current separation and preview-only posture.
- Old: richer ONTAP planning, protocol profiles, adaptive discovery, upgrade activity.
- Merge: adopt planning depth and profile defaults while preserving no-apply-by-default.

Firmware:
- Current: stronger compliance, waiver, package, upgrade planning surfaces.
- Old: useful upgrade helper and activity framing.
- Merge: baseline -> inventory -> compliance -> waiver -> package readiness -> upgrade plan -> guarded execution -> verification.

Build Verification:
- Current app clearly leads.
- Keep it as readiness summary and certification report.

## Tests And Lint

Current app:
- Broad backend pytest coverage.
- Clear root commands.
- Needs frontend unit/E2E coverage for the future Lab Setup and Run Center refactor.

Old app:
- Has pytest and a practical `scripts/health-check`.
- Less coverage for source/freshness semantics.

Decision:
- Keep current test framework.
- Add tests for:
  - workflow engine state transitions
  - action policy decisions
  - stale/historical issue classification
  - run bundle redaction
  - stage registry manifests
  - frontend Lab Setup/Run Center states

## Docs And Runbooks

Current app:
- Strong safety and command docs.

Old app:
- Strong operator HOWTO and automation principles.

Decision:
- Merge into a concise operator runbook:
  1. Select Lab Profile.
  2. Recheck live state.
  3. Resolve Lab Setup blockers.
  4. Build a run plan.
  5. Review and confirm.
  6. Monitor run.
  7. Review Reports & Issues.
  8. Recheck or fix.

## Skills And Agent Instructions

Current app:
- Strong skill set and AGENTS rules.

Old app:
- Provides useful product principles but no modern project skill framework.

Decision:
- Keep existing skills.
- Do not create new skills in this run.
- Track candidate skills and create only after repeated implementation runs reveal specific recurring mistakes.

## Capability Conclusion

Current app should remain the base. Old Lab Builder should be treated as a product and workflow reference, not an implementation source to copy wholesale. The highest-value merge is:
- Current app safety and data contracts.
- Old app workflow ceremony and run history.
- Current app reports/issues.
- Old app module/stage metadata.
- Current app React shell.
- Old app operator sidebar/context patterns.
