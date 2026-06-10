# Lab Builder Product Architecture Proposal

Date: 2026-06-09

Scope:
- Target repo: `/home/administrator/infra-config-portal`.
- Legacy reference: GitHub `stevehogeveen/lab-builder` at `main`.
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

## Product North Star

The app should feel like a real lab control plane:
- Select the active lab profile.
- See current readiness and blockers.
- Work through Lab Setup by device and stage.
- Build a run plan.
- Review exactly what will happen.
- Execute only through explicit gates.
- Monitor progress.
- Resolve issues from reports with evidence and recheck commands.

Mock, test, and historical output must never look like current real lab state. Real state must declare source, freshness, checked time, and recheck path.

## Proposed Sidebar Navigation

Primary:
- Dashboard
- Lab Setup
- Control Center
- Run Center
- Reports & Issues
- Firmware / Upgrades
- Build Verification
- Settings / Lab Profile

Secondary:
- Requests
- Audit Events
- Media
- Developer / Diagnostics

Sidebar context block:
- Active Lab Profile name.
- Provider mode.
- Readiness percentage.
- Current blocker count.
- Last live check time.
- Freshness status.
- Primary recheck command.

Sidebar utilities:
- Quick jump.
- Open issues.
- Compact view.
- Current run indicator when a run is active.

Navigation rules:
- Lab Setup is the guided path.
- Control Center is the expert action catalog.
- Run Center is for plan/review/execute/monitor/history.
- Reports & Issues is for actionable issues and evidence.
- Settings / Lab Profile owns local non-secret configuration and mode visibility.

## Dashboard

Purpose:
- Give a one-screen answer to "Can I run this lab workflow now?"

Content:
- Active profile summary.
- Current readiness score.
- Current blockers.
- Stale checks.
- Running or latest run.
- Top next action.
- Provider/toolchain health.
- Firmware baseline status.
- Build Verification summary.

Rules:
- No raw JSON.
- No historical artifact shown as current state.
- One primary next action.

## Lab Setup List / Detail Workflow

Lab Setup list rows:
- Cisco
- iLO / HPE Management
- HPE RAID
- ESXi Install
- NetApp
- Firmware / Baseline
- Build Verification
- Toolchain

Each row shows:
- Status: ready, needs attention, stale, not checked, blocked, unavailable.
- Source type.
- Last checked.
- Current blocker count.
- Next action.
- Primary recheck command.

Detail page sections:
- Current state.
- Desired/profile state.
- Diff.
- Blockers and warnings.
- Action plan.
- Evidence links.
- Recheck command.
- Raw evidence collapsed.

Detail page action model:
- Exactly one primary next action.
- Secondary actions grouped under "More actions".
- Write-like actions show policy gate and required acknowledgements.
- Disabled actions explain the missing condition.

Device detail examples:
- Cisco: discover console -> prompt readiness -> privilege -> bootstrap preview -> gated apply -> validate SSH/SCP -> save/reload decision.
- iLO: reachability -> auth -> inventory -> setup compare -> apply plan -> gated apply -> verify.
- RAID: discovery -> intent compare -> plan -> destructive gate -> apply -> pending/reboot -> validate.
- ESXi: media readiness -> kickstart/ISO -> virtual media -> boot override -> power action -> management validation.
- NetApp: console readiness -> current state -> planned/current compare -> setup validation -> NFS/vCenter readiness -> upgrade readiness.
- Firmware: inventory -> compliance -> waivers -> package readiness -> upgrade plan -> guarded upgrade.

## Control Center

Purpose:
- Expert command catalog and operator control surface.

Content:
- Action catalog grouped by Lab Profile, Cisco, iLO, RAID, ESXi, NetApp, Firmware, Verification, Reports.
- Each action has current/desired/diff, policy state, source freshness, manual command, report link, and last result.
- Direct execution remains disabled unless a future implementation routes through the workflow engine and policy gate.

Backend contract:
- `ActionDefinition`
- `ActionPlan`
- `ActionPolicyDecision`
- `ActionEvidence`
- `ActionRunRequest`
- `ActionRunResult`

Rules:
- Control Center must not become a second workflow engine.
- Actions feed the shared Run Center planner.
- Manual commands are still useful and should be copyable.

