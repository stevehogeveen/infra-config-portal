# Registry-Driven UI Clutter Audit

Date: 2026-06-09

## Scope

- Repository: `/home/administrator/infra-config-portal`
- Skills used: `lab-builder-skill-steward`, `lab-builder-real-runtime`, `lab-builder-ux`, `lab-builder-product-craft`, `lab-builder-hardware-run`, `lab-builder-report-remediation`, `lab-builder-toolchain`, `lab-builder-dual-app-architecture`
- No hardware workflow was run.
- Mock or test fixture state was not treated as real lab state.
- Secrets were not inspected or printed.

## Findings

### Run Center

- `RunCenter` loads `/api/v1/workflows/stages` and uses registry stage/detail panels for Cisco, iLO, RAID, ESXi, and NetApp.
- The guided view still keeps the older `RunChoice` run-builder cards, queue picker, and selected-work detail. These are now collapsed under `Guided build details`, which is acceptable as supporting workflow context but should not become the primary setup surface again.
- Provider sections for Cisco, iLO, RAID, ESXi, and NetApp no longer need separate hard-coded status cards when a registry stage is available. The remaining `RunCenterSectionFocus` summaries should stay secondary to `StageDetailPanel`.
- The NetApp provider-specific preview block remains large, but it is nested under a collapsed detail section titled `NetApp live readiness details`, so it functions as evidence rather than a main status row.
- `WorkflowStageList` is the shared stage-row component for Lab Setup and Run Center. It shows stage name, status, summary, next action, source/freshness, last checked, and issue count. It still benefits from showing the recheck command directly on the row.

### Control Center

- `ControlCenterPage` loads both the legacy control catalog and the workflow action registry.
- The default section is now the registry `Action Catalog`, and provider sections render registry `ActionCatalogTable` plus `WorkflowActionDetail` first.
- Legacy `ControlSection` blocks still exist, but current state, desired state, plan diff, report links, and diagnostics are collapsed under evidence. This keeps old provider detail available without duplicating the registry catalog as the main interaction model.
- `ActionButtonRow` still exists for legacy collapsed panels and Commander mode. It should remain hidden in collapsed evidence/advanced panels unless a registry action is missing.
- `ActionCatalogTable` exposes action, stage, provider, mode, availability, last run, source/freshness, and command/details.
- Commander mode and manual command helpers are collapsed by default.

### Lab Setup

- `/lab-setup` is a top-level sidebar route and is driven by `/api/v1/workflows/stages`.
- The active Lab Setup page uses a stage list plus selected-stage detail panel.
- Stage detail shows current state summary, desired state summary, next action, blockers, action list, selected action detail, run trace, and collapsed evidence.
- Copyable commands are present in action details and Control Center. Stage rows and action rows should expose the recheck command without requiring the operator to expand details.
- Historical artifact traces are labeled as `historical_artifact` / `historical`; the UI text tells operators to recheck before treating those artifacts as current state.

### Reports & Issues

- Report issue cards already link to `source_action_link` when the backend can resolve a registry action.
- `ReportEvidenceGroups` keeps raw report paths under a collapsed Evidence drawer, which matches the target pattern.
- `ReportActionGroups` is collapsed and groups issues by registry action/stage where possible.
- Some issue source labels still fall back to raw source/stage values when registry linkage is unavailable, but linked registry labels are preferred when present.
- Raw report artifacts are not sprayed across the main Reports page; they live under issue evidence or grouped evidence drawers.

### Repeated Source/Freshness Text

- Source/freshness handling is shared through `SourceFreshnessInline` for stage rows, action rows, action catalog rows, and run traces.
- Historical artifact traces are correctly labeled as `historical_artifact` / `historical`, but stage rows currently summarize them only as report counts.
- Recheck commands are present in registry actions as `command` or endpoint text. They should be visible directly in stage/action rows and detail panels to satisfy the operator recheck requirement.

## Cleanup Direction

- Add a top-level Lab Setup page at `/lab-setup` driven by `/api/v1/workflows/stages`.
- Use a list/detail layout: stage list on the left/main side and selected stage detail on the right.
- Make stage rows show status, summary, primary next action, last checked, issue count, source type, freshness, and recheck command.
- Keep reports, raw JSON, and artifact paths inside collapsed Evidence drawers.
- Use registry action labels and links in Reports and Control Center instead of raw artifact names whenever possible.
- Keep real-write and destructive actions visibly gated; do not add any direct hardware execution path.
