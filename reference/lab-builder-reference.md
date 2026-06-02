# Lab Builder Reference

Last inspected: 2026-06-02

Source path inspected: `/home/administrator/lab-builder`

Note: the source repository had uncommitted changes at inspection time. Treat
this as a product and workflow reference, not as a frozen API contract.

## Why This Matters

`lab-builder` is the closest existing example of what `infra-config-portal`
should become. Future work in this repository should use it as a reference for
workflow shape, operator UX, execution safety, artifact handling, and module
boundaries while still keeping this project mock-first by default.

Do not copy real credentials, real hostnames, real IPs, customer data, local
media, generated artifacts, or live provider configuration from `lab-builder`.

## What Lab Builder Does

Lab Builder is a FastAPI and Jinja operator console for controlled lab
provisioning. It helps an operator define a kit, complete setup sections, run
discovery and validation, preview intended changes, launch guarded execution,
monitor background jobs, and review artifacts after the run.

The app is aimed at lab and datacenter build workflows across:

- HPE iLO / Redfish
- storage and RAID planning
- ESXi install and post-config
- Windows / vSphere / WinRM setup
- NetApp ONTAP
- Cisco switch setup
- QNAP setup
- OVF / OVA template registration
- firmware and upgrade helper flows

The user model is operator-focused: a person works through setup pages, checks
readiness, previews actions, explicitly confirms real execution, and follows
job logs and reports.

## Core Workflow Model

The important product pattern is staged, guarded automation:

1. Create or load a kit.
2. Save global site, subnet, included systems, and credential references.
3. Complete setup sections for iLO, Storage, ESXi, Windows, and optional
   modules.
4. Run discovery against live devices where available.
5. Build previews, validation results, and command/action plans.
6. Use Run Center to preview selected stages.
7. Require a confirmation checkbox and exact `EXECUTE` phrase before real
   execution.
8. Run selected stages in a background job.
9. Track current stage, stage statuses, progress percentage, trace events, and
   logs.
10. Write reports, history entries, debug bundles, exports, generated files,
    and other artifacts.

For this repo, mirror the same lifecycle concepts but keep provider calls
mocked unless a future human-approved task explicitly adds a real adapter behind
strict configuration and safety gates.

## Safety And Execution Principles

Lab Builder's stated automation rule is:

> Never blindly execute. Never blindly fail. Always discover, compare, correct
> if safe, explain if not safe.

Key behaviors to preserve in this project:

- Treat desired intent as durable state; treat live provider paths as
  discoverable options.
- Run fresh discovery before risky apply steps.
- Compare approved intent to live state before execution.
- Auto-remediate only when the app can prove the same target and outcome are
  still selected.
- Block when continuing could modify the wrong hardware, destroy stale data, or
  hide a platform limitation.
- Explain blocked runs with intended action, discovered state, available
  options, why no option was safe, and what the operator should do next.
- Emit structured technician logs with tags such as `[DISCOVER]`, `[COMPARE]`,
  `[REMAP]`, `[DECISION]`, and `[BLOCKED]`.
- Generate debug bundles that redact passwords, tokens, authorization headers,
  cookies, session IDs, and raw secrets.

## Architecture Shape

Lab Builder is currently a large FastAPI app with a central `app/main.py`, but
newer code is split around modules, services, stages, and shared core helpers.

Important reference patterns:

- App entrypoint: `app/main.py`
- Module discovery: `app/core/registry.py`
- Module manifests: `app/modules/<name>/manifest.yml`
- Module routes: `app/modules/<name>/routes.py`
- Module service/domain logic: `app/modules/<name>/service.py`
- Stage execution framework: `app/core/stage_registry.py` and `app/stages/*`
- Background job progress: `app/core/jobs.py`
- Shared readiness, execution review, history, activity, storage planning, and
  HTTP response helpers under `app/core/`
- Templates: `templates/partials/pages/`
- Static app shell: `static/css/lab-builder.css`, `static/js/app-shell.js`

The module service contract is shaped around:

- `discover`
- `plan`
- `validate`
- `preview`
- `apply`
- `status`
- `repair`

For `infra-config-portal`, the analogous direction should be:

- API routes stay thin.
- Workflow lifecycle logic stays in services.
- Provider calls are behind adapter contracts.
- Stage-like execution should be explicit and auditable.
- Frontend pages should show readiness, blockers, plan detail, and job history.

## Major Sections And Capabilities

Lab Builder exposes pages and modules for:

- Dashboard: mission-control readiness and workflow status.
- Configuration / Global settings: kit creation, loading, import/export, subnet
  and site configuration.
- iLO Setup: users, SNMP, time, IPv6, virtual media, power actions, firmware
  upgrade support.
- Storage setup: target selection, discovery, RAID planning, approval, apply,
  reboot handling, artifacts.
- ESXi Setup / Config: ISO customization, virtual media boot, management
  network, hostname, DNS, password policy, post-config actions.
- Windows Setup: image/OVF registration, vSphere/WinRM probes, safe staged
  install planning.
- OVF Templates: local OVF/OVA directory registration for future VM deployment.
- NetApp Setup: ONTAP discovery, console/bootstrap helpers, IP setup,
  validation, plan/export/apply, upgrade activity, offline API compatibility
  catalog.
- Cisco Setup: console/SSH discovery, bootstrap, port discovery, plan,
  approval, apply, backup, reset, upgrade.
- QNAP Setup: setup and validation workflow placeholder/extension.
- Run Center: preview, execution review, confirmation, selected-stage launch,
  live job tracking.
- Reports / History: saved run summaries, exports, debug bundles, history and
  status display.
- Suggestion Center: operator feedback capture and triage.
- Upgrade Helper: media discovery, version/policy planning, firmware uploads.

## UX Patterns To Reuse

Lab Builder's UI is dense and operator-oriented. The useful patterns for this
project are:

- Make current kit state, blockers, and next action visible on every page.
- Treat setup navigation as a task list with status.
- Give feedback in the same area where the operator took action.
- Make empty states tell the operator what will appear and what to do next.
- Support expert speed through command palette or fast navigation without
  hiding visible controls.
- Keep accessibility, focus, status text, and non-color-only cues as
  operational reliability features.
- Keep Run Center central: preview, review, confirm, execute, monitor, report.

## Persistence And Artifacts

Lab Builder keeps local operator state out of the release package:

- `config/`: kit configuration and operator settings.
- `artifacts/`: generated outputs, job state, history, debug bundles, SQLite
  runtime data, reports, exports.
- `media/`: local ISO, firmware, OVF/OVA, VMDK, and related media.

For this project, keep the same distinction:

- Application source and docs are versioned.
- Local runtime data, generated outputs, and media should stay local.
- Secrets should never be committed.
- Artifacts should be easy to inspect and export.

## Implications For Infra Config Portal

Future tasks should gradually move this project from a single VM request MVP
toward a Lab Builder-like control plane:

- Start with request lifecycle correctness and audit events.
- Add plan/review surfaces before adding real execution.
- Add module/provider adapter contracts before adding provider implementations.
- Add readiness and blocker reporting before broadening workflows.
- Add job progress, logs, reports, and artifact handling as first-class product
  concepts.
- Keep provider adapters mocked by default.
- Preserve explicit approval gates for risky actions.

Do not try to port Lab Builder wholesale. Use it as the reference for desired
operator workflows, safety posture, and module architecture.