## Run Center

Purpose:
- Build, review, execute, monitor, and archive hardware workflows.

Main states:
- Choose run.
- Preview plan.
- Resolve blockers.
- Confirm.
- Running.
- Completed.
- Failed.
- Cancelled where safe.

Run Center flow:
1. Choose workflow scope: full lab, provider, or selected stages.
2. Build plan using stage registry and action catalog.
3. Show stage list, expected writes, read-only probes, evidence outputs, and blockers.
4. Require current source freshness where needed.
5. Require explicit confirmation for real write lanes.
6. Run through `HardwareRunService`.
7. Stream or poll stage progress.
8. Generate redacted run bundle and issue records.

Confirmation model:
- Preview and read-only runs do not require dangerous confirmations.
- Real write lanes require provider mode, action policy, acknowledgements, and exact phrase.
- Firmware, power, factory reset, OS install, and destructive storage categories require stronger gates.

Run monitor:
- Current stage.
- Progress percentage.
- Stage timeline.
- Recent log lines.
- Current blocker if failed.
- Evidence links as they appear.
- Stop/cancel only when meaningful and safe.

Run archive:
- Latest run.
- Recent runs by profile.
- Failed run debug bundle.
- Related reports.
- Recheck commands.

## Reports & Issues

Purpose:
- Turn evidence into action.

Default view:
- Current blockers.
- Warnings.
- Stale checks.
- Not checked.
- Historical archive.

Issue card contract:
- Problem.
- Source.
- Current value.
- Expected value.
- Where to fix.
- Recommended action.
- Copyable command.
- Recheck command.
- Evidence links.
- Source type.
- Freshness.
- Checked time.

Evidence hierarchy:
1. Current issues.
2. Recheck commands.
3. Run/stage evidence.
4. Redacted report files.
5. Raw JSON collapsed.

Rules:
- Historical artifacts cannot be red current blockers.
- Test fixtures are not operator-visible current state.
- Stale live-cached data is warning/history, not a fresh block.

## Firmware / Upgrades

Purpose:
- Manage firmware baselines, inventory, waivers, packages, and upgrade plans.

Sections:
- Baseline manifest.
- Device inventory.
- Compliance results.
- Waivers.
- Package readiness.
- Upgrade plan.
- Rollback notes.
- Upgrade history.

Run model:
- Inventory is read-only.
- Compliance is read-only/report.
- Waiver creation is app-state write only.
- Package checks are local filesystem/toolchain checks.
- Upgrade execution requires explicit real write lane and firmware gate.

Toolchain:
- Vendor tools and API clients must be detected before plan.
- Upgrade packages must be hashable and traceable.
- Reports must include redacted package and device identifiers, not secrets.

## Settings / Lab Profile

Purpose:
- Own non-secret local configuration and explain the current operating mode.

Sections:
- Active Lab Profile.
- Address plan.
- Provider targets configured/missing status only.
- Provider mode.
- Credential configuration status only.
- Tool paths.
- Media paths.
- Report/artifact locations.
- Runtime warning banner if checks are stale or not run.

Rules:
- Do not display secrets.
- Do not store raw secrets in profile records.
- Use configured/missing/redacted status.
- Provide recheck commands.

## Action Catalog

Purpose:
- Single source of action and stage metadata.

Action definition fields:
- `id`
- `label`
- `description`
- `provider`
- `stage`
- `category`
- `mode_requirements`
- `source_requirements`
- `toolchain_requirements`
- `inputs`
- `planner`
- `runner`
- `report`
- `manual_command`
- `recheck_command`
- `evidence_artifacts`
- `danger_level`
- `disabled_reason`

Consumers:
- Lab Setup detail pages.
- Control Center.
- Run Center planner.
- Reports & Issues.
- Build Verification.
- Docs/runbook generation.

## Real-Only Runtime State Model

Source types:
- `live_probe`
- `live_cached`
- `historical_artifact`
- `test_fixture`
- `not_checked`

Freshness:
- `current`
- `stale`
- `unknown`

Runtime records:
- `RuntimeObservation`: one observed fact set from a source.
- `ProviderRuntimeState`: latest provider-level summary.
- `HardwareRun`: operator-triggered run.
- `HardwareStageRun`: stage-level plan/progress/result.
- `EvidenceArtifact`: redacted file or structured output linked to run/stage/issue.
- `Issue`: normalized blocker/warning/stale/not-checked state.

Current-state rule:
- Only `live_probe`, or fresh `live_cached`, may represent current real lab state.
- `historical_artifact` and `test_fixture` can inform history and tests but must not block as current real lab state.
- `not_checked` must show a recheck command.

## Hardware Workflow Engine

Stage contract:
- `discover(context) -> observation`
- `plan(context, observation) -> plan`
- `apply(context, plan, policy_decision) -> result`
- `verify(context, result) -> observation`
- `report(context, run, stage) -> evidence`

Engine responsibilities:
- Resolve active profile.
- Check provider mode.
- Check action policy.
- Check source freshness.
- Check toolchain readiness.
- Execute stages in order.
- Record progress.
- Redact logs and evidence.
- Emit issues.
- Generate run bundle.
- Write audit events.

Initial stage set:
- Cisco console discovery.
- Cisco prompt/readiness.
- Cisco bootstrap preview/apply.
- iLO reachability/auth/inventory.
- iLO setup compare/apply/verify.
- HPE RAID discovery/plan/apply/pending/reset/validate.
- ESXi media/kickstart/virtual-media/boot/management validation.
- NetApp console/current/live/readiness/upgrade preview.
- Firmware inventory/compliance/waiver/package/upgrade plan.
- Build Verification.

Execution model:
- Start with preview/read-only stages.
- Enable write-like stages only through explicit provider mode and policy gate.
- Keep scripts as implementation details behind stage runners.

## Toolchain Layer

Purpose:
- Declare, detect, and report external tool readiness before workflow stages need them.

Toolchain requirement fields:
- Tool name.
- Provider.
- Purpose.
- Detection command.
- Minimum version when relevant.
- Install hint.
- Required for stages.
- Current status.
- Last checked.
- Evidence.

Provider guidance:
- Cisco: serial tools, terminal server/ser2net, SSH tooling, Netmiko/Ansible/pyATS as appropriate.
- iLO/HPE: Redfish client support, optional iLOrest, local TLS handling, firmware package tools.
- ESXi: ISO tooling, HTTP serving, virtual media via iLO, optional govc/vSphere tooling.
- NetApp: `netapp-ontap` client or REST tooling, console tooling, NFS/vCenter validation tools.
- Firmware: package inventory, hash verification, vendor tooling, baseline manifests.

UI placement:
- Toolchain summary on Dashboard.
- Detailed toolchain page under Settings or Lab Setup.
- Toolchain blockers in Reports & Issues.
- Tool requirements on Action Catalog entries.

## Backend Module Layout

Proposed backend packages:
- `app/backend/app/runtime/`
- `app/backend/app/actions/`
- `app/backend/app/workflows/`
- `app/backend/app/evidence/`
- `app/backend/app/issues/`
- `app/backend/app/toolchain/`
- `app/backend/app/lab_profiles/`
- `app/backend/app/providers/<provider>/`

Rules:
- API routes stay thin.
- Services own orchestration.
- Providers own external protocol details.
- Runtime/evidence/issues are shared infrastructure.

## Frontend Module Layout

Proposed frontend packages:
- `src/app/`: shell, routing, layout.
- `src/api/`: generated or organized clients.
- `src/components/status/`
- `src/components/issues/`
- `src/components/evidence/`
- `src/components/actions/`
- `src/components/runs/`
- `src/features/dashboard/`
- `src/features/lab-setup/`
- `src/features/control-center/`
- `src/features/run-center/`
- `src/features/reports/`
- `src/features/firmware/`
- `src/features/settings/`
- `src/features/requests/`

Migration principle:
- Split `App.tsx` by extracting components first.
- Avoid behavior changes during the first split.
- Add screenshot checks for changed visible surfaces.

## Architecture Conclusion

The final product should be a profile-aware, issue-driven hardware workflow control plane:
- The current app supplies safety and typed service boundaries.
- The old app supplies the operator workflow shape.
- The new shared layers turn device-specific scripts into coherent runs with current-state semantics, evidence, and remediation.
